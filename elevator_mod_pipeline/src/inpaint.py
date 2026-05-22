from __future__ import annotations

import os
import sys
import argparse
import importlib.util
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .utils import detection_mask, dilate_mask, load_image_rgb, phrase_matches, save_rgb, select_middle_floor_indicator_display


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        if (parent / "main2.py").exists():
            return parent
    raise FileNotFoundError("Could not find main2.py from inpaint.py location")


ROOT = _find_repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_MAIN2_MODULE: Any | None = None


def build_removal_mask(image: np.ndarray, detections: dict[str, Any], cfg: dict[str, Any]) -> np.ndarray:
    height, width = image.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    keywords = cfg["removal"]["target_keywords"]
    pad = int(cfg["removal"]["mask_padding_px"])

    selected_det = select_middle_floor_indicator_display(detections["detections"], keywords, height)
    for det in detections["detections"]:
        if not phrase_matches(det.get("phrase", ""), keywords):
            continue
        if selected_det is not None and det is not selected_det:
            continue
        det_mask = detection_mask(det, height, width)
        if det_mask.max() == 0:
            continue
        ys, xs = np.where(det_mask > 127)
        if len(xs) == 0:
            continue
        has_segmentation = any(det.get(key) is not None for key in ("mask", "segmentation", "rle"))
        det_pad = pad if has_segmentation else min(pad, int(cfg["removal"].get("box_mask_padding_px", 2)))
        x1, x2 = max(0, xs.min() - det_pad), min(width, xs.max() + det_pad)
        y1, y2 = max(0, ys.min() - det_pad), min(height, ys.max() + det_pad)
        padded = np.zeros_like(mask)
        padded[y1:y2, x1:x2] = 255
        mask = np.maximum(mask, np.maximum(det_mask, padded))

    mask = dilate_mask(mask, int(cfg["removal"]["mask_dilate_iterations"]))
    return _preserve_saturated_background(image, mask)

def inpaint_background(image_path: str | Path, mask: np.ndarray, cfg: dict[str, Any], out_path: str | Path) -> np.ndarray:
    image = load_image_rgb(image_path)
    engine = cfg["removal"].get("cleanup_engine", "auto").lower()
    if engine == "auto":
        engine = cfg["inpainting"]["engine"].lower()
    used_main2_lama = False
    if engine == "wall_patch":
        result = _wall_patch_cleanup(image, mask, cfg)
    elif engine == "lama":
        try:
            result = _run_lama(image, mask, cfg)
            used_main2_lama = True
        except Exception:
            if not cfg["inpainting"].get("fallback_to_opencv", True):
                raise
            result = _track_patch_cleanup(image, mask, cfg) if _is_floor_track_cleanup(cfg) else _wall_patch_cleanup(image, mask, cfg)
    else:
        result = _opencv_inpaint(image, mask)
    if not used_main2_lama:
        result = _masked_replace(image, result, mask, int(cfg["removal"].get("cleanup_feather_px", 2)))
    save_rgb(out_path, result)
    return result


def _opencv_inpaint(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    out = cv2.inpaint(bgr, (mask > 127).astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def _is_floor_track_cleanup(cfg: dict[str, Any]) -> bool:
    keywords = [keyword.lower() for keyword in cfg["removal"].get("target_keywords", [])]
    return any(keyword in {"door track", "threshold plate"} for keyword in keywords)


def _track_patch_cleanup(image: np.ndarray, mask: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    out = image.copy().astype(np.float32)
    binary = (mask > 127).astype(np.uint8)
    components, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    margin = int(cfg["removal"].get("wall_sample_margin_px", 55))
    rng = np.random.default_rng(42)

    for label in range(1, components):
        x, y, w, h, area = stats[label]
        if area <= 0:
            continue
        comp = labels == label
        x1, y1 = max(0, x - margin), max(0, y - margin)
        x2, y2 = min(image.shape[1], x + w + margin), min(image.shape[0], y + h + margin)
        patch = image[y1:y2, x1:x2]
        comp_patch = comp[y1:y2, x1:x2]

        ring = np.ones(comp_patch.shape, dtype=np.uint8)
        ring[comp_patch] = 0
        ring = cv2.erode(ring, np.ones((3, 3), np.uint8), iterations=1).astype(bool)
        samples = patch[ring]
        if len(samples) == 0:
            samples = patch.reshape(-1, 3)

        median = np.median(samples, axis=0)
        std = np.clip(np.std(samples, axis=0) * 0.35, 1.0, 9.0)
        fill = np.clip(median + rng.normal(0, std, patch.shape), 0, 255).astype(np.float32)
        fill = cv2.GaussianBlur(fill, (5, 5), 1.0)

        local_mask = np.zeros(comp_patch.shape, dtype=np.float32)
        local_mask[comp_patch] = 1.0
        feather = cv2.GaussianBlur(local_mask, (11, 11), 2.5)
        feather = np.clip(feather, 0, 1)[:, :, None]
        out_patch = out[y1:y2, x1:x2]
        out[y1:y2, x1:x2] = out_patch * (1 - feather) + fill * feather

    return np.clip(out, 0, 255).astype(np.uint8)


def _preserve_saturated_background(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Keep poster/graphic edges out of small padded cleanup masks."""
    if mask.max() == 0:
        return mask
    mask_area = int((mask > 127).sum())
    image_area = image.shape[0] * image.shape[1]
    if mask_area / max(image_area, 1) > 0.08:
        return mask

    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    saturated_background = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 45)
    refined = mask.copy()
    refined[saturated_background] = 0
    return refined


def _wall_patch_cleanup(image: np.ndarray, mask: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    """Clean wall-mounted objects without dragging poster/door colors into the wall."""
    out = image.copy().astype(np.float32)
    binary = (mask > 127).astype(np.uint8)
    components, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    margin = int(cfg["removal"].get("wall_sample_margin_px", 55))
    rng = np.random.default_rng(42)

    for label in range(1, components):
        x, y, w, h, area = stats[label]
        if area <= 0:
            continue
        comp = labels == label
        x1, y1 = max(0, x - margin), max(0, y - margin)
        x2, y2 = min(image.shape[1], x + w + margin), min(image.shape[0], y + h + margin)

        patch = image[y1:y2, x1:x2]
        comp_patch = comp[y1:y2, x1:x2]
        ring = np.ones(comp_patch.shape, dtype=np.uint8)
        ring[comp_patch] = 0
        ring = cv2.erode(ring, np.ones((3, 3), np.uint8), iterations=1).astype(bool)

        hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
        wall_like = (hsv[:, :, 1] < 55) & (hsv[:, :, 2] > 135) & ring
        samples = _surface_samples(patch, hsv, wall_like)
        if len(samples) < 40:
            samples = patch[wall_like]
        if len(samples) < 40:
            samples = patch[ring]
        if len(samples) == 0:
            samples = patch.reshape(-1, 3)

        median = np.median(samples, axis=0)
        std = np.clip(np.std(samples, axis=0), 1.0, 5.0)
        texture = rng.normal(0, std, patch.shape).astype(np.float32)
        fill = np.clip(median + texture, 0, 255).astype(np.float32)
        fill = cv2.GaussianBlur(fill, (3, 3), 0.5)

        local_mask = np.zeros(comp_patch.shape, dtype=np.float32)
        local_mask[comp_patch] = 1.0
        feather = cv2.GaussianBlur(local_mask, (9, 9), 2.0)
        feather = np.clip(feather, 0, 1)[:, :, None]
        out_patch = out[y1:y2, x1:x2]
        out[y1:y2, x1:x2] = out_patch * (1 - feather) + fill * feather

    return np.clip(out, 0, 255).astype(np.uint8)


def _surface_samples(patch: np.ndarray, hsv: np.ndarray, wall_like: np.ndarray) -> np.ndarray:
    """Prefer the clean wall cluster over nearby metal/shadow regions."""
    candidates = patch[wall_like]
    if len(candidates) < 40:
        return candidates

    values = hsv[:, :, 2][wall_like]
    bright_floor = np.percentile(values, 70)
    bright_neutral = wall_like & (hsv[:, :, 2] >= bright_floor) & (hsv[:, :, 1] < 45)
    samples = patch[bright_neutral]
    if len(samples) >= 40:
        return samples
    return candidates


def _run_lama(image: np.ndarray, mask: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    main2 = _load_main2()

    lama_repo = _resolve_existing_path(cfg["inpainting"].get("lama_repo"), main2.LAMA_REPO_DIR)
    model_dir = _resolve_existing_path(cfg["inpainting"].get("lama_model_dir"), main2.LAMA_MODEL)

    if str(lama_repo) not in sys.path:
        sys.path.insert(0, str(lama_repo))

    main2.ensure_lama_model(model_dir)

    device = main2.select_device(cfg["inpainting"].get("device", "auto"))
    args = argparse.Namespace(
        inpaint_crop_padding=int(cfg["inpainting"].get("inpaint_crop_padding", 384)),
        lama_max_side=int(cfg["inpainting"].get("lama_max_side", 1024)),
        blend_feather=int(cfg["inpainting"].get("blend_feather", 24)),
    )

    with main2.autocast_for(device):
        return main2.inpaint_image(image, mask, model_dir, device, args)


def _resolve_existing_path(config_value: str | None, fallback: Path) -> Path:
    candidates: list[Path] = []
    if config_value:
        configured = Path(config_value)
        candidates.extend([configured.resolve(), (ROOT / configured).resolve()])
    candidates.append(fallback.resolve())
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _select_lama_device(requested: str) -> str:
    if requested and requested != "auto":
        if requested == "cuda":
            try:
                import torch

                return "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _load_main2() -> Any:
    global _MAIN2_MODULE
    if _MAIN2_MODULE is None:
        main2_path = ROOT / "main2.py"
        spec = importlib.util.spec_from_file_location("elevator_pipeline_main2", main2_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load main2.py from {main2_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("elevator_pipeline_main2", module)
        spec.loader.exec_module(module)
        _MAIN2_MODULE = module
    return _MAIN2_MODULE


def _crop_to_mask(image: np.ndarray, mask: np.ndarray, pad: int) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
    ys, xs = np.where(mask > 127)
    if len(xs) == 0:
        return image, mask, (0, 0, image.shape[1], image.shape[0])
    x1 = max(0, int(xs.min()) - pad)
    x2 = min(image.shape[1], int(xs.max()) + pad)
    y1 = max(0, int(ys.min()) - pad)
    y2 = min(image.shape[0], int(ys.max()) + pad)
    return image[y1:y2, x1:x2], mask[y1:y2, x1:x2], (x1, y1, x2, y2)


def _masked_replace(original: np.ndarray, cleaned: np.ndarray, mask: np.ndarray, feather_px: int) -> np.ndarray:
    if mask.max() == 0:
        return original.copy()
    alpha = (mask > 127).astype(np.float32)
    if feather_px > 0:
        k = max(3, feather_px * 2 + 1)
        if k % 2 == 0:
            k += 1
        alpha = cv2.GaussianBlur(alpha, (k, k), feather_px)
    alpha = np.clip(alpha, 0, 1)[:, :, None]
    return np.clip(original.astype(np.float32) * (1 - alpha) + cleaned.astype(np.float32) * alpha, 0, 255).astype(np.uint8)
