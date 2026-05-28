from __future__ import annotations
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .utils import load_image_rgb, save_rgb


def maybe_refine(composite_path: str | Path, mask_path: str | Path, cfg: dict[str, Any], out_path: str | Path) -> None:
    if not cfg["refinement"].get("enabled", False):
        save_rgb(out_path, load_image_rgb(composite_path))
        return

    import torch
    from diffusers import StableDiffusionInpaintPipeline

    image = load_image_rgb(composite_path)
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None or mask.max() == 0:
        save_rgb(out_path, image)
        return

    ys, xs = np.where(mask > 10)
    pad = 40
    x1, x2 = max(0, xs.min() - pad), min(image.shape[1], xs.max() + pad)
    y1, y2 = max(0, ys.min() - pad), min(image.shape[0], ys.max() + pad)
    crop = image[y1:y2, x1:x2]
    crop_mask = cv2.GaussianBlur(mask[y1:y2, x1:x2], (31, 31), 10)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    pipe = StableDiffusionInpaintPipeline.from_pretrained(cfg["refinement"]["model_id"], torch_dtype=dtype).to(device)
    result = pipe(
        prompt=cfg["refinement"]["prompt"],
        negative_prompt=cfg["refinement"]["negative_prompt"],
        image=Image.fromarray(crop),
        mask_image=Image.fromarray(crop_mask),
        strength=float(cfg["refinement"]["strength"]),
        guidance_scale=float(cfg["refinement"]["guidance_scale"]),
        num_inference_steps=int(cfg["refinement"]["steps"]),
    ).images[0]

    result_np = np.array(result)
    if result_np.shape[:2] != crop.shape[:2]:
        result_np = cv2.resize(result_np, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_LANCZOS4)
    alpha = np.dstack([crop_mask.astype(np.float32) / 255.0] * 3)
    blended = np.clip(result_np.astype(np.float32) * alpha + crop.astype(np.float32) * (1 - alpha), 0, 255).astype(np.uint8)
    final = image.copy()
    final[y1:y2, x1:x2] = blended
    save_rgb(out_path, final)
