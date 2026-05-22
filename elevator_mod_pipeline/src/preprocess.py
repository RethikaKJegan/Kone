from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .utils import load_image_rgb, save_json, save_rgb, utc_now


CONFIG = {
    "weights": {"perspective": 0.40, "visibility": 0.20, "sharpness": 0.10, "exposure": 0.10, "context": 0.10, "crop_scale": 0.10},
    "hard_fails": {"perspective_fail": 0.62, "perspective_review": 0.68, "visibility_min": 0.40, "sharpness_extreme_min": 0.05, "min_short_side": 420},
    "thresholds": {"pass": 0.65, "review": 0.55},
}


def run_preprocessing(image_path: str | Path, cfg: dict[str, Any], out_image: str | Path, out_json: str | Path) -> Path:
    image = load_image_rgb(image_path)
    before = validate_image(image)
    corrected = image.copy()
    corrections: list[dict[str, Any]] = []

    if cfg.get("preprocessing", {}).get("auto_correct", True) and before["result"] != "PASS":
        corrected, correction = straighten_image(corrected, cfg)
        corrections.append(correction)

    after = validate_image(corrected)
    chosen = corrected if after["final_score"] >= before["final_score"] else image
    if chosen is image:
        corrections.append({"type": "revert", "reason": "correction_did_not_improve_score"})
        after = before

    save_rgb(out_image, chosen)
    save_json(
        out_json,
        {
            "metadata": {"source_image": str(image_path), "output_image": str(out_image), "timestamp": utc_now()},
            "before": before,
            "after": after,
            "corrections": corrections,
            "passed": after["result"] in {"PASS", "REVIEW"},
        },
    )
    return Path(out_image)


def validate_image(rgb: np.ndarray) -> dict[str, Any]:
    h, w = rgb.shape[:2]
    short_side = min(h, w)
    metrics: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    metrics["perspective"], reasons["perspective"] = perspective_score(rgb)
    metrics["visibility"], reasons["visibility"] = visibility_score(rgb)
    metrics["sharpness"], reasons["sharpness"] = sharpness_score(rgb)
    metrics["exposure"], reasons["exposure"] = exposure_score(rgb)
    metrics["context"], reasons["context"] = context_score(rgb)
    metrics["crop_scale"], reasons["crop_scale"] = crop_scale_score(rgb)
    final_score = clamp(sum(metrics[k] * CONFIG["weights"][k] for k in CONFIG["weights"]))

    hard_fail = []
    review = []
    if metrics["perspective"] < CONFIG["hard_fails"]["perspective_fail"]:
        hard_fail.append("Perspective below strict fail threshold.")
    elif metrics["perspective"] < CONFIG["hard_fails"]["perspective_review"]:
        review.append("Perspective is borderline; sending to REVIEW.")
    if metrics["visibility"] < CONFIG["hard_fails"]["visibility_min"]:
        hard_fail.append("Visibility below hard-fail threshold.")
    if metrics["sharpness"] < CONFIG["hard_fails"]["sharpness_extreme_min"]:
        hard_fail.append("Sharpness is extremely poor.")
    if short_side < CONFIG["hard_fails"]["min_short_side"]:
        hard_fail.append(f"Resolution too low. Shortest side = {short_side}px.")

    result = "FAIL"
    if hard_fail:
        result = "FAIL"
    elif review:
        result = "REVIEW"
    elif final_score >= CONFIG["thresholds"]["pass"]:
        result = "PASS"
    elif final_score >= CONFIG["thresholds"]["review"]:
        result = "REVIEW"

    reasons["hard_fail"] = hard_fail
    reasons["review"] = review
    reasons["suggestions"] = generate_suggestions(metrics, result)
    return {
        "result": result,
        "final_score": round(final_score, 4),
        "metrics": {k: round(v, 4) for k, v in metrics.items()},
        "reasons": reasons,
        "image_size": {"width": w, "height": h, "short_side": short_side},
    }


def straighten_image(rgb: np.ndarray, cfg: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    angle, confidence = dominant_roll_angle(rgb)
    max_roll = float(cfg.get("preprocessing", {}).get("max_roll_degrees", 12.0))
    applied = float(np.clip(angle, -max_roll, max_roll)) if confidence >= 0.35 else 0.0
    corrected = rotate_bound(rgb, -applied) if abs(applied) >= 0.35 else rgb.copy()
    side_offset = vertical_balance_offset(corrected)
    max_shift = float(cfg.get("preprocessing", {}).get("max_horizontal_shift_ratio", 0.035))
    if abs(side_offset) > 0.18:
        corrected = gentle_horizontal_rectify(corrected, float(np.clip(side_offset * max_shift, -max_shift, max_shift)))
    return corrected, {"type": "straighten", "roll_degrees": round(applied, 3), "line_confidence": round(confidence, 3), "side_offset": round(side_offset, 3)}


def perspective_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    lines = cv2.HoughLinesP(cv2.Canny(gray, 60, 160), 1, np.pi / 180, threshold=max(45, int(min(h, w) * 0.08)), minLineLength=max(35, int(min(h, w) * 0.08)), maxLineGap=14)
    if lines is None:
        return 0.55, ["Not enough structural lines found."]
    vertical_devs, horizontal_devs, vertical_xs, vertical_lengths = [], [], [], []
    for x1, y1, x2, y2 in lines[:, 0]:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
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
    hdev = float(np.median(horizontal_devs)) if horizontal_devs else None
    vertical_score = 1.0 - clamp(vdev / 12.0)
    horizontal_score = 1.0 - clamp((hdev or 3.5) / 10.0) if horizontal_devs else 0.65
    cx = float(np.average(vertical_xs, weights=vertical_lengths))
    center_offset = abs(cx - (w / 2)) / (w / 2)
    frontal_score = 1.0 - clamp(center_offset / 0.65)
    score = clamp((0.55 * vertical_score) + (0.35 * horizontal_score) + (0.10 * frontal_score))
    return score, [f"Vertical deviation approx {vdev:.1f} deg.", f"Horizontal deviation approx {hdev:.1f} deg." if hdev is not None else "Few horizontal lines found.", f"Frontal balance offset approx {center_offset:.2f}."]


def visibility_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    brightness, contrast = float(gray.mean()), float(gray.std())
    edge_density = np.count_nonzero(cv2.Canny(gray, 50, 150)) / gray.size
    score = clamp((0.40 * (1.0 - abs(brightness - 130) / 130)) + (0.35 * normalize_range(contrast, 18, 70)) + (0.25 * normalize_range(edge_density, 0.006, 0.075)))
    return score, ["Brightness is usable." if 40 <= brightness <= 230 else "Brightness needs correction.", "Contrast is usable." if contrast >= 18 else "Contrast is low."]


def sharpness_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    score = clamp((0.60 * normalize_range(lap_var, 20, 250)) + (0.40 * normalize_range(float(np.mean(gx * gx + gy * gy)), 300, 3500)))
    return score, [f"Sharpness Laplacian = {lap_var:.1f}."]


def exposure_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    dark_penalty = clamp(float(np.mean(gray < 25)) / 0.25)
    bright_penalty = clamp(float(np.mean(gray > 245)) / 0.22)
    glare_penalty = clamp(float(np.mean((hsv[:, :, 2] > 240) & (hsv[:, :, 1] < 50))) / 0.15)
    return clamp(1.0 - ((0.35 * dark_penalty) + (0.30 * bright_penalty) + (0.35 * glare_penalty))), ["Exposure checked for dark, clipped, and glare regions."]


def context_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    edges = cv2.Canny(gray, 50, 150)
    border = int(min(h, w) * 0.08)
    if h <= border * 2 or w <= border * 2:
        return 0.60, ["Small image; context check relaxed."]
    center_density = np.count_nonzero(edges[border : h - border, border : w - border]) / max(1, edges[border : h - border, border : w - border].size)
    full_density = np.count_nonzero(edges) / max(1, edges.size)
    score = clamp((0.70 * normalize_range(center_density, 0.004, 0.055)) + (0.30 * normalize_range(full_density, 0.006, 0.065)))
    return score, ["Enough local structure/context is present." if score >= 0.40 else "Local context is weak, but not hard-failed."]


def crop_scale_score(rgb: np.ndarray) -> tuple[float, list[str]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    ys, xs = np.where(cv2.Canny(gray, 50, 150) > 0)
    if len(xs) < 50:
        return 0.65, ["Too few edges for crop/scale; relaxed."]
    x1, x2, y1, y2 = xs.min(), xs.max(), ys.min(), ys.max()
    area_ratio = ((x2 - x1 + 1) * (y2 - y1 + 1)) / (w * h)
    min_margin = min(x1 / w, (w - x2) / w, y1 / h, (h - y2) / h)
    scale_score = normalize_range(area_ratio, 0.03, 0.16) if area_ratio < 0.08 else 0.70 if area_ratio > 0.96 else 1.0
    score = clamp((0.70 * scale_score) + (0.30 * normalize_range(min_margin, 0.0, 0.030)))
    return score, [f"Estimated structure area ratio = {area_ratio:.2f}.", f"Minimum border margin = {min_margin:.3f}."]


def dominant_roll_angle(rgb: np.ndarray) -> tuple[float, float]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    lines = cv2.HoughLinesP(cv2.Canny(gray, 60, 160), 1, np.pi / 180, threshold=max(45, int(min(h, w) * 0.08)), minLineLength=max(35, int(min(h, w) * 0.08)), maxLineGap=14)
    if lines is None:
        return 0.0, 0.0
    angles, weights = [], []
    for x1, y1, x2, y2 in lines[:, 0]:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < min(h, w) * 0.06:
            continue
        raw = math.degrees(math.atan2(dy, dx))
        angle = ((raw + 90) % 180) - 90
        if abs(angle) < 35:
            angles.append(angle)
            weights.append(length)
        elif abs(abs(angle) - 90) < 35:
            angles.append(angle - math.copysign(90, angle))
            weights.append(length)
    if not angles:
        return 0.0, 0.0
    return float(np.average(angles, weights=weights)), clamp(len(angles) / 12.0)


def vertical_balance_offset(rgb: np.ndarray) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    lines = cv2.HoughLinesP(cv2.Canny(gray, 60, 160), 1, np.pi / 180, threshold=max(45, int(min(h, w) * 0.08)), minLineLength=max(35, int(min(h, w) * 0.08)), maxLineGap=14)
    if lines is None:
        return 0.0
    xs, weights = [], []
    for x1, y1, x2, y2 in lines[:, 0]:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        angle = abs(math.degrees(math.atan2(dy, dx)))
        angle = angle if angle <= 90 else 180 - angle
        if angle > 55:
            xs.append((x1 + x2) * 0.5)
            weights.append(length)
    if not xs:
        return 0.0
    return float((np.average(xs, weights=weights) - (w * 0.5)) / (w * 0.5))


def rotate_bound(rgb: np.ndarray, angle: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    nw, nh = int((h * sin) + (w * cos)), int((h * cos) + (w * sin))
    matrix[0, 2] += (nw / 2) - w / 2
    matrix[1, 2] += (nh / 2) - h / 2
    return cv2.warpAffine(rgb, matrix, (nw, nh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def gentle_horizontal_rectify(rgb: np.ndarray, shift_ratio: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    shift = float(w * shift_ratio)
    src = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    dst = np.array([[max(0, shift), 0], [w - 1 + min(0, shift), 0], [w - 1 - max(0, shift), h - 1], [-min(0, shift), h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(rgb, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def generate_suggestions(metrics: dict[str, float], result: str) -> list[str]:
    if result == "PASS":
        return ["Image is suitable for GroundingDINO/SAM2 processing.", "Perspective, visibility, and quality are acceptable."]
    suggestions = []
    if metrics["perspective"] < CONFIG["hard_fails"]["perspective_fail"]:
        suggestions.append("Retake or correct the image from a straighter front-facing angle.")
    elif metrics["perspective"] < CONFIG["hard_fails"]["perspective_review"]:
        suggestions.append("Perspective is borderline; keep vertical edges straight and centered.")
    if metrics["visibility"] < 0.60:
        suggestions.append("Improve light and contrast around the target area.")
    if metrics["sharpness"] < 0.50:
        suggestions.append("Improve focus and avoid motion blur.")
    if metrics["exposure"] < 0.70:
        suggestions.append("Avoid strong glare, flash reflection, or very dark areas.")
    if metrics["context"] < 0.60:
        suggestions.append("Leave more surrounding elevator context in frame.")
    return suggestions or ["Use a straighter angle, better focus, and cleaner lighting."]


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def normalize_range(x: float, low: float, high: float) -> float:
    return clamp((x - low) / (high - low)) if high != low else 0.0
