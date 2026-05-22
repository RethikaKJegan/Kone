"""
Elevator Component Detection & Segmentation Pipeline
=====================================================
GroundingDINO (open-vocab detection) + SAM2 (pixel-wise segmentation)

Built-in prompts target every visible elevator component.
User only supplies an input image — no text prompt needed.

Usage (Colab):
    pipeline = ElevatorPipeline(device="cuda")
    results  = pipeline.run("elevator_photo.jpg")
    results.save("./outputs")

Usage (CLI):
    python elevator_pipeline.py --image elevator_photo.jpg --output-dir ./outputs
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage as ndi
from torchvision.ops import nms

# ---------------------------------------------------------------------------
# Paths — adjust these for your environment (Colab defaults below)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent if "__file__" in dir() else Path(".")

GDINO_DIR     = ROOT / "GroundingDINO"
SAM2_DIR      = ROOT / "sam2"
BERT_DIR      = ROOT / "bert-base-uncased"
CACHE_DIR     = ROOT / ".cache"
GDINO_CONFIG  = GDINO_DIR / "groundingdino" / "config" / "GroundingDINO_SwinT_OGC.py"
GDINO_WEIGHTS = ROOT / "weights" / "groundingdino_swint_ogc.pth"
SAM2_CONFIG   = "configs/sam2.1/sam2.1_hiera_l.yaml"
SAM2_WEIGHTS  = ROOT / "weights" / "sam2.1_hiera_large.pt"

# Offline / cache env
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

for _p in (GDINO_DIR, SAM2_DIR):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# Built-in elevator prompts — the core domain knowledge
# ---------------------------------------------------------------------------
ELEVATOR_PROMPTS: list[str] = [
    # Structural
    "elevator door . elevator wall . elevator panel . elevator ceiling . elevator floor",
    # Mechanical / functional
    "elevator button panel . elevator call button . floor indicator . handrail . mirror",
    # Safety & signage
    "emergency phone . safety sign . weight limit sign . floor number display . ventilation grille",
    # Door details
    "door frame . door track . door gap . threshold plate",
    # Interior fittings
    "light fixture . camera . speaker . card reader . key switch",
]

# Flattened for logging / legend
ALL_COMPONENT_NAMES = [
    comp.strip()
    for prompt in ELEVATOR_PROMPTS
    for comp in prompt.split(" . ")
]

# ---------------------------------------------------------------------------
# Color palette — one distinct color per component
# ---------------------------------------------------------------------------
_PALETTE = [
    (255,  64,  64), ( 64, 220,  64), ( 64, 120, 255), (255, 210,  50),
    (200,  64, 255), ( 50, 220, 220), (255, 140,  50), (140, 255,  80),
    (255,  80, 180), (100, 180, 255), (220, 180, 100), (180, 100, 220),
    ( 80, 255, 180), (255, 160, 160), (160, 160, 255), (200, 255, 100),
    (255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100),
    (255, 100, 255), (100, 255, 255), (200, 150,  50), ( 50, 200, 150),
]


def _color(i: int) -> tuple[int, int, int]:
    return _PALETTE[i % len(_PALETTE)]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    box_xyxy: np.ndarray          # [x1, y1, x2, y2] float32 pixels
    phrase: str
    score: float
    mask: Optional[np.ndarray] = None  # bool H×W, filled after SAM2

    @property
    def label(self) -> str:
        return f"{self.phrase} {self.score:.2f}"


@dataclass
class PipelineResult:
    image_rgb: np.ndarray
    detections: list[Detection]
    detected_image: Optional[np.ndarray] = None
    segmented_image: Optional[np.ndarray] = None

    def summary(self) -> str:
        lines = [f"Found {len(self.detections)} component(s):"]
        for i, d in enumerate(self.detections):
            box = d.box_xyxy.astype(int).tolist()
            px = f", mask={int(d.mask.sum()):,}px" if d.mask is not None else ""
            lines.append(f"  [{i}] {d.label:30s} box={box}{px}")
        return "\n".join(lines)

    def save(self, output_dir: str | Path = "./outputs") -> list[Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        saved = []

        def _save(name: str, arr: np.ndarray) -> Path:
            p = out / name
            img = Image.fromarray(arr)
            if p.suffix in (".jpg", ".jpeg"):
                img.save(p, quality=95, optimize=True)
            else:
                img.save(p)
            saved.append(p)
            return p

        _save("original.jpg", self.image_rgb)
        if self.detected_image is not None:
            _save("detected_boxes.jpg", self.detected_image)
        if self.segmented_image is not None:
            _save("segmented_masks.jpg", self.segmented_image)

        for i, det in enumerate(self.detections):
            if det.mask is not None:
                mask_uint8 = det.mask.astype(np.uint8) * 255
                tag = det.phrase.replace(" ", "_")
                _save(f"mask_{i:02d}_{tag}.png", mask_uint8)

        combined = self._combined_mask()
        if combined is not None:
            _save("combined_mask.png", combined)

        return saved

    def _combined_mask(self) -> Optional[np.ndarray]:
        masks = [d.mask for d in self.detections if d.mask is not None]
        if not masks:
            return None
        out = np.zeros_like(masks[0], dtype=bool)
        for m in masks:
            out |= m
        return out.astype(np.uint8) * 255


# ---------------------------------------------------------------------------
# Device helpers
# ---------------------------------------------------------------------------
def resolve_device(preference: str = "auto") -> str:
    if preference not in ("auto", ""):
        return preference
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def clear_cache(device: str) -> None:
    if device == "cuda":
        torch.cuda.empty_cache()
    elif device == "mps" and hasattr(torch, "mps"):
        torch.mps.empty_cache()


# ---------------------------------------------------------------------------
# GroundingDINO loader
# ---------------------------------------------------------------------------
def _load_gdino(device: str):
    import groundingdino.datasets.transforms as T
    from groundingdino.models import build_model
    from groundingdino.util.misc import clean_state_dict
    from groundingdino.util.slconfig import SLConfig

    args = SLConfig.fromfile(str(GDINO_CONFIG))
    args.device = device
    if BERT_DIR.exists():
        args.text_encoder_type = str(BERT_DIR)

    model = build_model(args)
    ckpt = torch.load(str(GDINO_WEIGHTS), map_location="cpu", weights_only=True)
    model.load_state_dict(clean_state_dict(ckpt.get("model", ckpt)), strict=False)
    model.eval().to(device)
    return model


def _gdino_transform():
    import groundingdino.datasets.transforms as T
    return T.Compose([
        T.RandomResize([800], max_size=1333),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def _load_image(path: str | Path):
    transform = _gdino_transform()
    pil = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    tensor, _ = transform(pil, None)
    return np.asarray(pil), tensor


def _cxcywh_to_xyxy(boxes: torch.Tensor, w: int, h: int) -> torch.Tensor:
    s = torch.tensor([w, h, w, h], dtype=torch.float32)
    b = boxes * s
    x1 = (b[:, 0] - b[:, 2] / 2).clamp(0, w)
    y1 = (b[:, 1] - b[:, 3] / 2).clamp(0, h)
    x2 = (b[:, 0] + b[:, 2] / 2).clamp(0, w)
    y2 = (b[:, 1] + b[:, 3] / 2).clamp(0, h)
    return torch.stack([x1, y1, x2, y2], dim=1)


# ---------------------------------------------------------------------------
# SAM2 loader
# ---------------------------------------------------------------------------
def _load_sam2(device: str):
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    model = build_sam2(SAM2_CONFIG, str(SAM2_WEIGHTS), device=device, apply_postprocessing=True)
    return SAM2ImagePredictor(model)


def _disk(r: int) -> np.ndarray:
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------
def draw_boxes(image_rgb: np.ndarray, detections: list[Detection]) -> np.ndarray:
    img = Image.fromarray(image_rgb).convert("RGBA")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()

    for i, det in enumerate(detections):
        r, g, b = _color(i)
        x1, y1, x2, y2 = det.box_xyxy.astype(int).tolist()
        draw.rectangle((x1, y1, x2, y2), outline=(r, g, b, 255), width=3)

        label = det.label
        tb = draw.textbbox((x1, y1), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ly = max(0, y1 - th - 10)
        draw.rectangle((x1, ly, x1 + tw + 10, ly + th + 8), fill=(15, 23, 42, 220))
        draw.text((x1 + 5, ly + 4), label, fill=(r, g, b, 255), font=font)

    return np.asarray(img.convert("RGB"))


def draw_masks(
    image_rgb: np.ndarray,
    detections: list[Detection],
    mask_alpha: float = 0.45,
) -> np.ndarray:
    base = Image.fromarray(image_rgb).convert("RGBA")
    canvas = base.copy()

    for i, det in enumerate(detections):
        if det.mask is None:
            continue
        r, g, b = _color(i)
        alpha = int(255 * mask_alpha)
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        overlay.paste(
            (r, g, b, alpha),
            mask=Image.fromarray(det.mask.astype(np.uint8) * 255, mode="L"),
        )
        canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()

    for i, det in enumerate(detections):
        r, g, b = _color(i)
        x1, y1, x2, y2 = det.box_xyxy.astype(int).tolist()
        draw.rectangle((x1, y1, x2, y2), outline=(r, g, b, 255), width=2)

        label = det.label
        tb = draw.textbbox((x1, y1), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ly = max(0, y1 - th - 10)
        draw.rectangle((x1, ly, x1 + tw + 10, ly + th + 8), fill=(15, 23, 42, 220))
        draw.text((x1 + 5, ly + 4), label, fill=(r, g, b, 255), font=font)

    return np.asarray(canvas.convert("RGB"))


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class ElevatorPipeline:
    """
    Production-ready elevator component detector + segmenter.

    Architecture:
        1. GroundingDINO runs N prompt groups → merged detections with NMS
        2. SAM2 segments each detection → pixel-precise masks
        3. Results bundled into PipelineResult for saving / display

    Models are loaded once and reused across calls.
    """

    def __init__(
        self,
        device: str = "auto",
        box_threshold: float = 0.25,
        text_threshold: float = 0.20,
        nms_threshold: float = 0.50,
        max_detections: int = 50,
        mask_dilate: int = 4,
        fill_holes: bool = True,
        prompts: list[str] | None = None,
    ):
        self.device = resolve_device(device)
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.nms_threshold = nms_threshold
        self.max_detections = max_detections
        self.mask_dilate = mask_dilate
        self.fill_holes = fill_holes
        self.prompts = prompts or ELEVATOR_PROMPTS

        self._gdino = None
        self._sam2 = None

    def _ensure_gdino(self):
        if self._gdino is None:
            print(f"[pipeline] Loading GroundingDINO on {self.device}...")
            self._gdino = _load_gdino(self.device)
        return self._gdino

    def _ensure_sam2(self):
        if self._sam2 is None:
            print(f"[pipeline] Loading SAM2 on {self.device}...")
            self._sam2 = _load_sam2(self.device)
        return self._sam2

    def detect(self, image_path: str | Path) -> tuple[np.ndarray, list[Detection]]:
        from groundingdino.util.utils import get_phrases_from_posmap

        model = self._ensure_gdino()
        image_rgb, image_tensor = _load_image(image_path)
        h, w = image_rgb.shape[:2]

        all_boxes, all_scores, all_phrases = [], [], []

        with torch.inference_mode():
            for prompt in self.prompts:
                caption = prompt.lower().strip().rstrip(".") + "."
                out = model(image_tensor[None].to(self.device), captions=[caption])

                logits = out["pred_logits"].cpu().sigmoid()[0]
                boxes = out["pred_boxes"].cpu()[0]

                keep = logits.max(dim=1)[0] > self.box_threshold
                logits, boxes = logits[keep], boxes[keep]
                if len(boxes) == 0:
                    continue

                scores = logits.max(dim=1)[0]
                tokenizer = model.tokenizer
                tokenized = tokenizer(caption)
                phrases = [
                    get_phrases_from_posmap(
                        l > self.text_threshold, tokenized, tokenizer
                    ).replace(".", "").strip()
                    for l in logits
                ]

                xyxy = _cxcywh_to_xyxy(boxes, w, h)
                all_boxes.append(xyxy)
                all_scores.append(scores)
                all_phrases.extend(phrases)

        if not all_boxes:
            return image_rgb, []

        all_boxes = torch.cat(all_boxes, dim=0)
        all_scores = torch.cat(all_scores, dim=0)

        keep_idx = nms(all_boxes, all_scores, self.nms_threshold)
        keep_idx = keep_idx[: self.max_detections]

        detections = []
        for i in keep_idx.tolist():
            detections.append(Detection(
                box_xyxy=all_boxes[i].numpy().astype(np.float32),
                phrase=all_phrases[i] if all_phrases[i] else "component",
                score=float(all_scores[i]),
            ))
        detections.sort(key=lambda d: d.score, reverse=True)
        return image_rgb, detections

    def segment(self, image_rgb: np.ndarray, detections: list[Detection]) -> list[Detection]:
        if not detections:
            return detections

        predictor = self._ensure_sam2()
        with torch.inference_mode():
            predictor.set_image(image_rgb)
            for det in detections:
                box = det.box_xyxy.astype(np.float32)
                cx = (box[0] + box[2]) / 2
                cy = (box[1] + box[3]) / 2

                masks, scores, _ = predictor.predict(
                    point_coords=np.array([[cx, cy]], dtype=np.float32),
                    point_labels=np.array([1], dtype=np.int32),
                    box=box,
                    multimask_output=True,
                )
                best = masks[np.argmax(scores)].astype(bool)
                if self.fill_holes:
                    best = ndi.binary_fill_holes(best)
                if self.mask_dilate > 0:
                    best = ndi.binary_dilation(best, structure=_disk(self.mask_dilate))
                det.mask = best

        return detections

    def run(self, image_path: str | Path) -> PipelineResult:
        print(f"[pipeline] Device: {self.device}")
        print(f"[pipeline] Prompts: {len(self.prompts)} groups, {len(ALL_COMPONENT_NAMES)} component types")
        print(f"[pipeline] Image: {image_path}")

        torch.set_grad_enabled(False)
        if hasattr(torch, "set_float32_matmul_precision"):
            torch.set_float32_matmul_precision("high")

        print("\n[1/3] Detecting elevator components with GroundingDINO...")
        image_rgb, detections = self.detect(image_path)
        if not detections:
            print("      No components detected. Try lowering box_threshold.")
            return PipelineResult(image_rgb=image_rgb, detections=[])
        print(f"      Found {len(detections)} component(s)")

        clear_cache(self.device)

        print("[2/3] Segmenting with SAM2...")
        detections = self.segment(image_rgb, detections)
        for i, d in enumerate(detections):
            px = int(d.mask.sum()) if d.mask is not None else 0
            print(f"      [{i}] {d.label:30s}  mask={px:,}px")

        clear_cache(self.device)

        print("[3/3] Rendering outputs...")
        detected_img = draw_boxes(image_rgb, detections)
        segmented_img = draw_masks(image_rgb, detections)

        result = PipelineResult(
            image_rgb=image_rgb,
            detections=detections,
            detected_image=detected_img,
            segmented_image=segmented_img,
        )
        print("\n" + result.summary())
        return result

    def unload(self) -> None:
        self._gdino = None
        self._sam2 = None
        clear_cache(self.device)
        print("[pipeline] Models unloaded.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Elevator component detection & segmentation (GroundingDINO + SAM2)"
    )
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--output-dir", default="./outputs", help="Directory for output images")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    parser.add_argument("--nms-threshold", type=float, default=0.50)
    parser.add_argument("--max-detections", type=int, default=50)
    parser.add_argument("--mask-dilate", type=int, default=4)
    args = parser.parse_args()

    pipeline = ElevatorPipeline(
        device=args.device,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        nms_threshold=args.nms_threshold,
        max_detections=args.max_detections,
        mask_dilate=args.mask_dilate,
    )
    result = pipeline.run(args.image)
    if not result.detections:
        return 1

    saved = result.save(args.output_dir)
    print(f"\nSaved {len(saved)} file(s) to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
