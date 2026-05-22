from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .utils import detection_mask, load_image_rgb, save_rgb


PALETTE = [
    (255, 64, 64),
    (64, 220, 64),
    (64, 120, 255),
    (255, 210, 50),
    (200, 64, 255),
    (50, 220, 220),
    (255, 140, 50),
]


def save_detection_visuals(image_path: str | Path, detections: dict[str, Any], out_dir: str | Path) -> None:
    image = load_image_rgb(image_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _save_combined(image, detections, out_dir / "groundingdino_output.png")
    _save_masks(image, detections, out_dir / "sam2_output.png")


def _save_boxes(image: np.ndarray, detections: dict[str, Any], path: Path) -> None:
    canvas = Image.fromarray(image.copy())
    draw = ImageDraw.Draw(canvas)
    font = _font(max(12, image.shape[0] // 70))
    for idx, det in enumerate(detections.get("detections", [])):
        color = PALETTE[idx % len(PALETTE)]
        x1, y1, x2, y2 = [int(round(v)) for v in det["box_xyxy"]]
        label = f"{det.get('phrase', '?')} {float(det.get('score', 0)):.2f}"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        text_box = draw.textbbox((x1, y1), label, font=font)
        draw.rectangle([text_box[0] - 2, text_box[1] - 2, text_box[2] + 2, text_box[3] + 2], fill=color)
        draw.text((x1, y1), label, fill=(0, 0, 0), font=font)
    canvas.save(path)


def _save_masks(image: np.ndarray, detections: dict[str, Any], path: Path) -> None:
    height, width = image.shape[:2]
    overlay = image.copy().astype(np.float32)
    has_mask = False
    for idx, det in enumerate(detections.get("detections", [])):
        mask = detection_mask(det, height, width) > 127
        if not mask.any():
            continue
        has_mask = True
        color = np.array(PALETTE[idx % len(PALETTE)], dtype=np.float32)
        overlay[mask] = overlay[mask] * 0.55 + color * 0.45
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, color.tolist(), 2)
    if not has_mask:
        _save_boxes(image, detections, path)
        return
    save_rgb(path, overlay.astype(np.uint8))


def _save_combined(image: np.ndarray, detections: dict[str, Any], path: Path) -> None:
    height, width = image.shape[:2]
    overlay = image.copy().astype(np.float32)
    for idx, det in enumerate(detections.get("detections", [])):
        mask = detection_mask(det, height, width) > 127
        if not mask.any():
            continue
        color = np.array(PALETTE[idx % len(PALETTE)], dtype=np.float32)
        overlay[mask] = overlay[mask] * 0.50 + color * 0.50

    canvas = Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(canvas)
    font = _font(max(13, image.shape[0] // 62))
    for idx, det in enumerate(detections.get("detections", [])):
        color = PALETTE[idx % len(PALETTE)]
        x1, y1, x2, y2 = [int(round(v)) for v in det["box_xyxy"]]
        label = f"{det.get('phrase', '?')} {float(det.get('score', 0)):.2f}"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        text_box = draw.textbbox((x1, y1), label, font=font)
        draw.rectangle([text_box[0] - 3, text_box[1] - 3, text_box[2] + 3, text_box[3] + 3], fill=color)
        draw.text((x1, y1), label, fill=(0, 0, 0), font=font)

    title = f"Elevator Component Detection + Segmentation ({len(detections.get('detections', []))} components)"
    title_font = _font(max(15, image.shape[0] // 50))
    title_h = max(28, title_font.size + 10 if hasattr(title_font, "size") else 28)
    titled = Image.new("RGB", (canvas.width, canvas.height + title_h), "white")
    titled_draw = ImageDraw.Draw(titled)
    title_box = titled_draw.textbbox((0, 0), title, font=title_font)
    titled_draw.text(((canvas.width - (title_box[2] - title_box[0])) // 2, 4), title, fill=(0, 0, 0), font=title_font)
    titled.paste(canvas, (0, title_h))
    titled.save(path)


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except Exception:
        return ImageFont.load_default()
