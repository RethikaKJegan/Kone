# =============================================================================
# Elevator Component Detection & Segmentation — Google Colab Notebook
# =============================================================================
# Copy-paste each section into a separate Colab cell.
# Runtime: GPU (T4 is sufficient). Estimated setup: ~3 min.
#
# Pipeline: GroundingDINO (detection) → SAM2 (segmentation)
# Input:    One elevator image
# Output:   Bounding boxes + pixel-precise masks for every component
# =============================================================================


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CELL 1 — Install dependencies & clone repos                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# !pip install -q torch torchvision numpy pillow scipy transformers pyyaml tqdm
# !pip install -q addict yapf timm pycocotools supervision

# # GroundingDINO
# !git clone -q https://github.com/IDEA-Research/GroundingDINO.git
# !pip install -q -e GroundingDINO/

# # SAM 2
# !git clone -q https://github.com/facebookresearch/sam2.git
# !cd sam2 && pip install -q -e .

# # Download weights
# !mkdir -p weights
# !wget -q -nc -O weights/groundingdino_swint_ogc.pth \
#     "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth"
# !wget -q -nc -O weights/sam2.1_hiera_large.pt \
#     "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt"


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CELL 2 — Upload your elevator image                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# from google.colab import files
# uploaded = files.upload()  # pick your elevator photo
# IMAGE_PATH = list(uploaded.keys())[0]
# print(f"Using: {IMAGE_PATH}")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CELL 3 — Pipeline code (run as-is)                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

from __future__ import annotations
import os, sys, warnings
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage as ndi
from torchvision.ops import nms

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(".")
GDINO_DIR     = ROOT / "GroundingDINO"
SAM2_DIR      = ROOT / "sam2"
GDINO_CONFIG  = GDINO_DIR / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
GDINO_WEIGHTS = ROOT / "weights/groundingdino_swint_ogc.pth"
SAM2_CONFIG   = "configs/sam2.1/sam2.1_hiera_l.yaml"
SAM2_WEIGHTS  = ROOT / "weights/sam2.1_hiera_large.pt"

os.environ["TOKENIZERS_PARALLELISM"] = "false"
for p in (GDINO_DIR, SAM2_DIR):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import groundingdino.datasets.transforms as T
from groundingdino.models import build_model
from groundingdino.util.misc import clean_state_dict
from groundingdino.util.slconfig import SLConfig
from groundingdino.util.utils import get_phrases_from_posmap
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor


# ── Built-in prompts (elevator domain) ────────────────────────────────────
ELEVATOR_PROMPTS = [
    "elevator door . elevator wall . elevator panel . elevator ceiling . elevator floor",
    "elevator button panel . call button . floor indicator display . handrail . mirror",
    "emergency phone . safety sign . weight limit sign . ventilation grille . door frame",
    "light fixture . security camera . speaker . card reader . threshold plate . door track",
]

# ── Colors ─────────────────────────────────────────────────────────────────
PALETTE = [
    (255,64,64),(64,220,64),(64,120,255),(255,210,50),(200,64,255),
    (50,220,220),(255,140,50),(140,255,80),(255,80,180),(100,180,255),
    (220,180,100),(180,100,220),(80,255,180),(255,160,160),(160,160,255),
    (200,255,100),(255,100,100),(100,255,100),(100,100,255),(255,255,100),
]

# ── Data class ─────────────────────────────────────────────────────────────
@dataclass
class Detection:
    box_xyxy: np.ndarray
    phrase: str
    score: float
    mask: Optional[np.ndarray] = None

    @property
    def label(self) -> str:
        return f"{self.phrase} {self.score:.2f}"


# ── Model loaders ─────────────────────────────────────────────────────────
def load_gdino(device):
    args = SLConfig.fromfile(str(GDINO_CONFIG))
    args.device = device
    model = build_model(args)
    ckpt = torch.load(str(GDINO_WEIGHTS), map_location="cpu", weights_only=True)
    model.load_state_dict(clean_state_dict(ckpt.get("model", ckpt)), strict=False)
    return model.eval().to(device)

def load_sam2(device):
    model = build_sam2(SAM2_CONFIG, str(SAM2_WEIGHTS), device=device, apply_postprocessing=True)
    return SAM2ImagePredictor(model)

IMG_TRANSFORM = T.Compose([
    T.RandomResize([800], max_size=1333),
    T.ToTensor(),
    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

def load_image(path):
    pil = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    tensor, _ = IMG_TRANSFORM(pil, None)
    return np.asarray(pil), tensor

def cxcywh_to_xyxy(boxes, w, h):
    s = torch.tensor([w, h, w, h], dtype=torch.float32)
    b = boxes * s
    x1 = (b[:,0] - b[:,2]/2).clamp(0, w)
    y1 = (b[:,1] - b[:,3]/2).clamp(0, h)
    x2 = (b[:,0] + b[:,2]/2).clamp(0, w)
    y2 = (b[:,1] + b[:,3]/2).clamp(0, h)
    return torch.stack([x1, y1, x2, y2], dim=1)

def disk(r):
    yy, xx = np.ogrid[-r:r+1, -r:r+1]
    return (xx*xx + yy*yy) <= r*r


# ── Detection (GroundingDINO across all prompts) ──────────────────────────
def detect_components(image_path, device, box_thresh=0.25, text_thresh=0.20, nms_thresh=0.50):
    model = load_gdino(device)
    image_rgb, image_tensor = load_image(image_path)
    h, w = image_rgb.shape[:2]

    all_boxes, all_scores, all_phrases = [], [], []

    with torch.inference_mode():
        for prompt in ELEVATOR_PROMPTS:
            caption = prompt.lower().strip().rstrip(".") + "."
            out = model(image_tensor[None].to(device), captions=[caption])

            logits = out["pred_logits"].cpu().sigmoid()[0]
            boxes  = out["pred_boxes"].cpu()[0]

            keep = logits.max(dim=1)[0] > box_thresh
            logits, boxes = logits[keep], boxes[keep]
            if len(boxes) == 0:
                continue

            scores = logits.max(dim=1)[0]
            tokenizer = model.tokenizer
            tokenized = tokenizer(caption)
            phrases = [
                get_phrases_from_posmap(l > text_thresh, tokenized, tokenizer)
                .replace(".", "").strip()
                for l in logits
            ]

            xyxy = cxcywh_to_xyxy(boxes, w, h)
            all_boxes.append(xyxy)
            all_scores.append(scores)
            all_phrases.extend(phrases)

    del model
    torch.cuda.empty_cache()

    if not all_boxes:
        return image_rgb, []

    all_boxes  = torch.cat(all_boxes)
    all_scores = torch.cat(all_scores)
    keep_idx   = nms(all_boxes, all_scores, nms_thresh)[:50]

    detections = []
    for i in keep_idx.tolist():
        detections.append(Detection(
            box_xyxy=all_boxes[i].numpy().astype(np.float32),
            phrase=all_phrases[i] or "component",
            score=float(all_scores[i]),
        ))
    detections.sort(key=lambda d: d.score, reverse=True)
    return image_rgb, detections


# ── Segmentation (SAM2) ──────────────────────────────────────────────────
def segment_components(image_rgb, detections, device, dilate=4, fill_holes=True):
    predictor = load_sam2(device)
    with torch.inference_mode():
        predictor.set_image(image_rgb)
        for det in detections:
            box = det.box_xyxy
            cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2

            masks, scores, _ = predictor.predict(
                point_coords=np.array([[cx, cy]], dtype=np.float32),
                point_labels=np.array([1], dtype=np.int32),
                box=box,
                multimask_output=True,
            )
            best = masks[np.argmax(scores)].astype(bool)
            if fill_holes:
                best = ndi.binary_fill_holes(best)
            if dilate > 0:
                best = ndi.binary_dilation(best, structure=disk(dilate))
            det.mask = best

    del predictor
    torch.cuda.empty_cache()
    return detections


# ── Visualization ─────────────────────────────────────────────────────────
def draw_boxes(image_rgb, detections):
    img = Image.fromarray(image_rgb).convert("RGBA")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    for i, det in enumerate(detections):
        r, g, b = PALETTE[i % len(PALETTE)]
        x1, y1, x2, y2 = det.box_xyxy.astype(int).tolist()
        draw.rectangle((x1,y1,x2,y2), outline=(r,g,b,255), width=3)
        label = det.label
        tb = draw.textbbox((x1,y1), label, font=font)
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        ly = max(0, y1-th-10)
        draw.rectangle((x1, ly, x1+tw+10, ly+th+8), fill=(15,23,42,220))
        draw.text((x1+5, ly+4), label, fill=(r,g,b,255), font=font)
    return np.asarray(img.convert("RGB"))

def draw_masks(image_rgb, detections, alpha=0.45):
    base = Image.fromarray(image_rgb).convert("RGBA")
    canvas = base.copy()

    for i, det in enumerate(detections):
        if det.mask is None:
            continue
        r, g, b = PALETTE[i % len(PALETTE)]
        a = int(255 * alpha)
        overlay = Image.new("RGBA", base.size, (0,0,0,0))
        overlay.paste((r,g,b,a), mask=Image.fromarray(det.mask.astype(np.uint8)*255, "L"))
        canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for i, det in enumerate(detections):
        r, g, b = PALETTE[i % len(PALETTE)]
        x1, y1, x2, y2 = det.box_xyxy.astype(int).tolist()
        draw.rectangle((x1,y1,x2,y2), outline=(r,g,b,255), width=2)
        label = det.label
        tb = draw.textbbox((x1,y1), label, font=font)
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        ly = max(0, y1-th-10)
        draw.rectangle((x1, ly, x1+tw+10, ly+th+8), fill=(15,23,42,220))
        draw.text((x1+5, ly+4), label, fill=(r,g,b,255), font=font)
    return np.asarray(canvas.convert("RGB"))


print("✓ Pipeline code loaded.")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CELL 4 — Run the pipeline                                              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# IMAGE_PATH = "your_elevator_image.jpg"   # ← set this or use Cell 2 upload
# DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# print(f"Device: {DEVICE}")
# print(f"Image:  {IMAGE_PATH}")
# print(f"Prompts: {len(ELEVATOR_PROMPTS)} groups\n")

# # Step 1: Detect
# print("=" * 60)
# print("STEP 1: GroundingDINO — detecting elevator components...")
# print("=" * 60)
# image_rgb, detections = detect_components(IMAGE_PATH, DEVICE)
# print(f"→ Found {len(detections)} component(s)\n")

# # Step 2: Segment
# print("=" * 60)
# print("STEP 2: SAM2 — pixel-wise segmentation...")
# print("=" * 60)
# detections = segment_components(image_rgb, detections, DEVICE)
# print(f"→ Segmented {len(detections)} mask(s)\n")

# # Step 3: Render
# detected_img  = draw_boxes(image_rgb, detections)
# segmented_img = draw_masks(image_rgb, detections)

# # Summary
# print("=" * 60)
# print("RESULTS")
# print("=" * 60)
# for i, d in enumerate(detections):
#     px = int(d.mask.sum()) if d.mask is not None else 0
#     box = d.box_xyxy.astype(int).tolist()
#     print(f"  [{i:2d}] {d.label:35s} box={box}  mask={px:,}px")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CELL 5 — Display results side by side                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# import matplotlib.pyplot as plt

# fig, axes = plt.subplots(1, 3, figsize=(24, 8))

# axes[0].imshow(image_rgb)
# axes[0].set_title("Original", fontsize=14)
# axes[0].axis("off")

# axes[1].imshow(detected_img)
# axes[1].set_title(f"GroundingDINO — {len(detections)} detections", fontsize=14)
# axes[1].axis("off")

# axes[2].imshow(segmented_img)
# axes[2].set_title(f"SAM2 Segmentation — {len(detections)} masks", fontsize=14)
# axes[2].axis("off")

# plt.tight_layout()
# plt.savefig("elevator_results.jpg", dpi=150, bbox_inches="tight")
# plt.show()
# print("Saved: elevator_results.jpg")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CELL 6 — Save individual masks + combined mask                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# import os
# os.makedirs("outputs", exist_ok=True)

# Image.fromarray(image_rgb).save("outputs/original.jpg", quality=95)
# Image.fromarray(detected_img).save("outputs/detected_boxes.jpg", quality=95)
# Image.fromarray(segmented_img).save("outputs/segmented_masks.jpg", quality=95)

# # Individual masks
# for i, det in enumerate(detections):
#     if det.mask is not None:
#         tag = det.phrase.replace(" ", "_")
#         mask_img = Image.fromarray(det.mask.astype(np.uint8) * 255)
#         mask_img.save(f"outputs/mask_{i:02d}_{tag}.png")

# # Combined mask
# if detections:
#     combined = np.zeros(image_rgb.shape[:2], dtype=bool)
#     for d in detections:
#         if d.mask is not None:
#             combined |= d.mask
#     Image.fromarray(combined.astype(np.uint8) * 255).save("outputs/combined_mask.png")

# print(f"Saved {2 + len(detections) + 1} files to outputs/")

# # Download all outputs
# !zip -q -r outputs.zip outputs/
# from google.colab import files
# files.download("outputs.zip")
