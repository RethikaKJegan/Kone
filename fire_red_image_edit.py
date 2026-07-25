from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from diffusers import DiffusionPipeline
from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError


MODEL_ID = "FireRedTeam/FireRed-Image-Edit-1.1"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone FireRed-Image-Edit 1.1 BF16 inference script"
    )
    parser.add_argument(
        "--image",
        required=True,
        type=Path,
        help="Input image path",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        type=str,
        help="Edit instruction for FireRed",
    )
    parser.add_argument(
        "--component",
        default=None,
        type=Path,
        help="Optional component image path to place into the input image",
    )
    parser.add_argument(
        "--box",
        nargs=4,
        type=int,
        default=None,
        metavar=("X1", "Y1", "X2", "Y2"),
        help="Target box in the input image: x1 y1 x2 y2",
    )
    parser.add_argument(
        "--pad",
        default=80,
        type=int,
        help="Padding around component box for FireRed local blending",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output image path",
    )
    parser.add_argument(
        "--model",
        default=MODEL_ID,
        type=str,
        help="Hugging Face model id or local model path",
    )
    parser.add_argument(
        "--seed",
        default=43,
        type=int,
        help="Generation seed",
    )
    parser.add_argument(
        "--steps",
        default=40,
        type=int,
        help="Number of inference steps",
    )
    parser.add_argument(
        "--true-cfg-scale",
        default=4.0,
        type=float,
        help="FireRed/Qwen edit CFG scale",
    )
    return parser.parse_args()

def load_component_image(image_path: Path) -> Image.Image:
    if not image_path.exists():
        raise FileNotFoundError(f"Component image not found: {image_path}")

    try:
        return Image.open(image_path).convert("RGBA")
    except UnidentifiedImageError as exc:
        raise ValueError(f"Invalid component image file: {image_path}") from exc


def validate_box(box: tuple[int, int, int, int], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    width, height = image_size

    if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        raise ValueError(f"Invalid --box {box} for image size {image_size}")
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid --box {box}: x2/y2 must be greater than x1/y1")

    return x1, y1, x2, y2


def place_component(
    base_image: Image.Image,
    component_image: Image.Image,
    box: tuple[int, int, int, int],
) -> Image.Image:
    x1, y1, x2, y2 = validate_box(box, base_image.size)
    target_w = x2 - x1
    target_h = y2 - y1

    fitted = ImageOps.contain(
        component_image,
        (target_w, target_h),
        method=Image.Resampling.LANCZOS,
    )

    slot = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    offset_x = (target_w - fitted.width) // 2
    offset_y = (target_h - fitted.height) // 2
    slot.paste(fitted, (offset_x, offset_y), fitted)

    result = base_image.convert("RGBA")
    result.paste(slot, (x1, y1), slot)
    return result.convert("RGB")
def expand_box(
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
    pad: int,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    width, height = image_size

    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(width, x2 + pad),
        min(height, y2 + pad),
    )


def place_component_in_crop(
    crop_image: Image.Image,
    component_image: Image.Image,
    component_box_in_crop: tuple[int, int, int, int],
) -> Image.Image:
    return place_component(
        base_image=crop_image,
        component_image=component_image,
        box=component_box_in_crop,
    )
def load_input_image(image_path: Path) -> Image.Image:
    if not image_path.exists():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    try:
        return Image.open(image_path).convert("RGB")
    except UnidentifiedImageError as exc:
        raise ValueError(f"Invalid image file: {image_path}") from exc


def load_pipeline(model: str, device: torch.device) -> DiffusionPipeline:
    if device.type != "cuda":
        raise RuntimeError(
            "CUDA GPU not available. FireRed-Image-Edit 1.1 BF16 inference is intended to run on CUDA."
        )

    # Load FireRed through its native Diffusers image-edit pipeline in BF16.
    try:
        pipe = DiffusionPipeline.from_pretrained(
            model,
            torch_dtype=torch.bfloat16,
            device_map="cuda",
        )
    except TypeError:
        pipe = DiffusionPipeline.from_pretrained(
            model,
            torch_dtype=torch.bfloat16,
        )
        pipe.to(device)

    pipe.set_progress_bar_config(disable=False)
    return pipe


def run_edit(
    pipe: DiffusionPipeline,
    image: Image.Image,
    prompt: str,
    seed: int,
    steps: int,
    true_cfg_scale: float,
) -> Image.Image:
    generator = torch.Generator(device="cuda").manual_seed(seed)

    # FireRed/Qwen edit uses the source image and natural-language edit instruction directly.
    with torch.inference_mode():
        result = pipe(
            image=image,
            prompt=prompt,
            generator=generator,
            true_cfg_scale=true_cfg_scale,
            negative_prompt=" ",
            num_inference_steps=steps,
            num_images_per_prompt=1,
        )

    if not result.images:
        raise RuntimeError("Pipeline returned no images.")

    return result.images[0]


def main() -> int:
    args = parse_args()

    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        input_image = load_input_image(args.image)

        if not args.prompt and not args.component:
            raise ValueError(
                "Provide either --prompt for FireRed editing or --component with --box for direct component placement."
            )

        if args.component is not None:
            if args.box is None:
                raise ValueError("--box is required when --component is provided.")

            component_box = validate_box(tuple(args.box), input_image.size)
            edit_box = expand_box(component_box, input_image.size, args.pad)

            crop = input_image.crop(edit_box)

            component_box_in_crop = (
                component_box[0] - edit_box[0],
                component_box[1] - edit_box[1],
                component_box[2] - edit_box[0],
                component_box[3] - edit_box[1],
            )

            component_image = load_component_image(args.component)

            placed_crop = place_component_in_crop(
                crop_image=crop,
                component_image=component_image,
                component_box_in_crop=component_box_in_crop,
            )

            pipe = load_pipeline(args.model, device)

            blend_prompt = args.prompt or (
                "Make the inserted elevator call button panel look realistically installed in the wall. "
                "Preserve the exact panel design, button layout, black display, up arrow, number 14, and down button. "
                "Blend only lighting, shadows, reflections, edges, perspective, and wall contact. "
                "Do not create a new panel design. Do not change the elevator, wall, floor, sign, or surrounding scene."
            )

            edited_crop = run_edit(
                pipe=pipe,
                image=placed_crop,
                prompt=blend_prompt,
                seed=args.seed,
                steps=args.steps,
                true_cfg_scale=args.true_cfg_scale,
            )

            if edited_crop.size != crop.size:
                edited_crop = edited_crop.resize(crop.size, Image.Resampling.LANCZOS)

            output_image = input_image.copy()
            output_image.paste(edited_crop, (edit_box[0], edit_box[1]))
        else:
            pipe = load_pipeline(args.model, device)

            output_image = run_edit(
                pipe=pipe,
                image=input_image,
                prompt=args.prompt,
                seed=args.seed,
                steps=args.steps,
                true_cfg_scale=args.true_cfg_scale,
            )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        output_image.save(args.output)

        print(f"Saved edited image: {args.output.resolve()}")
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
