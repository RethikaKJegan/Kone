"""
SAM 2: pixel-wise segmentation for any real-world object.
Accepts bounding boxes or point prompts and returns binary masks.

Usage:
    # Segment with a bounding box [x1,y1,x2,y2]:
    python sam2_segment.py --image input.jpeg --box 100,50,400,300

    # Segment with a center point:
    python sam2_segment.py --image input.jpeg --point 250,175

    # Multiple boxes:
    python sam2_segment.py --image input.jpeg --box 100,50,400,300 --box 500,100,700,400

    # Combined with GroundingDINO (programmatic):
    from grounding_dino_detect import detect
    from sam2_segment import segment_boxes
    dets = detect("photo.jpg", "dog", device="cpu")
    masks = segment_boxes("photo.jpg", [d["box_xyxy"] for d in dets], device="cpu")
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent
SAM2_DIR = ROOT / "sam2_src"
CACHE_DIR = ROOT / ".cache"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

if str(SAM2_DIR) not in sys.path:
    sys.path.insert(0, str(SAM2_DIR))

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_l.yaml"
SAM2_WEIGHTS = ROOT / "weights/sam2.1_hiera_large.pt"


# ---------------------------------------------------------------------------
# Model loader (cached singleton for production reuse)
# ---------------------------------------------------------------------------
_PREDICTOR_CACHE: dict[str, SAM2ImagePredictor] = {}


def load_predictor(device: str = "cpu") -> SAM2ImagePredictor:
    if device not in _PREDICTOR_CACHE:
        model = build_sam2(SAM2_CONFIG, str(SAM2_WEIGHTS), device=device, apply_postprocessing=True)
        _PREDICTOR_CACHE[device] = SAM2ImagePredictor(model)
    return _PREDICTOR_CACHE[device]


def load_image(path: str | Path) -> np.ndarray:
    return np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))


# ---------------------------------------------------------------------------
# Core segmentation API
# ---------------------------------------------------------------------------
def segment_boxes(
    image: str | Path | np.ndarray,
    boxes: list[np.ndarray | list],
    device: str = "cpu",
    multimask: bool = True,
    use_center_point: bool = True,
    dilate: int = 0,
    fill_holes: bool = True,
) -> list[np.ndarray]:
    """
    Segment objects given bounding boxes.

    Args:
        image: path or HWC uint8 RGB array.
        boxes: list of [x1, y1, x2, y2] arrays in pixel coords.
        multimask: use SAM's multi-mask mode (better for ambiguous prompts).
        use_center_point: also pass box center as a foreground point prompt.
        dilate: morphological dilation radius on the output mask (pixels).
        fill_holes: fill interior holes in each mask.

    Returns:
        List of boolean masks (H, W), one per box.
    """
    predictor = load_predictor(device)
    img = load_image(image) if isinstance(image, (str, Path)) else image

    with torch.inference_mode():
        predictor.set_image(img)
        masks = []
        for box in boxes:
            box = np.asarray(box, dtype=np.float32)
            point_coords, point_labels = None, None
            if use_center_point:
                cx = (box[0] + box[2]) / 2
                cy = (box[1] + box[3]) / 2
                point_coords = np.array([[cx, cy]], dtype=np.float32)
                point_labels = np.array([1], dtype=np.int32)

            raw_masks, scores, _ = predictor.predict(
                point_coords=point_coords,
                point_labels=point_labels,
                box=box,
                multimask_output=multimask,
            )
            best = raw_masks[np.argmax(scores)].astype(bool)
            best = _postprocess(best, dilate, fill_holes)
            masks.append(best)

    return masks


def segment_points(
    image: str | Path | np.ndarray,
    points: list[np.ndarray | list],
    labels: list[int] | None = None,
    device: str = "cpu",
    multimask: bool = True,
    dilate: int = 0,
    fill_holes: bool = True,
) -> list[np.ndarray]:
    """
    Segment objects given point prompts.

    Args:
        image: path or HWC uint8 RGB array.
        points: list of [x, y] foreground points.
        labels: 1 = foreground, 0 = background (default: all foreground).
        multimask: use SAM's multi-mask mode.
        dilate: dilation radius.
        fill_holes: fill interior holes.

    Returns:
        List of boolean masks, one per point.
    """
    predictor = load_predictor(device)
    img = load_image(image) if isinstance(image, (str, Path)) else image

    with torch.inference_mode():
        predictor.set_image(img)
        masks = []
        for i, pt in enumerate(points):
            pt = np.asarray(pt, dtype=np.float32).reshape(1, 2)
            lbl = np.array([labels[i] if labels else 1], dtype=np.int32)
            raw_masks, scores, _ = predictor.predict(
                point_coords=pt,
                point_labels=lbl,
                multimask_output=multimask,
            )
            best = raw_masks[np.argmax(scores)].astype(bool)
            best = _postprocess(best, dilate, fill_holes)
            masks.append(best)

    return masks


def combine_masks(masks: list[np.ndarray]) -> np.ndarray:
    """Merge multiple boolean masks into a single uint8 mask (0 or 255)."""
    if not masks:
        raise ValueError("No masks to combine")
    combined = masks[0].copy()
    for m in masks[1:]:
        combined |= m
    return combined.astype(np.uint8) * 255


# ---------------------------------------------------------------------------
# Postprocessing
# ---------------------------------------------------------------------------
def _postprocess(mask: np.ndarray, dilate: int, fill_holes: bool) -> np.ndarray:
    if fill_holes:
        mask = ndi.binary_fill_holes(mask)
    if dilate > 0:
        struct = _disk(dilate)
        mask = ndi.binary_dilation(mask, structure=struct)
    return mask.astype(bool)


def _disk(r: int) -> np.ndarray:
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------
PALETTE = [
    (255, 64, 64, 130), (64, 255, 64, 130), (64, 64, 255, 130),
    (255, 255, 64, 130), (255, 64, 255, 130), (64, 255, 255, 130),
]


def draw_masks(image_rgb: np.ndarray, masks: list[np.ndarray]) -> np.ndarray:
    img = Image.fromarray(image_rgb).convert("RGBA")
    for i, mask in enumerate(masks):
        color = PALETTE[i % len(PALETTE)]
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        alpha_map = Image.fromarray((mask > 0).astype(np.uint8) * color[3], mode="L")
        overlay.paste(color[:3], mask=alpha_map)
        img = Image.alpha_composite(img, overlay)
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


def _parse_box(s: str) -> np.ndarray:
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"Box must be x1,y1,x2,y2 — got '{s}'")
    return np.array(parts, dtype=np.float32)


def _parse_point(s: str) -> np.ndarray:
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Point must be x,y — got '{s}'")
    return np.array(parts, dtype=np.float32)


def main():
    parser = argparse.ArgumentParser(description="SAM 2 pixel-wise segmentation")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--box", type=_parse_box, action="append", default=[], help="Bounding box x1,y1,x2,y2")
    parser.add_argument("--point", type=_parse_point, action="append", default=[], help="Point prompt x,y")
    parser.add_argument("--output-mask", default="sam2_mask.png", help="Output mask path")
    parser.add_argument("--output-vis", default="sam2_output.jpg", help="Output visualization path")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--dilate", type=int, default=0, help="Mask dilation radius in pixels")
    parser.add_argument("--no-fill-holes", action="store_true")
    args = parser.parse_args()

    if not args.box and not args.point:
        parser.error("Provide at least one --box or --point prompt.")

    device = _select_device(args.device)
    print(f"Device: {device}")

    torch.set_grad_enabled(False)
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")

    fill = not args.no_fill_holes
    all_masks: list[np.ndarray] = []

    if args.box:
        print(f"Segmenting {len(args.box)} box prompt(s)...")
        all_masks.extend(segment_boxes(args.image, args.box, device=device, dilate=args.dilate, fill_holes=fill))

    if args.point:
        print(f"Segmenting {len(args.point)} point prompt(s)...")
        all_masks.extend(segment_points(args.image, args.point, device=device, dilate=args.dilate, fill_holes=fill))

    for i, m in enumerate(all_masks):
        pixels = int(m.sum())
        print(f"  Mask {i}: {pixels:,} pixels ({pixels * 100 / m.size:.1f}% of image)")

    merged = combine_masks(all_masks)
    Image.fromarray(merged).save(args.output_mask)
    print(f"Saved mask: {args.output_mask}")

    image_rgb = load_image(args.image)
    vis = draw_masks(image_rgb, all_masks)
    Image.fromarray(vis).save(args.output_vis, quality=95)
    print(f"Saved visualization: {args.output_vis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
