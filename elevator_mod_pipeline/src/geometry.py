from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

from .utils import detection_mask, load_image_rgb, save_json, select_detection, utc_now


def run_geometry(image_path: str | Path, detections: dict[str, Any], cfg: dict[str, Any], out_json: str | Path, out_depth: str | Path) -> dict[str, Any]:
    image_np = load_image_rgb(image_path)
    height, width = image_np.shape[:2]
    wall = select_detection(detections["detections"], ["wall"])
    door = select_detection(detections["detections"], ["elevator door"])

    depth_model = cfg["geometry"]["depth_model_id"]
    depth_error = None
    try:
        depth = _estimate_depth(Image.fromarray(image_np), depth_model)
    except Exception as exc:
        depth = _fallback_depth(image_np)
        depth_error = f"{type(exc).__name__}: {exc}"
        depth_model = "local_luminance_structure_fallback"
    depth = cv2.resize(depth, (width, height), interpolation=cv2.INTER_CUBIC)
    depth_relative = 1.0 / (depth + 1e-6)
    depth_relative = (depth_relative - depth_relative.min()) / max(float(depth_relative.max() - depth_relative.min()), 1e-6)
    np.savez_compressed(out_depth, depth_inverse=depth.astype(np.float32), depth_relative=depth_relative.astype(np.float32), height=height, width=width)

    if wall is None:
        wall = _synthetic_wall_detection(width, height, door)
        fallback_reason = "No wall detection found; using conservative background wall estimate"
    else:
        fallback_reason = None

    wall_mask = detection_mask(wall, height, width) > 127
    plane, quality = _fit_wall_plane(wall_mask, depth_relative, cfg)
    homography = _wall_homography(wall_mask, wall)
    scale = _estimate_scale(door, cfg) if door else None

    geometry = {
        "metadata": {
            "image_path": str(image_path),
            "image_width": width,
            "image_height": height,
            "timestamp": utc_now(),
            "depth_model": depth_model,
            "configured_depth_model": cfg["geometry"]["depth_model_id"],
            "depth_error": depth_error,
            "depth_map_file": str(out_depth),
            "fallback_reason": fallback_reason,
        },
        "wall_plane": {
            "equation_abcd": plane.tolist(),
            "normal": plane[:3].tolist(),
            "d": float(plane[3]),
            "quality": quality,
        },
        "scale": scale,
        "homography": homography,
        "gates_passed": {
            "plane_fit": bool(quality["passed"]),
            "scale_available": scale is not None,
            "homography_valid": homography["matrix_3x3"] is not None,
        },
    }
    save_json(out_json, geometry)
    save_depth_debug_sheet(image_path, out_depth, Path(out_json).with_name("depth_debug_sheet.png"))
    return geometry


def save_depth_debug_sheet(image_path: str | Path, depth_path: str | Path, out_path: str | Path) -> Path:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Could not load image for depth debug sheet: {image_path}")

    data = np.load(depth_path)
    key = "depth_relative" if "depth_relative" in data else data.files[0]
    depth = data[key].astype(np.float32)
    if depth.shape[:2] != image.shape[:2]:
        depth = cv2.resize(depth, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_CUBIC)
    depth_u8 = _normalize_depth_for_display(depth)
    depth_color = cv2.applyColorMap(depth_u8, cv2.COLORMAP_INFERNO)
    depth_color = cv2.GaussianBlur(depth_color, (3, 3), 0)

    gap = max(10, image.shape[1] // 60)
    title_h = max(34, image.shape[0] // 22)
    canvas_h = image.shape[0] + title_h
    canvas_w = image.shape[1] * 2 + gap
    canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
    canvas[title_h:, : image.shape[1]] = image
    canvas[title_h:, image.shape[1] + gap :] = depth_color

    font_scale = max(0.6, image.shape[1] / 900)
    thickness = max(1, int(round(font_scale * 1.8)))
    _draw_centered_title(canvas, "Input", 0, image.shape[1], title_h, font_scale, thickness)
    _draw_centered_title(canvas, "Depth (lighter = farther)", image.shape[1] + gap, image.shape[1], title_h, font_scale, thickness)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas)
    return out


def _normalize_depth_for_display(depth: np.ndarray) -> np.ndarray:
    depth = np.nan_to_num(depth.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    lo = float(np.percentile(depth, 2))
    hi = float(np.percentile(depth, 98))
    if hi - lo < 1e-6:
        return np.zeros(depth.shape, dtype=np.uint8)
    norm = np.clip((depth - lo) / (hi - lo), 0.0, 1.0)
    return (norm * 255).astype(np.uint8)


def _draw_centered_title(canvas: np.ndarray, text: str, x: int, width: int, title_h: int, font_scale: float, thickness: int) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_w, text_h = cv2.getTextSize(text, font, font_scale, thickness)[0]
    tx = x + max(0, (width - text_w) // 2)
    ty = max(text_h + 4, (title_h + text_h) // 2)
    cv2.putText(canvas, text, (tx, ty), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)


def _estimate_depth(image: Image.Image, model_id: str) -> np.ndarray:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModelForDepthEstimation.from_pretrained(model_id).to(device).eval()
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    return outputs.predicted_depth.squeeze().detach().cpu().numpy()


def _fallback_depth(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    h, w = gray.shape
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    edges = cv2.Canny((gray * 255).astype(np.uint8), 50, 150).astype(np.float32) / 255.0
    structure = cv2.GaussianBlur(edges, (0, 0), 9)
    depth = (0.55 * y) + (0.30 * (1.0 - gray)) + (0.15 * (1.0 - structure))
    depth = cv2.GaussianBlur(depth, (0, 0), 3)
    return (depth - depth.min()) / max(float(depth.max() - depth.min()), 1e-6)


def _fit_wall_plane(mask: np.ndarray, depth: np.ndarray, cfg: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    ys, xs = np.where(mask)
    if len(xs) < 20:
        return np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32), {"passed": False, "reason": "too_few_wall_pixels"}

    points = np.stack([xs.astype(np.float32), ys.astype(np.float32), depth[ys, xs].astype(np.float32)], axis=1)
    if len(points) > 20000:
        rng = np.random.default_rng(42)
        points = points[rng.choice(len(points), 20000, replace=False)]

    best = np.zeros(len(points), dtype=bool)
    rng = np.random.default_rng(42)
    for _ in range(200):
        sample = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(sample[1] - sample[0], sample[2] - sample[0])
        norm = np.linalg.norm(normal)
        if norm < 1e-8:
            continue
        normal /= norm
        d = -np.dot(normal, sample[0])
        inliers = np.abs(points @ normal + d) < 0.02
        if inliers.sum() > best.sum():
            best = inliers

    inlier_points = points[best] if best.any() else points
    centroid = inlier_points.mean(axis=0)
    _, _, vh = np.linalg.svd(inlier_points - centroid, full_matrices=False)
    normal = vh[-1]
    d = -np.dot(normal, centroid)
    residuals = np.abs(inlier_points @ normal + d)
    inlier_ratio = float(best.sum() / len(points))
    passed = inlier_ratio >= float(cfg["geometry"]["min_plane_inlier_ratio"]) and float(residuals.mean()) <= float(cfg["geometry"]["max_plane_residual"])
    quality = {
        "inlier_ratio": inlier_ratio,
        "n_inliers": int(best.sum()),
        "n_points": int(len(points)),
        "residual_mean": float(residuals.mean()),
        "residual_std": float(residuals.std()),
        "passed": bool(passed),
    }
    return np.array([normal[0], normal[1], normal[2], d], dtype=np.float32), quality


def _wall_homography(mask: np.ndarray, wall: dict[str, Any]) -> dict[str, Any]:
    corners = _mask_corners(mask)
    if corners is None:
        return {"matrix_3x3": None, "reprojection_error_px": None, "src_corners": None, "dst_rect_size": None}
    x1, y1, x2, y2 = wall["box_xyxy"]
    rect_w = float(x2 - x1)
    rect_h = float(y2 - y1)
    dst = np.array([[0, 0], [rect_w, 0], [rect_w, rect_h], [0, rect_h]], dtype=np.float32)
    matrix, _ = cv2.findHomography(corners, dst, cv2.RANSAC, 3.0)
    error = None
    if matrix is not None:
        src_h = np.column_stack([corners, np.ones(4)])
        projected = (matrix @ src_h.T).T
        projected = projected[:, :2] / projected[:, 2:3]
        error = float(np.linalg.norm(projected - dst, axis=1).mean())
    return {
        "matrix_3x3": matrix.tolist() if matrix is not None else None,
        "reprojection_error_px": error,
        "src_corners": corners.tolist(),
        "dst_rect_size": [rect_w, rect_h],
    }


def _mask_corners(mask: np.ndarray) -> np.ndarray | None:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    pts = np.column_stack([xs, ys])
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(sums)], pts[np.argmin(diffs)], pts[np.argmax(sums)], pts[np.argmax(diffs)]], dtype=np.float32)


def _estimate_scale(door: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    x1, _, x2, _ = door["box_xyxy"]
    door_px = float(x2 - x1)
    if door_px <= 0:
        return None
    return {
        "pixel_to_mm": float(cfg["geometry"]["known_door_width_mm"]) / door_px,
        "reference_object": "elevator door",
        "reference_width_mm": float(cfg["geometry"]["known_door_width_mm"]),
        "confidence": float(door.get("score", 0)),
    }


def _fallback_geometry(image_path: str | Path, width: int, height: int, reason: str) -> dict[str, Any]:
    return {
        "metadata": {"image_path": str(image_path), "image_width": width, "image_height": height, "timestamp": utc_now(), "fallback_reason": reason},
        "wall_plane": {"equation_abcd": [0, 0, 1, 0], "normal": [0, 0, 1], "d": 0, "quality": {"passed": False, "reason": reason}},
        "scale": None,
        "homography": {"matrix_3x3": None, "reprojection_error_px": None, "src_corners": None, "dst_rect_size": None},
        "gates_passed": {"plane_fit": False, "scale_available": False, "homography_valid": False},
    }


def _synthetic_wall_detection(width: int, height: int, door: dict[str, Any] | None) -> dict[str, Any]:
    mask = np.ones((height, width), dtype=np.uint8) * 255
    if door is not None:
        x1, y1, x2, y2 = [int(round(v)) for v in door["box_xyxy"]]
        pad = max(8, int(width * 0.025))
        mask[max(0, y1 - pad) : min(height, y2 + pad), max(0, x1 - pad) : min(width, x2 + pad)] = 0
    mask[: int(height * 0.05), :] = 0
    mask[int(height * 0.92) :, :] = 0
    return {
        "id": -1,
        "phrase": "elevator wall",
        "score": 0.25,
        "box_xyxy": [0.0, 0.0, float(width - 1), float(height - 1)],
        "box_xywh": [0.0, 0.0, float(width - 1), float(height - 1)],
        "box_area": float(width * height),
        "mask": {"size": [height, width], "counts": _mask_to_counts(mask > 127)},
    }


def _mask_to_counts(mask: np.ndarray) -> list[int]:
    flat = mask.astype(bool).flatten(order="F").astype(np.uint8)
    diffs = np.diff(np.concatenate([[0], flat, [0]]))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    counts: list[int] = []
    prev_end = 0
    for start, end in zip(starts, ends):
        counts.append(int(start - prev_end))
        counts.append(int(end - start))
        prev_end = end
    return counts
