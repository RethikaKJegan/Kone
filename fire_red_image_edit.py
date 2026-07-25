`from __future__ import annotations

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
        help="Additional edit instruction for FireRed",
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
        default=140,
        type=int,
        help="Padding around component box for FireRed local blending",
    )
    parser.add_argument(
        "--shadow-offset-x",
        default=6,
        type=int,
        help="Horizontal contact-shadow offset in pixels",
    )
    parser.add_argument(
        "--shadow-offset-y",
        default=10,
        type=int,
        help="Vertical contact-shadow offset in pixels",
    )
    parser.add_argument(
        "--shadow-blur",
        default=14.0,
        type=float,
        help="Contact-shadow Gaussian blur radius",
    )
    parser.add_argument(
        "--shadow-opacity",
        default=95,
        type=int,
        help="Contact-shadow opacity from 0 to 255",
    )
    parser.add_argument(
        "--crop-feather",
        default=28.0,
        type=float,
        help="Feather radius for blending the edited crop into the source image",
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
        default=777,
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


def load_input_image(image_path: Path) -> Image.Image:
    if not image_path.exists():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    try:
        with Image.open(image_path) as image:
            return ImageOps.exif_transpose(image).convert("RGB")
    except UnidentifiedImageError as exc:
        raise ValueError(f"Invalid image file: {image_path}") from exc


def load_component_image(image_path: Path) -> Image.Image:
    if not image_path.exists():
        raise FileNotFoundError(f"Component image not found: {image_path}")

    try:
        with Image.open(image_path) as image:
            return ImageOps.exif_transpose(image).convert("RGBA")
    except UnidentifiedImageError as exc:
        raise ValueError(f"Invalid component image file: {image_path}") from exc


def validate_box(
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    width, height = image_size

    if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        raise ValueError(f"Invalid --box {box} for image size {image_size}")

    if x2 <= x1 or y2 <= y1:
        raise ValueError(
            f"Invalid --box {box}: x2/y2 must be greater than x1/y1"
        )

    return x1, y1, x2, y2


def expand_box(
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
    pad: int,
) -> tuple[int, int, int, int]:
    if pad < 0:
        raise ValueError("--pad must be greater than or equal to 0")

    x1, y1, x2, y2 = box
    width, height = image_size

    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(width, x2 + pad),
        min(height, y2 + pad),
    )


def offset_mask(
    mask: Image.Image,
    offset_x: int,
    offset_y: int,
) -> Image.Image:
    shifted = Image.new("L", mask.size, 0)

    source_left = max(0, -offset_x)
    source_top = max(0, -offset_y)
    source_right = min(mask.width, mask.width - offset_x)
    source_bottom = min(mask.height, mask.height - offset_y)

    if source_right <= source_left or source_bottom <= source_top:
        return shifted

    destination_left = max(0, offset_x)
    destination_top = max(0, offset_y)

    shifted.paste(
        mask.crop(
            (
                source_left,
                source_top,
                source_right,
                source_bottom,
            )
        ),
        (destination_left, destination_top),
    )
    return shifted


def place_component(
    base_image: Image.Image,
    component_image: Image.Image,
    box: tuple[int, int, int, int],
    shadow_offset_x: int,
    shadow_offset_y: int,
    shadow_blur: float,
    shadow_opacity: int,
) -> Image.Image:
    if shadow_blur < 0:
        raise ValueError("--shadow-blur must be greater than or equal to 0")

    if not 0 <= shadow_opacity <= 255:
        raise ValueError("--shadow-opacity must be between 0 and 255")

    x1, y1, x2, y2 = validate_box(box, base_image.size)
    target_width = x2 - x1
    target_height = y2 - y1

    fitted = ImageOps.contain(
        component_image,
        (target_width, target_height),
        method=Image.Resampling.LANCZOS,
    )

    offset_x = (target_width - fitted.width) // 2
    offset_y = (target_height - fitted.height) // 2
    component_position = (x1 + offset_x, y1 + offset_y)

    component_layer = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    component_layer.paste(fitted, component_position, fitted)

    component_alpha = component_layer.getchannel("A")
    shadow_alpha = component_alpha.point(
        lambda value: round(value * shadow_opacity / 255)
    )

    if shadow_blur > 0:
        shadow_alpha = shadow_alpha.filter(
            ImageFilter.GaussianBlur(shadow_blur)
        )

    shadow_alpha = offset_mask(
        shadow_alpha,
        shadow_offset_x,
        shadow_offset_y,
    )

    shadow_layer = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    shadow_layer.putalpha(shadow_alpha)

    result = Image.alpha_composite(
        base_image.convert("RGBA"),
        shadow_layer,
    )
    result = Image.alpha_composite(result, component_layer)
    return result.convert("RGB")


def place_component_in_crop(
    crop_image: Image.Image,
    component_image: Image.Image,
    component_box_in_crop: tuple[int, int, int, int],
    shadow_offset_x: int,
    shadow_offset_y: int,
    shadow_blur: float,
    shadow_opacity: int,
) -> Image.Image:
    return place_component(
        base_image=crop_image,
        component_image=component_image,
        box=component_box_in_crop,
        shadow_offset_x=shadow_offset_x,
        shadow_offset_y=shadow_offset_y,
        shadow_blur=shadow_blur,
        shadow_opacity=shadow_opacity,
    )


def create_feather_mask(
    size: tuple[int, int],
    feather_radius: float,
) -> Image.Image:
    width, height = size

    if feather_radius <= 0:
        return Image.new("L", size, 255)

    maximum_inset = max(1, min(width, height) // 4)
    inset = min(maximum_inset, max(2, round(feather_radius * 1.5)))

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle(
        (
            inset,
            inset,
            width - inset - 1,
            height - inset - 1,
        ),
        fill=255,
    )

    return mask.filter(ImageFilter.GaussianBlur(feather_radius))


def paste_crop_with_feather(
    base_image: Image.Image,
    edited_crop: Image.Image,
    edit_box: tuple[int, int, int, int],
    feather_radius: float,
) -> Image.Image:
    mask = create_feather_mask(
        edited_crop.size,
        feather_radius,
    )

    result = base_image.copy()
    result.paste(
        edited_crop,
        (edit_box[0], edit_box[1]),
        mask,
    )
    return result


def load_pipeline(
    model: str,
    device: torch.device,
) -> DiffusionPipeline:
    if device.type != "cuda":
        raise RuntimeError(
            "CUDA GPU not available. FireRed-Image-Edit 1.1 BF16 "
            "inference is intended to run on CUDA."
        )

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

    return result.images[0].convert("RGB")


def build_blend_prompt(user_prompt: str | None) -> str:
    realism_prompt = (
        "Treat the currently inserted elevator landing call indicator panel as "
        "the fixed product that must be physically installed on the existing wall. "
        "Preserve its exact outer silhouette, dimensions, position, perspective, "
        "button count, button positions, display shape, arrow, number, typography, "
        "colors, and product design. Do not regenerate, reinterpret, replace, move, "
        "resize, rotate, warp, or duplicate it. "

        "Integrate only its physical material and its contact with the wall. Match "
        "the wall's existing light direction, exposure, white balance, color cast, "
        "contrast, black level, sharpness, depth of field, sensor noise, compression "
        "texture, and lens softness. Apply the scene illumination continuously across "
        "the panel instead of giving it independent studio lighting. "

        "Give the metal faceplate a realistic fine brushed-metal surface with subdued "
        "environment reflections, gentle highlight rolloff, slight natural surface "
        "variation, and restrained roughness. Do not produce a flat gray fill or "
        "plastic CGI material. Keep the black display glossy but not mirror-like. "
        "Preserve every display symbol exactly. Give the buttons shallow physical "
        "depth, restrained edge highlights, and small localized ambient occlusion. "

        "Create tight dark ambient occlusion directly along the panel-to-wall seam "
        "and a soft low-opacity cast shadow consistent with the existing scene light. "
        "The shadow must remain attached to the panel, soften with distance, and must "
        "not become a uniform rectangular drop shadow. Add subtle reflected wall color "
        "to the panel edges and faint panel reflection on the wall only when supported "
        "by the original wall material. "

        "Remove pasted-on appearance, cutout edges, alpha halos, bright fringes, "
        "uniform edge darkness, excessive bevels, excessive thickness, floating gaps, "
        "oversharpening, synthetic gloss, and perfectly clean render texture. "

        "Modify only the panel surface, its immediate mounting seam, and its physically "
        "necessary local shadow. Preserve all surrounding wall seams, stains, texture, "
        "elevator doors, elevator frame, signs, floor, reflections, architecture, image "
        "composition, and camera perspective exactly."
    )

    if user_prompt and user_prompt.strip():
        return f"{user_prompt.strip()} {realism_prompt}"

    return realism_prompt


def main() -> int:
    args = parse_args()

    try:
        if args.steps <= 0:
            raise ValueError("--steps must be greater than 0")

        if args.true_cfg_scale <= 0:
            raise ValueError("--true-cfg-scale must be greater than 0")

        if args.crop_feather < 0:
            raise ValueError(
                "--crop-feather must be greater than or equal to 0"
            )

        device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        input_image = load_input_image(args.image)

        if not args.prompt and not args.component:
            raise ValueError(
                "Provide either --prompt for FireRed editing or "
                "--component with --box for component placement."
            )

        if args.component is not None:
            if args.box is None:
                raise ValueError(
                    "--box is required when --component is provided."
                )

            component_box = validate_box(
                tuple(args.box),
                input_image.size,
            )
            edit_box = expand_box(
                component_box,
                input_image.size,
                args.pad,
            )
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
                shadow_offset_x=args.shadow_offset_x,
                shadow_offset_y=args.shadow_offset_y,
                shadow_blur=args.shadow_blur,
                shadow_opacity=args.shadow_opacity,
            )

            pipe = load_pipeline(args.model, device)
            blend_prompt = build_blend_prompt(args.prompt)

            edited_crop = run_edit(
                pipe=pipe,
                image=placed_crop,
                prompt=blend_prompt,
                seed=args.seed,
                steps=args.steps,
                true_cfg_scale=args.true_cfg_scale,
            )

            if edited_crop.size != crop.size:
                edited_crop = edited_crop.resize(
                    crop.size,
                    Image.Resampling.LANCZOS,
                )

            output_image = paste_crop_with_feather(
                base_image=input_image,
                edited_crop=edited_crop,
                edit_box=edit_box,
                feather_radius=args.crop_feather,
            )
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
    raise SystemExit(main())`