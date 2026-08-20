from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from fastapi import FastAPI
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageEnhance
from pydantic import BaseModel

from input_validation import validate_elevator_or_cop_upload, validate_input_image

app = FastAPI()
PIPELINE_LOCK = threading.Lock()
FIRERED_LOCK = threading.Lock()
FIRERED_LOCK_PATH = Path(os.environ.get("FIRERED_REPIN_LOCK_PATH", "/tmp/kone_firered_repin.lock"))

@contextmanager
def firered_repin_lock():
    FIRERED_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FIRERED_LOCK:
        with FIRERED_LOCK_PATH.open("w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)



def _run_pipeline_in_process(config_path: Path) -> None:
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from src.pipeline import run as run_pipeline

    run_pipeline(config_path)


class ProjectPayload(BaseModel):
    session_id: str
    project_id: str
    project_name: str | None = None
    storage_dir: str
    selected_components: list[str] | None = None
    component_assets: dict[str, str] | None = None
    environments: list[str] | None = None
    video_options: dict[str, Any] | None = None
    transform: dict[str, Any] | None = None
    transforms: list[dict[str, Any]] | None = None
    mask_data_url: str | None = None
    source_version: int | None = None
    source_base_mode: str | None = None


def write_status(storage_dir: str, data: dict[str, Any]) -> None:
    path = Path(storage_dir) / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"status.{os.getpid()}.{time.time_ns()}.tmp.json")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for _ in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.05)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.unlink(missing_ok=True)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def workspace_root() -> Path:
    return repo_root().parent


def selected_component_asset_paths(component_assets: dict[str, str] | None) -> dict[str, str]:
    default_dir = workspace_root() / "Frontend" / "kone-ui-master" / "public" / "components"
    default_files = {
        "ceiling": default_dir / "elevator-interior" / "Art Deco.png",
        "kds": default_dir / "lci" / "KDS90" / "Landing Call Indicator Flush - Up.png",
        "dcs1020": default_dir / "lci" / "DCS1020" / "Pedestal Mounted DOP KSP1068.png",
        "lci": default_dir / "lci.png",
        "door": default_dir / "door" / "Plain Stainless Steel Door.png",
        "cop": default_dir / "cop" / "Flush COP.png",
    }
    resolved: dict[str, str] = {}
    for component, default_path in default_files.items():
        raw = (component_assets or {}).get(component)
        candidates: list[Path] = []
        if raw and raw.startswith("/components/"):
            candidates.append(workspace_root() / "Frontend" / "kone-ui-master" / "public" / raw.lstrip("/"))
        candidates.append(default_path)
        for candidate in candidates:
            if candidate.exists():
                resolved[component] = str(candidate)
                break
    return resolved


def _load_pipeline_config(pipeline_dir: Path | None = None) -> dict[str, Any]:
    cfg_path = (pipeline_dir / "config.yaml") if pipeline_dir else None
    if cfg_path and cfg_path.exists():
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return yaml.safe_load((repo_root() / "config.yaml").read_text(encoding="utf-8"))


def _decode_mask_data_url(mask_data_url: str, image_size: tuple[int, int]) -> np.ndarray:
    if not mask_data_url or not isinstance(mask_data_url, str):
        raise ValueError("Magic eraser mask is required")
    payload = mask_data_url.split(",", 1)[1] if "," in mask_data_url else mask_data_url
    try:
        raw = base64.b64decode(payload)
    except Exception as exc:
        raise ValueError("Magic eraser mask is not valid base64") from exc
    mask_image = Image.open(io.BytesIO(raw)).convert("L")
    if mask_image.size != image_size:
        mask_image = mask_image.resize(image_size, Image.Resampling.NEAREST)
    mask = np.asarray(mask_image, dtype=np.uint8)
    mask = np.where(mask > 12, 255, 0).astype(np.uint8)
    if int(np.count_nonzero(mask)) < 8:
        raise ValueError("Paint over the object before running Magic Eraser")
    return mask


def _source_image_for_repin(storage: Path, preview_dir: Path, source_version: int, source_base_mode: str) -> Path:
    if source_base_mode == "original":
        source_candidates = [
            storage / "uploads" / "input.jpg",
            storage / "uploads" / f"repin_source_v{source_version}.png",
            preview_dir / f"final_output_v{source_version}.png",
            preview_dir / "final_output.png",
        ]
    else:
        source_candidates = [
            storage / "uploads" / f"repin_source_v{source_version}.png",
            preview_dir / f"final_output_v{source_version}.png",
            preview_dir / "final_output.png",
            storage / "uploads" / "input.jpg",
        ]
    source_image_path = next((candidate for candidate in source_candidates if candidate.exists()), None)
    if source_image_path is None:
        raise FileNotFoundError(f"Repin source Version {source_version} was not found")
    return source_image_path


def _has_manual_eraser_background(transform: dict[str, Any]) -> bool:
    history = transform.get("eraserHistory")
    return (
        (isinstance(history, list) and len(history) > 1)
        or bool(transform.get("magicEraserApplied") and transform.get("repinBackgroundPath"))
    )


def _has_user_eraser_background(transform: dict[str, Any]) -> bool:
    history = transform.get("eraserHistory")
    return (
        (isinstance(history, list) and len(history) > 1)
        or bool(transform.get("magicEraserApplied") and transform.get("repinBackgroundPath"))
    )


def _should_apply_repin_background(transform: dict[str, Any]) -> bool:
    component_key = str(transform.get("componentKey") or transform.get("componentType") or "").lower()
    source_component = str(transform.get("sourceVersionComponent") or "").lower()
    return _has_user_eraser_background(transform) or bool(component_key and source_component == component_key)


def _composite_repin_background_region(base_image: Image.Image, background_path: Path, component_mask: Image.Image | None) -> Image.Image:
    if component_mask is None or not background_path.exists():
        return base_image
    erased_image = Image.open(background_path).convert("RGB")
    if erased_image.size != base_image.size:
        erased_image = erased_image.resize(base_image.size, Image.Resampling.LANCZOS)
    mask = component_mask.convert("L")
    if mask.size != base_image.size:
        mask = mask.resize(base_image.size, Image.Resampling.NEAREST)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=2))
    result = base_image.convert("RGB").copy()
    result.paste(erased_image, (0, 0), mask)
    return result


def _original_bbox_mask_for_transform(transform: dict[str, Any], image_size: tuple[int, int]) -> Image.Image | None:
    original_bbox = transform.get("originalBbox")
    if not isinstance(original_bbox, list) or len(original_bbox) != 4:
        return None
    try:
        bbox_values = [float(value) for value in original_bbox]
    except (TypeError, ValueError):
        return None

    width, height = image_size
    source_width = _clamp_float(transform.get("originalImageWidth"), width)
    source_height = _clamp_float(transform.get("originalImageHeight"), height)
    scale_x = width / max(1.0, source_width)
    scale_y = height / max(1.0, source_height)
    x1 = max(0, min(width - 1, int(np.floor(bbox_values[0] * scale_x))))
    y1 = max(0, min(height - 1, int(np.floor(bbox_values[1] * scale_y))))
    x2 = max(x1 + 1, min(width, int(np.ceil(bbox_values[2] * scale_x))))
    y2 = max(y1 + 1, min(height, int(np.ceil(bbox_values[3] * scale_y))))
    mask = Image.new("L", image_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((x1, y1, x2, y2), fill=255)
    if min(x2 - x1, y2 - y1) > 8:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(1, min(x2 - x1, y2 - y1) // 80)))
    return mask


def _composite_repin_background_original_footprint(base_image: Image.Image, background_path: Path, transform: dict[str, Any]) -> Image.Image:
    mask = _original_bbox_mask_for_transform(transform, base_image.size)
    if mask is None or not background_path.exists():
        return base_image
    restored_image = Image.open(background_path).convert("RGB")
    if restored_image.size != base_image.size:
        restored_image = restored_image.resize(base_image.size, Image.Resampling.LANCZOS)
    result = base_image.convert("RGB").copy()
    result.paste(restored_image, (0, 0), mask)
    return result


def _restore_original_repin_footprint(base_image: Image.Image, storage: Path, transform: dict[str, Any]) -> Image.Image:
    original_path = storage / "uploads" / "input.jpg"
    original_bbox = transform.get("originalBbox")
    if not original_path.exists() or not isinstance(original_bbox, list) or len(original_bbox) != 4:
        return base_image

    try:
        bbox_values = [float(value) for value in original_bbox]
    except (TypeError, ValueError):
        return base_image

    original_image = Image.open(original_path).convert("RGB")
    if original_image.size != base_image.size:
        original_image = original_image.resize(base_image.size, Image.Resampling.LANCZOS)

    width, height = base_image.size
    source_width = _clamp_float(transform.get("originalImageWidth"), width)
    source_height = _clamp_float(transform.get("originalImageHeight"), height)
    scale_x = width / max(1.0, source_width)
    scale_y = height / max(1.0, source_height)

    x1 = max(0, min(width - 1, int(np.floor(bbox_values[0] * scale_x))))
    y1 = max(0, min(height - 1, int(np.floor(bbox_values[1] * scale_y))))
    x2 = max(x1 + 1, min(width, int(np.ceil(bbox_values[2] * scale_x))))
    y2 = max(y1 + 1, min(height, int(np.ceil(bbox_values[3] * scale_y))))

    result = base_image.convert("RGB")
    patch = original_image.crop((x1, y1, x2, y2))
    mask = Image.new("L", patch.size, 255)
    if min(patch.size) > 8:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=max(1, min(patch.size) // 80)))
    result.paste(patch, (x1, y1), mask)
    return result


def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default



def _transform_points_px(transform: dict[str, Any], image_size: tuple[int, int]) -> list[tuple[float, float]] | None:
    points = transform.get("points")
    if not isinstance(points, list) or len(points) != 4:
        return None

    width, height = image_size
    coordinate_space = str(transform.get("coordinateSpace") or "").lower()
    if coordinate_space == "pixels" or transform.get("imageWidth") or transform.get("imageHeight"):
        source_width = _clamp_float(transform.get("imageWidth"), width)
        source_height = _clamp_float(transform.get("imageHeight"), height)
        scale_x = width / max(1.0, source_width)
        scale_y = height / max(1.0, source_height)
    else:
        scale_x = width / 100.0
        scale_y = height / 100.0

    px_points: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, dict):
            return None
        x = _clamp_float(point.get("x")) * scale_x
        y = _clamp_float(point.get("y")) * scale_y
        px_points.append((float(np.clip(x, 0, width)), float(np.clip(y, 0, height))))

    xs = [point[0] for point in px_points]
    ys = [point[1] for point in px_points]
    if max(xs) - min(xs) < 1 or max(ys) - min(ys) < 1:
        return None
    return px_points


def _points_bbox_px(points: list[tuple[float, float]], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x1 = max(0, min(width - 1, int(np.floor(min(xs)))))
    y1 = max(0, min(height - 1, int(np.floor(min(ys)))))
    x2 = max(x1 + 1, min(width, int(np.ceil(max(xs)))))
    y2 = max(y1 + 1, min(height, int(np.ceil(max(ys)))))
    return x1, y1, x2, y2

def _segment_angle_degrees(start: tuple[float, float], end: tuple[float, float]) -> float:
    return float(np.degrees(np.arctan2(end[1] - start[1], end[0] - start[0])))


def _segment_length(start: tuple[float, float], end: tuple[float, float]) -> float:
    return float(np.hypot(end[0] - start[0], end[1] - start[1]))


def _component_key_from_transform(transform: dict[str, Any] | None) -> str:
    if not isinstance(transform, dict):
        return ""
    return str(transform.get("componentKey") or transform.get("componentType") or "").lower()


def _is_lci_or_cop_transform(transform: dict[str, Any] | None) -> bool:
    component_key = _component_key_from_transform(transform)
    return component_key in {"kds", "dcs1020", "lci", "cop"} or "landing call" in component_key or "control operating" in component_key


def _is_lci_transform(transform: dict[str, Any] | None) -> bool:
    component_key = _component_key_from_transform(transform)
    return component_key in {"kds", "dcs1020", "lci"} or "landing call" in component_key


def _wants_perspective_refine(transform: dict[str, Any] | None) -> bool:
    if not isinstance(transform, dict):
        return False
    raw_feedback = transform.get("feedbackOptions")
    if isinstance(raw_feedback, list):
        keys = {str(item).strip() for item in raw_feedback if str(item).strip()}
    else:
        key = str(transform.get("feedbackOption") or "").strip()
        keys = {key} if key else set()
    return bool(keys.intersection({"perspective_depth", "bad_perspective"}))

def _scene_line_angles_from_image(image: Image.Image) -> tuple[float | None, float | None]:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    if gray.size == 0:
        return None, None

    height, width = gray.shape[:2]
    scale = min(1.0, 900.0 / max(1, max(width, height)))
    if scale < 1.0:
        gray = cv2.resize(
            gray,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 60, 160)
    min_line_length = max(24, int(min(edges.shape[:2]) * 0.16))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=42,
        minLineLength=min_line_length,
        maxLineGap=12,
    )
    if lines is None:
        return None, None

    horizontal_angles: list[float] = []
    vertical_leans: list[float] = []
    for line in np.asarray(lines).reshape(-1, 4)[:180]:
        x1, y1, x2, y2 = [float(value) for value in line]
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < min_line_length:
            continue
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if abs(angle) <= 35.0 or abs(abs(angle) - 180.0) <= 35.0:
            horizontal_angles.append(((angle + 90.0) % 180.0) - 90.0)
        elif 55.0 <= abs(angle) <= 125.0:
            vertical_leans.append(angle - 90.0 if angle > 0.0 else angle + 90.0)

    horizontal = float(np.median(horizontal_angles)) if len(horizontal_angles) >= 2 else None
    vertical = float(np.median(vertical_leans)) if len(vertical_leans) >= 2 else None
    return horizontal, vertical


def _scene_line_perspective_prompt(image_path: Path) -> str:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None or image.size == 0:
        return ""

    height, width = image.shape[:2]
    scale = min(1.0, 900.0 / max(1, max(width, height)))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    blurred = cv2.GaussianBlur(image, (3, 3), 0)
    edges = cv2.Canny(blurred, 60, 160)
    min_line_length = max(24, int(min(edges.shape[:2]) * 0.18))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180.0,
        threshold=45,
        minLineLength=min_line_length,
        maxLineGap=12,
    )
    if lines is None:
        return ""

    horizontal_angles: list[float] = []
    vertical_leans: list[float] = []
    for line in np.asarray(lines).reshape(-1, 4)[:160]:
        x1, y1, x2, y2 = [float(value) for value in line]
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < min_line_length:
            continue
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if abs(angle) <= 35.0 or abs(abs(angle) - 180.0) <= 35.0:
            normalized = ((angle + 90.0) % 180.0) - 90.0
            horizontal_angles.append(normalized)
        elif 55.0 <= abs(angle) <= 125.0:
            lean = angle - 90.0 if angle > 0.0 else angle + 90.0
            vertical_leans.append(lean)

    parts: list[str] = []
    if len(horizontal_angles) >= 2:
        parts.append(f"dominant horizontal architectural edges run at about {float(np.median(horizontal_angles)):.1f} degrees")
    if len(vertical_leans) >= 2:
        parts.append(f"dominant vertical architectural edges lean about {float(np.median(vertical_leans)):.1f} degrees from upright")
    if not parts:
        return ""

    return (
        " Scene line analysis from the FireRed input crop estimates that "
        + " and ".join(parts)
        + ". Match these observed wall, doorway, floor, ceiling and elevator edge directions during refinement."
    )

def _perspective_analysis_prompt(
    transform: dict[str, Any],
    image_size: tuple[int, int],
    crop_box: tuple[int, int, int, int] | None = None,
) -> str:
    points = _transform_points_px(transform, image_size)
    if points is None:
        return (
            " Before refining, analyze the original photograph camera viewpoint from the visible elevator, wall, doorway, floor, ceiling and component edges. "
            "Preserve the same camera roll, tilt, perspective convergence and viewing angle; do not make the component or nearby elevator architecture straight-on."
        )

    tl, tr, br, bl = points
    top_angle = _segment_angle_degrees(tl, tr)
    bottom_angle = _segment_angle_degrees(bl, br)
    left_angle = _segment_angle_degrees(tl, bl)
    right_angle = _segment_angle_degrees(tr, br)
    top_width = max(1.0, _segment_length(tl, tr))
    bottom_width = max(1.0, _segment_length(bl, br))
    left_height = max(1.0, _segment_length(tl, bl))
    right_height = max(1.0, _segment_length(tr, br))
    horizontal_roll = (top_angle + bottom_angle) / 2.0
    vertical_lean = ((left_angle - 90.0) + (right_angle - 90.0)) / 2.0
    width_ratio = top_width / bottom_width
    height_ratio = right_height / left_height

    if width_ratio > 1.08:
        depth_hint = "the lower edge recedes from camera more than the upper edge"
    elif width_ratio < 0.92:
        depth_hint = "the upper edge recedes from camera more than the lower edge"
    else:
        depth_hint = "top and bottom depth scale are nearly even"

    if height_ratio > 1.08:
        side_hint = "the left side appears farther away and the right side appears closer"
    elif height_ratio < 0.92:
        side_hint = "the right side appears farther away and the left side appears closer"
    else:
        side_hint = "left and right side depth scale are nearly even"

    if crop_box is not None:
        crop_x, crop_y, _, _ = crop_box
        local_points = [(x - crop_x, y - crop_y) for x, y in points]
        coord_label = "crop-local"
    else:
        local_points = points
        coord_label = "image"

    point_text = ", ".join(
        f"({round(x, 1)}, {round(y, 1)})" for x, y in local_points
    )

    return (
        " Before refining, perform a perspective check from the four Repin corner pins. "
        f"The selected plane corners in {coord_label} coordinates are top-left, top-right, bottom-right, bottom-left: {point_text}. "
        f"Respect this plane exactly: average horizontal roll is {horizontal_roll:.1f} degrees, vertical lean from upright is {vertical_lean:.1f} degrees, "
        f"top-to-bottom scale ratio is {width_ratio:.2f}, and right-to-left side scale ratio is {height_ratio:.2f}. "
        f"This means {depth_hint}; {side_hint}. "
        "All refined edges, bevels, highlights, shadows, button/display face, handrail/contact cues and local wall seams must follow these same vanishing directions. "
        "Do not level, straighten, front-face, orthographically redraw, center-align, or catalog-render the component; keep it photographed from the same tilted camera viewpoint as the source image."
    )

def _quad_matches_rect(points: list[tuple[float, float]], image_size: tuple[int, int], tolerance: float = 1.5) -> bool:
    x1, y1, x2, y2 = _points_bbox_px(points, image_size)
    rect = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return all(
        abs(point[0] - rect_point[0]) <= tolerance and abs(point[1] - rect_point[1]) <= tolerance
        for point, rect_point in zip(points, rect)
    )


def _fit_quad_to_bbox(
    points: list[tuple[float, float]],
    bbox: tuple[int, int, int, int],
) -> list[tuple[float, float]]:
    x1, y1, x2, y2 = bbox
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    raw_x1, raw_x2 = min(xs), max(xs)
    raw_y1, raw_y2 = min(ys), max(ys)
    scale_x = (x2 - x1) / max(1.0, raw_x2 - raw_x1)
    scale_y = (y2 - y1) / max(1.0, raw_y2 - raw_y1)
    return [
        (x1 + (point[0] - raw_x1) * scale_x, y1 + (point[1] - raw_y1) * scale_y)
        for point in points
    ]



def _lci_wall_plane_quad(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    horizontal_angle: float,
    vertical_lean: float,
) -> tuple[list[tuple[float, float]], float, float] | None:
    x1, y1, x2, y2 = bbox
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    center_x = (x1 + x2) * 0.5
    side_position = float(np.clip((center_x / max(1.0, image_size[0]) - 0.5) * 2.0, -1.0, 1.0))
    line_strength = max(abs(horizontal_angle) / 14.0, abs(vertical_lean) / 12.0)
    plane_strength = float(np.clip(max(line_strength, abs(side_position) * 0.55), 0.0, 1.0))
    if plane_strength < 0.22:
        return None

    side = 1.0 if side_position >= 0.0 else -1.0
    horizontal_shift = float(np.clip(np.tan(np.radians(horizontal_angle)) * width, -height * 0.18, height * 0.18))
    vertical_shift = float(np.clip(np.tan(np.radians(vertical_lean)) * height, -width * 0.16, width * 0.16))
    side_taper = float(np.clip(height * (0.025 + 0.065 * plane_strength), height * 0.0, height * 0.095))

    if side >= 0.0:
        raw_quad = [
            (float(x1), float(y1)),
            (float(x2), float(y1) + side_taper + horizontal_shift),
            (float(x2) + vertical_shift, float(y2) - side_taper + horizontal_shift),
            (float(x1) + vertical_shift, float(y2)),
        ]
    else:
        raw_quad = [
            (float(x1), float(y1) + side_taper),
            (float(x2), float(y1) + horizontal_shift),
            (float(x2) + vertical_shift, float(y2) + horizontal_shift),
            (float(x1) + vertical_shift, float(y2) - side_taper),
        ]

    return _fit_quad_to_bbox(raw_quad, bbox), side_position, plane_strength


def _with_lci_cop_homography_points(transform: dict[str, Any], source_image: Image.Image) -> dict[str, Any]:
    if not _is_lci_or_cop_transform(transform):
        return transform

    image_size = source_image.size
    existing_points = _transform_points_px(transform, image_size)
    if existing_points is not None and not _quad_matches_rect(existing_points, image_size):
        return transform

    bbox = _points_bbox_px(existing_points, image_size) if existing_points is not None else _transform_box_px(transform, image_size)
    x1, y1, x2, y2 = bbox
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    if width < 8 or height < 8:
        return transform

    crop_box = _expanded_crop_box(bbox, image_size, pad_ratio=3.0)
    local_image = source_image.crop(crop_box)
    horizontal_angle, vertical_lean = _scene_line_angles_from_image(local_image)
    if horizontal_angle is None or vertical_lean is None:
        full_horizontal, full_vertical = _scene_line_angles_from_image(source_image)
        horizontal_angle = horizontal_angle if horizontal_angle is not None else full_horizontal
        vertical_lean = vertical_lean if vertical_lean is not None else full_vertical

    horizontal_angle = float(np.clip(horizontal_angle or 0.0, -14.0, 14.0))
    vertical_lean = float(np.clip(vertical_lean or 0.0, -12.0, 12.0))

    if _is_lci_transform(transform):
        plane = _lci_wall_plane_quad(bbox, image_size, horizontal_angle, vertical_lean)
        if plane is None:
            center_x = (x1 + x2) * 0.5
            side_position = float(np.clip((center_x / max(1.0, image_size[0]) - 0.5) * 2.0, -1.0, 1.0))
            plane_strength = max(abs(horizontal_angle) / 14.0, abs(vertical_lean) / 12.0)
            fitted_quad = None
        else:
            fitted_quad, side_position, plane_strength = plane
        internal_strength = float(np.clip(max(0.58, plane_strength, abs(side_position) * 0.72), 0.0, 0.95))
        next_transform = {**transform}
        next_transform.update({
            "autoLCIInternalPerspective": True,
            "autoLCISidePosition": round(side_position, 3),
            "autoLCIInternalPerspectiveStrength": round(internal_strength, 3),
            "autoPerspectiveHorizontalAngle": round(horizontal_angle, 2),
            "autoPerspectiveVerticalLean": round(vertical_lean, 2),
        })
        if fitted_quad is not None:
            next_transform.update({
                "points": [{"x": round(float(x), 1), "y": round(float(y), 1)} for x, y in fitted_quad],
                "coordinateSpace": "pixels",
                "imageWidth": image_size[0],
                "imageHeight": image_size[1],
                "autoLCIWallPlaneHomography": True,
            })
        return next_transform

    if abs(horizontal_angle) < 0.8 and abs(vertical_lean) < 0.8:
        return transform

    horizontal_shift = float(np.tan(np.radians(horizontal_angle)) * width)
    vertical_shift = float(np.tan(np.radians(vertical_lean)) * height)
    raw_quad = [
        (float(x1), float(y1)),
        (float(x2), float(y1) + horizontal_shift),
        (float(x2) + vertical_shift, float(y2) + horizontal_shift),
        (float(x1) + vertical_shift, float(y2)),
    ]
    fitted_quad = _fit_quad_to_bbox(raw_quad, bbox)
    next_transform = {**transform}
    next_transform.update({
        "points": [{"x": round(float(x), 1), "y": round(float(y), 1)} for x, y in fitted_quad],
        "coordinateSpace": "pixels",
        "imageWidth": image_size[0],
        "imageHeight": image_size[1],
        "autoPerspectiveHomography": True,
        "autoPerspectiveHorizontalAngle": round(horizontal_angle, 2),
        "autoPerspectiveVerticalLean": round(vertical_lean, 2),
    })
    return next_transform


def _transform_box_px(transform: dict[str, Any], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    coordinate_space = str(transform.get("coordinateSpace") or "").lower()
    if coordinate_space == "pixels" or transform.get("imageWidth") or transform.get("imageHeight"):
        source_width = _clamp_float(transform.get("imageWidth"), width)
        source_height = _clamp_float(transform.get("imageHeight"), height)
        scale_x = width / max(1.0, source_width)
        scale_y = height / max(1.0, source_height)
        x1 = round(_clamp_float(transform.get("x")) * scale_x)
        y1 = round(_clamp_float(transform.get("y")) * scale_y)
        box_w = round(_clamp_float(transform.get("width"), 10.0) * scale_x)
        box_h = round(_clamp_float(transform.get("height"), 10.0) * scale_y)
        x2 = x1 + box_w
        y2 = y1 + box_h
    else:
        x1 = round(_clamp_float(transform.get("x")) / 100.0 * width)
        y1 = round(_clamp_float(transform.get("y")) / 100.0 * height)
        x2 = round((_clamp_float(transform.get("x")) + _clamp_float(transform.get("width"), 10.0)) / 100.0 * width)
        y2 = round((_clamp_float(transform.get("y")) + _clamp_float(transform.get("height"), 10.0)) / 100.0 * height)
    x1, y1 = max(0, min(width - 1, x1)), max(0, min(height - 1, y1))
    x2, y2 = max(x1 + 1, min(width, x2)), max(y1 + 1, min(height, y2))
    return x1, y1, x2, y2


def _component_image_for_transform(transform: dict[str, Any], component_assets: dict[str, str] | None) -> Path:
    component_key = str(transform.get("componentKey") or transform.get("componentType") or "component").lower()
    editable_layer = transform.get("editableLayerPath")
    if editable_layer and Path(str(editable_layer)).exists():
        return Path(str(editable_layer))
    asset_path = selected_component_asset_paths(component_assets).get(component_key)
    if asset_path and Path(asset_path).exists():
        return Path(asset_path)
    raise ValueError(
        f"Repin requires an editable layer or component asset for {component_key}. "
        "Regenerate the automatic preview once so the selected component can be repinned directly."
    )


def _warp_component(component: Image.Image, transform: dict[str, Any], image_size: tuple[int, int]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    quad_points = _transform_points_px(transform, image_size)
    if quad_points is not None:
        x1, y1, x2, y2 = _points_bbox_px(quad_points, image_size)
        target_w, target_h = x2 - x1, y2 - y1
        if target_w <= 1 or target_h <= 1:
            raise ValueError("Repin transform points are too small")
        component_rgba = _lci_internal_perspective_component(component, transform)
        src_points = np.array(
            [
                [0, 0],
                [component_rgba.width, 0],
                [component_rgba.width, component_rgba.height],
                [0, component_rgba.height],
            ],
            dtype=np.float32,
        )
        dst_points = np.array(
            [[point[0] - x1, point[1] - y1] for point in quad_points],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(src_points, dst_points)
        warped_array = cv2.warpPerspective(
            np.asarray(component_rgba),
            matrix,
            (target_w, target_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
        return Image.fromarray(warped_array, "RGBA"), (x1, y1, x2, y2)

    x1, y1, x2, y2 = _transform_box_px(transform, image_size)
    target_w, target_h = x2 - x1, y2 - y1
    slot = component.convert("RGBA").resize((target_w, target_h), Image.Resampling.LANCZOS)
    slot = _lci_internal_perspective_component(slot, transform)

    skew_x = _clamp_float(transform.get("skewX"))
    skew_y = _clamp_float(transform.get("skewY"))
    if abs(skew_x) > 0.01 or abs(skew_y) > 0.01:
        pad_x = int(abs(skew_x) / 100.0 * target_h) + 8
        pad_y = int(abs(skew_y) / 100.0 * target_w) + 8
        padded = Image.new("RGBA", (slot.width + pad_x * 2, slot.height + pad_y * 2), (0, 0, 0, 0))
        padded.paste(slot, (pad_x, pad_y), slot)
        slot = padded.transform(
            padded.size,
            Image.Transform.AFFINE,
            (1, -skew_x / 100.0, 0, -skew_y / 100.0, 1, 0),
            resample=Image.Resampling.BICUBIC,
        )
        x1 -= pad_x
        y1 -= pad_y
        x2 = x1 + slot.width
        y2 = y1 + slot.height

    rotation = _clamp_float(transform.get("rotation"))
    if abs(rotation) > 0.01:
        slot = slot.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        x1 = round(cx - slot.width / 2)
        y1 = round(cy - slot.height / 2)
        x2 = x1 + slot.width
        y2 = y1 + slot.height

    return slot, (x1, y1, x2, y2)


def _lci_internal_perspective_component(component: Image.Image, transform: dict[str, Any]) -> Image.Image:
    comp = component.convert("RGBA")
    if not _is_lci_transform(transform):
        return comp

    # LCI is a thin wall-mounted faceplate. The outer homography carries camera
    # perspective; adding an internal side face creates the dark slab/reflection artifact.
    return comp


def _add_lci_plane_depth(component: Image.Image, transform: dict[str, Any]) -> Image.Image:
    if not _is_lci_transform(transform):
        return component

    comp = component.convert("RGBA")
    alpha_image = comp.getchannel("A")
    if alpha_image.getbbox() is None:
        return comp

    rgb = np.asarray(comp.convert("RGB"), dtype=np.float32)
    width, height = comp.size
    x_ramp = np.linspace(0.98, 1.02, width, dtype=np.float32)[None, :, None]
    y_ramp = np.linspace(1.015, 0.985, height, dtype=np.float32)[:, None, None]
    rgb = np.clip(rgb * x_ramp * y_ramp, 0.0, 255.0).astype(np.uint8)
    return Image.merge("RGBA", (*Image.fromarray(rgb, "RGB").split(), alpha_image))


def _match_component_to_scene(component: Image.Image, scene_crop: Image.Image) -> Image.Image:
    comp = component.convert("RGBA")
    alpha = np.asarray(comp.getchannel("A"), dtype=np.float32) / 255.0
    if float(alpha.max()) <= 0.0:
        return comp

    comp_rgb = np.asarray(comp.convert("RGB"), dtype=np.float32)
    scene_rgb = np.asarray(scene_crop.convert("RGB").resize(comp.size, Image.Resampling.BICUBIC), dtype=np.float32)
    visible = alpha > 0.08
    if int(np.count_nonzero(visible)) < 8:
        return comp

    comp_luma = (comp_rgb[..., 0] * 0.299 + comp_rgb[..., 1] * 0.587 + comp_rgb[..., 2] * 0.114)[visible]
    scene_luma = (scene_rgb[..., 0] * 0.299 + scene_rgb[..., 1] * 0.587 + scene_rgb[..., 2] * 0.114)[visible]
    gain = float(np.clip(np.median(scene_luma) / max(1.0, np.median(comp_luma)), 0.72, 1.22))
    scene_mean = scene_rgb[visible].mean(axis=0)
    comp_mean = comp_rgb[visible].mean(axis=0)
    balanced = comp_rgb * gain
    balanced = balanced * 0.88 + np.clip(balanced + (scene_mean - comp_mean) * 0.16, 0, 255) * 0.12

    light_x = np.linspace(0.96, 1.04, comp.width, dtype=np.float32)[None, :, None]
    light_y = np.linspace(1.03, 0.95, comp.height, dtype=np.float32)[:, None, None]
    balanced = np.clip(balanced * light_x * light_y, 0, 255).astype(np.uint8)
    return Image.merge("RGBA", (*Image.fromarray(balanced, "RGB").split(), comp.getchannel("A")))


def _soften_component_alpha(component: Image.Image) -> Image.Image:
    comp = component.convert("RGBA")
    alpha = comp.getchannel("A")
    if alpha.getbbox() is None:
        return comp
    edge = alpha.filter(ImageFilter.GaussianBlur(radius=0.8))
    return Image.merge("RGBA", (*comp.convert("RGB").split(), edge))


def _paste_with_contact_shadow(
    result: Image.Image,
    component: Image.Image,
    paste_xy: tuple[int, int],
    shadow_strength: float = 0.34,
) -> None:
    alpha = component.getchannel("A")
    shadow = Image.new("RGBA", component.size, (0, 0, 0, 0))
    blur_radius = max(1, int(min(component.size) * (0.018 if shadow_strength <= 0.10 else 0.035)))
    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    shadow_alpha = shadow_alpha.point(lambda value: int(value * shadow_strength))
    shadow.putalpha(shadow_alpha)
    offset = max(1, int(min(component.size) * 0.014))
    result.alpha_composite(shadow, (paste_xy[0] + offset, paste_xy[1] + offset))
    result.paste(component, paste_xy, component)


def _place_manual_component(base_image: Image.Image, component_image: Image.Image, transform: dict[str, Any]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    result = base_image.convert("RGBA")
    warped, bbox = _warp_component(component_image, transform, base_image.size)
    x1, y1, x2, y2 = bbox
    paste_x, paste_y = max(0, x1), max(0, y1)
    crop_l, crop_t = max(0, -x1), max(0, -y1)
    crop_r, crop_b = warped.width - max(0, x2 - base_image.width), warped.height - max(0, y2 - base_image.height)
    if crop_r <= crop_l or crop_b <= crop_t:
        raise ValueError("Repin transform places the component outside the image")
    visible = warped.crop((crop_l, crop_t, crop_r, crop_b))
    scene_crop = base_image.crop((paste_x, paste_y, paste_x + visible.width, paste_y + visible.height))
    visible = _add_lci_plane_depth(visible, transform)
    visible = _soften_component_alpha(_match_component_to_scene(visible, scene_crop))
    _paste_with_contact_shadow(result, visible, (paste_x, paste_y), 0.055 if _is_lci_transform(transform) else 0.34)
    px_bbox = (paste_x, paste_y, paste_x + visible.width, paste_y + visible.height)
    return result.convert("RGB"), px_bbox


def _component_mask_for_transform(component_image: Image.Image, transform: dict[str, Any], image_size: tuple[int, int]) -> Image.Image:
    warped, bbox = _warp_component(component_image, transform, image_size)
    x1, y1, x2, y2 = bbox
    paste_x, paste_y = max(0, x1), max(0, y1)
    crop_l, crop_t = max(0, -x1), max(0, -y1)
    crop_r, crop_b = warped.width - max(0, x2 - image_size[0]), warped.height - max(0, y2 - image_size[1])
    mask = Image.new("L", image_size, 0)
    if crop_r <= crop_l or crop_b <= crop_t:
        return mask
    visible_alpha = warped.crop((crop_l, crop_t, crop_r, crop_b)).getchannel("A")
    mask.paste(visible_alpha, (paste_x, paste_y), visible_alpha)
    return mask


def _firered_prompt(transform: dict[str, Any], perspective_analysis: str = "") -> str:
    raw_feedback = transform.get("feedbackOptions")
    if isinstance(raw_feedback, list):
        feedback_keys = [str(item).strip() for item in raw_feedback if str(item).strip()]
    else:
        feedback_key = str(transform.get("feedbackOption") or "").strip()
        feedback_keys = [feedback_key] if feedback_key else []
    component = str(transform.get("componentKey") or transform.get("componentType") or "component")
    component_perspective_sentence = ""
    shadow_sentence = (
        "Create tight ambient occlusion directly along all four panel-to-wall seams. Add one clearly visible soft cast shadow on the wall opposite the dominant light source. The shadow must begin at the panel boundary, remain attached to the plate, be darkest near the mounting edge and gradually soften with distance. The shadow must follow the existing panel silhouette and perspective. Do not create a second rectangle, backing plate, border, frame, floating layer or duplicate panel."
    )
    if _is_lci_transform(transform):
        shadow_sentence = (
            "For the LCI, keep shadowing minimal: only a thin contact occlusion directly under the single panel edge. Do not create a large cast shadow, offset rectangle, translucent duplicate, backing plate, second LCI, glass slab, or floating ghost panel."
        )
    if _is_lci_or_cop_transform(transform):
        component_perspective_sentence = (
            " STRICT LCI/COP PERSPECTIVE RULES: treat this small panel with the same camera-pose rules used for the elevator interior and doors. "
            "The LCI/COP is not a front-view asset; it is a rigid object mounted on the wall plane described by the four Repin pins, surrounding wall seams, doorway lines, floor lines and ceiling lines. "
            "The panel face, display glass, button plates, arrows, labels, bevels, screw holes, brushed-metal grain, reflections and side thickness must all share that exact plane perspective. "
            "Keep only the outer four corner coordinates, footprint and silhouette fixed; inside that silhouette, perspective correction is required and has priority over preserving a straight upright product-render look. "
            "If the wall is tilted or viewed from the side, the display and buttons must also tilt, taper and foreshorten. Their top and bottom edges must follow the same vanishing direction as the wall-mounted panel, not the screen. "
            "Remove any flat sticker look, pasted rectangular face, upright catalog view, parallel-to-screen buttons, or straight-on display. "
            "Do not make the LCI/COP visually larger, move it, replace the model, invent extra controls, or change the chosen outer pin placement. "
            "Treat LCI as a thin flat faceplate mounted flush to the wall, not as a protruding box. "
            "Never create side thickness, a dark side face, cast slab, mirrored copy, reflected twin, translucent echo, opposite-side reflection, or duplicate LCI/COP anywhere outside the selected four-corner mask."
        )
    feedback_instructions = {
        "edge_alignment": "Sharpen only the local edge alignment: make the component boundary sit flush to the wall with clean seams, no halos, no ghost outline, and no duplicate border.",
        "perspective_depth": "Improve local perspective depth: align bevels, face plane, thickness cues, and contact geometry to the camera angle while preserving the exact selected silhouette.",
        "lighting_shadow": "Match lighting and shadows: use the scene light direction, soft contact shadows, ambient occlusion, wall bounce light, and matching color temperature.",
        "material_reflections": "Improve material and reflections: make metal, plastic, glass, and button surfaces match surrounding reflectivity, roughness, exposure, and black levels.",
        "seamless_blending": "Blend naturally into the scene: remove pasted/sticker appearance, match camera grain, mild blur, compression, contrast, and surrounding texture continuity.",
        "wrong_placement": "The user has manually corrected placement; preserve that exact placement and make the mounted result believable at this location.",
        "wrong_component": "Preserve the exact visible component layer and product design from the repin canvas; do not replace it with a different panel, buttons, display, or interior material.",
        "bad_perspective": "Improve only perspective realism around the selected geometry: edge alignment, bevel thickness, wall contact, and local camera perspective cues.",
        "bad_lighting_shadow": "Focus refinement on realistic local lighting, soft contact shadows, ambient occlusion, wall bounce light, reflections, and matching color temperature.",
        "poor_blending_unrealistic": "Focus refinement on edge blending, material integration, camera grain, reflection consistency, and removing any sticker-like appearance.",
    }
    selected_instructions = [feedback_instructions.get(key, key) for key in feedback_keys]
    feedback_sentence = " User selected FireRed corrections: " + " ".join(selected_instructions) if selected_instructions else ""
    return (
        f"Photorealistically integrate the already placed KONE {component} into this real elevator photograph. "
        "The geometry is user-approved: keep the exact x/y position, width, height, aspect ratio, rotation, skew, perspective corner alignment, buttons, display, arrows, numbers, labels, and product design. "
        "The panel must remain inside the exact selected bounding box; do not make it taller, wider, straighter, less skewed, less rotated, or shifted. "
        "Photorealistically finish the physical installation of the single existing elevator landing call indicator already placed on the wall. The Repin geometry is final and immutable: preserve the exact four corner coordinates, bounding box, width, height, aspect ratio, rotation, skew, perspective transform, silhouette and wall position. Do not move, resize, straighten, widen, extend, crop or warp the panel."

        "Improve realism only through physically consistent appearance. Match the panel exposure, brightness, black level, contrast, white balance and color temperature to the surrounding wall and elevator photograph. Remove the flat pasted-image appearance. Give the faceplate realistic coated-metal construction with restrained roughness, subtle vertical material variation, soft wall-color reflections, natural highlight rolloff, mild camera softness and matching photographic grain. Keep the black display dark and glossy without changing its contents."

        "Infer the dominant light direction from the surrounding wall, ceiling highlights and elevator reflections. Apply that same illumination continuously across the panel. Create a restrained highlight on the light-facing edges and darker shading on the opposite edges."
        "Express depth only through subtle tonal shading and restrained edge highlights entirely inside the existing panel silhouette. Do not generate visible thickness, extrusion, backing material, raised extensions or any pixels resembling another object outside the exact four panel corners."

        f"{shadow_sentence}"

        "Preserve exactly every existing button, display, arrow, number, icon, logo, label, spacing and product detail. Do not add, remove, repeat, merge, redraw or reinterpret any control. Do not alter the elevator, door, wall tiles, joints, signs, floor or surrounding architecture. There is exactly one LCI in the edited region."
        "Do not move, resize, redesign, replace, erase, or duplicate the component. Do not alter elevator doors, wall tiles, signs, floor, ceiling, or background geometry outside the immediate component edge transition. "
        "No new buttons, no redesigned display, no warped text, no extra panels, no floating sticker look."
        f"{perspective_analysis}"
        f"{component_perspective_sentence}"
        f"{feedback_sentence}"
    )


def _expanded_crop_box(bbox: tuple[int, int, int, int], image_size: tuple[int, int], pad_ratio: float = 0.85) -> tuple[int, int, int, int]:
    width, height = image_size
    x1, y1, x2, y2 = bbox
    pad = int(max(80, min(width, height) * 0.035, max(x2 - x1, y2 - y1) * pad_ratio))
    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(width, x2 + pad),
        min(height, y2 + pad),
    )


def _crop_blend_mask(size: tuple[int, int], feather_px: int = 32) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    feather = max(2, min(feather_px, width // 3, height // 3))
    draw.rectangle((feather, feather, width - feather - 1, height - feather - 1), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=max(1, feather // 2)))


def _preserve_component_geometry(
    source_crop: Image.Image,
    edited_crop: Image.Image,
    component_mask: Image.Image | None,
    crop_box: tuple[int, int, int, int],
) -> Image.Image:
    if component_mask is None:
        return edited_crop
    crop_mask = component_mask.crop(crop_box)
    if crop_mask.getbbox() is None:
        return edited_crop
    # Preserve only the inner product details.
    # FireRed remains responsible for the outer edge, wall contact and shadows.
    preserve_mask = crop_mask.filter(
        ImageFilter.GaussianBlur(radius=0.8)
    )
    return Image.composite(source_crop, edited_crop, preserve_mask)


def _component_refine_mask(
    crop_size: tuple[int, int],
    crop_box: tuple[int, int, int, int],
    bbox: tuple[int, int, int, int],
) -> Image.Image:
    width, height = crop_size
    x1, y1, x2, y2 = [int(v) for v in bbox]
    cx1, cy1, _, _ = crop_box
    local = (
        max(0, x1 - cx1),
        max(0, y1 - cy1),
        min(width, x2 - cx1),
        min(height, y2 - cy1),
    )
    if local[2] <= local[0] or local[3] <= local[1]:
        return _crop_blend_mask(crop_size, feather_px=16)

    panel_w = max(1, local[2] - local[0])
    panel_h = max(1, local[3] - local[1])
    edge_pad = int(os.environ.get("FIRERED_EDGE_PAD", max(10, min(28, min(panel_w, panel_h) * 0.08))))
    feather = int(os.environ.get("FIRERED_EDGE_FEATHER", max(8, min(20, edge_pad))))
    mask = Image.new("L", crop_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle(
        (
            max(0, local[0] - edge_pad),
            max(0, local[1] - edge_pad),
            min(width - 1, local[2] + edge_pad),
            min(height - 1, local[3] + edge_pad),
        ),
        fill=255,
    )
    return mask.filter(ImageFilter.GaussianBlur(radius=max(1, feather)))


def _component_outer_ring_mask(
    component_mask: Image.Image | None,
    crop_box: tuple[int, int, int, int],
    crop_size: tuple[int, int],
) -> Image.Image:
    if component_mask is None:
        return Image.new("L", crop_size, 0)

    crop_mask = component_mask.crop(crop_box).convert("L")

    if crop_mask.size != crop_size:
        crop_mask = crop_mask.resize(crop_size, Image.Resampling.LANCZOS)

    if crop_mask.getbbox() is None:
        return Image.new("L", crop_size, 0)

    ring_width = int(os.environ.get("FIRERED_RING_WIDTH", "31"))
    ring_blur = float(os.environ.get("FIRERED_RING_BLUR", "5.0"))

    ring_width = max(3, ring_width)
    if ring_width % 2 == 0:
        ring_width += 1

    expanded = crop_mask.filter(ImageFilter.MaxFilter(ring_width))
    ring = ImageChops.subtract(expanded, crop_mask)
    ring = ring.filter(
        ImageFilter.GaussianBlur(radius=max(0.5, ring_blur))
    )

    return ring

def _offset_mask_without_wrap(
    mask: Image.Image,
    offset_x: int,
    offset_y: int,
) -> Image.Image:
    shifted = Image.new("L", mask.size, 0)

    source_left = max(0, -offset_x)
    source_top = max(0, -offset_y)
    source_right = min(mask.width, mask.width - offset_x)
    source_bottom = min(mask.height, mask.height - offset_y)

    if source_right <= source_left or source_bottom <= source_top:
        return shifted

    destination_left = max(0, offset_x)
    destination_top = max(0, offset_y)

    shifted.paste(
        mask.crop(
            (
                source_left,
                source_top,
                source_right,
                source_bottom,
            )
        ),
        (destination_left, destination_top),
    )
    return shifted
def _harmonize_placed_component(
    placed_image: Image.Image,
    component_mask: Image.Image,
) -> Image.Image:
    image = placed_image.convert("RGB")
    mask = component_mask.convert("L")

    if mask.size != image.size:
        mask = mask.resize(image.size, Image.Resampling.LANCZOS)

    if mask.getbbox() is None:
        return image

    expanded = mask.filter(ImageFilter.MaxFilter(31))
    surrounding_ring = ImageChops.subtract(expanded, mask)

    image_array = np.asarray(image, dtype=np.float32)
    mask_array = np.asarray(mask, dtype=np.float32) / 255.0
    ring_array = np.asarray(surrounding_ring, dtype=np.float32) / 255.0

    component_pixels = image_array[mask_array > 0.75]
    surrounding_pixels = image_array[ring_array > 0.20]

    if len(component_pixels) < 32 or len(surrounding_pixels) < 32:
        return image

    component_mid = np.percentile(component_pixels, 50, axis=0)
    component_low = np.percentile(component_pixels, 10, axis=0)
    component_high = np.percentile(component_pixels, 90, axis=0)

    surrounding_mid = np.percentile(surrounding_pixels, 50, axis=0)
    surrounding_low = np.percentile(surrounding_pixels, 10, axis=0)
    surrounding_high = np.percentile(surrounding_pixels, 90, axis=0)

    component_range = np.maximum(component_high - component_low, 18.0)
    surrounding_range = np.maximum(surrounding_high - surrounding_low, 18.0)

    contrast_scale = np.clip(
        surrounding_range / component_range,
        0.88,
        1.14,
    )

    brightness_shift = np.clip(
        surrounding_mid - component_mid,
        -38.0,
        18.0,
    )

    corrected = (
        (image_array - component_mid) * contrast_scale
        + component_mid
        + brightness_shift
    )

    correction_strength = float(
        os.environ.get("COMPONENT_COLOR_MATCH_STRENGTH", "0.55")
    )
    correction_strength = float(np.clip(correction_strength, 0.0, 1.0))

    corrected = (
        image_array * (1.0 - correction_strength)
        + corrected * correction_strength
    )
    corrected = np.clip(corrected, 0.0, 255.0)

    feathered_mask = mask.filter(ImageFilter.GaussianBlur(radius=0.7))
    feathered_array = (
        np.asarray(feathered_mask, dtype=np.float32) / 255.0
    )[..., None]

    corrected_component = (
        image_array * (1.0 - feathered_array)
        + corrected * feathered_array
    )

    contact_ring = ImageChops.subtract(
        mask.filter(ImageFilter.MaxFilter(5)),
        mask,
    ).filter(
        ImageFilter.GaussianBlur(radius=1.0)
    )

    shadow_offset_x = int(
        os.environ.get("COMPONENT_SHADOW_OFFSET_X", "-5")
    )
    shadow_offset_y = int(
        os.environ.get("COMPONENT_SHADOW_OFFSET_Y", "7")
    )
    shadow_blur = float(
        os.environ.get("COMPONENT_SHADOW_BLUR", "3.5")
    )

    shifted_mask = _offset_mask_without_wrap(
        mask,
        shadow_offset_x,
        shadow_offset_y,
    )

    cast_shadow = ImageChops.subtract(
        shifted_mask,
        mask,
    ).filter(
        ImageFilter.GaussianBlur(radius=shadow_blur)
    )

    contact_strength = float(
        os.environ.get("COMPONENT_CONTACT_SHADOW_STRENGTH", "0.14")
    )
    cast_strength = float(
        os.environ.get("COMPONENT_CAST_SHADOW_STRENGTH", "0.26")
    )

    contact_strength = float(np.clip(contact_strength, 0.0, 0.35))
    cast_strength = float(np.clip(cast_strength, 0.0, 0.80))

    contact_array = (
        np.asarray(contact_ring, dtype=np.float32) / 255.0
    )[..., None]
    cast_array = (
        np.asarray(cast_shadow, dtype=np.float32) / 255.0
    )[..., None]

    corrected_component *= 1.0 - contact_array * contact_strength
    corrected_component *= 1.0 - cast_array * cast_strength

    return Image.fromarray(
        np.clip(corrected_component, 0.0, 255.0).astype(np.uint8),
        mode="RGB",
    )
def _firered_constrained_composite(
    source_crop: Image.Image,
    edited_crop: Image.Image,
    component_mask: Image.Image | None,
    crop_box: tuple[int, int, int, int],
    transform: dict[str, Any] | None = None,
) -> Image.Image:
    if component_mask is None:
        return source_crop

    crop_size = source_crop.size
    crop_mask = component_mask.crop(crop_box).convert("L")

    if crop_mask.size != crop_size:
        crop_mask = crop_mask.resize(
            crop_size,
            Image.Resampling.LANCZOS,
        )

    if crop_mask.getbbox() is None:
        return source_crop

    is_lci_transform = _is_lci_transform(transform)
    lci_cop_perspective_refine = _is_lci_or_cop_transform(transform) and _wants_perspective_refine(transform)

    face_strength = float(
        os.environ.get(
            "FIRERED_FACE_STRENGTH",
            "0.10" if is_lci_transform else ("0.68" if lci_cop_perspective_refine else "0.20"),
        )
    )
    shadow_strength = float(
        os.environ.get("FIRERED_SHADOW_STRENGTH", "0.0" if is_lci_transform else "0.70")
    )

    face_strength = float(np.clip(face_strength, 0.0, 0.14 if is_lci_transform else (0.78 if lci_cop_perspective_refine else 0.33)))
    shadow_strength = float(np.clip(shadow_strength, 0.0, 0.08 if is_lci_transform else 0.85))

    inner_face_mask = crop_mask.filter(
        ImageFilter.MinFilter(5)
    ).filter(
        ImageFilter.GaussianBlur(radius=0.8)
    )

    outer_ring_mask = _component_outer_ring_mask(
        component_mask,
        crop_box,
        crop_size,
    )
    if is_lci_transform:
        outer_ring_mask = crop_mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(radius=0.45))

    grayscale = source_crop.convert("L")
    grayscale_array = np.asarray(grayscale, dtype=np.uint8)
    component_array = np.asarray(crop_mask, dtype=np.uint8)

    component_values = grayscale_array[component_array > 128]
    if len(component_values) == 0:
        return source_crop

    dark_threshold = int(np.percentile(component_values, 38))

    dark_details = grayscale.point(
        lambda value: 255 if value <= dark_threshold else 0
    )
    dark_details = ImageChops.multiply(
        dark_details,
        crop_mask,
    )

    edge_details = grayscale.filter(
        ImageFilter.FIND_EDGES
    ).point(
        lambda value: 255 if value >= 24 else 0
    )
    edge_details = ImageChops.multiply(
        edge_details,
        crop_mask,
    )

    if lci_cop_perspective_refine:
        protected_details = Image.new("L", crop_size, 0)
    else:
        protected_details = ImageChops.lighter(
            dark_details,
            edge_details,
        ).filter(
            ImageFilter.MaxFilter(5)
        ).filter(
            ImageFilter.GaussianBlur(radius=0.7)
        )

    face_refinement = Image.blend(
        source_crop,
        edited_crop,
        face_strength,
    )

    result = Image.composite(
        face_refinement,
        source_crop,
        inner_face_mask,
    )

    shadow_refinement = Image.blend(
        source_crop,
        edited_crop,
        shadow_strength,
    )

    result = Image.composite(
        shadow_refinement,
        result,
        outer_ring_mask,
    )

    result = Image.composite(
        source_crop,
        result,
        protected_details,
    )

    return result

def _run_firered_if_available(input_path: Path, output_path: Path, transform: dict[str, Any], bbox: tuple[int, int, int, int] | None = None, component_mask: Image.Image | None = None) -> bool:
    script = os.environ.get("FIRERED_REPIN_SCRIPT") or os.environ.get("FIRERED_IMAGE_EDIT_SCRIPT") or "/root/Kone/fire_red_image_edit.py"
    script_path = Path(script)
    if not script_path.exists():
        return False
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": os.environ.get(
            "FIRERED_CUDA_VISIBLE_DEVICES",
            os.environ.get("CUDA_VISIBLE_DEVICES", "0"),
        ),
    }
    fire_input = input_path
    fire_output = output_path
    crop_box: tuple[int, int, int, int] | None = None
    with Image.open(input_path) as source_probe:
        source_size = source_probe.size
    if bbox is not None:
        source = Image.open(input_path).convert("RGB")
        source_size = source.size
        crop_box = _expanded_crop_box(bbox, source.size)
        fire_input = output_path.with_name(f"{output_path.stem}_firered_crop_input.png")
        fire_output = output_path.with_name(f"{output_path.stem}_firered_crop_output.png")
        source.crop(crop_box).save(fire_input)
    perspective_analysis = (
        _perspective_analysis_prompt(transform, source_size, crop_box)
        + _scene_line_perspective_prompt(fire_input)
    )
    firered_prompt = _firered_prompt(transform, perspective_analysis)
    firered_steps = int(os.environ.get("FIRERED_STEPS", "36"))
    firered_cfg = float(os.environ.get("FIRERED_TRUE_CFG_SCALE", "3.8"))
    service_url = os.environ.get(
        "FIRERED_SERVICE_URL",
        "http://127.0.0.1:8010/edit",
    )

    service_succeeded = False

    try:
        import json
        import urllib.request

        request_payload = json.dumps(
            {
                "image": str(fire_input),
                "output": str(fire_output),
                "prompt": firered_prompt,
                "seed": int(os.environ.get("FIRERED_SEED", "777")),
                "steps": firered_steps,
                "true_cfg_scale": firered_cfg,
                "use_blend_prompt": False,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            service_url,
            data=request_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        print(
            f"[FIRERED] Using persistent service: {service_url}",
            flush=True,
        )

        with urllib.request.urlopen(
            request,
            timeout=float(
                os.environ.get("FIRERED_SERVICE_TIMEOUT", "900")
            ),
        ) as response:
            response_body = json.loads(
                response.read().decode("utf-8")
            )

        if not response_body.get("ok"):
            raise RuntimeError(
                f"Persistent service returned failure: {response_body}"
            )

        if not fire_output.exists():
            raise RuntimeError(
                f"Persistent service did not create output: {fire_output}"
            )

        print(
            "[FIRERED] Persistent service completed | "
            f"inference={response_body.get('inference_seconds')}s | "
            f"save={response_body.get('save_seconds')}s | "
            f"total={response_body.get('total_seconds')}s",
            flush=True,
        )

        service_succeeded = True

    except Exception as service_exc:
        print(
            "[FIRERED] Persistent service unavailable; "
            f"using subprocess fallback: {service_exc}",
            file=sys.stderr,
            flush=True,
        )

    if not service_succeeded:
        firered_python = os.environ.get("FIRERED_PYTHON", "/root/Kone/firered_venv/bin/python")
        try:
            completed = subprocess.run(
                [
                    firered_python,
                    str(script_path),
                    "--image",
                    str(fire_input),
                    "--prompt",
                    firered_prompt,
                    "--output",
                    str(fire_output),
                    "--steps",
                    str(firered_steps),
                    "--true-cfg-scale",
                    str(firered_cfg),
                ],
                check=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if completed.stdout.strip():
                print(completed.stdout.strip(), flush=True)
        except Exception as exc:
            detail = getattr(exc, "stderr", "") or getattr(exc, "stdout", "") or str(exc)
            last_line = str(detail).strip().splitlines()[-1] if str(detail).strip() else str(exc)
            print(
                f"[FIRERED] optional refinement skipped: {last_line}",
                file=sys.stderr,
                flush=True,
            )
            return False
    if crop_box is not None:
        if not fire_output.exists():
            return False
        source = Image.open(input_path).convert("RGB")
        source_crop = source.crop(crop_box)
        edited_crop = Image.open(fire_output).convert("RGB")
        crop_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
        if edited_crop.size != crop_size:
            edited_crop = edited_crop.resize(crop_size, Image.Resampling.LANCZOS)
        constrained_crop = _firered_constrained_composite(
            source_crop,
            edited_crop,
            component_mask,
            crop_box,
            transform,
        )

        blend_mask = _crop_blend_mask(
            crop_size,
            feather_px=int(max(24, min(crop_size) * 0.08)),
        )

        source.paste(
            constrained_crop,
            (crop_box[0], crop_box[1]),
            blend_mask,
        )

        source.save(output_path)
    return output_path.exists()


def _save_firered_editable_layer(output_path: Path, layer_path: Path, component_mask: Image.Image | None, bbox: list[int] | tuple[int, int, int, int] | None) -> bool:
    if component_mask is None or bbox is None or not output_path.exists():
        return False
    x1, y1, x2, y2 = [int(value) for value in bbox]
    if x2 <= x1 or y2 <= y1:
        return False
    final_image = Image.open(output_path).convert("RGBA")
    alpha = component_mask.convert("L")
    if alpha.size != final_image.size:
        alpha = alpha.resize(final_image.size, Image.Resampling.LANCZOS)
    x1 = max(0, min(final_image.width, x1))
    y1 = max(0, min(final_image.height, y1))
    x2 = max(0, min(final_image.width, x2))
    y2 = max(0, min(final_image.height, y2))
    if x2 <= x1 or y2 <= y1:
        return False
    layer = final_image.crop((x1, y1, x2, y2))
    layer.putalpha(alpha.crop((x1, y1, x2, y2)))
    layer_path.parent.mkdir(parents=True, exist_ok=True)
    layer.save(layer_path)
    return True


def public_status(status: str, error: Any = None) -> dict[str, Any]:
    return {
        "status": status,
        "preview_url": "preview/final_output.png" if status in {"preview_ready", "video_ready"} else None,
        "video_url": "video/elevator_animation.mp4" if status == "video_ready" else None,
        "download_url": None,
        "error": error,
    }


@app.post("/precheck")
def precheck(payload: ProjectPayload):
    image_path = Path(payload.storage_dir) / "uploads" / "input.jpg"
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((900, 900), Image.Resampling.LANCZOS)
    image_array = np.asarray(image)
    result = validate_input_image(image_array, {})
    if not result.get("valid", False):
        reason = _validation_message(result)
        failure = {
            "reason": reason,
            "validation": result,
        }
        write_status(payload.storage_dir, public_status("precheck_failed", failure))
        return {
            "ok": False,
            "next_action": "reupload",
            "image_type": "UNUSABLE",
            "message": reason,
            "reason": reason,
            "validation": result,
            "relevance": None,
        }
    relevance = validate_elevator_or_cop_upload(image_array, result)
    ok = bool(relevance.get("valid"))
    reason = None
    if not ok:
        reason = relevance.get("reason") or "Invalid image. Please upload a valid elevator image."
    failure = None if ok else {
        "reason": reason,
        "relevance": relevance,
    }
    write_status(payload.storage_dir, public_status("precheck_passed" if ok else "precheck_failed", failure))
    return {
        "ok": ok,
        "next_action": "continue" if ok else "reupload",
        "image_type": "ELEVATOR_IMAGE" if ok else relevance.get("image_type"),
        "message": None if ok else reason,
        "reason": None if ok else reason,
        "validation": result,
        "relevance": relevance,
    }


def _validation_message(validation: dict[str, Any]) -> str:
    reasons = validation.get("reasons", {}) or {}
    hard_fail = reasons.get("hard_fail") or []
    if hard_fail:
        return str(hard_fail[0])
    suggestions = reasons.get("suggestions") or []
    if suggestions:
        return str(suggestions[0])
    return "Invalid image. Please upload a valid elevator image."


@app.post("/run-components")
def run_components(payload: ProjectPayload):
    storage = Path(payload.storage_dir)
    input_image = storage / "uploads" / "input.jpg"
    preview_dir = storage / "preview"
    pipeline_dir = storage / "pipeline"
    preview_dir.mkdir(parents=True, exist_ok=True)
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    write_status(payload.storage_dir, public_status("processing"))

    cfg_path = repo_root() / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    panel_path = repo_root() / "tests" / "panels" / "mod_panel.png"
    component_assets = selected_component_asset_paths(payload.component_assets)
    cfg.update(
        {
            "run_dir": str(pipeline_dir),
            "input_image": str(input_image),
            "mod_panel": str(panel_path if panel_path.exists() else repo_root() / str(cfg.get("mod_panel", ""))),
            "input_validation": {"enabled": False},
            "video": {**cfg.get("video", {}), "enabled": False},
            "selected_components": payload.selected_components or [],
            "component_assets": component_assets,
            "environment": payload.environments or [],
        }
    )
    config_path = pipeline_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    try:
        with PIPELINE_LOCK:
            _run_pipeline_in_process(config_path)
        requested_components = [str(component).strip().lower() for component in (payload.selected_components or []) if str(component).strip()]
        placements_path = pipeline_dir / "component_placements.json"
        placements = json.loads(placements_path.read_text(encoding="utf-8")) if placements_path.exists() else []
        placed_components = {str(item.get("id") or item.get("component_type") or "").lower() for item in placements if isinstance(item, dict)}
        missing_components = [component for component in requested_components if component not in placed_components]
        if missing_components:
            raise ValueError(
                "Preview incomplete: missing selected component placement(s): " + ", ".join(missing_components)
            )
        final_output = pipeline_dir / "final_output.png"
        shutil.copy2(final_output if final_output.exists() else input_image, preview_dir / "final_output.png")
        status = public_status("preview_ready")
        status.update({
            "preview_url": "preview/final_output.png",
            "preview_versions": [{"version": 1, "url": "preview/final_output.png"}],
            "repin_pass": 1,
        })
        write_status(payload.storage_dir, status)
        return {"ok": True, "status": "preview_ready"}
    except Exception as exc:
        write_status(payload.storage_dir, public_status("failed", str(exc)))
        return {"ok": False, "status": "failed", "error": str(exc)}



@app.post("/repin-components")
def repin_components(payload: ProjectPayload):
    storage = Path(payload.storage_dir)
    preview_dir = storage / "preview"
    pipeline_dir = storage / "pipeline"
    preview_dir.mkdir(parents=True, exist_ok=True)
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    write_status(payload.storage_dir, public_status("processing"))

    try:
        incoming_transforms = payload.transforms if isinstance(payload.transforms, list) else []
        if payload.transform:
            incoming_transforms = [*incoming_transforms, payload.transform]

        transforms_by_component: dict[str, dict[str, Any]] = {}
        for item in incoming_transforms:
            if not isinstance(item, dict):
                continue
            key = str(item.get("componentKey") or item.get("componentType") or "").lower()
            if key:
                transforms_by_component[key] = item
        transforms = list(transforms_by_component.values())
        if not transforms:
            raise ValueError("Repin transform is required")

        target_transform = payload.transform or transforms[0]
        source_version = int(target_transform.get("sourceVersion") or 1)
        target_version = int(target_transform.get("targetVersion") or 2)
        if target_version > 5:
            raise ValueError("Version limit reached. Choose the best saved version to continue.")

        source_base_mode = str(target_transform.get("sourceBaseMode") or "version").lower()
        parent_version_id = target_transform.get("parentVersionId") or source_version
        parent_final_image_path = target_transform.get("parentFinalImagePath")
        source_image_path = _source_image_for_repin(storage, preview_dir, source_version, source_base_mode)

        placed_image = Image.open(source_image_path).convert("RGB")
        transforms = [
            _with_lci_cop_homography_points(transform, placed_image)
            for transform in transforms
        ]
        target_key = str(target_transform.get("componentKey") or target_transform.get("componentType") or "").lower()
        target_transform = next(
            (transform for transform in transforms if str(transform.get("componentKey") or transform.get("componentType") or "").lower() == target_key),
            transforms[0],
        )
        user_eraser_background_path = None
        eraser_candidates = [target_transform, *[item for item in transforms if item is not target_transform]]
        for eraser_transform in eraser_candidates:
            eraser_background_path = eraser_transform.get("repinBackgroundPath")
            if eraser_background_path and _has_user_eraser_background(eraser_transform):
                candidate_path = Path(str(eraser_background_path))
                if candidate_path.exists():
                    user_eraser_background_path = candidate_path
                    break
        if user_eraser_background_path:
            erased_base_image = Image.open(user_eraser_background_path).convert("RGB")
            if erased_base_image.size != placed_image.size:
                erased_base_image = erased_base_image.resize(placed_image.size, Image.Resampling.LANCZOS)
            placed_image = erased_base_image

        for restore_transform in transforms:
            restore_background_path = restore_transform.get("repinBackgroundPath")
            if restore_background_path:
                restore_background_path = Path(str(restore_background_path))
                if user_eraser_background_path and restore_background_path == user_eraser_background_path:
                    continue
                placed_image = _composite_repin_background_original_footprint(
                    placed_image,
                    restore_background_path,
                    restore_transform,
                )

        placements = []
        component_masks = []
        for transform in transforms:
            component_image = Image.open(
                _component_image_for_transform(
                    transform,
                    payload.component_assets,
                )
            ).convert("RGBA")

            component_mask = _component_mask_for_transform(
                component_image,
                transform,
                placed_image.size,
            )
            component_masks.append(component_mask)

            placed_image, bbox = _place_manual_component(
                placed_image,
                component_image,
                transform,
            )

            placed_image = placed_image
            placements.append({
                "id": transform.get("componentKey"),
                "component_type": transform.get("componentType"),
                "manual_repin": True,
                "source_version": source_version,
                "target_version": target_version,
                "feedback_option": transform.get("feedbackOption"),
                "feedback_options": transform.get("feedbackOptions") or ([transform.get("feedbackOption")] if transform.get("feedbackOption") else []),
                "transform": transform,
                "final_insertion_bbox": list(bbox),
                "final_component_placement": {"bbox": list(bbox), "reason": "manual_repin_transform"},
                "firered_realism_refine": False,
                "lama_used": False,
            })

        placed_path = pipeline_dir / f"repin_v{target_version}_placed.png"
        output_path = preview_dir / f"final_output_v{target_version}.png"
        placed_image.save(placed_path)
        print(json.dumps({
            "event": "repin_source_selected",
            "visualizationId": payload.project_id,
            "newVersionId": target_version,
            "parentVersionId": parent_version_id,
            "parentFinalImagePath": parent_final_image_path or str(source_image_path),
            "actualFireRedInputPath": str(placed_path),
            "activeComponentType": target_transform.get("componentType") or target_transform.get("componentKey"),
            "magicEraserApplied": _has_manual_eraser_background(target_transform),
        }), flush=True)
        target_key = str(target_transform.get("componentKey") or target_transform.get("componentType") or "").lower()
        target_index = next(
            (index for index, placement in enumerate(placements) if str(placement.get("id") or placement.get("component_type") or "").lower() == target_key),
            len(placements) - 1 if placements else -1,
        )
        target_bbox = placements[target_index]["final_insertion_bbox"] if target_index >= 0 else None
        target_mask = component_masks[target_index] if target_index >= 0 else None
        with firered_repin_lock():
            used_firered = _run_firered_if_available(placed_path, output_path, target_transform, target_bbox, target_mask)
        if not used_firered:
            placed_image.save(output_path)
        editable_layer_url = target_transform.get("editableLayerUrl")
        if used_firered and target_bbox is not None and target_mask is not None:
            editable_layer_name = f"repin_v{target_version}_{target_key or 'component'}_editable_layer.png"
            editable_layer_path = preview_dir / editable_layer_name
            if _save_firered_editable_layer(output_path, editable_layer_path, target_mask, target_bbox):
                editable_layer_url = f"preview/{editable_layer_name}"
                target_transform = {**target_transform, "editableLayerUrl": editable_layer_url}
                transforms = [
                    target_transform if str(item.get("componentKey") or item.get("componentType") or "").lower() == target_key else item
                    for item in transforms
                ]
        shutil.copy2(output_path, preview_dir / "final_output.png")

        for placement in placements:
            placement["firered_realism_refine"] = used_firered

        placements_path = pipeline_dir / "component_placements.json"
        placements_path.write_text(json.dumps(placements, indent=2), encoding="utf-8")
        (pipeline_dir / f"repin_transform_v{target_version}.json").write_text(json.dumps({
            "source_version": source_version,
            "target_version": target_version,
            "transforms": transforms,
            "placements": placements,
            "firered_realism_refine": used_firered,
            "source_base_mode": source_base_mode,
            "lama_used": False,
            "parent_version_id": parent_version_id,
            "parent_final_image_path": parent_final_image_path or str(source_image_path),
            "actual_firered_input_path": str(placed_path),
        }, indent=2), encoding="utf-8")

        print(json.dumps({
            "event": "repin_generation_saved",
            "visualizationId": payload.project_id,
            "newVersionId": target_version,
            "parentVersionId": parent_version_id,
            "parentFinalImagePath": parent_final_image_path or str(source_image_path),
            "actualFireRedInputPath": str(placed_path),
            "activeComponentType": target_transform.get("componentType") or target_transform.get("componentKey"),
            "magicEraserApplied": _has_manual_eraser_background(target_transform),
            "generatedFinalImagePath": str(output_path),
        }), flush=True)

        status = public_status("preview_ready")
        status.update({
            "preview_url": f"preview/final_output_v{target_version}.png",
            "current_preview_url": "preview/final_output.png",
            "repin_pass": target_version,
            "preview_versions": [{
                "version": target_version,
                "url": f"preview/final_output_v{target_version}.png",
                "sourceVersion": source_version,
                "transform": target_transform,
                "feedbackOption": target_transform.get("feedbackOption"),
                "feedbackOptions": target_transform.get("feedbackOptions") or ([target_transform.get("feedbackOption")] if target_transform.get("feedbackOption") else []),
                "sourceBaseMode": source_base_mode,
                "parentVersionId": parent_version_id,
                "parentFinalImagePath": parent_final_image_path or str(source_image_path),
                "finalImagePath": str(output_path),
            }],
        })
        write_status(payload.storage_dir, status)
        return {
            "ok": True,
            "status": "preview_ready",
            "preview_url": status["preview_url"],
            "repin_pass": target_version,
            "preview_versions": status["preview_versions"],
            "parent_final_image_path": parent_final_image_path or str(source_image_path),
            "actual_firered_input_path": str(placed_path),
            "generated_final_image_path": str(output_path),
        }
    except Exception as exc:
        write_status(payload.storage_dir, public_status("failed", str(exc)))
        return {"ok": False, "status": "failed", "error": str(exc)}

@app.post("/repin-erase")
def repin_erase(payload: ProjectPayload):
    storage = Path(payload.storage_dir)
    preview_dir = storage / "preview"
    pipeline_dir = storage / "pipeline"
    preview_dir.mkdir(parents=True, exist_ok=True)
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    try:
        run_id = time.time_ns()
        warnings.simplefilter("always", FutureWarning)
        warnings.simplefilter("always", UserWarning)
        transform = payload.transform or {}
        source_version = int(payload.source_version or transform.get("sourceVersion") or 1)
        source_base_mode = str(payload.source_base_mode or transform.get("sourceBaseMode") or "version").lower()
        component_key = str(transform.get("componentKey") or transform.get("componentType") or "component").lower()
        print(f"[REPIN_ERASE] start run_id={run_id} component={component_key} source_version={source_version} source_base_mode={source_base_mode}", flush=True)
        repin_background_path = transform.get("repinBackgroundPath")
        if repin_background_path and Path(str(repin_background_path)).exists():
            source_image_path = Path(str(repin_background_path))
        else:
            source_image_path = _source_image_for_repin(storage, preview_dir, source_version, source_base_mode)
        source_image = Image.open(source_image_path).convert("RGB")
        print(f"[REPIN_ERASE] source run_id={run_id} path={source_image_path}", flush=True)
        mask = _decode_mask_data_url(payload.mask_data_url or "", source_image.size)
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
        print(f"[REPIN_ERASE] mask run_id={run_id} pixels={int(np.count_nonzero(mask))} size={source_image.size}", flush=True)

        mask_path = pipeline_dir / f"repin_erase_mask_v{source_version}_{run_id}.png"
        output_path = preview_dir / f"repin_erased_v{source_version}_{run_id}.png"
        cv2.imwrite(str(mask_path), mask)

        repo_path = str(repo_root())
        if repo_path not in sys.path:
            sys.path.insert(0, repo_path)
        try:
            from src.inpaint import inpaint_background
        except Exception:
            from inpaint import inpaint_background

        cfg = _load_pipeline_config(pipeline_dir)
        cfg.setdefault("inpainting", {})
        cfg.setdefault("removal", {})
        cfg["inpainting"]["engine"] = cfg["inpainting"].get("engine") or "lama"
        cfg["inpainting"]["fallback_to_opencv"] = True
        print(f"[REPIN_ERASE] inpaint run_id={run_id} output={output_path}", flush=True)
        inpaint_background(source_image_path, mask, cfg, output_path)
        print(f"[REPIN_ERASE] done run_id={run_id} output={output_path}", flush=True)

        status = public_status("preview_ready")
        status.update({
            "preview_url": str(output_path.relative_to(storage)),
            "current_preview_url": str(output_path.relative_to(storage)),
            "repin_erased_url": str(output_path.relative_to(storage)),
            "repin_erase_mask_url": str(mask_path.relative_to(storage)),
        })
        write_status(payload.storage_dir, status)
        return {
            "ok": True,
            "status": "preview_ready",
            "preview_url": status["preview_url"],
            "repin_background_url": status["repin_erased_url"],
            "mask_url": status["repin_erase_mask_url"],
        }
    except Exception as exc:
        print(f"[REPIN_ERASE] failed error={exc}", flush=True)
        write_status(payload.storage_dir, public_status("failed", str(exc)))
        return {"ok": False, "status": "failed", "error": str(exc)}


@app.post("/generate-video")
def generate_video(payload: ProjectPayload):
    from video_router import render_video

    storage = Path(payload.storage_dir)
    preview_image = storage / "preview" / "final_output.png"
    pipeline_dir = storage / "pipeline"
    video_dir = storage / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / "elevator_animation.mp4"
    cfg_path = pipeline_dir / "config.yaml"
    detections_path = pipeline_dir / "elevator_detections.json"
    geometry_path = pipeline_dir / "geometry.json"
    depth_path = pipeline_dir / "depth_map.npz"

    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else yaml.safe_load((repo_root() / "config.yaml").read_text(encoding="utf-8"))
        video_options = payload.video_options or {}
        motion = video_options.get("motion") or video_options.get("motion_style")
        video_cfg = cfg.get("video", {})
        requested_engine = str(video_options.get("engine", video_cfg.get("engine", "opencv"))).strip().lower()
        wan_engines = {"wan", "wan2.2", "wan22"}
        comfy_engines = {"comfy", "comfy_wan", "comfy_i2v", "comfy_flf2v", "wan_comfy"}
        effective_engine = (
            requested_engine
            if requested_engine in comfy_engines
            else "wan2.2"
            if requested_engine in wan_engines
            else "opencv"
        )
        cfg["video"] = {
            **video_cfg,
            "enabled": True,
            "engine": effective_engine,
            "requested_engine": requested_engine,
            "quality": video_options.get("quality", video_cfg.get("quality", "720p")),
            "duration_seconds": video_options.get("duration_seconds", video_options.get("duration", 9.0)),
            "preserve_source_aspect": True,
            "ffmpeg_pan_overscan": 0.20,
            "ffmpeg_zoom_amount": 0.35,
        }
        if video_options.get("mode") == "door_functionality":
            cfg["video"].update({"mode": "door_functionality"})
            cfg["video"].pop("motion_style", None)
        elif motion:
            cfg["video"].update({"motion_style": motion, "mode": "motion"})
        elif requested_engine in {"wan", "wan2.2", "wan22", "comfy", "comfy_wan", "comfy_i2v", "wan_comfy"}:
            cfg["video"].setdefault("motion_style", "zoom_in")
        if cfg["video"].get("engine") in comfy_engines:
            cfg["video"].setdefault("fps", 16)
            cfg["video"].setdefault("duration_seconds", 5)
            cfg["video"].setdefault("quality_mode", video_options.get("quality_mode", "best"))
            cfg["video"]["comfy"] = {
                **cfg["video"].get("comfy", {}),
                **video_options.get("comfy", {}),
                "quality_mode": video_options.get("quality_mode", cfg["video"].get("quality_mode", "best")),
            }
        if cfg["video"].get("engine") == "wan2.2":
            cfg["video"].setdefault("fps", 16)
            cfg["video"].setdefault("duration_seconds", 5)
            wan_defaults = {
                "model_key": "wan22_14b_i2v",
                "task": "i2v-14B",
                "size": "832*480",
                "frame_num": 81,
                "sample_steps": 40,
                "sample_shift": 3.0,
                "sample_guide_scale": None,
                "repo_dir": "/root/wan22_install/Wan2.2",
                "checkpoint_dir": "/root/wan22_install/Wan2.2/Wan2.2-I2V-A14B",
                "offload_model": False,
                "t5_cpu": False,
                "convert_model_dtype": True,
                "min_size_bytes": 1_000_000,
            }
            cfg["video"]["wan"] = {
                **cfg["video"].get("wan", {}),
                **wan_defaults,
                **video_options.get("wan", {}),
                "enabled": True,
            }
        detections = json.loads(detections_path.read_text(encoding="utf-8")) if detections_path.exists() else {}
        geometry = json.loads(geometry_path.read_text(encoding="utf-8")) if geometry_path.exists() else {}
        render_video(
            preview_image,
            detections,
            geometry,
            cfg,
            video_path,
            depth_path if depth_path.exists() else None,
        )
        write_status(payload.storage_dir, public_status("video_ready"))
        return {"ok": True, "status": "video_ready"}
    except Exception as exc:
        write_status(payload.storage_dir, public_status("failed", str(exc)))
        return {"ok": False, "status": "failed", "error": str(exc)}