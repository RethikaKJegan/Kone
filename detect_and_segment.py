"""
Unified GroundingDINO + SAM 2 pipeline.

GroundingDINO detects objects as bounding boxes, SAM 2 segments them
pixel-wise. The final output shows both boxes and filled masks overlaid
on the original image.

Device fallback order: CUDA -> MPS (Apple Silicon) -> CPU

Usage:
    python detect_and_segment.py "person" --image input.jpeg
    python detect_and_segment.py "car . person . bag" --image photo.jpg
    python detect_and_segment.py "dog" --image photo.jpg --output result.jpg --box-threshold 0.3
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path
from typing import NamedTuple

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage as ndi
from torchvision.ops import nms

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT             = Path(__file__).resolve().parent
GDINO_DIR        = ROOT / "GroundingDINO"
SAM2_DIR         = ROOT / "sam2_src"
BERT_DIR         = ROOT / "bert-base-uncased"
CACHE_DIR        = ROOT / ".cache"
GDINO_CONFIG     = GDINO_DIR / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
GDINO_WEIGHTS    = ROOT / "weights/groundingdino_swint_ogc.pth"
SAM2_CONFIG      = "configs/sam2.1/sam2.1_hiera_l.yaml"
SAM2_WEIGHTS     = ROOT / "weights/sam2.1_hiera_large.pt"

# ---------------------------------------------------------------------------
# Environment – silence noisy optional deps, keep everything offline
# ---------------------------------------------------------------------------
CACHE_DIR.mkdir(parents=True, exist_ok=True)
(CACHE_DIR / "matplotlib").mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR",        str(CACHE_DIR / "matplotlib"))
os.environ.setdefault("HF_HOME",             str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE",      "1")
os.environ.setdefault("HF_HUB_DISABLE_XET",  "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_NO_TF",   "1")
os.environ.setdefault("USE_TF",               "0")
os.environ.setdefault("USE_FLAX",             "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

for _p in (GDINO_DIR, SAM2_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import groundingdino.datasets.transforms as T
from groundingdino.models import build_model
from groundingdino.util.misc import clean_state_dict
from groundingdino.util.slconfig import SLConfig
from groundingdino.util.utils import get_phrases_from_posmap
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

# ---------------------------------------------------------------------------
# Device selection with automatic fallback
# ---------------------------------------------------------------------------
def resolve_device(preference: str = "auto") -> str:
    """
    Return the best available device.
    Fallback chain: CUDA -> MPS -> CPU
    """
    if preference not in ("auto", ""):
        if preference == "cuda" and not torch.cuda.is_available():
            warnings.warn("CUDA requested but not available – falling back to CPU.")
            return "cpu"
        if preference == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            warnings.warn("MPS requested but not available – falling back to CPU.")
            return "cpu"
        return preference

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def device_info(device: str) -> str:
    if device == "cuda":
        name = torch.cuda.get_device_name(0)
        mem  = torch.cuda.get_device_properties(0).total_memory // (1024 ** 3)
        return f"cuda ({name}, {mem} GB)"
    if device == "mps":
        return "mps (Apple Silicon)"
    return "cpu"


def clear_cache(device: str) -> None:
    if device == "cuda":
        torch.cuda.empty_cache()
    elif device == "mps" and hasattr(torch, "mps"):
        torch.mps.empty_cache()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
class Detection(NamedTuple):
    box_xyxy: np.ndarray   # [x1, y1, x2, y2] float32, pixel coords
    phrase:   str
    score:    float


# ---------------------------------------------------------------------------
# GroundingDINO – model + inference
# ---------------------------------------------------------------------------
_gdino_cache: dict[str, object] = {}

def _load_gdino(device: str):
    if device not in _gdino_cache:
        args = SLConfig.fromfile(str(GDINO_CONFIG))
        args.device = device
        if BERT_DIR.exists():
            args.text_encoder_type = str(BERT_DIR)
        model = build_model(args)
        ckpt  = torch.load(str(GDINO_WEIGHTS), map_location="cpu", weights_only=True)
        model.load_state_dict(clean_state_dict(ckpt.get("model", ckpt)), strict=False)
        model.eval().to(device)
        _gdino_cache[device] = model
    return _gdino_cache[device]


_IMG_TRANSFORM = T.Compose([
    T.RandomResize([800], max_size=1333),
    T.ToTensor(),
    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def _load_image(path: str | Path) -> tuple[np.ndarray, torch.Tensor]:
    pil = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    tensor, _ = _IMG_TRANSFORM(pil, None)
    return np.asarray(pil), tensor


def _cxcywh_to_xyxy(boxes: torch.Tensor, w: int, h: int) -> torch.Tensor:
    s  = torch.tensor([w, h, w, h], dtype=torch.float32)
    b  = boxes * s
    x1 = (b[:, 0] - b[:, 2] / 2).clamp(0, w)
    y1 = (b[:, 1] - b[:, 3] / 2).clamp(0, h)
    x2 = (b[:, 0] + b[:, 2] / 2).clamp(0, w)
    y2 = (b[:, 1] + b[:, 3] / 2).clamp(0, h)
    return torch.stack([x1, y1, x2, y2], dim=1)


def run_grounding_dino(
    image_path: str | Path,
    prompt: str,
    device: str,
    box_threshold: float = 0.25,
    text_threshold: float = 0.20,
    nms_threshold:  float = 0.65,
    max_detections: int   = 50,
) -> tuple[np.ndarray, list[Detection]]:
    """
    Run GroundingDINO on an image.
    Returns (image_rgb, list[Detection]).
    """
    model = _load_gdino(device)
    image_rgb, image_t = _load_image(image_path)
    h, w = image_rgb.shape[:2]

    caption = prompt.lower().strip().rstrip(".") + "."

    with torch.inference_mode():
        out = model(image_t[None].to(device), captions=[caption])

    logits = out["pred_logits"].cpu().sigmoid()[0]
    boxes  = out["pred_boxes"].cpu()[0]

    keep   = logits.max(dim=1)[0] > box_threshold
    logits, boxes = logits[keep], boxes[keep]
    if len(boxes) == 0:
        return image_rgb, []

    scores    = logits.max(dim=1)[0]
    tokenizer = model.tokenizer
    tokenized = tokenizer(caption)
    phrases   = [
        get_phrases_from_posmap(l > text_threshold, tokenized, tokenizer).replace(".", "")
        for l in logits
    ]

    xyxy     = _cxcywh_to_xyxy(boxes, w, h)
    keep_idx = nms(xyxy, scores, nms_threshold)[:max_detections]

    detections = []
    for i in keep_idx.tolist():
        detections.append(Detection(
            box_xyxy=xyxy[i].numpy().astype(np.float32),
            phrase=phrases[i] or prompt.strip(". "),
            score=float(scores[i]),
        ))
    detections.sort(key=lambda d: d.score, reverse=True)
    return image_rgb, detections


# ---------------------------------------------------------------------------
# SAM 2 – model + inference
# ---------------------------------------------------------------------------
_sam2_cache: dict[str, SAM2ImagePredictor] = {}

def _load_sam2(device: str) -> SAM2ImagePredictor:
    if device not in _sam2_cache:
        model = build_sam2(SAM2_CONFIG, str(SAM2_WEIGHTS), device=device, apply_postprocessing=True)
        _sam2_cache[device] = SAM2ImagePredictor(model)
    return _sam2_cache[device]


def _disk(r: int) -> np.ndarray:
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r


def _best_mask(masks: np.ndarray, scores: np.ndarray, box: np.ndarray) -> np.ndarray:
    """Pick the mask with the highest SAM score, weighted by how well it covers the box."""
    x1, y1, x2, y2 = box.astype(int)
    box_area = max(1, (x2 - x1) * (y2 - y1))
    ranked = []
    for mask, score in zip(masks.astype(bool), scores):
        inside = int(mask[y1:y2, x1:x2].sum())
        ranked.append(float(score) + 0.2 * inside / box_area)
    return masks[np.argmax(ranked)].astype(bool)


def run_sam2(
    image_rgb: np.ndarray,
    detections: list[Detection],
    device: str,
    dilate: int       = 4,
    fill_holes: bool  = True,
) -> list[np.ndarray]:
    """
    Run SAM 2 on each detected bounding box.
    Returns a list of boolean masks (H, W), one per detection.
    """
    predictor = _load_sam2(device)
    masks = []

    with torch.inference_mode():
        predictor.set_image(image_rgb)
        for det in detections:
            box = det.box_xyxy
            cx  = (box[0] + box[2]) / 2
            cy  = (box[1] + box[3]) / 2

            raw_masks, scores, _ = predictor.predict(
                point_coords=np.array([[cx, cy]], dtype=np.float32),
                point_labels=np.array([1], dtype=np.int32),
                box=box,
                multimask_output=True,
            )
            best = _best_mask(raw_masks, scores, box)

            if fill_holes:
                best = ndi.binary_fill_holes(best)
            if dilate > 0:
                best = ndi.binary_dilation(best, structure=_disk(dilate))
            masks.append(best)

    return masks


# ---------------------------------------------------------------------------
# Visualization – boxes + filled masks in one pass
# ---------------------------------------------------------------------------
_COLORS = [
    (255,  64,  64), ( 64, 220,  64), ( 64, 120, 255),
    (255, 210,  50), (200,  64, 255), ( 50, 220, 220),
    (255, 140,  50), (140, 255,  80),
]


def render(
    image_rgb:  np.ndarray,
    detections: list[Detection],
    masks:      list[np.ndarray],
    mask_alpha: float = 0.45,
) -> np.ndarray:
    """
    Draw SAM2 filled masks + GroundingDINO bounding boxes + labels
    on a single output image.
    """
    base   = Image.fromarray(image_rgb).convert("RGBA")
    canvas = base.copy()

    # Filled masks (translucent colour per object)
    for i, mask in enumerate(masks):
        r, g, b = _COLORS[i % len(_COLORS)]
        alpha   = int(255 * mask_alpha)
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        overlay.paste(
            (r, g, b, alpha),
            mask=Image.fromarray((mask > 0).astype(np.uint8) * 255, mode="L"),
        )
        canvas = Image.alpha_composite(canvas, overlay)

    # Bounding boxes + labels on top
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for i, det in enumerate(detections):
        r, g, b   = _COLORS[i % len(_COLORS)]
        x1, y1, x2, y2 = det.box_xyxy.astype(int).tolist()
        label     = f"{det.phrase} {det.score:.2f}"

        draw.rectangle((x1, y1, x2, y2), outline=(r, g, b, 255), width=3)
        tb  = draw.textbbox((x1, y1), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ly  = max(0, y1 - th - 8)
        draw.rectangle((x1, ly, x1 + tw + 8, ly + th + 6), fill=(15, 23, 42, 220))
        draw.text((x1 + 4, ly + 3), label, fill=(r, g, b, 255), font=font)

    return np.asarray(canvas.convert("RGB"))


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------
def run_pipeline(
    image_path:     str | Path,
    prompt:         str,
    device:         str     = "auto",
    box_threshold:  float   = 0.25,
    text_threshold: float   = 0.20,
    nms_threshold:  float   = 0.65,
    max_detections: int     = 50,
    mask_dilate:    int     = 4,
    fill_holes:     bool    = True,
    mask_alpha:     float   = 0.45,
) -> tuple[np.ndarray, list[Detection], list[np.ndarray]]:
    """
    Full pipeline: image -> GroundingDINO boxes -> SAM 2 masks -> rendered output.

    Returns:
        output_rgb   – H×W×3 uint8 image with boxes and masks drawn
        detections   – list of Detection(box_xyxy, phrase, score)
        masks        – list of boolean H×W masks, one per detection
    """
    device = resolve_device(device)
    print(f"[pipeline] device : {device_info(device)}")
    print(f"[pipeline] prompt : '{prompt}'")
    print(f"[pipeline] image  : {image_path}")

    torch.set_grad_enabled(False)
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")

    # Step 1 – GroundingDINO
    print("[1/2] GroundingDINO  – detecting objects...")
    image_rgb, detections = run_grounding_dino(
        image_path, prompt, device,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        nms_threshold=nms_threshold,
        max_detections=max_detections,
    )
    if not detections:
        print("      No objects found. Try lowering --box-threshold.")
        return image_rgb, [], []
    for det in detections:
        b = det.box_xyxy.astype(int).tolist()
        print(f"      [{det.score:.3f}] {det.phrase:20s}  box={b}")

    clear_cache(device)

    # Step 2 – SAM 2
    print("[2/2] SAM 2          – segmenting pixel-wise...")
    masks = run_sam2(image_rgb, detections, device, dilate=mask_dilate, fill_holes=fill_holes)
    for i, m in enumerate(masks):
        px = int(m.sum())
        print(f"      Mask {i} ({detections[i].phrase}): {px:,} px  ({px * 100 / m.size:.1f}%)")

    clear_cache(device)

    output_rgb = render(image_rgb, detections, masks, mask_alpha=mask_alpha)
    return output_rgb, detections, masks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="GroundingDINO + SAM 2 detection & segmentation pipeline"
    )
    parser.add_argument("prompt", help="Object(s) to find, e.g. 'person' or 'car . person . bag'")
    parser.add_argument("--image",          default=str(ROOT / "input.jpeg"))
    parser.add_argument("--output",         default="pipeline_output.jpg")
    parser.add_argument("--device",         default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--box-threshold",  type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    parser.add_argument("--nms-threshold",  type=float, default=0.65)
    parser.add_argument("--max-detections", type=int,   default=50)
    parser.add_argument("--mask-dilate",    type=int,   default=4,
                        help="Dilation radius for SAM2 masks (pixels)")
    parser.add_argument("--mask-alpha",     type=float, default=0.45,
                        help="Opacity of the segmentation overlay (0-1)")
    parser.add_argument("--no-fill-holes",  action="store_true")
    args = parser.parse_args()

    output_rgb, detections, masks = run_pipeline(
        image_path     = args.image,
        prompt         = args.prompt,
        device         = args.device,
        box_threshold  = args.box_threshold,
        text_threshold = args.text_threshold,
        nms_threshold  = args.nms_threshold,
        max_detections = args.max_detections,
        mask_dilate    = args.mask_dilate,
        fill_holes     = not args.no_fill_holes,
        mask_alpha     = args.mask_alpha,
    )

    if not detections:
        return 1

    out = Path(args.output)
    Image.fromarray(output_rgb).save(str(out), quality=95)
    print(f"\nSaved → {out}   ({len(detections)} object(s) detected & segmented)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
