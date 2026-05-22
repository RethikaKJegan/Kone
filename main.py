from __future__ import annotations

import argparse
import contextlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage as ndi
from torchvision.ops import nms


ROOT = Path(__file__).resolve().parent
GROUNDING_DINO_DIR = ROOT / "GroundingDINO"
SAM2_DIR = ROOT / "sam2_src"
LAMA_REPO_DIR = ROOT / "lama"
LAMA_MODEL = ROOT / "big-lama"
BERT_DIR = ROOT / "bert-base-uncased"
CACHE_DIR = ROOT / ".cache"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
(CACHE_DIR / "matplotlib").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(CACHE_DIR / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_DIR))
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

for package_dir in (GROUNDING_DINO_DIR, SAM2_DIR, LAMA_REPO_DIR):
    package_path = str(package_dir)
    if package_path not in sys.path:
        sys.path.insert(0, package_path)

import groundingdino.datasets.transforms as T
from groundingdino.models import build_model
from groundingdino.util.misc import clean_state_dict
from groundingdino.util.slconfig import SLConfig
from groundingdino.util.utils import get_phrases_from_posmap


CONFIG_PATH = GROUNDING_DINO_DIR / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
DINO_WEIGHTS = ROOT / "weights/groundingdino_swint_ogc.pth"
SAM2_WEIGHTS = ROOT / "weights/sam2.1_hiera_large.pt"
SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_l.yaml"
DEFAULT_IMAGE = ROOT / "input.jpeg"


@dataclass(frozen=True)
class Detection:
    box_xyxy: np.ndarray
    phrase: str
    score: float

    @property
    def label(self) -> str:
        phrase = self.phrase.strip() or "object"
        return f"{phrase} {self.score:.2f}"


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def select_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def lama_device_for(device: str) -> str:
    return "cuda" if device == "cuda" else "cpu"


def autocast_for(device: str):
    if device == "cuda":
        return torch.autocast(device_type="cuda", dtype=torch.bfloat16)
    return contextlib.nullcontext()


def ensure_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def ensure_lama_model(path: Path) -> None:
    ensure_file(path / "config.yaml", "LaMa config")
    ensure_file(path / "models/best.ckpt", "LaMa checkpoint")


def load_torch(path: Path):
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


def preprocess_caption(caption: str) -> str:
    result = caption.lower().strip()
    return result if result.endswith(".") else result + "."


def load_groundingdino_model(config_path: Path, weights_path: Path, device: str):
    args = SLConfig.fromfile(str(config_path))
    args.device = device
    if BERT_DIR.exists():
        args.text_encoder_type = str(BERT_DIR)

    model = build_model(args)
    checkpoint = load_torch(weights_path)
    state_dict = checkpoint["model"] if isinstance(checkpoint, dict) and "model" in checkpoint else checkpoint
    model.load_state_dict(clean_state_dict(state_dict), strict=False)
    model.eval()
    return model.to(device)


def load_rgb_image(image_path: Path) -> tuple[np.ndarray, torch.Tensor]:
    transform = T.Compose(
        [
            T.RandomResize([800], max_size=1333),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    image_pil = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    image_source = np.asarray(image_pil)
    image_transformed, _ = transform(image_pil, None)
    return image_source, image_transformed


def predict_groundingdino(
    model,
    image: torch.Tensor,
    caption: str,
    box_threshold: float,
    text_threshold: float,
    device: str,
) -> tuple[torch.Tensor, torch.Tensor, list[str]]:
    caption = preprocess_caption(caption)
    image = image.to(device)

    outputs = model(image[None], captions=[caption])
    prediction_logits = outputs["pred_logits"].cpu().sigmoid()[0]
    prediction_boxes = outputs["pred_boxes"].cpu()[0]

    keep = prediction_logits.max(dim=1)[0] > box_threshold
    logits = prediction_logits[keep]
    boxes = prediction_boxes[keep]

    tokenizer = model.tokenizer
    tokenized = tokenizer(caption)
    phrases = [
        get_phrases_from_posmap(logit > text_threshold, tokenized, tokenizer).replace(".", "")
        for logit in logits
    ]
    return boxes, logits.max(dim=1)[0], phrases


def to_xyxy(box: torch.Tensor, width: int, height: int) -> np.ndarray:
    cx, cy, bw, bh = box.detach().cpu().numpy() * np.array(
        [width, height, width, height],
        dtype=np.float32,
    )
    x1 = np.clip(cx - bw / 2, 0, width - 1)
    y1 = np.clip(cy - bh / 2, 0, height - 1)
    x2 = np.clip(cx + bw / 2, 0, width - 1)
    y2 = np.clip(cy + bh / 2, 0, height - 1)
    return np.array([x1, y1, x2, y2], dtype=np.float32)


def expand_box(
    box_xyxy: np.ndarray,
    width: int,
    height: int,
    padding: int,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box_xyxy
    return (
        max(0, int(np.floor(x1)) - padding),
        max(0, int(np.floor(y1)) - padding),
        min(width, int(np.ceil(x2)) + padding),
        min(height, int(np.ceil(y2)) + padding),
    )


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def choose_detections(
    boxes: torch.Tensor,
    logits: torch.Tensor,
    phrases: list[str],
    limit: int,
    width: int,
    height: int,
    fallback_phrase: str,
    nms_threshold: float,
    min_area_ratio: float,
) -> list[Detection]:

    if len(boxes) == 0:
        return []

    # ========================================================
    # CONVERT BOXES
    # ========================================================

    xyxy = torch.tensor(
        np.stack([
            to_xyxy(box, width, height)
            for box in boxes
        ]),
        dtype=torch.float32,
    )

    scores = logits.cpu()

    detections: list[Detection] = []

    # ========================================================
    # RAW DETECTION FILTERING
    # ========================================================

    for idx in range(len(xyxy)):

        box = xyxy[idx].numpy()

        score = float(scores[idx].item())

        phrase = phrases[idx].strip().lower()

        x1, y1, x2, y2 = box

        w = x2 - x1
        h = y2 - y1

        area = w * h

        aspect = h / max(w, 1)

        cx = (x1 + x2) / 2

        # ====================================================
        # GLOBAL AREA FILTER
        # ====================================================

        if area < width * height * min_area_ratio:
            continue

        # ====================================================
        # DOOR FILTERS
        # ====================================================

        if "door" in phrase:
            # doors should not start too high
            if y1 < height * 0.10:
                continue

            # doors are tall

            if aspect < 1.4:
                continue

            # avoid tiny detections

            if w < width * 0.08:
                continue

            # doors usually centered

            if abs(cx - width / 2) > width * 0.35:
                continue

        # ====================================================
        # FLOOR FILTERS
        # ====================================================

        if "floor" in phrase:

            # floor must stay low

            if y1 < height * 0.60:
                continue

            # floor should not span full image

            if w > width * 0.60:
                continue

        # ====================================================
        # PANEL FILTERS
        # ====================================================

        if "panel" in phrase:

            # panels are vertical

            if w > h:
                continue

            # avoid giant detections

            if area > width * height * 0.10:
                continue

        # ====================================================
        # HANDRAIL FILTERS
        # ====================================================

        if "handrail" in phrase:

            # handrails are horizontal

            if w < h:
                continue

            # handrails stay inside cabin

            if y1 < height * 0.20:
                continue

        # ====================================================
        # INDICATOR FILTERS
        # ====================================================

        if "indicator" in phrase:

            # indicators stay near top

            if y2 > height * 0.45:
                continue

            # indicators are small

            if area > width * height * 0.05:
                continue

        # ====================================================
        # LIGHT FILTERS
        # ====================================================

        if "light" in phrase:
            
            if y2 > height * 0.35:
                continue
            
            if w < h:
                continue
            
            if area < width * height * 0.01:
                continue
            if abs(cx - width / 2) > width * 0.30:
                continue

            # lights stay near top

            if y2 > height * 0.35:
                continue

        detections.append(
            Detection(
                box_xyxy=box.astype(np.float32),
                phrase=phrase,
                score=score,
            )
        )

    # ========================================================
    # CLASS-AWARE NMS
    # ========================================================

    grouped: dict[str, list[Detection]] = {}

    for det in detections:
        grouped.setdefault(det.phrase, []).append(det)

    final: list[Detection] = []

    for label, dets in grouped.items():

        cls_boxes = torch.tensor(
            [d.box_xyxy for d in dets],
            dtype=torch.float32,
        )

        cls_scores = torch.tensor(
            [d.score for d in dets],
            dtype=torch.float32,
        )

        keep = nms(
            cls_boxes,
            cls_scores,
            nms_threshold,
        )

        for k in keep:

            final.append(
                dets[int(k)]
            )

    # ========================================================
    # SORT
    # ========================================================

    final.sort(
        key=lambda d: d.score,
        reverse=True,
    )

    # ========================================================
    # CONTAINMENT SUPPRESSION
    # ========================================================

    cleaned: list[Detection] = []

    for det in final:

        keep_detection = True

        x1, y1, x2, y2 = det.box_xyxy

        area_det = (
            (x2 - x1) *
            (y2 - y1)
        )

        for existing in cleaned:

            # only compare same semantic class

            if det.phrase != existing.phrase:
                continue

            ex1, ey1, ex2, ey2 = existing.box_xyxy

            # ------------------------------------------------
            # INTERSECTION
            # ------------------------------------------------

            ix1 = max(x1, ex1)
            iy1 = max(y1, ey1)

            ix2 = min(x2, ex2)
            iy2 = min(y2, ey2)

            iw = max(0, ix2 - ix1)
            ih = max(0, iy2 - iy1)

            inter = iw * ih

            area_existing = (
                (ex2 - ex1) *
                (ey2 - ey1)
            )

            containment = inter / max(area_det, 1)

            # ------------------------------------------------
            # SUPPRESS NESTED DUPLICATES
            # ------------------------------------------------

            if containment > 0.85:

                # suppress smaller nested box

                if area_det < area_existing:

                    keep_detection = False
                    break

        if keep_detection:
            cleaned.append(det)

    return cleaned[:limit]

    


def load_sam2_predictor(config: str, weights: Path, device: str):
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    model = build_sam2(config, str(weights), device=device, apply_postprocessing=True)
    return SAM2ImagePredictor(model)


def score_sam_mask(mask: np.ndarray, sam_score: float, box_xyxy: np.ndarray) -> float:
    x1, y1, x2, y2 = box_xyxy.astype(int)
    box_area = max(1, (x2 - x1) * (y2 - y1))
    mask_area = max(1, int(mask.sum()))
    inside = int(mask[y1:y2, x1:x2].sum())
    inside_ratio = inside / mask_area
    box_coverage = inside / box_area
    return float(sam_score) + 0.25 * inside_ratio + 0.10 * box_coverage


def make_mask_for_detection(
    predictor,
    detection: Detection,
    multimask: bool,
    use_center_point: bool,
) -> np.ndarray:
    box = detection.box_xyxy.astype(np.float32)
    point_coords = None
    point_labels = None
    if use_center_point:
        x1, y1, x2, y2 = box
        point_coords = np.array([[(x1 + x2) / 2, (y1 + y2) / 2]], dtype=np.float32)
        point_labels = np.array([1], dtype=np.int32)

    masks, scores, _ = predictor.predict(
        point_coords=point_coords,
        point_labels=point_labels,
        box=box,
        multimask_output=multimask,
    )
    masks_bool = masks.astype(bool)
    if len(masks_bool) == 0:
        raise RuntimeError(f"SAM2 returned no masks for {detection.label}")

    ranked = [
        score_sam_mask(mask, float(score), box)
        for mask, score in zip(masks_bool, scores)
    ]
    return masks_bool[int(np.argmax(ranked))]


def disk(radius: int) -> np.ndarray:
    yy, xx = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    return (xx * xx + yy * yy) <= radius * radius


def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    if min_area <= 0:
        return mask
    labeled, count = ndi.label(mask)
    if count == 0:
        return mask
    sizes = np.bincount(labeled.ravel())
    keep = sizes >= min_area
    keep[0] = False
    return keep[labeled]


def postprocess_mask(
    mask: np.ndarray,
    close_radius: int,
    dilate_radius: int,
    min_component_area: int,
    fill_holes: bool,
) -> np.ndarray:
    result = mask.astype(bool)
    result = remove_small_components(result, min_component_area)
    if fill_holes:
        result = ndi.binary_fill_holes(result)
    if close_radius > 0:
        result = ndi.binary_closing(result, structure=disk(close_radius))
    if dilate_radius > 0:
        result = ndi.binary_dilation(result, structure=disk(dilate_radius))
    return result


def make_mask(
    predictor,
    image_rgb: np.ndarray,
    detections: list[Detection],
    multimask: bool,
    use_center_point: bool,
    close_radius: int,
    dilate_radius: int,
    min_component_area: int,
    fill_holes: bool,
) -> np.ndarray:
    predictor.set_image(image_rgb)
    combined = np.zeros(image_rgb.shape[:2], dtype=bool)
    for detection in detections:
        combined |= make_mask_for_detection(
            predictor,
            detection,
            multimask=multimask,
            use_center_point=use_center_point,
        )
    refined = postprocess_mask(
        combined,
        close_radius=close_radius,
        dilate_radius=dilate_radius,
        min_component_area=min_component_area,
        fill_holes=fill_holes,
    )
    return refined.astype(np.uint8) * 255


def draw_detections(
    image_rgb: np.ndarray,
    detections: list[Detection],
    mask: np.ndarray,
) -> np.ndarray:
    image = Image.fromarray(image_rgb).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mask_image = Image.fromarray((mask > 0).astype(np.uint8) * 120, mode="L")
    overlay.paste((255, 64, 64, 120), mask=mask_image)
    image = Image.alpha_composite(image, overlay)

    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for detection in detections:
        x1, y1, x2, y2 = detection.box_xyxy.astype(int).tolist()
        draw.rectangle((x1, y1, x2, y2), outline=(44, 220, 112, 255), width=4)
        label = detection.label
        left, top, right, bottom = draw.textbbox((x1, y1), label, font=font)
        text_height = bottom - top
        text_width = right - left
        label_y = max(0, y1 - text_height - 8)
        draw.rectangle(
            (x1, label_y, x1 + text_width + 8, label_y + text_height + 6),
            fill=(15, 23, 42, 230),
        )
        draw.text((x1 + 4, label_y + 3), label, fill=(255, 255, 255, 255), font=font)
    return np.asarray(image.convert("RGB"))


def blend_crop(
    base_rgb: np.ndarray,
    generated_rgb: np.ndarray,
    mask: np.ndarray,
    feather: int,
) -> np.ndarray:
    alpha = (mask > 0).astype(np.float32)
    if feather > 0:
        alpha = ndi.gaussian_filter(alpha, sigma=max(0.1, feather / 3))
        alpha = np.clip(alpha, 0, 1)
    alpha = alpha[..., None]
    blended = generated_rgb.astype(np.float32) * alpha + base_rgb.astype(np.float32) * (1 - alpha)
    return np.clip(blended, 0, 255).astype(np.uint8)


def inpaint_image(
    image_rgb: np.ndarray,
    mask: np.ndarray,
    lama_model: Path,
    device: str,
    args: argparse.Namespace,
) -> np.ndarray:
    bbox = mask_bbox(mask)
    if bbox is None:
        return image_rgb.copy()

    from lama_inpaint import LamaInpainter

    height, width = image_rgb.shape[:2]
    if args.inpaint_crop_padding >= 0:
        crop_box = np.array(bbox, dtype=np.float32)
        x1, y1, x2, y2 = expand_box(crop_box, width, height, args.inpaint_crop_padding)
    else:
        x1, y1, x2, y2 = 0, 0, width, height

    crop_rgb = image_rgb[y1:y2, x1:x2]
    crop_mask = mask[y1:y2, x1:x2]
    inpainter = LamaInpainter(lama_model, device=lama_device_for(device))
    generated_crop = inpainter.inpaint(crop_rgb, crop_mask, max_side=args.lama_max_side)

    result = image_rgb.copy()
    result[y1:y2, x1:x2] = blend_crop(
        crop_rgb,
        generated_crop,
        crop_mask,
        args.blend_feather,
    )
    return result


def save_image(path: Path, image: np.ndarray) -> None:
    output = Image.fromarray(image)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        output.save(path, quality=95, optimize=True)
    else:
        output.save(path)


def clear_device_cache(device: str) -> None:
    if device == "cuda":
        torch.cuda.empty_cache()
    elif device == "mps" and hasattr(torch, "mps"):
        torch.mps.empty_cache()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove prompted objects from an image with GroundingDINO, SAM2, and LaMa.")
    parser.add_argument("prompt", nargs="?", help="Object to remove, for example: chair")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help="Input image path")
    parser.add_argument("--output-dir", default=str(ROOT), help="Directory for output images")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    parser.add_argument("--max-detections", type=int, default=5)
    parser.add_argument("--nms-threshold", type=float, default=0.65)
    parser.add_argument("--min-detection-area", type=float, default=0.0005)
    parser.add_argument("--sam2-config", default=SAM2_CONFIG)
    parser.add_argument("--sam2-weights", default=str(SAM2_WEIGHTS))
    parser.add_argument("--sam2-multimask", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sam2-center-point", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--mask-close", type=int, default=3)
    parser.add_argument("--mask-dilate", type=int, default=16)
    parser.add_argument("--mask-min-component-area", type=int, default=64)
    parser.add_argument("--fill-mask-holes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--inpaint-crop-padding", type=int, default=384)
    parser.add_argument("--blend-feather", type=int, default=24)
    parser.add_argument("--lama-model", default=str(LAMA_MODEL))
    parser.add_argument("--lama-max-side", type=int, default=1024, help="Resize LaMa crop only if its largest side exceeds this value; use 0 to disable")
    return parser.parse_args()


def get_prompt(prompt: str | None) -> str:
    if prompt:
        return prompt.strip()
    if sys.stdin.isatty():
        return input("Enter object to remove: ").strip()
    raise ValueError("Pass the object to remove, for example: python main.py chair")


def main() -> int:
    args = parse_args()
    prompt = get_prompt(args.prompt)
    image_path = resolve_path(args.image)
    output_dir = resolve_path(args.output_dir)
    lama_model = resolve_path(args.lama_model)
    sam2_weights = resolve_path(args.sam2_weights)
    device = select_device(args.device)
    lama_device = lama_device_for(device)

    ensure_file(CONFIG_PATH, "GroundingDINO config")
    ensure_file(DINO_WEIGHTS, "GroundingDINO weights")
    ensure_file(BERT_DIR / "config.json", "BERT local config")
    ensure_file(sam2_weights, "SAM2 weights")
    ensure_lama_model(lama_model)
    ensure_file(image_path, "Input image")
    output_dir.mkdir(parents=True, exist_ok=True)

    torch.set_grad_enabled(False)
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")

    print(f"Prompt: {prompt}")
    print(f"Device: {device}")
    print(f"LaMa device: {lama_device}")
    print("Pipeline: GroundingDINO -> SAM2 -> LaMa")

    with torch.inference_mode():
        image_source, image = load_rgb_image(image_path)
        height, width, _ = image_source.shape

        print("Loading GroundingDINO...")
        dino = load_groundingdino_model(CONFIG_PATH, DINO_WEIGHTS, device=device)
        boxes, logits, phrases = predict_groundingdino(
            model=dino,
            image=image,
            caption=prompt,
            box_threshold=args.box_threshold,
            text_threshold=args.text_threshold,
            device=device,
        )
        del dino
        clear_device_cache(device)

        detections = choose_detections(
            boxes,
            logits,
            phrases,
            args.max_detections,
            width,
            height,
            prompt,
            nms_threshold=args.nms_threshold,
            min_area_ratio=args.min_detection_area,
        )
        if not detections:
            print("No object detected. Try lowering --box-threshold or changing the prompt.")
            return 1
        print("Detected:", ", ".join(detection.label for detection in detections))

        print("Loading SAM2...")
        predictor = load_sam2_predictor(args.sam2_config, sam2_weights, device=device)
        with autocast_for(device):
            mask = make_mask(
                predictor,
                image_source,
                detections,
                multimask=args.sam2_multimask,
                use_center_point=args.sam2_center_point,
                close_radius=args.mask_close,
                dilate_radius=args.mask_dilate,
                min_component_area=args.mask_min_component_area,
                fill_holes=args.fill_mask_holes,
            )
        del predictor
        clear_device_cache(device)

        print("Inpainting with LaMa...")
        detected_rgb = draw_detections(image_source, detections, mask)
        final_rgb = inpaint_image(image_source, mask, lama_model, device, args)

    outputs = {
        "output_original.jpg": image_source,
        "output_detected.jpg": detected_rgb,
        "output_mask.png": mask,
        "output_final.jpg": final_rgb,
        "output_final_lama.jpg": final_rgb,
    }
    for filename, image_data in outputs.items():
        path = output_dir / filename
        save_image(path, image_data)
        print(f"Saved: {path}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
