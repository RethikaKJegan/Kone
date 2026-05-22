from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .utils import load_image_rgba, load_image_rgb, save_rgb, select_detection, select_middle_floor_indicator_display


def insert_mod_panel(background_path: str | Path, mod_path: str | Path, detections: dict[str, Any], geometry: dict[str, Any], cfg: dict[str, Any], out_path: str | Path, mask_out: str | Path, removal_mask: np.ndarray | None = None) -> np.ndarray:
    bg = load_image_rgb(background_path)
    mod = close_internal_alpha_holes(load_image_rgba(mod_path))
    height, width = bg.shape[:2]
    target_box = _target_box(width, height, detections, cfg, mod.shape[:2], removal_mask)
    warped = _warp_long_panel_to_exact_box(mod, target_box, bg.shape[:2]) if _is_long_panel_track_case(cfg, mod.shape[:2]) else _warp_mod_to_scene(mod, target_box, geometry, bg.shape[:2], cfg)

    fg = warped[:, :, :3]
    alpha = refine_alpha(warped[:, :, 3].astype(np.float32) / 255.0)
    fg = harmonize_foreground(fg, bg, alpha)
    fg = match_scene_white_balance(fg)
    fg = add_wall_bounce_light(fg, alpha)
    fg = perceptual_compress(fg)
    fg = edge_integration(fg, alpha)
    fg = transfer_wall_texture(bg, fg, alpha, float(cfg["insertion"]["texture_strength"]))

    bg_shadowed = apply_realistic_shadow(bg, alpha, float(cfg["insertion"]["shadow_strength"]))
    bg_shadowed = add_contact_shadow(bg_shadowed, alpha, float(cfg["insertion"]["shadow_strength"]))
    bg_shadowed = add_wall_grounding(bg_shadowed, alpha)
    final = alpha_composite(bg_shadowed, fg, alpha)
    final = add_camera_finish(final)
    final = recover_detail(final)

    save_rgb(out_path, final)
    cv2.imwrite(str(mask_out), (alpha > 0.03).astype(np.uint8) * 255)
    return final


def _target_box(width: int, height: int, detections: dict[str, Any], cfg: dict[str, Any], mod_hw: tuple[int, int] | None = None, removal_mask: np.ndarray | None = None) -> list[int]:
    ins = cfg["insertion"]
    if ins.get("manual_box_xyxy"):
        return [int(v) for v in ins["manual_box_xyxy"]]
    if ins["placement"] == "detection":
        det = select_valid_component_detection(detections["detections"], ins["target_keywords"], height, width, mod_hw)
        if det:
            detection_box = [int(round(v)) for v in det["box_xyxy"]]
            erased_box = _select_erased_long_panel_box(removal_mask, detection_box, cfg, mod_hw)
            return erased_box or detection_box
    rx1, ry1, rx2, ry2 = ins["fallback_box_ratio_xyxy"]
    return [int(width * rx1), int(height * ry1), int(width * rx2), int(height * ry2)]


def select_valid_component_detection(
    detections: list[dict[str, Any]],
    keywords: list[str],
    height: int,
    width: int,
    mod_hw: tuple[int, int] | None,
) -> dict[str, Any] | None:
    ordered = [
        _select_long_panel_detection(detections, keywords, mod_hw),
        select_middle_floor_indicator_display(detections, keywords, height),
        select_detection(detections, keywords),
    ]
    candidates = [det for det in ordered if det is not None]
    if not candidates:
        return None
    valid = [det for det in candidates if _valid_component_detection(det, keywords, width, height)]
    return max(valid or candidates, key=lambda det: float(det.get("score", 0.0)))


def _valid_component_detection(det: dict[str, Any], keywords: list[str], width: int, height: int) -> bool:
    phrase = str(det.get("phrase", "")).lower()
    x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
    bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
    area_ratio = (bw * bh) / max(width * height, 1)
    cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    target_text = " ".join(k.lower() for k in keywords)

    if "floor indicator" in target_text or "display" in target_text:
        return cy < height * 0.42 and area_ratio < 0.08 and bw > 6 and bh > 4
    if "button panel" in target_text or "elevator panel" in target_text or "call button" in target_text:
        if "mod panel" in phrase or "panel" == phrase:
            return False
        aspect = bh / bw
        near_side_wall = cx < width * 0.42 or cx > width * 0.58
        return 0.00004 <= area_ratio <= 0.16 and 0.45 <= aspect <= 8.5 and near_side_wall
    if "emergency" in target_text:
        return area_ratio <= 0.18 and bh / bw <= 5.5
    return area_ratio <= 0.25


def _select_long_panel_detection(detections: list[dict[str, Any]], keywords: list[str], mod_hw: tuple[int, int] | None) -> dict[str, Any] | None:
    if not mod_hw:
        return None
    mh, mw = mod_hw
    if mh / max(mw, 1) < 4:
        return None
    if not any(k.lower() in {"door track", "threshold plate"} for k in keywords):
        return None

    candidates: list[dict[str, Any]] = []
    for det in detections:
        phrase = det.get("phrase", "").lower()
        if phrase not in {"door track", "threshold plate", "elevator button panel"}:
            continue
        x1, y1, x2, y2 = [float(v) for v in det["box_xyxy"]]
        box_w, box_h = max(1.0, x2 - x1), max(1.0, y2 - y1)
        if box_h / box_w >= 3:
            candidates.append(det)
    if not candidates:
        return None
    return max(candidates, key=lambda d: float(d.get("score", 0)))

def _is_long_panel_track_case(cfg: dict[str, Any], mod_hw: tuple[int, int]) -> bool:
    mh, mw = mod_hw
    keywords = [k.lower() for k in cfg["insertion"].get("target_keywords", [])]
    return mh / max(mw, 1) >= 4 and any(k in {"door track", "threshold plate"} for k in keywords)


def _select_erased_long_panel_box(removal_mask: np.ndarray | None, detection_box: list[int], cfg: dict[str, Any], mod_hw: tuple[int, int] | None) -> list[int] | None:
    if removal_mask is None or mod_hw is None or not _is_long_panel_track_case(cfg, mod_hw):
        return None
    binary = (removal_mask > 127).astype(np.uint8)
    components, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if components <= 1:
        return None

    dx1, dy1, dx2, dy2 = detection_box
    dcx = (dx1 + dx2) * 0.5
    best: tuple[float, list[int]] | None = None
    image_area = removal_mask.shape[0] * removal_mask.shape[1]
    for label in range(1, components):
        x, y, w, h, area = [int(v) for v in stats[label]]
        if area < 50 or area / max(image_area, 1) > 0.08:
            continue
        if h / max(w, 1) < 3.0:
            continue
        if h < max(80, int((dy2 - dy1) * 0.8)):
            continue
        cx = x + w * 0.5
        overlap_y = max(0, min(y + h, dy2) - max(y, dy1))
        score = overlap_y - abs(cx - dcx) * 0.25 + h * 0.05
        box = [x, y, x + w, y + h]
        if best is None or score > best[0]:
            best = (score, box)
    return best[1] if best else None


def _warp_long_panel_to_exact_box(mod: np.ndarray, box: list[int], out_hw: tuple[int, int]) -> np.ndarray:
    x1, y1, x2, y2 = box
    box_w, box_h = max(1, x2 - x1), max(1, y2 - y1)
    mh, mw = mod.shape[:2]
    scale = box_h / max(mh, 1)
    new_w, new_h = max(1, int(mw * scale)), box_h
    mod = cv2.resize(mod, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    px = x1 + (box_w - new_w) // 2
    quad = np.array([[px, y1], [px + new_w, y1], [px + new_w, y2], [px, y2]], dtype=np.float32)
    return warp_rgba_to_quad(mod, quad, out_hw)


def _warp_mod_to_scene(mod: np.ndarray, box: list[int], geometry: dict[str, Any], out_hw: tuple[int, int], cfg: dict[str, Any]) -> np.ndarray:
    x1, y1, x2, y2 = box
    box_w, box_h = max(1, x2 - x1), max(1, y2 - y1)
    mh, mw = mod.shape[:2]
    mode = cfg["insertion"].get("size_mode", "fit_box")
    if mode == "preserve_asset":
        scale = 1.0
    elif mode == "fixed_height":
        scale = float(cfg["insertion"]["fixed_height_px"]) / mh
    else:
        desired_h = box_h * float(cfg["insertion"].get("target_height_multiplier", 1.0))
        scale = desired_h / mh
    scale *= float(cfg["insertion"]["scale_multiplier"])
    native_scene_scale = min(
        out_hw[1] / float(cfg["insertion"].get("native_reference_width_px", 600)),
        out_hw[0] / float(cfg["insertion"].get("native_reference_height_px", 800)),
    )
    native_scene_scale = max(1.0, native_scene_scale)
    if not cfg["insertion"].get("allow_upscale", False):
        scale = min(scale, native_scene_scale)
    new_w, new_h = max(1, int(mw * scale)), max(1, int(mh * scale))
    mod = cv2.resize(mod, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    normal = geometry.get("wall_plane", {}).get("normal") or [0, 0, 1]
    side_skew = float(cfg["insertion"]["side_skew"]) + abs(float(normal[0])) * 0.005
    top_shrink = float(cfg["insertion"]["top_shrink"]) + abs(float(normal[1])) * 0.003
    px = x1 + (box_w - new_w) // 2
    py = y1 + (box_h - new_h) // 2
    quad = np.array(
        [
            [px + int(new_w * side_skew), py],
            [px + new_w - int(new_w * side_skew), py - int(new_h * top_shrink)],
            [px + new_w, py + new_h],
            [px, py + new_h],
        ],
        dtype=np.float32,
    )
    return warp_rgba_to_quad(mod, quad, out_hw)


def close_internal_alpha_holes(rgba: np.ndarray) -> np.ndarray:
    out = rgba.copy()
    alpha = out[:, :, 3]
    transparent = alpha < 8
    _, labels = cv2.connectedComponents(transparent.astype(np.uint8))
    border_labels = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    internal = transparent & ~np.isin(labels, border_labels)
    out[:, :, :3][internal] = [10, 10, 10]
    out[:, :, 3][internal] = 255
    return out


def warp_rgba_to_quad(rgba: np.ndarray, quad: np.ndarray, out_hw: tuple[int, int]) -> np.ndarray:
    out_h, out_w = out_hw
    h, w = rgba.shape[:2]
    src = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, quad)
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    premul = rgb * alpha[:, :, None]
    warped_premul = cv2.warpPerspective(premul, matrix, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    warped_alpha = cv2.warpPerspective(alpha, matrix, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    warped_rgb = warped_premul / np.maximum(warped_alpha[:, :, None], 1e-6)
    return np.dstack([np.clip(warped_rgb, 0, 255), warped_alpha * 255]).astype(np.uint8)


def refine_alpha(alpha: np.ndarray) -> np.ndarray:
    return np.clip(cv2.GaussianBlur(alpha, (3, 3), 0.12), 0, 1)


def harmonize_foreground(fg: np.ndarray, bg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    mask = alpha > 0.05
    if mask.sum() < 50:
        return fg
    fg_lab = cv2.cvtColor(fg, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(bg, cv2.COLOR_RGB2LAB).astype(np.float32)
    delta = (bg_lab[:, :, 0][mask].mean() - fg_lab[:, :, 0][mask].mean()) * 0.10
    fg_lab[:, :, 0] += delta
    fg_lab[:, :, 1] *= 0.985
    fg_lab[:, :, 2] *= 0.985
    return cv2.cvtColor(np.clip(fg_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


def match_scene_white_balance(fg: np.ndarray) -> np.ndarray:
    out = fg.astype(np.float32)
    out[:, :, 0] *= 1.03
    out[:, :, 1] *= 1.01
    out[:, :, 2] *= 0.97
    return np.clip(out, 0, 255).astype(np.uint8)


def add_wall_bounce_light(fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    glow = cv2.GaussianBlur(solid, (31, 31), 10)
    glow = np.clip(glow - solid, 0, 1)
    out = fg.astype(np.float32)
    out += glow[:, :, None] * 3.0
    return np.clip(out, 0, 255).astype(np.uint8)


def perceptual_compress(fg: np.ndarray) -> np.ndarray:
    return cv2.convertScaleAbs(fg, alpha=0.975, beta=3)


def edge_integration(fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    edge = cv2.Canny((alpha * 255).astype(np.uint8), 30, 90)
    edge = cv2.GaussianBlur(edge.astype(np.float32), (5, 5), 1.2) / 255.0
    soft = cv2.GaussianBlur(fg, (3, 3), 0.7)
    edge_mask = np.clip(edge * 2.2, 0, 1)
    return np.clip(fg.astype(np.float32) * (1 - edge_mask[:, :, None]) + soft.astype(np.float32) * edge_mask[:, :, None], 0, 255).astype(np.uint8)


def transfer_wall_texture(bg: np.ndarray, fg: np.ndarray, alpha: np.ndarray, strength: float) -> np.ndarray:
    mask = alpha > 0.03
    wall_detail = bg.astype(np.float32) - cv2.GaussianBlur(bg, (0, 0), 2.0).astype(np.float32)
    out = fg.astype(np.float32)
    out[mask] += wall_detail[mask] * max(strength, 0.10)
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_realistic_shadow(bg: np.ndarray, alpha: np.ndarray, strength: float) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    shadow = cv2.GaussianBlur(solid, (31, 31), 10)
    shadow = np.roll(np.roll(shadow, 10, axis=0), -7, axis=1)
    shadow = np.clip(shadow - solid, 0, 1)
    contact = cv2.GaussianBlur(solid, (11, 11), 3)
    contact = np.roll(np.roll(contact, 3, axis=0), -2, axis=1)
    shadow_mask = np.clip((shadow * 0.11 + contact * 0.30) * max(0.55, strength / 0.12), 0, 0.42)
    return np.clip(bg.astype(np.float32) * (1 - shadow_mask[:, :, None]), 0, 255).astype(np.uint8)


def add_contact_shadow(bg: np.ndarray, alpha: np.ndarray, strength: float) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    contact = cv2.GaussianBlur(solid, (7, 7), 1.6)
    contact = np.roll(np.roll(contact, 3, axis=0), -3, axis=1)
    edge = cv2.Canny((solid * 255).astype(np.uint8), 20, 80)
    edge = cv2.GaussianBlur(edge.astype(np.float32) / 255.0, (5, 5), 1.5)
    contact = np.clip(contact + edge * 0.8, 0, 1)
    amount = 0.28 * max(0.55, strength / 0.12)
    return np.clip(bg.astype(np.float32) * (1 - contact[:, :, None] * amount), 0, 255).astype(np.uint8)


def add_wall_grounding(bg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    halo = cv2.GaussianBlur(solid, (51, 51), 18)
    halo = np.clip(halo - solid, 0, 1)
    return np.clip(bg.astype(np.float32) * (1 - halo[:, :, None] * 0.035), 0, 255).astype(np.uint8)


def alpha_composite(bg: np.ndarray, fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    return np.clip(fg.astype(np.float32) * alpha[:, :, None] + bg.astype(np.float32) * (1 - alpha[:, :, None]), 0, 255).astype(np.uint8)


def add_camera_finish(img: np.ndarray) -> np.ndarray:
    out = img.astype(np.float32) + np.random.default_rng(42).normal(0, 0.22, img.shape)
    blur = cv2.GaussianBlur(np.clip(out, 0, 255), (0, 0), 1.4)
    out = cv2.addWeighted(np.clip(out, 0, 255), 1.12, blur, -0.12, 0)
    haze = cv2.GaussianBlur(out, (0, 0), 12)
    return np.clip(cv2.addWeighted(out, 0.985, haze, 0.015, 0), 0, 255).astype(np.uint8)


def recover_detail(img: np.ndarray) -> np.ndarray:
    detail = cv2.GaussianBlur(img, (0, 0), 1.2)
    return np.clip(cv2.addWeighted(img, 1.08, detail, -0.08, 0), 0, 255).astype(np.uint8)
