from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .utils import load_image_rgba, load_image_rgb, save_rgb, select_detection, select_middle_floor_indicator_display

LOGGER = logging.getLogger(__name__)

OPERATING_PANEL_CLASS = "tall stainless steel elevator operating panel with round buttons"
LANDING_CALL_INDICATOR_CLASS = "landing_call_indicator"
VALID_MOD_PANEL_TARGETS = {OPERATING_PANEL_CLASS, "elevator call button panel"}
INVALID_MOD_PANEL_TARGETS = {
    LANDING_CALL_INDICATOR_CLASS,
    "accessibility_control_panel",
    "wheelchair button",
    "wheelchair_indicator",
    "weight_limit_sign",
    "floor_indicator_display",
    "elevator_door",
    "elevator_cabin",
    "threshold_plate",
    "handrail",
    "security_camera",
    "emergency_phone",
}


def insert_mod_panel(background_path: str | Path, mod_path: str | Path, detections: dict[str, Any], geometry: dict[str, Any], cfg: dict[str, Any], out_path: str | Path, mask_out: str | Path, removal_mask: np.ndarray | None = None) -> np.ndarray:
    bg = load_image_rgb(background_path)
    mod = close_internal_alpha_holes(load_image_rgba(mod_path))
    height, width = bg.shape[:2]
    target_box, placement_reason = _target_box(width, height, detections, cfg, mod.shape[:2], removal_mask, bg)
    LOGGER.info("[PLACE] Final component placement: %s reason=%s", target_box, placement_reason)
    mod = match_mod_appearance_to_cleaned_region(mod, bg, target_box)
    warped = (
        _warp_long_panel_to_exact_box(mod, target_box, bg.shape[:2])
        if _is_long_panel_track_case(cfg, mod.shape[:2])
        else _warp_mod_to_scene(mod, target_box, geometry, bg.shape[:2], cfg, bg)
    )

    fg = warped[:, :, :3]
    alpha = refine_alpha(warped[:, :, 3].astype(np.float32) / 255.0)
    alpha, mask_debug = validate_or_rebuild_alpha(alpha, target_box, cfg, "harmonization")
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
    mask = (alpha > 0.03).astype(np.uint8) * 255
    cv2.imwrite(str(mask_out), mask)
    write_component_placement_debug(cfg, target_box, placement_reason, detections, bg, mask_debug)
    return final


def preselect_mod_panel_placement(
    image_rgb: np.ndarray,
    mod_path: str | Path,
    detections: dict[str, Any],
    cfg: dict[str, Any],
    removal_mask: np.ndarray | None = None,
) -> list[int] | None:
    manual_box = cfg.get("insertion", {}).get("manual_box_xyxy")
    if manual_box:
        box = [int(v) for v in manual_box]
        cfg.setdefault("_placement_debug", {})
        cfg["_placement_debug"].update(
            {
                "placement_preselected": True,
                "preselected_reason": "manual_box_xyxy",
                "insert_bbox": box,
                "inpaint_bbox": box,
                "aligned_artifact_cleanup": {"status": "manual_box_xyxy"},
            }
        )
        return box
    requested_type = cfg.get("_requested_component_type")
    if requested_type not in {"elevator_ceiling", "elevator_door"} and not _is_elevator_mod_panel_request(cfg, mod_path):
        return None
    if requested_type not in {"elevator_ceiling", "elevator_door"}:
        cfg["_requested_component_type"] = "elevator_mod_panel"
    mod = close_internal_alpha_holes(load_image_rgba(mod_path))
    height, width = image_rgb.shape[:2]
    target_box, reason = _target_box(width, height, detections, cfg, mod.shape[:2], removal_mask, image_rgb)
    preserve_floor_indicator = bool(cfg.get("removal", {}).get("preserve_floor_indicator_display", True))
    if cfg.get("_requested_component_type") == "elevator_mod_panel" and not preserve_floor_indicator:
        inpaint_box, cleanup_debug = extend_inpaint_bbox_for_aligned_panel_artifacts(target_box, detections.get("detections", []), width, height)
    else:
        inpaint_box, cleanup_debug = target_box, {
            "status": "preserved_floor_indicator_display" if cfg.get("_requested_component_type") == "elevator_mod_panel" else "not_needed"
        }
    cfg.setdefault("_placement_debug", {})
    cfg["_placement_debug"].update(
        {
            "placement_preselected": True,
            "preselected_reason": reason,
            "insert_bbox": target_box,
            "inpaint_bbox": inpaint_box,
            "aligned_artifact_cleanup": cleanup_debug,
        }
    )
    return inpaint_box


def localized_mask_from_bbox(image_shape: tuple[int, int] | tuple[int, int, int], bbox: list[int], pad: int = 0) -> np.ndarray:
    height, width = image_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
    x2, y2 = min(width, x2 + pad), min(height, y2 + pad)
    if x2 <= x1 or y2 <= y1:
        raise RuntimeError(f"Invalid localized inpaint bbox: {bbox}")
    mask[y1:y2, x1:x2] = 255
    return mask


def _target_box(width: int, height: int, detections: dict[str, Any], cfg: dict[str, Any], mod_hw: tuple[int, int] | None = None, removal_mask: np.ndarray | None = None, image: np.ndarray | None = None) -> tuple[list[int], str]:
    ins = cfg["insertion"]
    if ins.get("manual_box_xyxy"):
        return [int(v) for v in ins["manual_box_xyxy"]], "manual_box_xyxy"
    if cfg.get("_placement_debug", {}).get("placement_preselected"):
        selected = cfg.get("_placement_debug", {}).get("insert_bbox") or cfg.get("_placement_debug", {}).get("inpaint_bbox")
        if selected:
            return [int(v) for v in selected], str(cfg["_placement_debug"].get("preselected_reason", "preselected_target"))
    elevator_roi = selected_elevator_roi_for_placement(width, height, detections, cfg, image) if image is not None else None
    credible_elevator_roi = elevator_roi if has_credible_elevator_detection(detections, width, height) else None
    rejected_components: list[dict[str, Any]] = []
    if ins["placement"] == "detection":
        requested_type = cfg.get("_requested_component_type")
        LOGGER.info("[TARGET] Requested component: %s", requested_type or "auto")
        if requested_type == "elevator_ceiling":
            box, reason = select_ceiling_target_box(detections["detections"], width, height)
            cfg["_placement_debug"] = {
                "requested_component_type": requested_type,
                "selected_replacement_target_type": "elevator_ceiling",
                "selected_replacement_target_bbox": box,
                "inpaint_bbox": box,
                "scale_to_target_bbox": True,
                "placement_mode": "existing_ceiling",
            }
            return box, reason
        if requested_type == "elevator_door":
            det = _largest_detection_of_type(detections["detections"], {"elevator_door"}, width, height, 0.70)
            if det:
                box = padded_box([int(round(v)) for v in det["box_xyxy"]], width, height, int(ins.get("existing_panel_padding_px", 2)))
                cfg["_placement_debug"] = {
                    "requested_component_type": requested_type,
                    "selected_replacement_target_type": "elevator_door",
                    "selected_replacement_target_bbox": box,
                    "inpaint_bbox": box,
                    "scale_to_target_bbox": True,
                    "placement_mode": "existing_component",
                }
                return box, "detected_elevator_door"
        is_mod_panel_request = requested_type == "elevator_mod_panel" or (
            not requested_type and _needs_contextual_panel_fallback(ins.get("target_keywords", []))
        )
        if is_mod_panel_request:
            det = select_mod_panel_target(detections["detections"], height, width, credible_elevator_roi, rejected_components)
            cfg["_placement_debug"] = {"rejected_component_detections": rejected_components}
            if det:
                detection_box = [int(round(v)) for v in det["box_xyxy"]]
                panel_box, expansion_debug = expand_control_panel_bbox(image, detections["detections"], detection_box, width, height, det.get("normalized_component_type"))
                target_box = padded_box(panel_box, width, height, int(ins.get("existing_panel_padding_px", 4)))
                target_box, target_clamp_debug = clamp_existing_panel_target_box(
                    target_box,
                    width,
                    height,
                    cfg,
                    max_ratio_override=0.55 if det.get("normalized_component_type") == OPERATING_PANEL_CLASS else None,
                )
                cfg["_placement_debug"].update(
                    {
                        "requested_component_type": "elevator_mod_panel",
                        "valid_replacement_targets": valid_target_debug(detections["detections"]),
                        "selected_replacement_target_type": det.get("normalized_component_type"),
                        "selected_replacement_target_source": det.get("source"),
                        "selected_replacement_target_bbox": detection_box,
                        "target_panel_bbox": panel_box,
                        "target_panel_expansion": expansion_debug,
                        "target_padding_px": int(ins.get("existing_panel_padding_px", 4)),
                        "target_box_clamp": target_clamp_debug,
                        "inpaint_bbox": target_box,
                        "scale_to_target_bbox": True,
                        "placement_mode": "existing_panel",
                    }
                )
                LOGGER.info("[TARGET] Selected existing panel target: %s bbox=%s", det.get("normalized_component_type"), detection_box)
                return target_box, f"detected_{det.get('normalized_component_type')}"

        if is_mod_panel_request:
            if elevator_roi is None:
                raise RuntimeError("No valid elevator_mod_panel placement target: no existing panel and no elevator door detected")
            LOGGER.info("[PLACE] Existing panel not detected; placing elevator_mod_panel on adjacent wall")
            box = adjacent_wall_panel_box(width, height, detections, cfg, mod_hw, image, elevator_roi)
            cfg["_placement_debug"].update(
                {
                    "requested_component_type": "elevator_mod_panel",
                    "valid_replacement_targets": valid_target_debug(detections["detections"]),
                    "selected_replacement_target_type": "synthesized_adjacent_wall",
                    "selected_replacement_target_bbox": None,
                    "inpaint_bbox": box,
                    "scale_to_target_bbox": True,
                    "placement_mode": "synthesized_adjacent_wall",
                }
            )
            LOGGER.info("[TARGET] No valid panel detected; synthesizing adjacent-wall placement")
            return box, "adjacent_wall_next_to_selected_elevator_roi"

        det = select_valid_component_detection(detections["detections"], ins["target_keywords"], height, width, mod_hw, elevator_roi, rejected_components)
        cfg["_placement_debug"] = {"rejected_component_detections": rejected_components}
        if det:
            detection_box = [int(round(v)) for v in det["box_xyxy"]]
            erased_box = _select_erased_long_panel_box(removal_mask, detection_box, cfg, mod_hw)
            target_box = erased_box or detection_box
            cfg["_placement_debug"].update(
                {
                    "requested_component_type": cfg.get("_requested_component_type"),
                    "selected_replacement_target_type": det.get("normalized_component_type"),
                    "selected_replacement_target_bbox": detection_box,
                    "inpaint_bbox": target_box,
                    "scale_to_target_bbox": True,
                    "placement_mode": "existing_component",
                }
            )
            return target_box, f"detected_{det.get('normalized_component_type') or det.get('phrase')}"
    rx1, ry1, rx2, ry2 = ins["fallback_box_ratio_xyxy"]
    return [int(width * rx1), int(height * ry1), int(width * rx2), int(height * ry2)], "configured_fallback_ratio"


def _needs_contextual_panel_fallback(keywords: list[str]) -> bool:
    joined = " ".join(k.lower() for k in keywords)
    return any(term in joined for term in ("button", "panel", "control", "mod"))


def select_ceiling_target_box(detections: list[dict[str, Any]], width: int, height: int) -> tuple[list[int], str]:
    ceiling = _largest_detection_of_type(detections, {"elevator_ceiling"}, width, height, 0.35)
    if ceiling:
        return padded_box([int(round(v)) for v in ceiling["box_xyxy"]], width, height, 4), "detected_elevator_ceiling"

    door = _largest_detection_of_type(detections, {"elevator_door"}, width, height, 0.70)
    if door:
        x1, y1, x2, y2 = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
        door_w, door_h = max(1.0, x2 - x1), max(1.0, y2 - y1)
        band_h = max(height * 0.10, door_h * 0.16)
        box = [
            int(np.clip(x1 - door_w * 0.12, 0, width - 1)),
            int(np.clip(y1 - band_h, 0, height - 2)),
            int(np.clip(x2 + door_w * 0.12, 1, width)),
            int(np.clip(y1 + door_h * 0.04, 1, height)),
        ]
        if box[2] - box[0] > 8 and box[3] - box[1] > 8:
            return box, "synthesized_ceiling_above_elevator_door"

    cabin = _largest_detection_of_type(detections, {"elevator_cabin"}, width, height, 0.75)
    if cabin:
        x1, y1, x2, y2 = [float(v) for v in cabin.get("box_xyxy", [0, 0, 0, 0])]
        box = [int(x1), int(y1), int(x2), int(y1 + max(12.0, (y2 - y1) * 0.18))]
        return padded_box(box, width, height, 2), "synthesized_ceiling_from_elevator_interior"

    return [int(width * 0.14), int(height * 0.04), int(width * 0.86), int(height * 0.20)], "fallback_top_ceiling_band"


def _largest_detection_of_type(
    detections: list[dict[str, Any]],
    normalized_types: set[str],
    width: int,
    height: int,
    max_area_ratio: float,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for det in detections:
        if str(det.get("normalized_component_type") or "").lower() not in normalized_types:
            continue
        if det.get("source") == "image_structure_fallback":
            continue
        if float(det.get("score", 0.0)) < 0.20:
            continue
        area_ratio = _box_area(det.get("box_xyxy", [])) / max(width * height, 1)
        if 0.0005 <= area_ratio <= max_area_ratio:
            candidates.append(det)
    return max(candidates, key=lambda item: _box_area(item.get("box_xyxy", []))) if candidates else None


def _is_elevator_mod_panel_request(cfg: dict[str, Any], mod_path: str | Path) -> bool:
    requested_type = cfg.get("_requested_component_type")
    if requested_type:
        return requested_type == "elevator_mod_panel"
    stem = Path(mod_path).stem.lower()
    if "mod" not in stem or _is_long_panel_track_case(cfg, (999, 1)):
        return False
    return True


def select_mod_panel_target(
    detections: list[dict[str, Any]],
    height: int,
    width: int,
    elevator_roi: list[int] | None,
    rejected: list[dict[str, Any]],
) -> dict[str, Any] | None:
    valid: list[dict[str, Any]] = []
    for det in detections:
        norm = str(det.get("normalized_component_type") or "").lower()
        phrase = str(det.get("phrase") or "").lower()
        reason = invalid_mod_panel_target_reason(det, width, height, elevator_roi)
        if reason:
            if norm in INVALID_MOD_PANEL_TARGETS or any(term in phrase for term in ("weight", "capacity", "indicator", "door", "cabin", "handrail", "camera", "threshold")):
                LOGGER.info("[TARGET] Rejected target: %s reason=%s", norm or phrase, reason)
                rejected.append(rejection_debug(det, reason))
            continue
        valid.append(det)
    if not valid:
        return None
    panels = [det for det in valid if str(det.get("normalized_component_type")) == OPERATING_PANEL_CLASS]
    if panels:
        return max(panels, key=lambda det: _box_area(det.get("box_xyxy", [0, 0, 0, 0])) * (0.70 + float(det.get("score", 0.0))))
    priority = {OPERATING_PANEL_CLASS: 0, "elevator call button panel": 1}
    return min(valid, key=lambda det: (priority.get(str(det.get("normalized_component_type")), 9), -float(det.get("score", 0.0))))


def invalid_mod_panel_target_reason(det: dict[str, Any], width: int, height: int, elevator_roi: list[int] | None) -> str | None:
    norm = str(det.get("normalized_component_type") or "").lower()
    phrase = str(det.get("phrase") or "").lower()
    if norm in INVALID_MOD_PANEL_TARGETS:
        return f"not valid for elevator_mod_panel"
    if norm not in VALID_MOD_PANEL_TARGETS:
        return "not a valid elevator_mod_panel target"
    x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
    bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
    area_ratio = (bw * bh) / max(width * height, 1)
    max_area_ratio = 0.55 if norm == OPERATING_PANEL_CLASS else 0.10
    if area_ratio > max_area_ratio:
        return "panel candidate too large"
    max_aspect = 12.0 if norm == OPERATING_PANEL_CLASS else 8.5
    if bh / bw > max_aspect or bh / bw < 0.35:
        return "invalid panel aspect"
    if norm != OPERATING_PANEL_CLASS and elevator_roi and box_overlap_fraction([int(x1), int(y1), int(x2), int(y2)], elevator_roi) > 0.35:
        return "inside elevator opening"
    return None


def rejection_debug(det: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "bbox": det.get("box_xyxy"),
        "phrase": det.get("phrase"),
        "raw_detection_label": det.get("raw_detection_label", det.get("phrase")),
        "source_prompt": det.get("source_prompt", det.get("phrase")),
        "normalized_component_type": det.get("normalized_component_type"),
        "score": det.get("score"),
        "reason": reason,
    }


def valid_target_debug(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [rejection_debug(det, "valid") for det in detections if str(det.get("normalized_component_type") or "").lower() in VALID_MOD_PANEL_TARGETS]


def padded_box(box: list[int], width: int, height: int, pad: int) -> list[int]:
    x1, y1, x2, y2 = box
    return [max(0, x1 - pad), max(0, y1 - pad), min(width, x2 + pad), min(height, y2 + pad)]


def extend_inpaint_bbox_for_aligned_panel_artifacts(
    target_box: list[int],
    detections: list[dict[str, Any]],
    width: int,
    height: int,
) -> tuple[list[int], dict[str, Any]]:
    x1, y1, x2, y2 = [int(v) for v in target_box]
    target_w, target_h = max(1, x2 - x1), max(1, y2 - y1)
    cleanup_box = [x1, y1, x2, y2]
    included: list[dict[str, Any]] = []
    for det in detections:
        norm = str(det.get("normalized_component_type") or "").lower()
        phrase = str(det.get("phrase") or "").lower()
        if norm not in {"floor_indicator_display"} and not any(term in phrase for term in ("indicator", "display")):
            continue
        bx1, by1, bx2, by2 = [int(round(v)) for v in det.get("box_xyxy", [0, 0, 0, 0])]
        bw, bh = max(1, bx2 - bx1), max(1, by2 - by1)
        horizontal_overlap = max(0, min(x2, bx2) - max(x1, bx1)) / max(1, min(target_w, bw))
        vertical_gap = y1 - by2
        if horizontal_overlap >= 0.45 and -int(target_h * 0.22) <= vertical_gap <= int(target_h * 0.55) and bh <= target_h * 1.20:
            cleanup_box = [min(cleanup_box[0], bx1), min(cleanup_box[1], by1), max(cleanup_box[2], bx2), max(cleanup_box[3], by2)]
            included.append(
                {
                    "bbox": [bx1, by1, bx2, by2],
                    "normalized_component_type": norm,
                    "phrase": det.get("phrase"),
                    "reason": "aligned_display_artifact_above_panel",
                }
            )
    if not included:
        return target_box, {"status": "not_needed"}
    cleanup_box = padded_box(cleanup_box, width, height, max(2, int(min(target_w, target_h) * 0.08)))
    LOGGER.info("[INPAINT] Extending cleanup bbox for aligned old panel artifacts: %s", cleanup_box)
    return cleanup_box, {"status": "extended", "included_artifacts": included, "cleanup_bbox": cleanup_box}


def _box_area(box: Any) -> float:
    try:
        x1, y1, x2, y2 = [float(v) for v in box]
    except Exception:
        return 0.0
    return max(1.0, x2 - x1) * max(1.0, y2 - y1)


def clamp_existing_panel_target_box(
    box: list[int],
    width: int,
    height: int,
    cfg: dict[str, Any],
    max_ratio_override: float | None = None,
) -> tuple[list[int], dict[str, Any]]:
    x1, y1, x2, y2 = [int(v) for v in box]
    box_w, box_h = max(1, x2 - x1), max(1, y2 - y1)
    image_area = max(1, width * height)
    area_ratio = (box_w * box_h) / image_area
    max_ratio = float(
        max_ratio_override
        if max_ratio_override is not None
        else cfg["insertion"].get("max_existing_panel_target_area_ratio", cfg["insertion"].get("max_insert_area_ratio", 0.12))
    )
    if area_ratio <= max_ratio:
        return [x1, y1, x2, y2], {"status": "not_clamped", "area_ratio": float(area_ratio), "max_area_ratio": max_ratio}

    shrink = (max_ratio / max(area_ratio, 1e-6)) ** 0.5
    new_w = max(2, int(round(box_w * shrink)))
    new_h = max(2, int(round(box_h * shrink)))
    cx = (x1 + x2) * 0.5
    cy = (y1 + y2) * 0.5
    nx1 = int(round(cx - new_w * 0.5))
    ny1 = int(round(cy - new_h * 0.5))
    nx1 = int(np.clip(nx1, 0, max(0, width - new_w)))
    ny1 = int(np.clip(ny1, 0, max(0, height - new_h)))
    clamped = [nx1, ny1, min(width, nx1 + new_w), min(height, ny1 + new_h)]
    clamped_ratio = ((clamped[2] - clamped[0]) * (clamped[3] - clamped[1])) / image_area
    LOGGER.info("[TARGET] Clamped oversized panel target area %.3f -> %.3f", area_ratio, clamped_ratio)
    return clamped, {
        "status": "clamped",
        "reason": "max_existing_panel_target_area_ratio",
        "original_bbox": [x1, y1, x2, y2],
        "original_area_ratio": float(area_ratio),
        "clamped_bbox": clamped,
        "clamped_area_ratio": float(clamped_ratio),
        "max_area_ratio": max_ratio,
    }


def expand_control_panel_bbox(
    image_rgb: np.ndarray | None,
    detections: list[dict[str, Any]],
    seed_box: list[int],
    width: int,
    height: int,
    seed_type: str | None = None,
) -> tuple[list[int], dict[str, Any]]:
    panel_types = {OPERATING_PANEL_CLASS, "elevator call button panel"}
    x1, y1, x2, y2 = seed_box
    seed_w = max(1, x2 - x1)
    seed_cx = (x1 + x2) * 0.5
    members: list[dict[str, Any]] = []
    explicit_members: list[list[int]] = []
    deferred_cop_members: list[tuple[list[int], dict[str, Any]]] = []
    union = [x1, y1, x2, y2]
    supporting_members = 0
    for det in detections:
        norm = str(det.get("normalized_component_type") or "").lower()
        phrase = str(det.get("phrase") or "").lower()
        if norm in INVALID_MOD_PANEL_TARGETS:
            continue
        if norm not in panel_types:
            continue
        box = [int(round(v)) for v in det.get("box_xyxy", [0, 0, 0, 0])]
        bx1, by1, bx2, by2 = box
        bw, bh = max(1, bx2 - bx1), max(1, by2 - by1)
        box_area_ratio = (bw * bh) / max(width * height, 1)
        if box_area_ratio > 0.10:
            continue
        bcx = (bx1 + bx2) * 0.5
        horizontal_overlap = max(0, min(x2, bx2) - max(x1, bx1)) / max(1, min(seed_w, bw))
        same_column = horizontal_overlap >= 0.28 or abs(bcx - seed_cx) <= max(seed_w * 0.75, width * 0.055)
        vertical_gap = max(0, max(y1, by1) - min(y2, by2))
        same_physical_panel = vertical_gap <= max(height * 0.035, seed_box_height(seed_box) * 0.85) or horizontal_overlap >= 0.70
        if seed_type and norm != str(seed_type).lower():
            continue
        if same_column and vertical_gap <= height * 0.26:
            member_debug = {
                "bbox": box,
                "normalized_component_type": norm,
                "phrase": det.get("phrase"),
                "score": det.get("score"),
            }
            union = [min(union[0], bx1), min(union[1], by1), max(union[2], bx2), max(union[3], by2)]
            explicit_members.append(box)
            if box != seed_box:
                supporting_members += 1
            members.append(member_debug)

    explicit_union = union.copy()
    explicit_area = _box_area(explicit_union)
    for box, member_debug in deferred_cop_members:
        if explicit_members and _box_area(box) > explicit_area * 2.25:
            members.append({**member_debug, "excluded_from_expansion_reason": "raw_cop_box_larger_than_explicit_button_panel"})
            continue
        bx1, by1, bx2, by2 = box
        union = [min(union[0], bx1), min(union[1], by1), max(union[2], bx2), max(union[3], by2)]
        if box != seed_box:
            supporting_members += 1
        members.append(member_debug)

    member_union = union.copy()
    if supporting_members > 0:
        grown = grow_to_visible_panel_plate(image_rgb, union, width, height)
        union, expansion_limit_debug = bound_panel_expansion_to_members(grown, member_union, width, height)
    else:
        union = padded_box(union, width, height, max(3, int(width * 0.01)))
        expansion_limit_debug = {"status": "not_needed"}
    return union, {"seed_bbox": seed_box, "seed_type": seed_type, "member_detections": members, "member_union_bbox": member_union, "expanded_bbox": union, "expansion_limit": expansion_limit_debug}


def seed_box_height(box: list[int]) -> int:
    return max(1, int(box[3]) - int(box[1]))


def bound_panel_expansion_to_members(grown_box: list[int], member_union: list[int], width: int, height: int) -> tuple[list[int], dict[str, Any]]:
    gx1, gy1, gx2, gy2 = [int(v) for v in grown_box]
    ux1, uy1, ux2, uy2 = [int(v) for v in member_union]
    grown_w, grown_h = max(1, gx2 - gx1), max(1, gy2 - gy1)
    member_w, member_h = max(1, ux2 - ux1), max(1, uy2 - uy1)
    grown_area_ratio = (grown_w * grown_h) / max(width * height, 1)
    max_area_ratio = 0.10
    max_w = max(member_w + int(width * 0.06), int(member_w * 1.65))
    max_h = max(member_h + int(height * 0.10), int(member_h * 1.55))
    too_large = grown_area_ratio > max_area_ratio or grown_w > max_w or grown_h > max_h
    if not too_large:
        return [gx1, gy1, gx2, gy2], {"status": "not_clamped", "area_ratio": float(grown_area_ratio)}

    pad_x = max(4, int(min(width * 0.018, member_w * 0.35)))
    pad_y = max(6, int(min(height * 0.030, member_h * 0.22)))
    bounded = padded_box([ux1, uy1, ux2, uy2], width, height, max(pad_x, pad_y))
    LOGGER.info("[TARGET] Rejected over-expanded panel plate %s; using bounded member union %s", grown_box, bounded)
    return bounded, {
        "status": "clamped",
        "reason": "grown_panel_plate_too_large_or_crossed_wall",
        "grown_bbox": [gx1, gy1, gx2, gy2],
        "grown_area_ratio": float(grown_area_ratio),
        "member_union_bbox": [ux1, uy1, ux2, uy2],
        "bounded_bbox": bounded,
    }


def grow_to_visible_panel_plate(image_rgb: np.ndarray | None, box: list[int], width: int, height: int) -> list[int]:
    if image_rgb is None:
        return padded_box(box, width, height, max(3, int(width * 0.008)))
    x1, y1, x2, y2 = box
    pad_x = max(4, int(width * 0.012))
    pad_y = max(6, int(height * 0.025))
    x1, y1, x2, y2 = padded_box([x1, y1, x2, y2], width, height, 0)
    search_x1, search_x2 = max(0, x1 - pad_x * 4), min(width, x2 + pad_x * 4)
    search_y1, search_y2 = max(0, y1 - pad_y * 4), min(height, y2 + pad_y * 4)
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    roi = gray[search_y1:search_y2, search_x1:search_x2]
    if roi.size == 0:
        return padded_box([x1, y1, x2, y2], width, height, max(pad_x, 3))
    edges = cv2.Canny(cv2.GaussianBlur(roi, (5, 5), 0), 35, 110)
    col_energy = edges.mean(axis=0)
    row_energy = edges.mean(axis=1)
    local_x1, local_x2 = x1 - search_x1, x2 - search_x1
    local_y1, local_y2 = y1 - search_y1, y2 - search_y1

    left_candidates = np.where(col_energy[: max(local_x1, 1)] > max(6.0, np.percentile(col_energy, 72)))[0]
    right_candidates = np.where(col_energy[min(local_x2, len(col_energy) - 1) :] > max(6.0, np.percentile(col_energy, 72)))[0]
    top_candidates = np.where(row_energy[: max(local_y1, 1)] > max(6.0, np.percentile(row_energy, 72)))[0]
    bottom_candidates = np.where(row_energy[min(local_y2, len(row_energy) - 1) :] > max(6.0, np.percentile(row_energy, 72)))[0]

    if len(left_candidates):
        x1 = search_x1 + int(left_candidates[-1])
    if len(right_candidates):
        x2 = search_x1 + min(local_x2, len(col_energy) - 1) + int(right_candidates[0])
    if len(top_candidates):
        y1 = search_y1 + int(top_candidates[-1])
    if len(bottom_candidates):
        y2 = search_y1 + min(local_y2, len(row_energy) - 1) + int(bottom_candidates[0])
    return padded_box([x1, y1, x2, y2], width, height, max(2, min(pad_x, pad_y)))


def adjacent_wall_panel_box(
    width: int,
    height: int,
    detections: dict[str, Any],
    cfg: dict[str, Any],
    mod_hw: tuple[int, int] | None,
    image: np.ndarray | None,
    elevator_roi: list[int] | None = None,
) -> list[int]:
    roi = elevator_roi
    if roi is None:
        roi = [int(width * 0.30), int(height * 0.18), int(width * 0.70), int(height * 0.90)]
    x1, y1, x2, y2 = roi
    wall_left = x1
    wall_right = width - x2
    side = "left" if wall_left >= wall_right else "right"
    mh, mw = mod_hw or (180, 70)
    target_h = int(np.clip((y2 - y1) * 0.22, height * 0.12, height * 0.24))
    target_w = max(18, int(round(target_h * mw / max(mh, 1))))
    cy = int(np.clip(y1 + (y2 - y1) * 0.48, height * 0.34, height * 0.68))
    min_margin = max(18, int(width * float(cfg.get("insertion", {}).get("adjacent_wall_min_margin_ratio", 0.055))))
    gap = max(min_margin, int(width * 0.035))
    strip_pad = max(8, min_margin // 2)
    if side == "left":
        usable_w = max(0, x1 - gap)
        px1 = max(0, (usable_w - target_w) // 2) if usable_w < target_w + strip_pad * 2 else max(strip_pad, x1 - gap - target_w)
        px2 = min(x1 - gap, px1 + target_w)
    else:
        usable_w = max(0, width - (x2 + gap))
        px1 = min(width - target_w, x2 + gap + max(0, (usable_w - target_w) // 2)) if usable_w < target_w + strip_pad * 2 else min(width - target_w - strip_pad, x2 + gap)
        px2 = min(width, px1 + target_w)
    py1 = int(np.clip(cy - target_h // 2, max(0, y1 + int((y2 - y1) * 0.12)), min(height - target_h, y2 - target_h)))
    py2 = min(height, py1 + target_h)
    return [int(px1), int(py1), int(px2), int(py2)]


def selected_elevator_roi_for_placement(width: int, height: int, detections: dict[str, Any], cfg: dict[str, Any], image_rgb: np.ndarray) -> list[int] | None:
    from .video import select_best_elevator_roi

    roi_image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    roi, _ = select_best_elevator_roi(roi_image, detections, None, {}, cfg)
    if roi is None:
        return None
    x1, y1, x2, y2 = roi
    return [int(np.clip(x1, 0, width - 2)), int(np.clip(y1, 0, height - 2)), int(np.clip(x2, x1 + 2, width)), int(np.clip(y2, y1 + 2, height))]


def has_credible_elevator_detection(detections: dict[str, Any], width: int, height: int) -> bool:
    for det in detections.get("detections", []):
        norm = str(det.get("normalized_component_type") or "").lower()
        if norm not in {"elevator_door", "elevator_cabin"} or det.get("source") == "image_structure_fallback":
            continue
        if float(det.get("score", 0.0)) < 0.28:
            continue
        x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
        bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
        area_ratio = (bw * bh) / max(width * height, 1)
        if 0.03 <= area_ratio <= 0.65 and bh / bw >= 1.05:
            return True
    return False


def write_component_placement_debug(
    cfg: dict[str, Any],
    bbox: list[int],
    reason: str,
    detections: dict[str, Any],
    image_rgb: np.ndarray | None = None,
    mask_debug: dict[str, Any] | None = None,
) -> None:
    run_dir = cfg.get("run_dir")
    if not run_dir:
        return
    path = Path(run_dir) / "component_placement_debug.json"
    placement_debug = cfg.get("_placement_debug", {})
    payload = {
        "requested_component_type": placement_debug.get("requested_component_type"),
        "valid_replacement_targets": placement_debug.get("valid_replacement_targets", []),
        "rejected_replacement_targets": placement_debug.get("rejected_component_detections", []),
        "selected_replacement_target_type": placement_debug.get("selected_replacement_target_type"),
        "selected_replacement_target_source": placement_debug.get("selected_replacement_target_source"),
        "selected_replacement_target_bbox": placement_debug.get("selected_replacement_target_bbox"),
        "target_panel_bbox": placement_debug.get("target_panel_bbox"),
        "placement_mode": placement_debug.get("placement_mode"),
        "target_padding_px": placement_debug.get("target_padding_px"),
        "inpaint_bbox": placement_debug.get("inpaint_bbox") or bbox,
        "inpaint_completed": True,
        "final_insertion_bbox": placement_debug.get("final_insertion_bbox") or bbox,
        "insertion_scale_factor": placement_debug.get("insertion_scale_factor"),
        "insertion_size_validation_status": placement_debug.get("insertion_size_validation_status"),
        "homography_destination_quad": placement_debug.get("homography_destination_quad"),
        "homography_alignment": placement_debug.get("homography_alignment"),
        "final_component_placement": {"bbox": placement_debug.get("final_insertion_bbox") or bbox, "reason": reason},
        "rejected_component_detections": placement_debug.get("rejected_component_detections", []),
        "harmonization_mask_bbox": (mask_debug or {}).get("harmonization_mask_bbox"),
        "harmonization_mask_white_area_ratio": (mask_debug or {}).get("harmonization_mask_white_area_ratio"),
        "harmonization_mask_validation_status": (mask_debug or {}).get("harmonization_mask_validation_status"),
        "mask_rebuilt_reason": (mask_debug or {}).get("mask_rebuilt_reason"),
        "component_detections": [
            {
                "bbox": det.get("box_xyxy"),
                "phrase": det.get("phrase"),
                "raw_detection_label": det.get("raw_detection_label", det.get("phrase")),
                "source_prompt": det.get("source_prompt", det.get("phrase")),
                "normalized_component_type": det.get("normalized_component_type"),
                "score": det.get("score"),
            }
            for det in detections.get("detections", [])
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if image_rgb is not None:
        overlay = cv2.cvtColor(image_rgb.copy(), cv2.COLOR_RGB2BGR)
        x1, y1, x2, y2 = [int(v) for v in bbox]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 220, 255), 3)
        cv2.imwrite(str(Path(run_dir) / "final_component_placement.png"), overlay)
        target_overlay = cv2.cvtColor(image_rgb.copy(), cv2.COLOR_RGB2BGR)
        for item in placement_debug.get("valid_replacement_targets", []):
            if item.get("bbox"):
                tx1, ty1, tx2, ty2 = [int(round(v)) for v in item["bbox"]]
                cv2.rectangle(target_overlay, (tx1, ty1), (tx2, ty2), (0, 220, 0), 2)
        for item in placement_debug.get("rejected_component_detections", []):
            if item.get("bbox"):
                rx1, ry1, rx2, ry2 = [int(round(v)) for v in item["bbox"]]
                cv2.rectangle(target_overlay, (rx1, ry1), (rx2, ry2), (0, 0, 255), 2)
        cv2.imwrite(str(Path(run_dir) / "valid_vs_rejected_replacement_targets.png"), target_overlay)


def select_valid_component_detection(
    detections: list[dict[str, Any]],
    keywords: list[str],
    height: int,
    width: int,
    mod_hw: tuple[int, int] | None,
    elevator_roi: list[int] | None = None,
    rejected: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    ordered = [
        _select_long_panel_detection(detections, keywords, mod_hw),
        select_middle_floor_indicator_display(detections, keywords, height),
        select_detection(detections, keywords),
    ]
    candidates = [det for det in ordered if det is not None]
    if not candidates:
        return None
    valid = []
    for det in candidates:
        valid_det, reason = _valid_component_detection(det, keywords, width, height, elevator_roi)
        if valid_det:
            valid.append(det)
        elif rejected is not None:
            rejected.append(
                {
                    "bbox": det.get("box_xyxy"),
                    "phrase": det.get("phrase"),
                    "normalized_component_type": det.get("normalized_component_type"),
                    "reason": reason,
                }
            )
    return max(valid, key=lambda det: float(det.get("score", 0.0))) if valid else None


def _valid_component_detection(det: dict[str, Any], keywords: list[str], width: int, height: int, elevator_roi: list[int] | None = None) -> tuple[bool, str]:
    phrase = str(det.get("phrase", "")).lower()
    x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
    bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
    area_ratio = (bw * bh) / max(width * height, 1)
    cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    target_text = " ".join(k.lower() for k in keywords)

    if any(term in target_text for term in ("landing call", "hall call", "lci")):
        norm = str(det.get("normalized_component_type") or "").lower()
        if norm in {OPERATING_PANEL_CLASS, "floor_indicator_display", "weight_limit_sign"}:
            return False, "not_landing_call_indicator"
        if any(term in phrase for term in ("floor", "display", "capacity", "weight", "car operating panel")):
            return False, "not_landing_call_indicator"
        aspect = bh / bw
        near_side_wall = cx < width * 0.45 or cx > width * 0.55
        return (
            norm in {LANDING_CALL_INDICATOR_CLASS, "elevator call button panel", "accessibility_control_panel", "wheelchair button"}
            and 0.00004 <= area_ratio <= 0.10
            and 0.35 <= aspect <= 5.5
            and near_side_wall
        ), "invalid_landing_call_indicator_geometry"
    if "floor indicator" in target_text or "display" in target_text:
        return (cy < height * 0.42 and area_ratio < 0.08 and bw > 6 and bh > 4), "invalid_floor_indicator_geometry"
    if "button panel" in target_text or "elevator panel" in target_text or "call button" in target_text:
        if "mod panel" in phrase or "panel" == phrase:
            return False, "ambiguous_panel_label"
        if det.get("normalized_component_type") == "weight_limit_sign" or any(term in phrase for term in ("weight", "capacity", "limit")):
            return False, "sign_not_external_control_panel"
        if elevator_roi and det.get("normalized_component_type") not in {"accessibility_control_panel", OPERATING_PANEL_CLASS, "elevator call button panel"}:
            det_box = [int(round(v)) for v in det.get("box_xyxy", [0, 0, 0, 0])]
            if box_overlap_fraction(det_box, elevator_roi) > 0.20:
                LOGGER.info("[PLACE] Rejected detected panel inside elevator opening: %s", det_box)
                return False, "inside elevator opening"
        aspect = bh / bw
        near_side_wall = cx < width * 0.42 or cx > width * 0.58
        return (0.00004 <= area_ratio <= 0.16 and 0.45 <= aspect <= 8.5 and near_side_wall), "invalid_external_panel_geometry"
    if "emergency" in target_text:
        return (area_ratio <= 0.18 and bh / bw <= 5.5), "invalid_emergency_component_geometry"
    return (area_ratio <= 0.25), "invalid_component_area"


def box_overlap_fraction(a: list[int], b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    area = max(1, (ax2 - ax1) * (ay2 - ay1))
    return inter / area


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
        if phrase not in {"door track", "threshold plate", OPERATING_PANEL_CLASS, "elevator call button panel"}:
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


def _warp_mod_to_scene(
    mod: np.ndarray,
    box: list[int],
    geometry: dict[str, Any],
    out_hw: tuple[int, int],
    cfg: dict[str, Any],
    image_rgb: np.ndarray | None = None,
) -> np.ndarray:
    x1, y1, x2, y2 = box
    box_w, box_h = max(1, x2 - x1), max(1, y2 - y1)
    mh, mw = mod.shape[:2]
    mode = cfg["insertion"].get("size_mode", "fit_box")
    placement_debug = cfg.get("_placement_debug", {})
    if placement_debug.get("scale_to_target_bbox"):
        scale = min(box_w / max(mw, 1), box_h / max(mh, 1)) * float(cfg["insertion"].get("target_bbox_fill_ratio", 0.96))
        scale_reason = "fit_detected_or_synthesized_target_bbox"
    elif mode == "preserve_asset":
        scale = 1.0
        scale_reason = "preserve_asset"
    elif mode == "fixed_height":
        scale = float(cfg["insertion"]["fixed_height_px"]) / mh
        scale_reason = "fixed_height"
    else:
        desired_h = box_h * float(cfg["insertion"].get("target_height_multiplier", 1.0))
        scale = desired_h / mh
        scale_reason = "fit_box_height_multiplier"
    scale *= float(cfg["insertion"]["scale_multiplier"])
    native_scene_scale = min(
        out_hw[1] / float(cfg["insertion"].get("native_reference_width_px", 600)),
        out_hw[0] / float(cfg["insertion"].get("native_reference_height_px", 800)),
    )
    native_scene_scale = max(1.0, native_scene_scale)
    if not cfg["insertion"].get("allow_upscale", False) and not placement_debug.get("scale_to_target_bbox"):
        scale = min(scale, native_scene_scale)
    scale, scale_clamp_debug = clamp_insertion_scale(scale, [mw, mh], [x1, y1, x2, y2], out_hw, cfg)
    new_w, new_h = max(1, int(mw * scale)), max(1, int(mh * scale))
    validate_insertion_size([x1, y1, x2, y2], [new_w, new_h], out_hw, cfg)
    placement_debug["insertion_scale_factor"] = float(scale)
    placement_debug["insertion_scale_reason"] = scale_reason
    if scale_clamp_debug:
        placement_debug.update(scale_clamp_debug)
    placement_debug["insertion_size_validation_status"] = "passed"
    mod = cv2.resize(mod, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    px = x1 + (box_w - new_w) // 2
    py = y1 + (box_h - new_h) // 2
    quad, homography_debug = build_wall_aligned_destination_quad(
        image_rgb=image_rgb,
        box=[px, py, px + new_w, py + new_h],
        target_box=[x1, y1, x2, y2],
        geometry=geometry,
        cfg=cfg,
        out_hw=out_hw,
    )
    qx1, qy1 = np.floor(quad.min(axis=0)).astype(int)
    qx2, qy2 = np.ceil(quad.max(axis=0)).astype(int)
    placement_debug["final_insertion_bbox"] = [
        int(np.clip(qx1, 0, out_hw[1] - 1)),
        int(np.clip(qy1, 0, out_hw[0] - 1)),
        int(np.clip(qx2, 1, out_hw[1])),
        int(np.clip(qy2, 1, out_hw[0])),
    ]
    placement_debug["homography_destination_quad"] = quad.round(3).tolist()
    placement_debug["homography_alignment"] = homography_debug
    cfg["_placement_debug"] = placement_debug
    return warp_rgba_to_quad(mod, quad, out_hw)


def build_wall_aligned_destination_quad(
    image_rgb: np.ndarray | None,
    box: list[int],
    target_box: list[int],
    geometry: dict[str, Any],
    cfg: dict[str, Any],
    out_hw: tuple[int, int],
) -> tuple[np.ndarray, dict[str, Any]]:
    image_h, image_w = out_hw
    x1, y1, x2, y2 = [int(v) for v in box]
    width = max(2.0, float(x2 - x1))
    height = max(2.0, float(y2 - y1))
    cx = (x1 + x2) * 0.5
    cy = (y1 + y2) * 0.5
    placement_debug = cfg.get("_placement_debug", {})
    if placement_debug.get("placement_mode") in {"existing_panel", "existing_ceiling"}:
        quad = np.array(
            [
                [x1, y1],
                [x2, y1],
                [x2, y2],
                [x1, y2],
            ],
            dtype=np.float32,
        )
        return quad, {
            "mode": f"{placement_debug.get('placement_mode')}_rectified_homography",
            "reason": "use_detected_or_synthesized_component_bbox_without_wall_shear",
            "vertical_shear": 0.0,
            "horizontal_shear": 0.0,
            "top_shrink": 0.0,
            "side_skew": 0.0,
        }

    orientation = estimate_local_wall_orientation(image_rgb, target_box)
    normal = geometry.get("wall_plane", {}).get("normal") or [0, 0, 1]
    vertical_shear = float(orientation.get("vertical_dx_per_y", 0.0))
    horizontal_shear = float(orientation.get("horizontal_dy_per_x", 0.0))

    # Keep the perspective physically plausible; noisy wall lines should not twist the panel.
    max_shear = float(cfg["insertion"].get("homography_max_local_shear", 0.14))
    vertical_shear = float(np.clip(vertical_shear, -max_shear, max_shear))
    horizontal_shear = float(np.clip(horizontal_shear, -max_shear, max_shear))

    plane_bias = float(np.clip(float(normal[0]) * 0.006, -0.025, 0.025))
    side_skew = float(cfg["insertion"].get("side_skew", 0.008)) + plane_bias
    top_shrink = float(cfg["insertion"].get("top_shrink", 0.015)) + abs(float(normal[1])) * 0.003
    top_shrink = float(np.clip(top_shrink, 0.0, 0.16))

    top_width = width * (1.0 - top_shrink)
    bottom_width = width * (1.0 + min(top_shrink * 0.35, 0.045))
    top_center = np.array([cx - vertical_shear * height * 0.5, cy - height * 0.5], dtype=np.float32)
    bottom_center = np.array([cx + vertical_shear * height * 0.5, cy + height * 0.5], dtype=np.float32)
    top_vec = np.array([top_width * 0.5, horizontal_shear * top_width * 0.5], dtype=np.float32)
    bottom_vec = np.array([bottom_width * 0.5, horizontal_shear * bottom_width * 0.5], dtype=np.float32)
    side_offset = np.array([side_skew * width, 0.0], dtype=np.float32)

    quad = np.array(
        [
            top_center - top_vec + side_offset,
            top_center + top_vec - side_offset,
            bottom_center + bottom_vec,
            bottom_center - bottom_vec,
        ],
        dtype=np.float32,
    )
    quad[:, 0] = np.clip(quad[:, 0], 0, image_w - 1)
    quad[:, 1] = np.clip(quad[:, 1], 0, image_h - 1)
    debug = {
        "mode": "wall_oriented_homography",
        "local_orientation": orientation,
        "vertical_shear": vertical_shear,
        "horizontal_shear": horizontal_shear,
        "top_shrink": top_shrink,
        "side_skew": side_skew,
    }
    return quad, debug


def estimate_local_wall_orientation(image_rgb: np.ndarray | None, box: list[int]) -> dict[str, Any]:
    if image_rgb is None:
        return {"status": "no_image", "vertical_dx_per_y": 0.0, "horizontal_dy_per_x": 0.0, "line_count": 0}
    height, width = image_rgb.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = max(2, x2 - x1), max(2, y2 - y1)
    pad_x = max(24, int(bw * 1.2))
    pad_y = max(24, int(bh * 0.8))
    sx1, sy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    sx2, sy2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
    roi = image_rgb[sy1:sy2, sx1:sx2]
    if roi.size == 0:
        return {"status": "empty_roi", "vertical_dx_per_y": 0.0, "horizontal_dy_per_x": 0.0, "line_count": 0}

    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 45, 130)
    min_len = max(18, int(min(roi.shape[:2]) * 0.16))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(18, min_len // 2), minLineLength=min_len, maxLineGap=12)
    if lines is None:
        return {"status": "no_lines", "vertical_dx_per_y": 0.0, "horizontal_dy_per_x": 0.0, "line_count": 0}

    vertical_slopes: list[float] = []
    horizontal_slopes: list[float] = []
    for line in lines[:, 0]:
        lx1, ly1, lx2, ly2 = [float(v) for v in line]
        dx, dy = lx2 - lx1, ly2 - ly1
        length = float(np.hypot(dx, dy))
        if length < min_len:
            continue
        angle = abs(np.degrees(np.arctan2(dy, dx)))
        angle = angle if angle <= 90 else 180 - angle
        if angle >= 58 and abs(dy) > 1:
            vertical_slopes.append(float(np.clip(dx / dy, -0.30, 0.30)))
        elif angle <= 32 and abs(dx) > 1:
            horizontal_slopes.append(float(np.clip(dy / dx, -0.30, 0.30)))

    vertical = float(np.median(vertical_slopes)) if vertical_slopes else 0.0
    horizontal = float(np.median(horizontal_slopes)) if horizontal_slopes else 0.0
    return {
        "status": "estimated",
        "vertical_dx_per_y": vertical,
        "horizontal_dy_per_x": horizontal,
        "line_count": int(len(lines)),
        "vertical_line_count": len(vertical_slopes),
        "horizontal_line_count": len(horizontal_slopes),
    }


def clamp_insertion_scale(
    scale: float,
    mod_wh: list[int],
    target_box: list[int],
    out_hw: tuple[int, int],
    cfg: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    image_h, image_w = out_hw
    mod_w, mod_h = max(1, int(mod_wh[0])), max(1, int(mod_wh[1]))
    target_w = max(1, target_box[2] - target_box[0])
    target_h = max(1, target_box[3] - target_box[1])
    original_scale = float(scale)
    max_scale = original_scale
    reasons: list[str] = []

    max_area_ratio = float(cfg["insertion"].get("max_insert_area_ratio", 0.12))
    target_type = cfg.get("_placement_debug", {}).get("selected_replacement_target_type")
    if target_type == OPERATING_PANEL_CLASS:
        max_area_ratio = max(max_area_ratio, 0.55)
    elif target_type == "elevator_door":
        max_area_ratio = max(max_area_ratio, 0.70)
    elif target_type == "elevator_ceiling":
        max_area_ratio = max(max_area_ratio, 0.35)
    max_area_px = max(1.0, image_w * image_h * max_area_ratio)
    projected_area = (mod_w * original_scale) * (mod_h * original_scale)
    if projected_area > max_area_px:
        max_scale = min(max_scale, (max_area_px / max(mod_w * mod_h, 1)) ** 0.5)
        reasons.append("max_insert_area_ratio")

    if cfg.get("_placement_debug", {}).get("placement_mode") == "existing_panel":
        max_factor = float(cfg["insertion"].get("existing_panel_max_scale_factor", 1.10))
        panel_max_scale = min((target_w * max_factor) / mod_w, (target_h * max_factor) / mod_h)
        if panel_max_scale < max_scale:
            max_scale = panel_max_scale
            reasons.append("existing_panel_max_scale_factor")

    clamped_scale = max(0.001, min(original_scale, max_scale))
    if clamped_scale >= original_scale:
        return original_scale, {}

    insert_w, insert_h = max(1, int(mod_w * clamped_scale)), max(1, int(mod_h * clamped_scale))
    area_ratio = (insert_w * insert_h) / max(image_w * image_h, 1)
    return clamped_scale, {
        "insertion_scale_clamped": True,
        "insertion_original_scale_factor": original_scale,
        "insertion_scale_clamp_reasons": sorted(set(reasons)),
        "insertion_area_ratio_after_clamp": float(area_ratio),
    }


def validate_insertion_size(target_box: list[int], insert_wh: list[int], out_hw: tuple[int, int], cfg: dict[str, Any]) -> None:
    image_h, image_w = out_hw
    target_w = max(1, target_box[2] - target_box[0])
    target_h = max(1, target_box[3] - target_box[1])
    insert_w, insert_h = insert_wh
    area_ratio = (insert_w * insert_h) / max(image_w * image_h, 1)
    max_area_ratio = float(cfg["insertion"].get("max_insert_area_ratio", 0.12))
    target_type = cfg.get("_placement_debug", {}).get("selected_replacement_target_type")
    if target_type == OPERATING_PANEL_CLASS:
        max_area_ratio = max(max_area_ratio, 0.55)
    elif target_type == "elevator_door":
        max_area_ratio = max(max_area_ratio, 0.70)
    elif target_type == "elevator_ceiling":
        max_area_ratio = max(max_area_ratio, 0.35)
    if area_ratio > max_area_ratio:
        raise RuntimeError(f"Insertion size validation failed: area_ratio={area_ratio:.3f} > {max_area_ratio:.3f}")
    if cfg.get("_placement_debug", {}).get("placement_mode") == "existing_panel":
        max_factor = float(cfg["insertion"].get("existing_panel_max_scale_factor", 1.10))
        if insert_w > target_w * max_factor or insert_h > target_h * max_factor:
            raise RuntimeError(
                "Insertion size validation failed: existing panel replacement exceeds target bbox "
                f"insert={insert_wh} target={[target_w, target_h]} max_factor={max_factor}"
            )


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
    matrix, status = cv2.findHomography(src, quad, 0)
    if matrix is None or status is None:
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


def validate_or_rebuild_alpha(alpha: np.ndarray, insertion_bbox: list[int], cfg: dict[str, Any], mask_name: str) -> tuple[np.ndarray, dict[str, Any]]:
    ratio, bbox, nearly_full = mask_stats(alpha)
    max_ratio = float(cfg["insertion"].get("max_harmonization_mask_area_ratio", 0.35))
    debug = {
        f"{mask_name}_mask_bbox": bbox,
        f"{mask_name}_mask_white_area_ratio": ratio,
        f"{mask_name}_mask_validation_status": "passed",
    }
    LOGGER.info("[MASK] Validating harmonization mask coverage=%.4f", ratio)
    if ratio <= max_ratio and not nearly_full:
        return alpha, debug

    rebuilt = np.zeros_like(alpha, dtype=np.float32)
    x1, y1, x2, y2 = [int(v) for v in insertion_bbox]
    pad = int(cfg["insertion"].get("harmonization_mask_rebuild_padding_px", 2))
    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
    x2, y2 = min(alpha.shape[1], x2 + pad), min(alpha.shape[0], y2 + pad)
    rebuilt[y1:y2, x1:x2] = 1.0
    ratio2, bbox2, nearly_full2 = mask_stats(rebuilt)
    debug.update(
        {
            f"{mask_name}_mask_bbox": bbox2,
            f"{mask_name}_mask_white_area_ratio": ratio2,
            f"{mask_name}_mask_validation_status": "rebuilt",
            "mask_rebuilt_reason": "rejected_full_or_oversized_mask",
        }
    )
    LOGGER.info("[MASK] Rebuilt localized mask from insertion bbox after rejecting full-image mask")
    if ratio2 > max_ratio or nearly_full2:
        raise RuntimeError(
            f"Harmonization mask validation failed after rebuild: coverage={ratio2:.4f} bbox={bbox2}"
        )
    return rebuilt, debug


def mask_stats(alpha: np.ndarray) -> tuple[float, list[int] | None, bool]:
    mask = alpha > 0.03
    ratio = float(mask.mean()) if mask.size else 0.0
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return ratio, None, False
    bbox = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
    h, w = mask.shape[:2]
    bbox_area_ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / max(w * h, 1)
    nearly_full = bbox_area_ratio > 0.82 or (bbox[0] <= 2 and bbox[1] <= 2 and bbox[2] >= w - 2 and bbox[3] >= h - 2)
    return ratio, bbox, nearly_full


def match_mod_appearance_to_cleaned_region(mod_rgba: np.ndarray, cleaned_bg: np.ndarray, target_box: list[int]) -> np.ndarray:
    """Match panel appearance to the cleaned target surface before geometric placement."""
    height, width = cleaned_bg.shape[:2]
    x1, y1, x2, y2 = [int(round(value)) for value in target_box]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return mod_rgba

    target = cleaned_bg[y1:y2, x1:x2]
    visible = mod_rgba[:, :, 3] > 8
    if int(visible.sum()) < 20 or target.size == 0:
        return mod_rgba

    panel_lab = cv2.cvtColor(mod_rgba[:, :, :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    target_lab = cv2.cvtColor(target, cv2.COLOR_RGB2LAB).astype(np.float32)
    panel_l = panel_lab[:, :, 0][visible]
    target_l = target_lab[:, :, 0].reshape(-1)

    percentiles = [5, 25, 50, 75, 95]
    source_levels = np.percentile(panel_l, percentiles).astype(np.float32)
    target_levels = np.percentile(target_l, percentiles).astype(np.float32)
    source_levels = np.maximum.accumulate(source_levels + np.arange(len(source_levels), dtype=np.float32) * 0.01)

    current_l = panel_lab[:, :, 0]
    mapped_l = np.interp(current_l, source_levels, target_levels).astype(np.float32)
    correction = np.clip(mapped_l - current_l, -55.0, 55.0)
    panel_lab[:, :, 0] = np.clip(current_l + correction * 0.78, 0, 255)

    panel_color_mean = panel_lab[:, :, 1:3][visible].mean(axis=0)
    target_color_mean = target_lab[:, :, 1:3].reshape(-1, 2).mean(axis=0)
    color_shift = np.clip((target_color_mean - panel_color_mean) * 0.70, -18.0, 18.0)
    panel_lab[:, :, 1:3] = np.clip(panel_lab[:, :, 1:3] + color_shift, 0, 255)

    out = mod_rgba.copy()
    out[:, :, :3] = cv2.cvtColor(panel_lab.astype(np.uint8), cv2.COLOR_LAB2RGB)
    LOGGER.info(
        "[PLACE] Pre-matched MOD appearance to cleaned region levels L50=%.1f->%.1f color_shift=(%.1f, %.1f)",
        float(source_levels[2]),
        float(target_levels[2]),
        float(color_shift[0]),
        float(color_shift[1]),
    )
    return out


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
