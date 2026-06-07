from __future__ import annotations

import argparse
import json
import shutil
import warnings
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .insert_mod import match_mod_appearance_to_cleaned_region


SD_HANDOFF_TEXT = """Image:
{image}

Mask:
{mask}

Recommended SD inpainting settings:
- denoising strength: 0.20–0.35
- mask blur: 10–20 px
- masked content: original
- preserve unmasked area: enabled
- inpaint area: whole image

Prompt:
realistic elevator wall, installed elevator button panel, subtle contact shadow, seamless metal edge, same perspective, same lighting, photorealistic

Negative prompt:
distorted buttons, changed panel, wrong perspective, extra buttons, blurry labels, warped text, melted metal, deformed display, altered numbers
"""


def parse_points(text: str, expected_count: int) -> np.ndarray:
    parts = [part.strip() for part in str(text).replace(";", " ").split() if part.strip()]
    if len(parts) != expected_count:
        raise ValueError(f"Expected exactly {expected_count} points, got {len(parts)}: {text}")
    points: list[list[float]] = []
    for part in parts:
        coords = [value.strip() for value in part.split(",")]
        if len(coords) != 2:
            raise ValueError(f"Point must be x,y: {part}")
        points.append([float(coords[0]), float(coords[1])])
    return np.array(points, dtype=np.float32)


def ensure_output_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_base_image(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Base image cannot load: {path}")
    return image


def load_panel_image(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Panel image cannot load: {path}")
    return image


def compute_grid_homography(plane_points: np.ndarray, grid_cols: int, grid_rows: int) -> np.ndarray:
    if len(plane_points) != 4:
        raise ValueError("Plane must contain exactly four points")
    if grid_cols <= 0 or grid_rows <= 0:
        raise ValueError("Grid rows/cols must be > 0")
    src = np.array([[0, 0], [grid_cols, 0], [grid_cols, grid_rows], [0, grid_rows]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(src, plane_points.astype(np.float32))
    if not np.isfinite(H).all():
        raise ValueError("Computed homography is invalid")
    return H


def project_grid_point(H: np.ndarray, x: float, y: float) -> tuple[float, float]:
    point = np.array([x, y, 1.0], dtype=np.float64)
    projected = H.astype(np.float64) @ point
    if abs(float(projected[2])) < 1e-9:
        raise ValueError(f"Projected point has invalid homogeneous coordinate: {(x, y)}")
    projected = projected[:2] / projected[2]
    return float(projected[0]), float(projected[1])


def draw_wall_plane(image: np.ndarray, plane_points: np.ndarray) -> np.ndarray:
    marked = image.copy()
    pts = np.round(plane_points).astype(np.int32)
    overlay = marked.copy()
    cv2.fillPoly(overlay, [pts], (0, 180, 255))
    marked = cv2.addWeighted(overlay, 0.18, marked, 0.82, 0)
    cv2.polylines(marked, [pts], True, (0, 180, 255), 3, cv2.LINE_AA)
    for idx, (x, y) in enumerate(pts, start=1):
        cv2.circle(marked, (int(x), int(y)), 5, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.putText(marked, str(idx), (int(x) + 7, int(y) - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA)
    return marked


def draw_perspective_grid(image: np.ndarray, H: np.ndarray, grid_cols: int, grid_rows: int) -> np.ndarray:
    grid = image.copy()
    for col in range(grid_cols + 1):
        p1 = project_grid_point(H, float(col), 0.0)
        p2 = project_grid_point(H, float(col), float(grid_rows))
        cv2.line(grid, _rounded_point(p1), _rounded_point(p2), (0, 255, 255), 1, cv2.LINE_AA)
    for row in range(grid_rows + 1):
        p1 = project_grid_point(H, 0.0, float(row))
        p2 = project_grid_point(H, float(grid_cols), float(row))
        cv2.line(grid, _rounded_point(p1), _rounded_point(p2), (0, 255, 255), 1, cv2.LINE_AA)
    return grid


def compute_local_component_quad(
    image_shape: tuple[int, int] | tuple[int, int, int],
    placement_debug: dict[str, Any] | None = None,
    target_box: list[int] | list[float] | None = None,
) -> np.ndarray:
    height, width = image_shape[:2]
    placement_debug = placement_debug or {}
    quad = _placement_quad_or_none(placement_debug)
    if quad is not None:
        return _clip_quad(quad, width, height)
    box = (
        target_box
        or placement_debug.get("final_insertion_bbox")
        or placement_debug.get("target_panel_bbox")
        or placement_debug.get("selected_replacement_target_bbox")
        or placement_debug.get("inpaint_bbox")
    )
    if not box:
        box_w = max(2.0, width * 0.08)
        box_h = max(2.0, height * 0.18)
        cx, cy = width * 0.5, height * 0.5
        box = [cx - box_w * 0.5, cy - box_h * 0.5, cx + box_w * 0.5, cy + box_h * 0.5]
    x1, y1, x2, y2 = [float(v) for v in box]
    quad = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
    return _clip_quad(quad, width, height)


def estimate_local_surface_quad(
    image: np.ndarray | None,
    component_type: str,
    target_bbox: list[int] | list[float],
    target_mask: np.ndarray | None = None,
    scene_masks: dict[str, np.ndarray] | None = None,
    lines: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    if image is None:
        quad = compute_local_component_quad((int(target_bbox[3]), int(target_bbox[2]), 3), {}, target_bbox)
        return quad, {"used_surface_source": "fallback_local_bbox", "fallback_used": True, "reason": "no_image"}
    height, width = image.shape[:2]
    box = _clip_box(target_bbox, width, height)
    base_quad = compute_local_component_quad(image.shape, {}, box)
    local_lines = lines if lines is not None else _detect_local_lines(image, box, component_type)
    if target_mask is not None:
        mask_quad = _quad_from_mask(target_mask, width, height)
        if mask_quad is not None:
            return mask_quad, {"used_surface_source": "mask_contour", "fallback_used": False}
    if str(component_type).lower() in {"elevator_door", "door", "elevator_cabin", "interior", "elevator_ceiling", "ceiling"}:
        door_quad = _door_frame_quad_from_lines(local_lines, box, width, height)
        if door_quad is not None:
            return door_quad, {"used_surface_source": "door_frame", "fallback_used": False}
    panel_quad = _panel_quad_from_lines(local_lines, box, width, height)
    if panel_quad is not None:
        source = "panel_edges" if str(component_type).lower() in {"elevator call button panel", "car_operating_panel", "car operating panel", "landing_call_indicator"} else "line_detection"
        return panel_quad, {"used_surface_source": source, "fallback_used": False}
    angle = _dominant_local_angle(local_lines, prefer_vertical=True)
    if angle is not None:
        quad = _tilted_quad_from_bbox(box, angle, width, height)
        return quad, {"used_surface_source": "line_detection", "fallback_used": False, "dominant_angle_degrees": float(angle)}
    return base_quad, {"used_surface_source": "fallback_local_bbox", "fallback_used": True}


def estimate_local_surface_angle_degrees(local_quad: np.ndarray) -> float:
    return estimate_quad_angle_degrees(local_quad)


def build_asset_quad_on_surface(
    target_bbox: list[int] | list[float],
    surface_quad: np.ndarray,
    component_type: str,
    padding_ratio: float = 0.0,
) -> np.ndarray:
    x1, y1, x2, y2 = [float(v) for v in target_bbox]
    bw, bh = max(2.0, x2 - x1), max(2.0, y2 - y1)
    if padding_ratio:
        px, py = bw * padding_ratio, bh * padding_ratio
        x1 -= px
        x2 += px
        y1 -= py
        y2 += py
    surface = np.asarray(surface_quad, dtype=np.float32)
    sx1, sy1 = np.min(surface[:, 0]), np.min(surface[:, 1])
    sx2, sy2 = np.max(surface[:, 0]), np.max(surface[:, 1])
    sw, sh = max(2.0, float(sx2 - sx1)), max(2.0, float(sy2 - sy1))

    def norm_x(value: float) -> float:
        return float(np.clip((value - sx1) / sw, -0.10, 1.10))

    def norm_y(value: float) -> float:
        return float(np.clip((value - sy1) / sh, -0.10, 1.10))

    u1, u2 = norm_x(x1), norm_x(x2)
    v1, v2 = norm_y(y1), norm_y(y2)

    destination = np.array(
        [
            _bilinear_quad_point(surface, u1, v1),
            _bilinear_quad_point(surface, u2, v1),
            _bilinear_quad_point(surface, u2, v2),
            _bilinear_quad_point(surface, u1, v2),
        ],
        dtype=np.float32,
    )
    if cv2.contourArea(destination) < 4.0:
        return compute_local_component_quad((max(2, int(y2 + 2)), max(2, int(x2 + 2)), 3), {}, [x1, y1, x2, y2])
    return destination


def warp_asset_to_surface(
    asset: np.ndarray,
    asset_mask: np.ndarray | None,
    destination_quad: np.ndarray,
    output_shape: tuple[int, int] | tuple[int, int, int],
) -> np.ndarray:
    rgba = asset
    if rgba.ndim == 3 and rgba.shape[2] == 3:
        alpha = asset_mask if asset_mask is not None else np.full(rgba.shape[:2], 255, dtype=np.uint8)
        rgba = np.dstack([rgba, alpha])
    return warp_panel_to_quad(rgba, destination_quad, output_shape)


def draw_surface_perspective_debug(
    image: np.ndarray,
    surface_quad: np.ndarray,
    destination_quad: np.ndarray,
    component_type: str,
) -> np.ndarray:
    marked = image.copy()
    if marked.ndim == 3 and marked.shape[2] == 3:
        pass
    surface_pts = np.round(surface_quad).astype(np.int32)
    dest_pts = np.round(destination_quad).astype(np.int32)
    overlay = marked.copy()
    cv2.fillPoly(overlay, [surface_pts], (0, 180, 255))
    marked = cv2.addWeighted(overlay, 0.16, marked, 0.84, 0)
    cv2.polylines(marked, [surface_pts], True, (0, 220, 255), 2, cv2.LINE_AA)
    cv2.polylines(marked, [dest_pts], True, (255, 80, 0), 3, cv2.LINE_AA)
    try:
        H = compute_grid_homography(surface_quad.astype(np.float32), 4, 8)
        marked = draw_perspective_grid(marked, H, 4, 8)
    except Exception:
        pass
    x, y = dest_pts[0]
    cv2.putText(marked, str(component_type), (int(x), int(y) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 80, 0), 2, cv2.LINE_AA)
    return marked


def compute_local_component_homography(source_size: tuple[int, int], target_quad: np.ndarray) -> np.ndarray:
    src_w, src_h = [max(1, int(v)) for v in source_size]
    src = np.array([[0, 0], [src_w - 1, 0], [src_w - 1, src_h - 1], [0, src_h - 1]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(src, target_quad.astype(np.float32))
    if not np.isfinite(H).all():
        raise ValueError("Local component homography is invalid")
    return H


def estimate_quad_angle_degrees(target_quad: np.ndarray) -> float:
    quad = target_quad.astype(np.float32)
    top = quad[1] - quad[0]
    bottom = quad[2] - quad[3]
    edge = (top + bottom) * 0.5
    return float(np.degrees(np.arctan2(float(edge[1]), float(edge[0]))))


def warp_component_to_local_quad(
    component_rgba: np.ndarray,
    target_quad: np.ndarray,
    output_shape: tuple[int, int] | tuple[int, int, int],
) -> np.ndarray:
    return warp_panel_to_quad(component_rgba, target_quad, output_shape)


def draw_local_perspective_grid(
    image: np.ndarray,
    target_quad: np.ndarray,
    grid_cols: int = 4,
    grid_rows: int = 8,
) -> np.ndarray:
    marked = image.copy()
    quad = target_quad.astype(np.float32)
    H = compute_grid_homography(quad, max(1, int(grid_cols)), max(1, int(grid_rows)))
    pts = np.round(quad).astype(np.int32)
    overlay = marked.copy()
    cv2.fillPoly(overlay, [pts], (0, 220, 255))
    marked = cv2.addWeighted(overlay, 0.18, marked, 0.82, 0)
    cv2.polylines(marked, [pts], True, (0, 180, 255), 2, cv2.LINE_AA)
    return draw_perspective_grid(marked, H, max(1, int(grid_cols)), max(1, int(grid_rows)))


def compute_mod_destination(H: np.ndarray, mod_box: np.ndarray) -> np.ndarray:
    if len(mod_box) != 2:
        raise ValueError("MOD box must contain exactly two points")
    (x1, y1), (x2, y2) = mod_box.astype(np.float32)
    dst = np.array(
        [
            project_grid_point(H, float(x1), float(y1)),
            project_grid_point(H, float(x2), float(y1)),
            project_grid_point(H, float(x2), float(y2)),
            project_grid_point(H, float(x1), float(y2)),
        ],
        dtype=np.float32,
    )
    if cv2.contourArea(dst) <= 1.0:
        raise ValueError(f"Projected MOD destination has invalid area: {dst.tolist()}")
    return dst


def compute_mod_box_from_destination(H: np.ndarray, dst_quad: np.ndarray) -> np.ndarray:
    if len(dst_quad) != 4:
        raise ValueError("Destination quad must contain exactly four points")
    H_inv = np.linalg.inv(H.astype(np.float64))
    top_left = project_grid_point(H_inv, float(dst_quad[0][0]), float(dst_quad[0][1]))
    bottom_right = project_grid_point(H_inv, float(dst_quad[2][0]), float(dst_quad[2][1]))
    mod_box = np.array([top_left, bottom_right], dtype=np.float32)
    if not np.isfinite(mod_box).all():
        raise ValueError("Auto MOD box contains invalid coordinates")
    return mod_box


def prepare_panel_rgba(panel: np.ndarray) -> np.ndarray:
    if panel.ndim == 2:
        rgb = cv2.cvtColor(panel, cv2.COLOR_GRAY2BGR)
        alpha = np.full(panel.shape, 255, dtype=np.uint8)
        return np.dstack([rgb, alpha])
    if panel.shape[2] == 4:
        rgba = cv2.cvtColor(panel, cv2.COLOR_BGRA2RGBA)
        alpha = rgba[:, :, 3]
        if int(alpha.max()) > 0:
            return rgba
        return np.dstack([rgba[:, :, :3], _fallback_alpha_from_rgb(rgba[:, :, :3])])
    if panel.shape[2] == 3:
        rgb = cv2.cvtColor(panel, cv2.COLOR_BGR2RGB)
        alpha = _fallback_alpha_from_rgb(rgb)
        return np.dstack([rgb, alpha])
    raise ValueError(f"Unsupported panel channel count: {panel.shape}")


def warp_panel_to_quad(panel_rgba: np.ndarray, dst_quad: np.ndarray, output_shape: tuple[int, int] | tuple[int, int, int]) -> np.ndarray:
    height, width = output_shape[:2]
    panel_h, panel_w = panel_rgba.shape[:2]
    src_quad = np.array([[0, 0], [panel_w, 0], [panel_w, panel_h], [0, panel_h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src_quad, dst_quad.astype(np.float32))
    warped_rgba = cv2.warpPerspective(
        panel_rgba,
        M,
        (width, height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    if warped_rgba.ndim != 3 or warped_rgba.shape[2] != 4:
        raise RuntimeError("Warped panel did not preserve RGBA channels")
    return warped_rgba


def alpha_composite(base: np.ndarray, warped_panel: np.ndarray) -> np.ndarray:
    panel_rgb = cv2.cvtColor(warped_panel[:, :, :3], cv2.COLOR_RGB2BGR)
    alpha = refine_alpha(warped_panel[:, :, 3].astype(np.float32) / 255.0)
    return alpha_composite_rgb(base, panel_rgb, alpha)


def alpha_composite_rgb(bg: np.ndarray, fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    return np.clip(fg.astype(np.float32) * alpha[:, :, None] + bg.astype(np.float32) * (1.0 - alpha[:, :, None]), 0, 255).astype(np.uint8)


def match_panel_lighting(base: np.ndarray, warped_rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    mask = alpha > 10
    if int(mask.sum()) < 20:
        return warped_rgb
    base_lab = cv2.cvtColor(base, cv2.COLOR_BGR2LAB)
    panel_bgr = cv2.cvtColor(warped_rgb, cv2.COLOR_RGB2BGR)
    panel_lab = cv2.cvtColor(panel_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    base_l = float(base_lab[:, :, 0][mask].mean())
    panel_l = float(panel_lab[:, :, 0][mask].mean())
    if panel_l <= 1e-3:
        return warped_rgb
    scale = np.clip(base_l / panel_l, 0.82, 1.18)
    panel_lab[:, :, 0] = np.clip(panel_lab[:, :, 0] * scale, 0, 255)
    matched_bgr = cv2.cvtColor(panel_lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
    return cv2.cvtColor(matched_bgr, cv2.COLOR_BGR2RGB)


def realistic_composite(base: np.ndarray, warped_panel: np.ndarray, match_lighting: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    alpha = refine_alpha(warped_panel[:, :, 3].astype(np.float32) / 255.0)
    fg_rgb = warped_panel[:, :, :3]
    if match_lighting:
        fg_rgb = match_panel_lighting(base, fg_rgb, warped_panel[:, :, 3])
    fg_bgr = cv2.cvtColor(fg_rgb, cv2.COLOR_RGB2BGR)
    fg_bgr = harmonize_foreground(fg_bgr, base, alpha)
    fg_bgr = match_scene_white_balance(fg_bgr)
    fg_bgr = add_wall_bounce_light(fg_bgr, alpha)
    fg_bgr = cv2.convertScaleAbs(fg_bgr, alpha=0.975, beta=3)
    fg_bgr = edge_integration(fg_bgr, alpha)
    fg_bgr = transfer_wall_texture(base, fg_bgr, alpha)

    grounded = apply_realistic_shadow(base, alpha)
    grounded = add_contact_shadow(grounded, alpha)
    grounded = add_wall_grounding(grounded, alpha)
    final = alpha_composite_rgb(grounded, fg_bgr, alpha)
    final = add_camera_realism(final)
    final = add_scene_haze(final)
    final = recover_detail(final)
    mask = (alpha > 0.03).astype(np.uint8) * 255
    return final, mask, alpha


def refine_alpha(alpha: np.ndarray) -> np.ndarray:
    return np.clip(cv2.GaussianBlur(alpha.astype(np.float32), (3, 3), 0.12), 0.0, 1.0)


def harmonize_foreground(fg: np.ndarray, bg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    mask = alpha > 0.05
    if int(mask.sum()) < 50:
        return fg
    fg_lab = cv2.cvtColor(fg, cv2.COLOR_BGR2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(bg, cv2.COLOR_BGR2LAB).astype(np.float32)
    delta = (float(bg_lab[:, :, 0][mask].mean()) - float(fg_lab[:, :, 0][mask].mean())) * 0.10
    fg_lab[:, :, 0] = np.clip(fg_lab[:, :, 0] + delta, 0, 255)
    fg_lab[:, :, 1] *= 0.985
    fg_lab[:, :, 2] *= 0.985
    return cv2.cvtColor(np.clip(fg_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def match_scene_white_balance(fg: np.ndarray) -> np.ndarray:
    out = fg.astype(np.float32)
    out[:, :, 2] *= 1.03
    out[:, :, 1] *= 1.01
    out[:, :, 0] *= 0.97
    return np.clip(out, 0, 255).astype(np.uint8)


def add_wall_bounce_light(fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    glow = cv2.GaussianBlur(solid, (31, 31), 10)
    glow = np.clip(glow - solid, 0, 1)
    return np.clip(fg.astype(np.float32) + glow[:, :, None] * 3.0, 0, 255).astype(np.uint8)


def apply_realistic_shadow(bg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    shadow = cv2.GaussianBlur(solid, (31, 31), 10)
    shadow = np.roll(np.roll(shadow, 10, axis=0), -7, axis=1)
    shadow = np.clip(shadow - solid, 0, 1)
    contact = cv2.GaussianBlur(solid, (11, 11), 3)
    contact = np.roll(np.roll(contact, 3, axis=0), -2, axis=1)
    shadow_mask = np.clip(shadow * 0.11 + contact * 0.30, 0, 0.42)
    return np.clip(bg.astype(np.float32) * (1.0 - shadow_mask[:, :, None]), 0, 255).astype(np.uint8)


def add_contact_shadow(bg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    contact = cv2.GaussianBlur(solid, (7, 7), 1.6)
    contact = np.roll(np.roll(contact, 3, axis=0), -3, axis=1)
    edge = cv2.Canny((solid * 255).astype(np.uint8), 20, 80)
    edge = cv2.GaussianBlur(edge.astype(np.float32) / 255.0, (5, 5), 1.5)
    contact = np.clip(contact + edge * 0.8, 0, 1)
    return np.clip(bg.astype(np.float32) * (1.0 - contact[:, :, None] * 0.28), 0, 255).astype(np.uint8)


def add_wall_grounding(bg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    solid = (alpha > 0.03).astype(np.float32)
    halo = cv2.GaussianBlur(solid, (51, 51), 18)
    halo = np.clip(halo - solid, 0, 1)
    return np.clip(bg.astype(np.float32) * (1.0 - halo[:, :, None] * 0.035), 0, 255).astype(np.uint8)


def edge_integration(fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    edge = cv2.Canny((alpha * 255).astype(np.uint8), 30, 90)
    edge = cv2.GaussianBlur(edge.astype(np.float32), (5, 5), 1.2) / 255.0
    soft = cv2.GaussianBlur(fg, (3, 3), 0.7)
    edge_mask = np.clip(edge * 2.2, 0, 1)
    return np.clip(fg.astype(np.float32) * (1 - edge_mask[:, :, None]) + soft.astype(np.float32) * edge_mask[:, :, None], 0, 255).astype(np.uint8)


def transfer_wall_texture(bg: np.ndarray, fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    mask = alpha > 0.03
    wall_blur = cv2.GaussianBlur(bg, (0, 0), 2.0)
    wall_detail = bg.astype(np.float32) - wall_blur.astype(np.float32)
    out = fg.astype(np.float32)
    out[mask] += wall_detail[mask] * 0.10
    return np.clip(out, 0, 255).astype(np.uint8)


def add_camera_realism(img: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(42)
    out = img.astype(np.float32) + rng.normal(0, 0.22, img.shape)
    out = np.clip(out, 0, 255)
    blur = cv2.GaussianBlur(out, (0, 0), 1.4)
    return np.clip(cv2.addWeighted(out, 1.12, blur, -0.12, 0), 0, 255).astype(np.uint8)


def add_scene_haze(img: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 12)
    return np.clip(cv2.addWeighted(img, 0.985, blur, 0.015, 0), 0, 255).astype(np.uint8)


def recover_detail(img: np.ndarray) -> np.ndarray:
    detail = cv2.GaussianBlur(img, (0, 0), 1.2)
    return np.clip(cv2.addWeighted(img, 1.08, detail, -0.08, 0), 0, 255).astype(np.uint8)


def create_edge_refine_mask(alpha: np.ndarray, outer_kernel_size: int = 31, inner_kernel_size: int = 11) -> np.ndarray:
    alpha_u8 = (alpha > 10).astype(np.uint8) * 255
    outer_kernel = _odd_kernel(outer_kernel_size)
    inner_kernel = _odd_kernel(inner_kernel_size)
    dilated = cv2.dilate(alpha_u8, np.ones((outer_kernel, outer_kernel), np.uint8), iterations=1)
    eroded = cv2.erode(alpha_u8, np.ones((inner_kernel, inner_kernel), np.uint8), iterations=1)
    return cv2.subtract(dilated, eroded)


def validate_edge_mask(mask: np.ndarray, image_shape: tuple[int, int] | tuple[int, int, int]) -> None:
    if mask.ndim != 2:
        raise ValueError("Edge mask must be single-channel")
    height, width = image_shape[:2]
    if mask.shape != (height, width):
        raise ValueError(f"Edge mask shape {mask.shape} does not match image shape {(height, width)}")
    coverage = float((mask > 0).sum()) / float(max(height * width, 1))
    if coverage <= 0.0:
        raise ValueError("Edge mask is empty")
    if coverage > 0.12:
        raise ValueError(f"Edge mask covers too much image area: {coverage:.3f}")


def save_outputs(
    out_dir: str | Path,
    original: np.ndarray,
    wall_plane_marked: np.ndarray,
    perspective_grid: np.ndarray,
    warped_panel: np.ndarray,
    placed: np.ndarray,
    edge_mask: np.ndarray,
    sd_ready: np.ndarray,
) -> dict[str, Path]:
    out = ensure_output_dir(out_dir)
    outputs = {
        "original": out / "01_original.jpg",
        "wall_plane_marked": out / "02_wall_plane_marked.jpg",
        "perspective_grid": out / "03_perspective_grid.jpg",
        "mod_panel_warped": out / "04_mod_panel_warped.png",
        "mod_panel_placed": out / "05_mod_panel_placed.jpg",
        "edge_refine_mask": out / "06_edge_refine_mask.png",
        "sd_ready_composite": out / "07_sd_ready_composite.jpg",
    }
    cv2.imwrite(str(outputs["original"]), original)
    cv2.imwrite(str(outputs["wall_plane_marked"]), wall_plane_marked)
    cv2.imwrite(str(outputs["perspective_grid"]), perspective_grid)
    cv2.imwrite(str(outputs["mod_panel_warped"]), cv2.cvtColor(warped_panel, cv2.COLOR_RGBA2BGRA))
    cv2.imwrite(str(outputs["mod_panel_placed"]), placed)
    cv2.imwrite(str(outputs["edge_refine_mask"]), edge_mask)
    cv2.imwrite(str(outputs["sd_ready_composite"]), sd_ready)
    return outputs


def run_perspective_mod_placement(
    base_path: str | Path,
    panel_path: str | Path,
    out_dir: str | Path,
    plane_points: np.ndarray,
    grid_cols: int,
    grid_rows: int,
    mod_box: np.ndarray,
    match_lighting: bool = False,
) -> dict[str, Path]:
    base = load_base_image(base_path)
    panel = load_panel_image(panel_path)
    if len(plane_points) != 4:
        raise ValueError("Plane must contain exactly four points")
    if len(mod_box) != 2:
        raise ValueError("MOD box must contain exactly two points")
    if grid_cols <= 0 or grid_rows <= 0:
        raise ValueError("Grid rows/cols must be > 0")
    _warn_if_mod_box_outside_grid(mod_box, grid_cols, grid_rows)

    H = compute_grid_homography(plane_points, grid_cols, grid_rows)
    dst_quad = compute_mod_destination(H, mod_box)
    panel_rgba = prepare_panel_rgba(panel)
    dst_min = np.floor(dst_quad.min(axis=0)).astype(int)
    dst_max = np.ceil(dst_quad.max(axis=0)).astype(int)
    panel_rgba = match_mod_appearance_to_cleaned_region(
        panel_rgba,
        cv2.cvtColor(base, cv2.COLOR_BGR2RGB),
        [int(dst_min[0]), int(dst_min[1]), int(dst_max[0]), int(dst_max[1])],
    )
    warped = warp_panel_to_quad(panel_rgba, dst_quad, base.shape)
    if match_lighting:
        warped = warped.copy()
        warped[:, :, :3] = match_panel_lighting(base, warped[:, :, :3], warped[:, :, 3])
    placed, harmonization_mask, alpha = realistic_composite(base, warped, match_lighting)
    edge_mask = create_edge_refine_mask((alpha * 255).astype(np.uint8))
    validate_edge_mask(edge_mask, base.shape)
    outputs = save_outputs(
        out_dir,
        base,
        draw_wall_plane(base, plane_points),
        draw_perspective_grid(draw_wall_plane(base, plane_points), H, grid_cols, grid_rows),
        warped,
        placed,
        edge_mask,
        placed,
    )
    outputs["harmonization_mask"] = Path(out_dir) / "harmonization_mask.png"
    outputs["composite"] = Path(out_dir) / "composite.png"
    cv2.imwrite(str(outputs["harmonization_mask"]), harmonization_mask)
    cv2.imwrite(str(outputs["composite"]), placed)
    return outputs


def run_auto_perspective_mod_placement(
    base_path: str | Path,
    panel_path: str | Path,
    out_dir: str | Path,
    geometry: dict[str, Any],
    placement_debug: dict[str, Any],
    grid_cols: int = 8,
    grid_rows: int = 12,
    match_lighting: bool = False,
) -> dict[str, Path]:
    base = load_base_image(base_path)
    plane_points = infer_wall_plane_points(base.shape, geometry, placement_debug)
    destination = infer_mod_destination_quad(placement_debug)
    H = compute_grid_homography(plane_points, grid_cols, grid_rows)
    mod_box = compute_mod_box_from_destination(H, destination)
    outputs = run_perspective_mod_placement(
        base_path,
        panel_path,
        out_dir,
        plane_points,
        grid_cols,
        grid_rows,
        mod_box,
        match_lighting,
    )
    metadata = {
        "mode": "auto",
        "plane_points": plane_points.tolist(),
        "grid_cols": int(grid_cols),
        "grid_rows": int(grid_rows),
        "mod_box": mod_box.tolist(),
        "mod_destination_quad": compute_mod_destination(H, mod_box).tolist(),
        "source_destination_quad": destination.tolist(),
    }
    (ensure_output_dir(out_dir) / "auto_perspective_grid.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return outputs


def run_from_config(cfg: dict[str, Any], base_path: str | Path, panel_path: str | Path, out_dir: str | Path) -> dict[str, Path] | None:
    perspective_cfg = cfg.get("perspective_mod_placement", {})
    if not perspective_cfg.get("enabled", False):
        return None
    if perspective_cfg.get("auto", True) and not perspective_cfg.get("plane") and not perspective_cfg.get("mod_box"):
        return None
    plane = _points_from_config(perspective_cfg.get("plane"), 4, "perspective_mod_placement.plane")
    mod_box = _points_from_config(perspective_cfg.get("mod_box"), 2, "perspective_mod_placement.mod_box")
    grid_cols = int(perspective_cfg.get("grid_cols", 0))
    grid_rows = int(perspective_cfg.get("grid_rows", 0))
    match_lighting = bool(perspective_cfg.get("match_lighting", False))
    return run_perspective_mod_placement(base_path, panel_path, out_dir, plane, grid_cols, grid_rows, mod_box, match_lighting)


def copy_pipeline_handoff(outputs: dict[str, Path], composite_path: str | Path, panel_mask_path: str | Path) -> None:
    shutil.copyfile(outputs["sd_ready_composite"], composite_path)
    shutil.copyfile(outputs.get("harmonization_mask", outputs["edge_refine_mask"]), panel_mask_path)


def infer_wall_plane_points(
    image_shape: tuple[int, int] | tuple[int, int, int],
    geometry: dict[str, Any],
    placement_debug: dict[str, Any],
) -> np.ndarray:
    height, width = image_shape[:2]
    local_quad = _placement_quad_or_none(placement_debug)
    src_corners = geometry.get("homography", {}).get("src_corners")
    if src_corners is not None:
        points = np.array(src_corners, dtype=np.float32)
        if points.shape == (4, 2) and cv2.contourArea(points) > width * height * 0.05:
            if local_quad is not None and _quad_skew_score(local_quad) > _quad_skew_score(points) + 0.02:
                return _clip_quad(_expanded_local_plane(local_quad), width, height)
            return _clip_quad(points, width, height)

    if local_quad is not None:
        return _clip_quad(_expanded_local_plane(local_quad), width, height)

    box = (
        placement_debug.get("target_panel_bbox")
        or placement_debug.get("selected_replacement_target_bbox")
        or placement_debug.get("inpaint_bbox")
        or placement_debug.get("final_insertion_bbox")
    )
    if box:
        x1, y1, x2, y2 = [float(v) for v in box]
        bw, bh = max(2.0, x2 - x1), max(2.0, y2 - y1)
        pad_x = max(bw * 3.0, width * 0.18)
        pad_y = max(bh * 0.8, height * 0.12)
        left = max(0.0, x1 - pad_x)
        right = min(float(width - 1), x2 + pad_x)
        top = max(0.0, y1 - pad_y)
        bottom = min(float(height - 1), y2 + pad_y)
        return np.array([[left, top], [right, top], [right, bottom], [left, bottom]], dtype=np.float32)

    return np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)


def infer_mod_destination_quad(placement_debug: dict[str, Any]) -> np.ndarray:
    points = _placement_quad_or_none(placement_debug)
    if points is not None:
        return points
    box = placement_debug.get("final_insertion_bbox") or placement_debug.get("inpaint_bbox")
    if not box:
        raise ValueError("Cannot infer MOD destination: missing final insertion bbox")
    x1, y1, x2, y2 = [float(v) for v in box]
    points = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
    if cv2.contourArea(points) <= 1.0:
        raise ValueError("Cannot infer MOD destination: invalid insertion bbox")
    return points


def _points_from_config(value: Any, expected_count: int, name: str) -> np.ndarray:
    if isinstance(value, str):
        return parse_points(value, expected_count)
    if isinstance(value, (list, tuple)):
        points = np.array(value, dtype=np.float32)
        if points.shape != (expected_count, 2):
            raise ValueError(f"{name} must contain exactly {expected_count} x,y points")
        return points
    raise ValueError(f"{name} is required")


def _fallback_alpha_from_rgb(rgb: np.ndarray) -> np.ndarray:
    intensity = rgb.max(axis=2)
    alpha = (intensity > 8).astype(np.uint8) * 255
    if int(alpha.sum()) == 0:
        alpha = np.full(rgb.shape[:2], 255, dtype=np.uint8)
    return alpha


def _rounded_point(point: tuple[float, float]) -> tuple[int, int]:
    return int(round(point[0])), int(round(point[1]))


def _odd_kernel(size: int) -> int:
    size = max(3, int(size))
    return size if size % 2 == 1 else size + 1


def _warn_if_mod_box_outside_grid(mod_box: np.ndarray, grid_cols: int, grid_rows: int) -> None:
    x_values = mod_box[:, 0]
    y_values = mod_box[:, 1]
    if x_values.min() < 0 or y_values.min() < 0 or x_values.max() > grid_cols or y_values.max() > grid_rows:
        warnings.warn("MOD box is outside grid bounds", RuntimeWarning, stacklevel=2)


def _clip_quad(points: np.ndarray, width: int, height: int) -> np.ndarray:
    clipped = points.astype(np.float32).copy()
    clipped[:, 0] = np.clip(clipped[:, 0], 0, width - 1)
    clipped[:, 1] = np.clip(clipped[:, 1], 0, height - 1)
    return clipped


def _bilinear_quad_point(quad: np.ndarray, u: float, v: float) -> np.ndarray:
    top = quad[0] * (1.0 - u) + quad[1] * u
    bottom = quad[3] * (1.0 - u) + quad[2] * u
    return (top * (1.0 - v) + bottom * v).astype(np.float32)


def _clip_box(box: list[int] | list[float], width: int, height: int) -> list[float]:
    x1, y1, x2, y2 = [float(v) for v in box]
    return [
        float(np.clip(x1, 0, width - 2)),
        float(np.clip(y1, 0, height - 2)),
        float(np.clip(x2, x1 + 2, width)),
        float(np.clip(y2, y1 + 2, height)),
    ]


def _detect_local_lines(image: np.ndarray, box: list[float], component_type: str) -> np.ndarray:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    bw, bh = max(2, x2 - x1), max(2, y2 - y1)
    is_large = str(component_type).lower() in {"elevator_door", "door", "elevator_cabin", "interior", "elevator_ceiling", "ceiling"}
    pad_x = max(28, int(bw * (0.38 if is_large else 1.20)))
    pad_y = max(28, int(bh * (0.20 if is_large else 0.85)))
    sx1, sy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    sx2, sy2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
    crop = image[sy1:sy2, sx1:sx2]
    if crop.size == 0:
        return np.empty((0, 4), dtype=np.float32)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.shape[2] == 3 else crop
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 130)
    min_len = max(18, int(min(bw, bh) * 0.20))
    raw = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(22, min_len // 2), minLineLength=min_len, maxLineGap=max(8, min_len // 3))
    if raw is None:
        return np.empty((0, 4), dtype=np.float32)
    lines = raw.reshape(-1, 4).astype(np.float32)
    lines[:, [0, 2]] += sx1
    lines[:, [1, 3]] += sy1
    return lines


def _line_angle(line: np.ndarray) -> float:
    x1, y1, x2, y2 = [float(v) for v in line]
    return float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))


def _line_length(line: np.ndarray) -> float:
    x1, y1, x2, y2 = [float(v) for v in line]
    return float(np.hypot(x2 - x1, y2 - y1))


def _x_at_y(line: np.ndarray, y: float) -> float | None:
    x1, y1, x2, y2 = [float(v) for v in line]
    if abs(y2 - y1) < 1e-3:
        return None
    t = (y - y1) / (y2 - y1)
    return x1 + (x2 - x1) * t


def _y_at_x(line: np.ndarray, x: float) -> float | None:
    x1, y1, x2, y2 = [float(v) for v in line]
    if abs(x2 - x1) < 1e-3:
        return None
    t = (x - x1) / (x2 - x1)
    return y1 + (y2 - y1) * t


def _door_frame_quad_from_lines(lines: np.ndarray, box: list[float], width: int, height: int) -> np.ndarray | None:
    if lines.size == 0:
        return None
    x1, y1, x2, y2 = box
    cx = (x1 + x2) * 0.5
    verticals = [line for line in lines if 58 <= abs(_line_angle(line)) <= 122 and _line_length(line) >= (y2 - y1) * 0.18]
    lefts = [line for line in verticals if ((line[0] + line[2]) * 0.5) < cx]
    rights = [line for line in verticals if ((line[0] + line[2]) * 0.5) >= cx]
    if not lefts or not rights:
        return None
    left = max(lefts, key=_line_length)
    right = max(rights, key=_line_length)
    lx_top, lx_bottom = _x_at_y(left, y1), _x_at_y(left, y2)
    rx_top, rx_bottom = _x_at_y(right, y1), _x_at_y(right, y2)
    if None in {lx_top, lx_bottom, rx_top, rx_bottom}:
        return None
    quad = np.array([[lx_top, y1], [rx_top, y1], [rx_bottom, y2], [lx_bottom, y2]], dtype=np.float32)
    if cv2.contourArea(quad) <= 2:
        return None
    return _clip_quad(quad, width, height)


def _panel_quad_from_lines(lines: np.ndarray, box: list[float], width: int, height: int) -> np.ndarray | None:
    if lines.size == 0:
        return None
    x1, y1, x2, y2 = box
    vertical_angle = _dominant_local_angle(lines, prefer_vertical=True)
    horizontal_angle = _dominant_local_angle(lines, prefer_vertical=False)
    if vertical_angle is None and horizontal_angle is None:
        return None
    angle = vertical_angle if vertical_angle is not None else (horizontal_angle + 90.0)
    return _tilted_quad_from_bbox(box, angle, width, height)


def _dominant_local_angle(lines: np.ndarray, prefer_vertical: bool) -> float | None:
    if lines.size == 0:
        return None
    candidates: list[tuple[float, float]] = []
    for line in lines:
        angle = _line_angle(line)
        length = _line_length(line)
        if prefer_vertical:
            deviation = min(abs(angle - 90), abs(angle + 90))
            if deviation > 32:
                continue
            normalized = angle - 90 if angle >= 0 else angle + 90
        else:
            deviation = min(abs(angle), abs(abs(angle) - 180))
            if deviation > 28:
                continue
            normalized = angle if abs(angle) <= 90 else angle - np.sign(angle) * 180
        candidates.append((float(normalized), length))
    if not candidates:
        return None
    angles = np.array([item[0] for item in candidates], dtype=np.float32)
    weights = np.array([item[1] for item in candidates], dtype=np.float32)
    order = np.argsort(angles)
    angles, weights = angles[order], weights[order]
    midpoint = float(weights.sum() * 0.5)
    return float(angles[min(len(angles) - 1, int(np.searchsorted(np.cumsum(weights), midpoint)))])


def _tilted_quad_from_bbox(box: list[float], vertical_angle_degrees: float, width: int, height: int) -> np.ndarray:
    x1, y1, x2, y2 = [float(v) for v in box]
    bw, bh = max(2.0, x2 - x1), max(2.0, y2 - y1)
    cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    theta = np.radians(vertical_angle_degrees)
    v = np.array([np.sin(theta), np.cos(theta)], dtype=np.float32)
    hvec = np.array([np.cos(theta), -np.sin(theta)], dtype=np.float32)
    quad = np.array(
        [
            [cx, cy] - hvec * bw * 0.5 - v * bh * 0.5,
            [cx, cy] + hvec * bw * 0.5 - v * bh * 0.5,
            [cx, cy] + hvec * bw * 0.5 + v * bh * 0.5,
            [cx, cy] - hvec * bw * 0.5 + v * bh * 0.5,
        ],
        dtype=np.float32,
    )
    return _clip_quad(quad, width, height)


def _quad_vertical_shear(quad: np.ndarray) -> float:
    tl, tr, br, bl = quad.astype(np.float32)
    left_h = max(float(np.linalg.norm(bl - tl)), 1.0)
    right_h = max(float(np.linalg.norm(br - tr)), 1.0)
    return float(((bl[0] - tl[0]) / left_h + (br[0] - tr[0]) / right_h) * 0.5)


def _quad_horizontal_shear(quad: np.ndarray) -> float:
    tl, tr, br, bl = quad.astype(np.float32)
    top_w = max(float(np.linalg.norm(tr - tl)), 1.0)
    bottom_w = max(float(np.linalg.norm(br - bl)), 1.0)
    return float(((tr[1] - tl[1]) / top_w + (br[1] - bl[1]) / bottom_w) * 0.5)


def _quad_from_mask(mask: np.ndarray, width: int, height: int) -> np.ndarray | None:
    binary = (mask > 0).astype(np.uint8)
    if binary.sum() < 16:
        return None
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) <= 4:
        return None
    rect = cv2.minAreaRect(contour)
    points = cv2.boxPoints(rect).astype(np.float32)
    center = points.mean(axis=0)
    ordered = sorted(points, key=lambda p: np.arctan2(p[1] - center[1], p[0] - center[0]))
    ordered = np.array(ordered, dtype=np.float32)
    top_first = np.roll(ordered, -int(np.argmin(ordered.sum(axis=1))), axis=0)
    return _clip_quad(top_first, width, height)


def _placement_quad_or_none(placement_debug: dict[str, Any]) -> np.ndarray | None:
    quad = placement_debug.get("homography_destination_quad")
    if quad is None:
        return None
    points = np.array(quad, dtype=np.float32)
    if points.shape != (4, 2) or cv2.contourArea(points) <= 1.0:
        return None
    return points


def _expanded_local_plane(quad: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = quad.astype(np.float32)
    top = tr - tl
    bottom = br - bl
    left = bl - tl
    right = br - tr
    return np.array(
        [
            tl - top * 3.0 - left * 1.25,
            tr + top * 5.0 - right * 1.25,
            br + bottom * 5.0 + right * 1.25,
            bl - bottom * 3.0 + left * 1.25,
        ],
        dtype=np.float32,
    )


def _quad_skew_score(quad: np.ndarray) -> float:
    tl, tr, br, bl = quad.astype(np.float32)
    top_w = max(float(np.linalg.norm(tr - tl)), 1.0)
    bottom_w = max(float(np.linalg.norm(br - bl)), 1.0)
    left_h = max(float(np.linalg.norm(bl - tl)), 1.0)
    right_h = max(float(np.linalg.norm(br - tr)), 1.0)
    horizontal_tilt = abs(float(tr[1] - tl[1])) / top_w + abs(float(br[1] - bl[1])) / bottom_w
    vertical_tilt = abs(float(bl[0] - tl[0])) / left_h + abs(float(br[0] - tr[0])) / right_h
    return horizontal_tilt + vertical_tilt


def main() -> None:
    parser = argparse.ArgumentParser(description="Place a MOD panel onto an elevator wall using a perspective grid homography.")
    parser.add_argument("--base", required=True, help="Base elevator image path")
    parser.add_argument("--panel", required=True, help="MOD/button panel image path")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--plane", required=True, help='Four plane points: "x,y x,y x,y x,y" in TL TR BR BL order')
    parser.add_argument("--grid-cols", required=True, type=int, help="Perspective grid columns")
    parser.add_argument("--grid-rows", required=True, type=int, help="Perspective grid rows")
    parser.add_argument("--mod-box", required=True, help='Two grid points: "x1,y1 x2,y2" in top-left bottom-right order')
    parser.add_argument("--match-lighting", action="store_true", help="Conservatively match panel luminance to target wall")
    args = parser.parse_args()

    outputs = run_perspective_mod_placement(
        args.base,
        args.panel,
        args.out,
        parse_points(args.plane, 4),
        args.grid_cols,
        args.grid_rows,
        parse_points(args.mod_box, 2),
        args.match_lighting,
    )
    print(SD_HANDOFF_TEXT.format(image=outputs["sd_ready_composite"], mask=outputs["edge_refine_mask"]))


if __name__ == "__main__":
    main()
