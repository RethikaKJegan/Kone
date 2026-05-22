# ===========================================================================
# Elevator Component Detection & Segmentation — Single Colab Cell
# ===========================================================================
# 1. Open Google Colab → Runtime → Change runtime type → GPU (T4 is fine)
# 2. Paste this entire block into ONE cell and run it
# 3. It will ask you to upload an elevator image, then produce results
# ===========================================================================

# ── Step 0: Install everything ─────────────────────────────────────────────
import subprocess, sys

def run(cmd):
    subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Installing dependencies...")
run("pip install -q torch torchvision numpy pillow scipy transformers pyyaml tqdm")
run("pip install -q addict yapf timm pycocotools")

import os
from pathlib import Path

if not Path("GroundingDINO").exists():
    print("Cloning GroundingDINO...")
    run("git clone -q https://github.com/IDEA-Research/GroundingDINO.git")
    run("pip install -q -e GroundingDINO/")

if not Path("sam2").exists():
    print("Cloning SAM2...")
    run("git clone -q https://github.com/facebookresearch/sam2.git")
    run("cd sam2 && pip install -q -e .")

os.makedirs("weights", exist_ok=True)
if not Path("weights/groundingdino_swint_ogc.pth").exists():
    print("Downloading GroundingDINO weights...")
    run("wget -q -O weights/groundingdino_swint_ogc.pth "
        "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth")

if not Path("weights/sam2.1_hiera_large.pt").exists():
    print("Downloading SAM2 weights...")
    run("wget -q -O weights/sam2.1_hiera_large.pt "
        "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt")

print("Setup complete.\n")

# ── Step 1: Upload image ──────────────────────────────────────────────────
from google.colab import files as colab_files

print("Upload your elevator image:")
uploaded = colab_files.upload()
IMAGE_PATH = list(uploaded.keys())[0]
print(f"Using: {IMAGE_PATH}\n")

# ── Step 2: Imports & paths ───────────────────────────────────────────────
from __future__ import annotations
import warnings
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage as ndi
from torchvision.ops import nms
from dataclasses import dataclass
from typing import Optional
import matplotlib.pyplot as plt

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

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {DEVICE}")

# ── Step 3: Built-in elevator prompts ─────────────────────────────────────
ELEVATOR_PROMPTS = [
    "elevator door . elevator wall . elevator panel . elevator ceiling . elevator floor",
    "elevator button panel . call button . floor indicator display . handrail . mirror",
    "emergency phone . safety sign . weight limit sign . ventilation grille . door frame",
    "light fixture . security camera . speaker . card reader . threshold plate . door track",
]

# ── Step 4: Colors ────────────────────────────────────────────────────────
PALETTE = [
    (255,64,64),(64,220,64),(64,120,255),(255,210,50),(200,64,255),
    (50,220,220),(255,140,50),(140,255,80),(255,80,180),(100,180,255),
    (220,180,100),(180,100,220),(80,255,180),(255,160,160),(160,160,255),
    (200,255,100),(255,100,100),(100,255,100),(100,100,255),(255,255,100),
]

# ── Step 5: Data class ────────────────────────────────────────────────────
@dataclass
class Detection:
    box_xyxy: np.ndarray
    phrase: str
    score: float
    mask: Optional[np.ndarray] = None

    @property
    def label(self) -> str:
        return f"{self.phrase} {self.score:.2f}"

# ── Step 6: Helpers ───────────────────────────────────────────────────────
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

# ── Step 7: GroundingDINO detection ───────────────────────────────────────
print("\n" + "="*60)
print("STEP 1/3: GroundingDINO — detecting elevator components...")
print("="*60)

args_cfg = SLConfig.fromfile(str(GDINO_CONFIG))
args_cfg.device = DEVICE
gdino = build_model(args_cfg)
ckpt = torch.load(str(GDINO_WEIGHTS), map_location="cpu", weights_only=True)
gdino.load_state_dict(clean_state_dict(ckpt.get("model", ckpt)), strict=False)
gdino.eval().to(DEVICE)
print("GroundingDINO loaded.")

image_rgb, image_tensor = load_image(IMAGE_PATH)
h, w = image_rgb.shape[:2]
print(f"Image size: {w}x{h}")

all_boxes, all_scores, all_phrases = [], [], []

torch.set_grad_enabled(False)
with torch.inference_mode():
    for prompt in ELEVATOR_PROMPTS:
        caption = prompt.lower().strip().rstrip(".") + "."
        out = gdino(image_tensor[None].to(DEVICE), captions=[caption])

        logits = out["pred_logits"].cpu().sigmoid()[0]
        boxes  = out["pred_boxes"].cpu()[0]

        keep = logits.max(dim=1)[0] > 0.25
        logits, boxes = logits[keep], boxes[keep]
        if len(boxes) == 0:
            continue

        scores = logits.max(dim=1)[0]
        tokenizer = gdino.tokenizer
        tokenized = tokenizer(caption)
        phrases = [
            get_phrases_from_posmap(l > 0.20, tokenized, tokenizer)
            .replace(".", "").strip()
            for l in logits
        ]

        xyxy = cxcywh_to_xyxy(boxes, w, h)
        all_boxes.append(xyxy)
        all_scores.append(scores)
        all_phrases.extend(phrases)

del gdino
torch.cuda.empty_cache()

if not all_boxes:
    print("No components detected. Try a different image.")
else:
    all_boxes  = torch.cat(all_boxes)
    all_scores = torch.cat(all_scores)
    keep_idx   = nms(all_boxes, all_scores, 0.50)[:50]

    detections = []
    for i in keep_idx.tolist():
        detections.append(Detection(
            box_xyxy=all_boxes[i].numpy().astype(np.float32),
            phrase=all_phrases[i] or "component",
            score=float(all_scores[i]),
        ))
    detections.sort(key=lambda d: d.score, reverse=True)
    print(f"Detected {len(detections)} component(s):")
    for i, d in enumerate(detections):
        print(f"  [{i:2d}] {d.label:35s} box={d.box_xyxy.astype(int).tolist()}")

    # ── Step 8: SAM2 segmentation ─────────────────────────────────────────
    print("\n" + "="*60)
    print("STEP 2/3: SAM2 — pixel-wise segmentation...")
    print("="*60)

    sam2_model = build_sam2(SAM2_CONFIG, str(SAM2_WEIGHTS), device=DEVICE, apply_postprocessing=True)
    predictor  = SAM2ImagePredictor(sam2_model)
    print("SAM2 loaded.")

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
            best = ndi.binary_fill_holes(best)
            best = ndi.binary_dilation(best, structure=disk(4))
            det.mask = best

    del predictor, sam2_model
    torch.cuda.empty_cache()

    print("Segmentation complete:")
    for i, d in enumerate(detections):
        px = int(d.mask.sum()) if d.mask is not None else 0
        print(f"  [{i:2d}] {d.phrase:30s} → {px:,} pixels")

    # ── Step 9: Render outputs ────────────────────────────────────────────
    print("\n" + "="*60)
    print("STEP 3/3: Rendering outputs...")
    print("="*60)

    # Bounding box image
    box_img = Image.fromarray(image_rgb).convert("RGBA")
    draw = ImageDraw.Draw(box_img)
    font = ImageFont.load_default()
    for i, det in enumerate(detections):
        r, g, b = PALETTE[i % len(PALETTE)]
        x1, y1, x2, y2 = det.box_xyxy.astype(int).tolist()
        draw.rectangle((x1,y1,x2,y2), outline=(r,g,b,255), width=3)
        label = det.label
        tb = draw.textbbox((x1,y1), label, font=font)
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        ly = max(0, y1-th-10)
        draw.rectangle((x1,ly,x1+tw+10,ly+th+8), fill=(15,23,42,220))
        draw.text((x1+5,ly+4), label, fill=(r,g,b,255), font=font)
    detected_img = np.asarray(box_img.convert("RGB"))

    # Mask overlay image
    base = Image.fromarray(image_rgb).convert("RGBA")
    canvas = base.copy()
    for i, det in enumerate(detections):
        if det.mask is None:
            continue
        r, g, b = PALETTE[i % len(PALETTE)]
        overlay = Image.new("RGBA", base.size, (0,0,0,0))
        overlay.paste((r,g,b,115), mask=Image.fromarray(det.mask.astype(np.uint8)*255, "L"))
        canvas = Image.alpha_composite(canvas, overlay)
    draw2 = ImageDraw.Draw(canvas)
    for i, det in enumerate(detections):
        r, g, b = PALETTE[i % len(PALETTE)]
        x1, y1, x2, y2 = det.box_xyxy.astype(int).tolist()
        draw2.rectangle((x1,y1,x2,y2), outline=(r,g,b,255), width=2)
        label = det.label
        tb = draw2.textbbox((x1,y1), label, font=font)
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        ly = max(0, y1-th-10)
        draw2.rectangle((x1,ly,x1+tw+10,ly+th+8), fill=(15,23,42,220))
        draw2.text((x1+5,ly+4), label, fill=(r,g,b,255), font=font)
    segmented_img = np.asarray(canvas.convert("RGB"))

    # ── Step 10: Display ──────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(24, 8))
    axes[0].imshow(image_rgb);          axes[0].set_title("Original", fontsize=14);                                      axes[0].axis("off")
    axes[1].imshow(detected_img);       axes[1].set_title(f"GroundingDINO — {len(detections)} detections", fontsize=14);  axes[1].axis("off")
    axes[2].imshow(segmented_img);      axes[2].set_title(f"SAM2 — {len(detections)} masks", fontsize=14);               axes[2].axis("off")
    plt.tight_layout()
    plt.savefig("elevator_results.jpg", dpi=150, bbox_inches="tight")
    plt.show()

    # ── Step 11: Save all outputs ─────────────────────────────────────────
    os.makedirs("outputs", exist_ok=True)
    Image.fromarray(image_rgb).save("outputs/original.jpg", quality=95)
    Image.fromarray(detected_img).save("outputs/detected_boxes.jpg", quality=95)
    Image.fromarray(segmented_img).save("outputs/segmented_masks.jpg", quality=95)

    for i, det in enumerate(detections):
        if det.mask is not None:
            tag = det.phrase.replace(" ", "_")
            Image.fromarray(det.mask.astype(np.uint8)*255).save(f"outputs/mask_{i:02d}_{tag}.png")

    combined = np.zeros(image_rgb.shape[:2], dtype=bool)
    for d in detections:
        if d.mask is not None:
            combined |= d.mask
    Image.fromarray(combined.astype(np.uint8)*255).save("outputs/combined_mask.png")

    total_files = 3 + len(detections) + 1
    print(f"\nSaved {total_files} files to outputs/")
    print("Done!")
