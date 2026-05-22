# ===========================================================================
# Elevator Component Detection & Segmentation — Bi-LSTM Text Encoder
# ===========================================================================
# Replaces BERT with a Bi-LSTM inside GroundingDINO.
#
# 1. Open Google Colab → Runtime → Change runtime type → GPU (T4)
# 2. Paste this entire block into ONE cell and run
# 3. Upload an elevator image when prompted → get detection + segmentation
#
# Architecture:
#   BERT tokenizer (vocab only) → Bi-LSTM encoder → GroundingDINO decoder
#   SAM2 segments each detected bounding box into pixel masks
# ===========================================================================


# ═══════════════════════════════════════════════════════════════════════════
#  INSTALL & DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════
import subprocess, sys, os
from pathlib import Path

def run(cmd):
    subprocess.check_call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("=" * 60)
print("SETUP")
print("=" * 60)

print("[1/5] Installing dependencies...")
run("pip install -q torch torchvision numpy pillow scipy transformers pyyaml tqdm")
run("pip install -q addict yapf timm pycocotools")

if not Path("GroundingDINO").exists():
    print("[2/5] Cloning GroundingDINO...")
    run("git clone -q https://github.com/IDEA-Research/GroundingDINO.git")
    run("pip install -q -e GroundingDINO/")
else:
    print("[2/5] GroundingDINO already present.")

if not Path("sam2").exists():
    print("[3/5] Cloning SAM2...")
    run("git clone -q https://github.com/facebookresearch/sam2.git")
    run("cd sam2 && pip install -q -e .")
else:
    print("[3/5] SAM2 already present.")

os.makedirs("weights", exist_ok=True)
if not Path("weights/groundingdino_swint_ogc.pth").exists():
    print("[4/5] Downloading GroundingDINO weights...")
    run("wget -q -O weights/groundingdino_swint_ogc.pth "
        "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth")
else:
    print("[4/5] GroundingDINO weights already present.")

if not Path("weights/sam2.1_hiera_large.pt").exists():
    print("[5/5] Downloading SAM2 weights...")
    run("wget -q -O weights/sam2.1_hiera_large.pt "
        "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt")
else:
    print("[5/5] SAM2 weights already present.")

print("Setup complete.\n")


# ═══════════════════════════════════════════════════════════════════════════
#  UPLOAD IMAGE
# ═══════════════════════════════════════════════════════════════════════════
from google.colab import files as colab_files

print("Upload your elevator image:")
uploaded = colab_files.upload()
IMAGE_PATH = list(uploaded.keys())[0]
print(f"Using: {IMAGE_PATH}\n")


# ═══════════════════════════════════════════════════════════════════════════
#  IMPORTS & PATHS
# ═══════════════════════════════════════════════════════════════════════════
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import types

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage as ndi
from torchvision.ops import nms
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
from transformers import BertModel, AutoTokenizer

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {DEVICE}\n")


# ═══════════════════════════════════════════════════════════════════════════
#  BI-LSTM TEXT ENCODER  (replaces BERT's transformer layers)
# ═══════════════════════════════════════════════════════════════════════════
#
# Interface contract with GroundingDINO:
#   - Input:  input_ids, attention_mask, position_ids, token_type_ids
#   - Output: dict with "last_hidden_state" → (batch, seq_len, 768)
#   - Must expose .config.hidden_size = 768
#
# Design:
#   BERT word embeddings (frozen, transferred) → Bi-LSTM → projection → 768
#   This keeps the vocabulary knowledge from BERT while swapping the
#   encoder architecture from self-attention to recurrent.

class BiLSTMConfig:
    """Minimal config object that GroundingDINO reads from self.bert.config."""
    def __init__(self, hidden_size=768, num_hidden_layers=2):
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.output_attentions = False
        self.output_hidden_states = False
        self.use_return_dict = True
        self.is_decoder = False
        self.use_cache = False


class BiLSTMTextEncoder(nn.Module):
    """
    Drop-in replacement for BertModelWarper inside GroundingDINO.

    Architecture:
        token_ids → BERT embedding layer (transferred) → Bi-LSTM (2 layers)
                  → linear projection → 768-dim output

    The embedding layer is initialized from BERT's pretrained word/position/
    token_type embeddings so the model starts with meaningful token
    representations. The LSTM layers are randomly initialized and would
    need fine-tuning for best results.
    """

    def __init__(
        self,
        bert_model: BertModel,
        lstm_hidden: int = 512,
        lstm_layers: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.config = BiLSTMConfig(hidden_size=bert_model.config.hidden_size)
        bert_hidden = bert_model.config.hidden_size  # 768

        # Transfer BERT's embedding layer (word + position + token_type + LayerNorm)
        self.embeddings = bert_model.embeddings
        for param in self.embeddings.parameters():
            param.requires_grad = False

        # Bi-LSTM encoder
        self.lstm = nn.LSTM(
            input_size=bert_hidden,
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if lstm_layers > 1 else 0.0,
        )

        # Project Bi-LSTM output (2 * lstm_hidden) back to BERT's hidden size
        self.projection = nn.Linear(lstm_hidden * 2, bert_hidden)
        self.layer_norm = nn.LayerNorm(bert_hidden)
        self.dropout = nn.Dropout(dropout)

        # Dummy pooler to match BertModelWarper interface
        self.pooler = bert_model.pooler

        self._init_lstm_weights()

    def _init_lstm_weights(self):
        for name, param in self.lstm.named_parameters():
            if "weight_ih" in name:
                nn.init.xavier_uniform_(param)
            elif "weight_hh" in name:
                nn.init.orthogonal_(param)
            elif "bias" in name:
                nn.init.zeros_(param)
                # Set forget gate bias to 1 for better gradient flow
                hidden = self.lstm.hidden_size
                param.data[hidden:2*hidden].fill_(1.0)

    def forward(
        self,
        input_ids=None,
        attention_mask=None,
        token_type_ids=None,
        position_ids=None,
        head_mask=None,
        inputs_embeds=None,
        encoder_hidden_states=None,
        encoder_attention_mask=None,
        past_key_values=None,
        use_cache=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
        **kwargs,
    ):
        # Get embeddings from BERT's embedding layer
        if input_ids is not None:
            batch_size, seq_len = input_ids.shape
        else:
            batch_size, seq_len = inputs_embeds.shape[:2]

        if token_type_ids is None and input_ids is not None:
            token_type_ids = torch.zeros_like(input_ids)

        embedding_output = self.embeddings(
            input_ids=input_ids,
            position_ids=position_ids,
            token_type_ids=token_type_ids,
            inputs_embeds=inputs_embeds,
        )

        # Pack padded sequences for efficient LSTM processing
        if attention_mask is not None and attention_mask.dim() == 2:
            lengths = attention_mask.sum(dim=1).cpu().clamp(min=1)
            packed = nn.utils.rnn.pack_padded_sequence(
                embedding_output, lengths, batch_first=True, enforce_sorted=False
            )
            lstm_out, _ = self.lstm(packed)
            lstm_out, _ = nn.utils.rnn.pad_packed_sequence(
                lstm_out, batch_first=True, total_length=seq_len
            )
        else:
            lstm_out, _ = self.lstm(embedding_output)

        # Project back to 768 and normalize
        hidden_states = self.projection(lstm_out)
        hidden_states = self.layer_norm(hidden_states + embedding_output)  # residual
        hidden_states = self.dropout(hidden_states)

        # Pooler for CLS token
        pooled = self.pooler(hidden_states) if self.pooler is not None else None

        return {"last_hidden_state": hidden_states, "pooler_output": pooled}


def build_gdino_with_bilstm(config_path, weights_path, device):
    """
    Build GroundingDINO with Bi-LSTM text encoder instead of BERT.

    Steps:
        1. Build the standard model (which creates BERT internally)
        2. Swap self.bert with BiLSTMTextEncoder
        3. Load checkpoint, skipping incompatible BERT encoder keys
        4. The feat_map (768 → hidden_dim) still works because output is 768
    """
    print("  Building GroundingDINO architecture...")
    args = SLConfig.fromfile(str(config_path))
    args.device = device
    model = build_model(args)

    # ── Swap BERT encoder → Bi-LSTM ──────────────────────────────────
    print("  Replacing BERT transformer with Bi-LSTM encoder...")

    # Access the raw BERT model before it was wrapped
    # model.bert is a BertModelWarper, which holds .embeddings, .encoder, .pooler
    # We need the original BertModel to extract embeddings
    # Reconstruct a minimal BertModel-like object for embedding transfer
    original_bert = BertModel.from_pretrained("bert-base-uncased")

    bilstm_encoder = BiLSTMTextEncoder(
        bert_model=original_bert,
        lstm_hidden=512,
        lstm_layers=2,
        dropout=0.1,
    )
    model.bert = bilstm_encoder
    del original_bert

    # ── Load checkpoint (skip BERT encoder weights) ──────────────────
    print("  Loading GroundingDINO checkpoint (skipping BERT encoder keys)...")
    ckpt = torch.load(str(weights_path), map_location="cpu", weights_only=True)
    state_dict = clean_state_dict(ckpt.get("model", ckpt))

    # Separate keys: keep everything except bert.encoder.* (LSTM replaces those)
    # Keep bert.embeddings.* → transferred via BERT pretrained init above
    # Keep feat_map.* → still compatible (768 → hidden_dim)
    compatible_keys = {}
    skipped_keys = []
    for k, v in state_dict.items():
        # Skip BERT's transformer encoder layers — Bi-LSTM replaces them
        if k.startswith("bert.encoder."):
            skipped_keys.append(k)
            continue
        # Skip BERT embeddings — already initialized from pretrained BERT
        if k.startswith("bert.embeddings."):
            skipped_keys.append(k)
            continue
        # Skip pooler — already transferred
        if k.startswith("bert.pooler."):
            skipped_keys.append(k)
            continue
        compatible_keys[k] = v

    missing, unexpected = model.load_state_dict(compatible_keys, strict=False)
    bilstm_keys = [k for k in missing if k.startswith("bert.")]
    other_missing = [k for k in missing if not k.startswith("bert.")]

    print(f"  Loaded {len(compatible_keys)} checkpoint keys")
    print(f"  Skipped {len(skipped_keys)} BERT encoder keys (replaced by Bi-LSTM)")
    print(f"  Bi-LSTM new params: {len(bilstm_keys)} (randomly initialized)")
    if other_missing:
        print(f"  Other missing keys: {other_missing}")

    model.eval().to(device)

    # Count parameters
    total = sum(p.numel() for p in model.parameters())
    lstm_params = sum(p.numel() for p in model.bert.lstm.parameters())
    proj_params = sum(p.numel() for p in model.bert.projection.parameters())
    ln_params = sum(p.numel() for p in model.bert.layer_norm.parameters())
    print(f"\n  Model parameters:  {total:,} total")
    print(f"  Bi-LSTM params:    {lstm_params + proj_params + ln_params:,} "
          f"(LSTM={lstm_params:,}, proj={proj_params:,}, LN={ln_params:,})")

    return model


# ═══════════════════════════════════════════════════════════════════════════
#  ELEVATOR PROMPTS & HELPERS
# ═══════════════════════════════════════════════════════════════════════════
ELEVATOR_PROMPTS = [
    "elevator door . elevator wall . elevator panel . elevator ceiling . elevator floor",
    "elevator button panel . call button . floor indicator display . handrail . mirror",
    "emergency phone . safety sign . weight limit sign . ventilation grille . door frame",
    "light fixture . security camera . speaker . card reader . threshold plate . door track",
]

PALETTE = [
    (255,64,64),(64,220,64),(64,120,255),(255,210,50),(200,64,255),
    (50,220,220),(255,140,50),(140,255,80),(255,80,180),(100,180,255),
    (220,180,100),(180,100,220),(80,255,180),(255,160,160),(160,160,255),
    (200,255,100),(255,100,100),(100,255,100),(100,100,255),(255,255,100),
]

@dataclass
class Detection:
    box_xyxy: np.ndarray
    phrase: str
    score: float
    mask: Optional[np.ndarray] = None

    @property
    def label(self) -> str:
        return f"{self.phrase} {self.score:.2f}"

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


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 1 — GROUNDING DINO DETECTION (Bi-LSTM)
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("STEP 1/3: GroundingDINO with Bi-LSTM text encoder")
print("=" * 60)

gdino = build_gdino_with_bilstm(GDINO_CONFIG, GDINO_WEIGHTS, DEVICE)

image_rgb, image_tensor = load_image(IMAGE_PATH)
h, w = image_rgb.shape[:2]
print(f"\nImage: {IMAGE_PATH} ({w}x{h})")
print(f"Running {len(ELEVATOR_PROMPTS)} prompt groups...\n")

all_boxes, all_scores, all_phrases = [], [], []

BOX_THRESHOLD = 0.20   # slightly lower since Bi-LSTM isn't fine-tuned
TEXT_THRESHOLD = 0.15

torch.set_grad_enabled(False)
with torch.inference_mode():
    for i, prompt in enumerate(ELEVATOR_PROMPTS):
        caption = prompt.lower().strip().rstrip(".") + "."
        out = gdino(image_tensor[None].to(DEVICE), captions=[caption])

        logits = out["pred_logits"].cpu().sigmoid()[0]
        boxes  = out["pred_boxes"].cpu()[0]

        keep = logits.max(dim=1)[0] > BOX_THRESHOLD
        logits, boxes = logits[keep], boxes[keep]
        if len(boxes) == 0:
            print(f"  Prompt {i+1}: \"{prompt[:50]}...\" → 0 detections")
            continue

        scores = logits.max(dim=1)[0]
        tokenizer = gdino.tokenizer
        tokenized = tokenizer(caption)
        phrases = [
            get_phrases_from_posmap(l > TEXT_THRESHOLD, tokenized, tokenizer)
            .replace(".", "").strip()
            for l in logits
        ]

        xyxy = cxcywh_to_xyxy(boxes, w, h)
        all_boxes.append(xyxy)
        all_scores.append(scores)
        all_phrases.extend(phrases)
        print(f"  Prompt {i+1}: \"{prompt[:50]}...\" → {len(boxes)} detection(s)")

del gdino
torch.cuda.empty_cache()

if not all_boxes:
    print("\nNo components detected. Try a clearer elevator image or lower BOX_THRESHOLD.")
    raise SystemExit(0)

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

print(f"\n✓ Detected {len(detections)} component(s) after NMS:")
for i, d in enumerate(detections):
    print(f"  [{i:2d}] {d.label:35s} box={d.box_xyxy.astype(int).tolist()}")


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 2 — SAM2 SEGMENTATION
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 2/3: SAM2 — pixel-wise segmentation")
print("=" * 60)

sam2_model = build_sam2(SAM2_CONFIG, str(SAM2_WEIGHTS), device=DEVICE, apply_postprocessing=True)
predictor  = SAM2ImagePredictor(sam2_model)
print("SAM2 loaded.\n")

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
    pct = px * 100 / (h * w)
    print(f"  [{i:2d}] {d.phrase:30s} → {px:>8,} px ({pct:.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 3 — RENDER & DISPLAY
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 3/3: Rendering outputs")
print("=" * 60)

font = ImageFont.load_default()

# ── Bounding box image ────────────────────────────────────────────────
box_img = Image.fromarray(image_rgb).convert("RGBA")
draw = ImageDraw.Draw(box_img)
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

# ── Mask overlay image ────────────────────────────────────────────────
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

# ── Display ───────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(24, 8))
axes[0].imshow(image_rgb);     axes[0].set_title("Original", fontsize=14);                                        axes[0].axis("off")
axes[1].imshow(detected_img);  axes[1].set_title(f"GroundingDINO [Bi-LSTM] — {len(detections)} detections", fontsize=14);  axes[1].axis("off")
axes[2].imshow(segmented_img); axes[2].set_title(f"SAM2 — {len(detections)} masks", fontsize=14);                 axes[2].axis("off")
plt.suptitle("Elevator Pipeline: Bi-LSTM Text Encoder + SAM2", fontsize=16, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig("elevator_bilstm_results.jpg", dpi=150, bbox_inches="tight")
plt.show()

# ── Save all outputs ──────────────────────────────────────────────────
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
print("=" * 60)
print("DONE — Bi-LSTM GroundingDINO + SAM2 elevator pipeline complete")
print("=" * 60)
