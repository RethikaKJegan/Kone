from __future__ import annotations

import base64
import json
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from PIL import Image, ImageOps


@dataclass
class Detection:
    id: int
    phrase: str
    score: float
    box_xyxy: list[float]
    mask: dict[str, Any] | None = None

    @property
    def box_xywh(self) -> list[float]:
        x1, y1, x2, y2 = self.box_xyxy
        return [x1, y1, x2 - x1, y2 - y1]


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_json(path: str | Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_image_rgb(path: str | Path) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return np.asarray(img)


def save_rgb(path: str | Path, image: np.ndarray) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(image, 0, 255).astype(np.uint8)).save(path)


def load_image_rgba(path: str | Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)


def mask_to_rle(mask: np.ndarray) -> dict[str, Any]:
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
    return {"size": [int(mask.shape[0]), int(mask.shape[1])], "counts": counts}


def rle_to_mask(rle: dict[str, Any], height: int, width: int) -> np.ndarray:
    counts = rle.get("counts", [])
    h, w = rle.get("size", [height, width])
    if isinstance(counts, str):
        counts = _decode_compressed_coco_counts(counts)
    flat = np.zeros(int(h) * int(w), dtype=np.uint8)
    cursor = 0
    value = 0
    for count in counts:
        count = min(int(count), flat.size - cursor)
        if value:
            flat[cursor : cursor + count] = 255
        cursor += count
        value = 1 - value
        if cursor >= flat.size:
            break
    mask = flat.reshape((int(w), int(h))).T
    if mask.shape != (height, width):
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
    return mask


def _decode_compressed_coco_counts(counts: str) -> list[int]:
    data = counts.encode("ascii")
    decoded: list[int] = []
    idx = 0
    while idx < len(data):
        x = 0
        shift = 0
        more = True
        while more:
            c = data[idx] - 48
            idx += 1
            more = c > 31
            x |= (c & 31) << shift
            shift += 5
        if x & 1:
            x = -(x >> 1)
        else:
            x >>= 1
        if len(decoded) > 2:
            x += decoded[-2]
        decoded.append(x)
    return decoded


def bitmap_b64_to_mask(payload: dict[str, Any], height: int, width: int) -> np.ndarray:
    h, w = payload.get("size", [height, width])
    packed = zlib.decompress(base64.b64decode(payload["data"]))
    flat = np.unpackbits(np.frombuffer(packed, dtype=np.uint8))[: int(h) * int(w)]
    mask = (flat.reshape((int(h), int(w))) * 255).astype(np.uint8)
    if mask.shape != (height, width):
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
    return mask


def detection_mask(det: dict[str, Any], height: int, width: int) -> np.ndarray:
    mask_data = det.get("mask") or det.get("segmentation") or det.get("rle")
    if isinstance(mask_data, dict) and "data" in mask_data:
        return bitmap_b64_to_mask(mask_data, height, width)
    if isinstance(mask_data, dict):
        return rle_to_mask(mask_data, height, width)
    if isinstance(mask_data, list):
        return rle_to_mask({"size": [height, width], "counts": mask_data}, height, width)
    x1, y1, x2, y2 = [int(round(v)) for v in det["box_xyxy"]]
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[max(0, y1) : min(height, y2), max(0, x1) : min(width, x2)] = 255
    return mask


def dilate_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask
    kernel = np.ones((3, 3), np.uint8)
    return cv2.dilate(mask.astype(np.uint8), kernel, iterations=iterations)


def phrase_matches(phrase: str, keywords: list[str]) -> bool:
    lower = phrase.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def select_detection(detections: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
    matches = [d for d in detections if phrase_matches(d.get("phrase", ""), keywords)]
    if not matches:
        return None
    return max(matches, key=lambda d: float(d.get("score", 0)))


def detection_box_area(det: dict[str, Any]) -> float:
    if det.get("box_area") is not None:
        return float(det["box_area"])
    x1, y1, x2, y2 = [float(v) for v in det["box_xyxy"]]
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def select_middle_floor_indicator_display(detections: list[dict[str, Any]], keywords: list[str], height: int | None = None) -> dict[str, Any] | None:
    """Pick the middle/nested display when OWLv2 returns housing, display, and digits."""
    if not any(keyword.lower() == "floor indicator display" for keyword in keywords):
        return None
    candidates = [d for d in detections if d.get("phrase", "").lower() == "floor indicator display"]
    if len(candidates) < 3:
        return None

    def center_y(det: dict[str, Any]) -> float:
        _, y1, _, y2 = [float(v) for v in det["box_xyxy"]]
        return (y1 + y2) * 0.5

    top_candidates = candidates
    if height is not None:
        top_band = [d for d in candidates if center_y(d) < height * 0.25]
        if len(top_band) >= 3:
            top_candidates = top_band

    ranked = sorted(top_candidates, key=detection_box_area, reverse=True)
    return ranked[len(ranked) // 2]
