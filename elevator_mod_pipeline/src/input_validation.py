from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "fail_on_invalid": True,
    "require_elevator": True,
    "weights": {
        "perspective": 0.40,
        "visibility": 0.20,
        "sharpness": 0.10,
        "exposure": 0.10,
        "context": 0.10,
        "crop_scale": 0.10,
    },
    "hard_fails": {
        "perspective_fail": 0.62,
        "perspective_review": 0.68,
        "visibility_min": 0.40,
        "sharpness_extreme_min": 0.05,
        "min_short_side": 420,
    },
    "thresholds": {
        "pass": 0.65,
        "review": 0.55,
    },
    "elevator_presence": {
        "min_score": 0.22,
        "door_min_score": 0.30,
        "cabin_min_score": 0.34,
        "panel_min_score": 0.25,
        "door_min_area_ratio": 0.05,
        "standalone_panel_min_score": 0.30,
        "standalone_panel_min_area_ratio": 0.02,
        "valid_types": [
            "tall stainless steel elevator operating panel with round buttons",
            "elevator call button panel",
            "wheelchair button",
            "accessibility_control_panel",
            "floor_indicator_display",
            "weight_limit_sign",
            "elevator_door",
            "elevator_cabin",
            "threshold_plate",
            "handrail",
            "security_camera",
            "emergency_phone",
        ],
    },
}


def merged_validation_config(cfg: dict[str, Any]) -> dict[str, Any]:
    user = cfg.get("input_validation", {}) or {}
    merged = {
        **DEFAULT_CONFIG,
        **user,
        "weights": {**DEFAULT_CONFIG["weights"], **user.get("weights", {})},
        "hard_fails": {**DEFAULT_CONFIG["hard_fails"], **user.get("hard_fails", {})},
        "thresholds": {**DEFAULT_CONFIG["thresholds"], **user.get("thresholds", {})},
        "elevator_presence": {**DEFAULT_CONFIG["elevator_presence"], **user.get("elevator_presence", {})},
    }
    return merged


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def normalize_range(x: float, low: float, high: float) -> float:
    return clamp((x - low) / (high - low)) if high != low else 0.0


def validate_input_image(rgb: np.ndarray, cfg: dict[str, Any]) -> dict[str, Any]:
    validation_cfg = merged_validation_config(cfg)
    h, w = rgb.shape[:2]
    short_side = min(h, w)
    metrics: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    metrics["perspective"], reasons["perspective"] = perspective_score(rgb, validation_cfg)
    metrics["visibility"], reasons["visibility"] = visibility_score(rgb)
    metrics["sharpness"], reasons["sharpness"] = sharpness_score(rgb)
    metrics["exposure"], reasons["exposure"] = exposure_score(rgb)
    metrics["context"], reasons["context"] = context_score(rgb)
    metrics["crop_scale"], reasons["crop_scale"] = crop_scale_score(rgb)

    final_score = clamp(sum(metrics[k] * validation_cfg["weights"][k] for k in validation_cfg["weights"]))
    hard_fail: list[str] = []
    review_reasons: list[str] = []
    hard_fails = validation_cfg["hard_fails"]

    if metrics["perspective"] < hard_fails["perspective_fail"]:
        hard_fail.append("Perspective below strict fail threshold.")
    elif metrics["perspective"] < hard_fails["perspective_review"]:
        review_reasons.append("Perspective is borderline; sending to REVIEW.")
    if metrics["visibility"] < hard_fails["visibility_min"]:
        hard_fail.append("Visibility below hard-fail threshold.")
    if metrics["sharpness"] < hard_fails["sharpness_extreme_min"]:
        hard_fail.append("Sharpness is extremely poor.")
    if short_side < hard_fails["min_short_side"]:
        hard_fail.append(f"Resolution too low. Shortest side = {short_side}px.")

    reasons["hard_fail"] = hard_fail
    reasons["review"] = review_reasons
    if hard_fail:
        result = "FAIL"
    elif review_reasons:
        result = "REVIEW"
    elif final_score >= validation_cfg["thresholds"]["pass"]:
        result = "PASS"
    elif final_score >= validation_cfg["thresholds"]["review"]:
        result = "REVIEW"
    else:
        result = "FAIL"

    reasons["suggestions"] = generate_suggestions(metrics, result, validation_cfg)
    return {
        "result": result,
        "valid": result != "FAIL",
        "final_score": round(final_score, 4),
        "metrics": {k: round(v, 4) for k, v in metrics.items()},
        "reasons": reasons,
        "image_size": {"width": w, "height": h, "short_side": short_side},
        "note": "Quality/perspective validator. Object correctness is handled by detector; elevator presence is checked after detection.",
    }


def perspective_score(rgb: np.ndarray, cfg: dict[str, Any]) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    edges = cv2.Canny(gray, 60, 160)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(45, int(min(h, w) * 0.08)),
        minLineLength=max(35, int(min(h, w) * 0.08)),
        maxLineGap=14,
    )
    if lines is None:
        return 0.55, ["Not enough structural lines found."]

    vertical_devs: list[float] = []
    horizontal_devs: list[float] = []
    vertical_xs: list[float] = []
    vertical_lengths: list[float] = []
    for l in lines[:, 0]:
        x1, y1, x2, y2 = [int(v) for v in l]
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < min(h, w) * 0.06:
            continue
        angle = abs(math.degrees(math.atan2(dy, dx)))
        angle = angle if angle <= 90 else 180 - angle
        if angle > 55:
            vertical_devs.append(abs(90 - angle))
            vertical_xs.append((x1 + x2) / 2)
            vertical_lengths.append(length)
        if angle < 35:
            horizontal_devs.append(abs(angle))

    if len(vertical_devs) < 2:
        return 0.58, ["Few vertical lines found; perspective confidence is low."]

    vdev = float(np.median(vertical_devs))
    vertical_score = 1.0 - clamp(vdev / 12.0)
    if horizontal_devs:
        hdev = float(np.median(horizontal_devs))
        horizontal_score = 1.0 - clamp(hdev / 10.0)
    else:
        hdev = None
        horizontal_score = 0.65

    if vertical_xs:
        cx = float(np.average(vertical_xs, weights=vertical_lengths))
        center_offset = abs(cx - (w / 2)) / (w / 2)
        frontal_score = 1.0 - clamp(center_offset / 0.65)
    else:
        center_offset = 1.0
        frontal_score = 0.50

    score = clamp((0.55 * vertical_score) + (0.35 * horizontal_score) + (0.10 * frontal_score))
    reasons = [
        f"Vertical deviation ~= {vdev:.1f} deg.",
        f"Horizontal deviation ~= {hdev:.1f} deg." if hdev is not None else "Few horizontal lines found.",
        f"Frontal balance offset ~= {center_offset:.2f}.",
    ]
    hard_fails = cfg["hard_fails"]
    if score < hard_fails["perspective_fail"]:
        reasons.append("Perspective is poor; image should fail.")
    elif score < hard_fails["perspective_review"]:
        reasons.append("Perspective is borderline; image should review.")
    else:
        reasons.append("Perspective is acceptable.")
    return score, reasons


def visibility_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / edges.size
    brightness_score = clamp(1.0 - abs(brightness - 130) / 130)
    contrast_score = normalize_range(contrast, 18, 70)
    edge_score = normalize_range(edge_density, 0.006, 0.075)
    score = clamp((0.40 * brightness_score) + (0.35 * contrast_score) + (0.25 * edge_score))
    reasons = ["Brightness is usable." if 40 <= brightness <= 230 else ("Image is dark." if brightness < 40 else "Image is bright.")]
    reasons.append("Contrast is usable." if contrast >= 18 else "Contrast is low.")
    return score, reasons


def sharpness_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    lap_score = normalize_range(lap_var, 20, 250)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float(np.mean(gx * gx + gy * gy))
    tenengrad_score = normalize_range(tenengrad, 300, 3500)
    score = clamp((0.60 * lap_score) + (0.40 * tenengrad_score))
    if score < 0.25:
        reason = f"Sharpness is low, but not hard-failed unless extremely bad. Laplacian = {lap_var:.1f}."
    elif score < 0.60:
        reason = f"Sharpness is moderate. Laplacian = {lap_var:.1f}."
    else:
        reason = f"Sharpness is usable. Laplacian = {lap_var:.1f}."
    return score, [reason]


def exposure_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    dark_pct = np.mean(gray < 25)
    bright_pct = np.mean(gray > 245)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    glare_pct = np.mean((val > 240) & (sat < 50))
    score = clamp(1.0 - ((0.35 * clamp(dark_pct / 0.25)) + (0.30 * clamp(bright_pct / 0.22)) + (0.35 * clamp(glare_pct / 0.15))))
    reasons = []
    if dark_pct > 0.15:
        reasons.append(f"Too many dark pixels: {dark_pct*100:.1f}%.")
    if bright_pct > 0.14:
        reasons.append(f"Too many overexposed pixels: {bright_pct*100:.1f}%.")
    if glare_pct > 0.10:
        reasons.append(f"Glare/reflection hotspot detected: {glare_pct*100:.1f}%.")
    return score, reasons or ["Exposure/glare is acceptable."]


def context_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    edges = cv2.Canny(gray, 50, 150)
    border = int(min(h, w) * 0.08)
    if h <= border * 2 or w <= border * 2:
        return 0.60, ["Small image; context check relaxed."]
    center = edges[border : h - border, border : w - border]
    center_density = np.count_nonzero(center) / max(1, center.size)
    full_density = np.count_nonzero(edges) / max(1, edges.size)
    score = clamp((0.70 * normalize_range(center_density, 0.004, 0.055)) + (0.30 * normalize_range(full_density, 0.006, 0.065)))
    return score, ["Enough local structure/context is present." if score >= 0.40 else "Local context is weak, but not hard-failed."]


def crop_scale_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    edges = cv2.Canny(gray, 50, 150)
    ys, xs = np.where(edges > 0)
    if len(xs) < 50:
        return 0.65, ["Too few edges for crop/scale; relaxed."]
    x1, x2 = xs.min(), xs.max()
    y1, y2 = ys.min(), ys.max()
    area_ratio = ((x2 - x1 + 1) * (y2 - y1 + 1)) / (w * h)
    min_margin = min(x1 / w, (w - x2) / w, y1 / h, (h - y2) / h)
    if area_ratio < 0.08:
        scale_score = normalize_range(area_ratio, 0.03, 0.16)
    elif area_ratio > 0.96:
        scale_score = 0.70
    else:
        scale_score = 1.0
    crop_score = normalize_range(min_margin, 0.000, 0.030)
    score = clamp((0.70 * scale_score) + (0.30 * crop_score))
    return score, [
        "Crop/scale is only a soft metric. It will not hard-fail.",
        f"Estimated structure area ratio = {area_ratio:.2f}.",
        f"Minimum border margin = {min_margin:.3f}.",
    ]


def generate_suggestions(metrics: dict[str, float], result: str, cfg: dict[str, Any]) -> list[str]:
    if result == "PASS":
        return ["Image looks good and is suitable for detection/segmentation processing.", "Perspective, visibility, and quality are acceptable."]
    suggestions: list[str] = []
    if metrics["perspective"] < cfg["hard_fails"]["perspective_fail"]:
        suggestions.append("Retake the image straight from the front. Avoid side angle, tilted camera, or diagonal view.")
    elif metrics["perspective"] < cfg["hard_fails"]["perspective_review"]:
        suggestions.append("Perspective is borderline. Stand more centered and keep vertical edges straight.")
    if metrics["visibility"] < cfg["hard_fails"]["visibility_min"]:
        suggestions.append("Improve visibility. Make sure the area is clearly visible with enough light and contrast.")
    elif metrics["visibility"] < 0.60:
        suggestions.append("Visibility is moderate. Adjust lighting or move slightly closer so details are clearer.")
    if metrics["sharpness"] < 0.25:
        suggestions.append("Image is blurry. Hold the phone steady, tap to focus, and retake.")
    elif metrics["sharpness"] < 0.50:
        suggestions.append("Sharpness is low. Retake with better focus and avoid motion blur.")
    if metrics["exposure"] < 0.50:
        suggestions.append("Lighting/exposure is poor. Avoid strong glare, flash reflection, or very dark areas.")
    elif metrics["exposure"] < 0.70:
        suggestions.append("Exposure is moderate. Try softer lighting and avoid direct reflection.")
    if metrics["context"] < 0.40:
        suggestions.append("Add a little more surrounding area if possible. Do not crop too tightly.")
    elif metrics["context"] < 0.60:
        suggestions.append("Context is limited. Step back slightly if possible.")
    if metrics["crop_scale"] < 0.40:
        suggestions.append("Image may be too cropped or scale is poor. Keep the target fully inside the frame.")
    elif metrics["crop_scale"] < 0.60:
        suggestions.append("Crop/scale is moderate. Leave small margins around the visible target.")
    return suggestions or ["Retake with a straighter angle, better focus, and cleaner lighting."]


def validate_elevator_presence(detections: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    validation_cfg = merged_validation_config(cfg)
    presence_cfg = validation_cfg["elevator_presence"]
    valid_types = {str(item).lower() for item in presence_cfg["valid_types"]}
    min_score = float(presence_cfg["min_score"])
    meta = detections.get("metadata", {})
    image_w = int(meta.get("image_width", 0) or 0)
    image_h = int(meta.get("image_height", 0) or 0)
    matches = []
    match_types: list[str] = []
    match_detections: list[dict[str, Any]] = []
    rejected = []
    for det in detections.get("detections", []):
        norm = str(det.get("normalized_component_type") or det.get("phrase") or "").strip().lower()
        score = float(det.get("score", 0.0) or 0.0)
        valid, reason = elevator_detection_is_reliable(det, norm, score, image_w, image_h, valid_types, min_score, presence_cfg)
        record = {
            "normalized_component_type": norm,
            "raw_detection_label": det.get("raw_detection_label", det.get("phrase")),
            "score": score,
            "bbox": det.get("box_xyxy"),
        }
        if valid:
            matches.append(record)
            match_types.append(norm)
            match_detections.append(det)
        elif norm in valid_types:
            record["reason"] = reason
            rejected.append(record)
    if matches and not any(norm in {"elevator_door", "elevator_cabin"} for norm in match_types):
        has_standalone_panel = any(
            _is_convincing_standalone_panel(det, norm, image_w, image_h, presence_cfg)
            for det, norm in zip(match_detections, match_types)
        )
        if not has_standalone_panel:
            for record in matches:
                rejected.append({**record, "reason": "no credible doorway or close-up elevator panel anchor"})
            matches = []
    valid = bool(matches)
    return {
        "result": "PASS" if valid else "FAIL",
        "valid": valid,
        "matched_elevator_components": matches,
        "rejected_elevator_components": rejected,
        "reason": None if valid else "No elevator-related component was detected with sufficient confidence.",
        "suggestions": [] if valid else ["Upload an image that clearly contains an elevator, elevator doorway, cabin, or elevator control panel."],
    }


def elevator_detection_is_reliable(
    det: dict[str, Any],
    norm: str,
    score: float,
    image_w: int,
    image_h: int,
    valid_types: set[str],
    min_score: float,
    presence_cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    if norm not in valid_types:
        return False, "not an elevator validation type"
    if score < min_score:
        return False, "below minimum confidence"
    x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
    bw = max(0.0, x2 - x1)
    bh = max(0.0, y2 - y1)
    image_area = max(float(image_w * image_h), 1.0)
    area_ratio = (bw * bh) / image_area
    aspect = bh / max(bw, 1.0)
    raw = str(det.get("raw_detection_label", det.get("phrase", ""))).lower()
    source = str(det.get("source", "")).lower()

    if source == "image_structure_fallback" or raw == "image_structure_fallback":
        return False, "image-structure fallback is not enough for input validation"

    if norm in {
        "tall stainless steel elevator operating panel with round buttons",
        "elevator call button panel",
        "wheelchair button",
        "accessibility_control_panel",
        "floor_indicator_display",
        "weight_limit_sign",
    }:
        if score < float(presence_cfg.get("panel_min_score", 0.25)):
            return False, "panel/sign confidence too low"
        if area_ratio > 0.22:
            return False, "panel/sign detection is implausibly large"
        return True, None

    if norm == "elevator_door":
        repaired_sources = {"closed_door_header_recovery", "groundingdino_open_door_entrance_repair"}
        door_min_score = min_score if source in repaired_sources else float(presence_cfg.get("door_min_score", 0.30))
        if score < door_min_score:
            return False, "door confidence too low"
        min_door_area = float(presence_cfg.get("door_min_area_ratio", 0.05))
        if not (min_door_area <= area_ratio <= 0.55):
            return False, "door area is not plausible"
        if aspect < 0.85:
            return False, "door is not vertical enough"
        return True, None

    if norm == "elevator_cabin":
        if score < float(presence_cfg.get("cabin_min_score", 0.34)):
            return False, "cabin/interior confidence too low"
        if area_ratio > 0.70:
            return False, "cabin/interior covers nearly the whole image"
        if aspect < 0.75:
            return False, "cabin/interior is not vertical enough"
        return True, None

    if norm in {"threshold_plate", "handrail", "security_camera", "emergency_phone"}:
        if score < max(min_score, 0.32):
            return False, "supporting component confidence too low"
        if area_ratio > 0.18:
            return False, "supporting component is implausibly large"
        return True, None

    return False, "unsupported validation type"


def _is_convincing_standalone_panel(
    det: dict[str, Any],
    norm: str,
    image_w: int,
    image_h: int,
    presence_cfg: dict[str, Any],
) -> bool:
    if norm not in {
        "tall stainless steel elevator operating panel with round buttons",
        "elevator call button panel",
        "accessibility_control_panel",
    }:
        return False
    x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
    area_ratio = max(0.0, x2 - x1) * max(0.0, y2 - y1) / max(float(image_w * image_h), 1.0)
    score = float(det.get("score", 0.0) or 0.0)
    return (
        score >= float(presence_cfg.get("standalone_panel_min_score", 0.30))
        and area_ratio >= float(presence_cfg.get("standalone_panel_min_area_ratio", 0.02))
    )
