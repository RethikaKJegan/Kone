"""
GroundingDINO: open-vocabulary object detection.
Accepts any text prompt and returns bounding boxes with labels.

Usage:
    python grounding_dino_detect.py "person . bag . car" --image input.jpeg
    python grounding_dino_detect.py "dog" --image photo.jpg --box-threshold 0.3
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from torchvision.ops import nms

ROOT = Path(__file__).resolve().parent
GROUNDING_DINO_DIR = ROOT / "GroundingDINO"
BERT_DIR = ROOT / "bert-base-uncased"
CACHE_DIR = ROOT / ".cache"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

if str(GROUNDING_DINO_DIR) not in sys.path:
    sys.path.insert(0, str(GROUNDING_DINO_DIR))

import groundingdino.datasets.transforms as T
from groundingdino.models import build_model
from groundingdino.util.misc import clean_state_dict
from groundingdino.util.slconfig import SLConfig
from groundingdino.util.utils import get_phrases_from_posmap

CONFIG_PATH = GROUNDING_DINO_DIR / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
WEIGHTS_PATH = ROOT / "weights/groundingdino_swint_ogc.pth"


# ---------------------------------------------------------------------------
# Model loader (cached singleton for production reuse)
# ---------------------------------------------------------------------------
_MODEL_CACHE: dict[str, object] = {}


def load_model(device: str = "cpu") -> object:
    key = device
    if key not in _MODEL_CACHE:
        args = SLConfig.fromfile(str(CONFIG_PATH))
        args.device = device
        if BERT_DIR.exists():
            args.text_encoder_type = str(BERT_DIR)
        model = build_model(args)
        ckpt = torch.load(str(WEIGHTS_PATH), map_location="cpu", weights_only=True)
        sd = ckpt.get("model", ckpt)
        model.load_state_dict(clean_state_dict(sd), strict=False)
        model.eval().to(device)
        _MODEL_CACHE[key] = model
    return _MODEL_CACHE[key]


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------
_TRANSFORM = T.Compose([
    T.RandomResize([800], max_size=1333),
    T.ToTensor(),
    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def load_image(path: str | Path) -> tuple[np.ndarray, torch.Tensor]:
    pil = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    src = np.asarray(pil)
    transformed, _ = _TRANSFORM(pil, None)
    return src, transformed


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def detect(
    image_path: str | Path,
    prompt: str,
    box_threshold: float = 0.25,
    text_threshold: float = 0.20,
    nms_threshold: float = 0.65,
    max_detections: int = 50,
    device: str = "cpu",
) -> list[dict]:
    """
    Detect objects matching `prompt` in the image.

    Returns list of dicts with keys: box_xyxy, phrase, score.
    box_xyxy is in absolute pixel coordinates [x1, y1, x2, y2].
    """
    model = load_model(device)
    image_src, image_tensor = load_image(image_path)
    h, w = image_src.shape[:2]

    caption = prompt.lower().strip()
    if not caption.endswith("."):
        caption += "."

    with torch.inference_mode():
        outputs = model(image_tensor[None].to(device), captions=[caption])

    logits = outputs["pred_logits"].cpu().sigmoid()[0]
    boxes = outputs["pred_boxes"].cpu()[0]

    keep = logits.max(dim=1)[0] > box_threshold
    logits, boxes = logits[keep], boxes[keep]
    if len(boxes) == 0:
        return []

    scores = logits.max(dim=1)[0]
    tokenizer = model.tokenizer
    tokenized = tokenizer(caption)
    phrases = [
        get_phrases_from_posmap(l > text_threshold, tokenized, tokenizer).replace(".", "")
        for l in logits
    ]

    xyxy = _cxcywh_to_xyxy(boxes, w, h)
    nms_keep = nms(xyxy, scores, nms_threshold)[:max_detections]

    results = []
    for i in nms_keep.tolist():
        results.append({
            "box_xyxy": xyxy[i].numpy().astype(np.float32),
            "phrase": phrases[i] or prompt.strip(". "),
            "score": float(scores[i]),
        })
    results.sort(key=lambda d: d["score"], reverse=True)
    return results


def _cxcywh_to_xyxy(boxes: torch.Tensor, w: int, h: int) -> torch.Tensor:
    scale = torch.tensor([w, h, w, h], dtype=torch.float32)
    cxcywh = boxes * scale
    x1 = (cxcywh[:, 0] - cxcywh[:, 2] / 2).clamp(0, w)
    y1 = (cxcywh[:, 1] - cxcywh[:, 3] / 2).clamp(0, h)
    x2 = (cxcywh[:, 0] + cxcywh[:, 2] / 2).clamp(0, w)
    y2 = (cxcywh[:, 1] + cxcywh[:, 3] / 2).clamp(0, h)
    return torch.stack([x1, y1, x2, y2], dim=1)


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------
def draw_detections(image_rgb: np.ndarray, detections: list[dict]) -> np.ndarray:
    img = Image.fromarray(image_rgb).convert("RGBA")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    for det in detections:
        x1, y1, x2, y2 = det["box_xyxy"].astype(int).tolist()
        label = f"{det['phrase']} {det['score']:.2f}"
        draw.rectangle((x1, y1, x2, y2), outline=(44, 220, 112, 255), width=3)
        tb = draw.textbbox((x1, y1), label, font=font)
        th = tb[3] - tb[1]
        tw = tb[2] - tb[0]
        ly = max(0, y1 - th - 8)
        draw.rectangle((x1, ly, x1 + tw + 8, ly + th + 6), fill=(15, 23, 42, 230))
        draw.text((x1 + 4, ly + 3), label, fill=(255, 255, 255, 255), font=font)

    return np.asarray(img.convert("RGB"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _select_device(req: str) -> str:
    if req != "auto":
        return req
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def main():
    parser = argparse.ArgumentParser(description="GroundingDINO open-vocabulary detector")
    parser.add_argument("prompt", help="Objects to detect, e.g. 'person . bag . car'")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--output", default="dino_output.jpg", help="Output image path")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    parser.add_argument("--nms-threshold", type=float, default=0.65)
    parser.add_argument("--max-detections", type=int, default=50)
    args = parser.parse_args()

    device = _select_device(args.device)
    print(f"Device: {device} | Prompt: '{args.prompt}'")

    torch.set_grad_enabled(False)
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")

    detections = detect(
        args.image, args.prompt,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        nms_threshold=args.nms_threshold,
        max_detections=args.max_detections,
        device=device,
    )

    if not detections:
        print("No objects detected. Try lowering --box-threshold or changing the prompt.")
        return 1

    for det in detections:
        box = det["box_xyxy"].astype(int).tolist()
        print(f"  [{det['score']:.3f}] {det['phrase']:20s}  box={box}")

    image_src, _ = load_image(args.image)
    vis = draw_detections(image_src, detections)
    out_path = Path(args.output)
    Image.fromarray(vis).save(str(out_path), quality=95)
    print(f"Saved: {out_path}  ({len(detections)} detections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
