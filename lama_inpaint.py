from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
import yaml
from PIL import Image


ROOT = Path(__file__).resolve().parent
LAMA_REPO_DIR = ROOT / "lama"

if str(LAMA_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(LAMA_REPO_DIR))

from saicinpainting.training.modules import make_generator


INTERPOLATION_RE = re.compile(r"^\$\{([^}]+)\}$")


def get_nested(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in path.split("."):
        current = current[part]
    return current


def resolve_config_value(value: Any, root: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_config_value(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_config_value(item, root) for item in value]
    if isinstance(value, str):
        match = INTERPOLATION_RE.match(value)
        if match:
            token = match.group(1)
            if token.startswith("env:"):
                return ""
            return resolve_config_value(get_nested(root, token), root)
    return value


def pil_resampling(name: str):
    return getattr(getattr(Image, "Resampling", Image), name)


def resize_for_lama(image: np.ndarray, mask: np.ndarray, max_side: int) -> tuple[np.ndarray, np.ndarray, tuple[int, int] | None]:
    if max_side <= 0:
        return image, mask, None

    height, width = image.shape[:2]
    largest = max(height, width)
    if largest <= max_side:
        return image, mask, None

    scale = max_side / largest
    new_width = max(8, int(round(width * scale)))
    new_height = max(8, int(round(height * scale)))

    resized_image = np.asarray(
        Image.fromarray(image).resize((new_width, new_height), pil_resampling("LANCZOS"))
    )
    resized_mask = np.asarray(
        Image.fromarray((mask > 0).astype(np.uint8) * 255).resize(
            (new_width, new_height),
            pil_resampling("NEAREST"),
        )
    )
    return resized_image, resized_mask, (width, height)


def pad_to_modulo(tensor: torch.Tensor, modulo: int) -> tuple[torch.Tensor, tuple[int, int]]:
    height, width = tensor.shape[-2:]
    pad_height = (modulo - height % modulo) % modulo
    pad_width = (modulo - width % modulo) % modulo
    if pad_height == 0 and pad_width == 0:
        return tensor, (height, width)

    mode = "reflect" if height > 1 and width > 1 else "replicate"
    padded = F.pad(tensor, (0, pad_width, 0, pad_height), mode=mode)
    return padded, (height, width)


def install_lightning_checkpoint_stub() -> list[type]:
    if "pytorch_lightning.callbacks.model_checkpoint" in sys.modules:
        module = sys.modules["pytorch_lightning.callbacks.model_checkpoint"]
        return [module.ModelCheckpoint] if hasattr(module, "ModelCheckpoint") else []

    lightning_module = types.ModuleType("pytorch_lightning")
    callbacks_module = types.ModuleType("pytorch_lightning.callbacks")
    checkpoint_module = types.ModuleType("pytorch_lightning.callbacks.model_checkpoint")

    class ModelCheckpoint:
        pass

    ModelCheckpoint.__module__ = "pytorch_lightning.callbacks.model_checkpoint"
    checkpoint_module.ModelCheckpoint = ModelCheckpoint
    callbacks_module.model_checkpoint = checkpoint_module
    lightning_module.callbacks = callbacks_module
    lightning_module.seed_everything = lambda seed: seed

    sys.modules.setdefault("pytorch_lightning", lightning_module)
    sys.modules.setdefault("pytorch_lightning.callbacks", callbacks_module)
    sys.modules.setdefault("pytorch_lightning.callbacks.model_checkpoint", checkpoint_module)
    return [ModelCheckpoint]


class LamaInpainter:
    def __init__(self, model_dir: str | Path, device: str = "cpu") -> None:
        self.model_dir = Path(model_dir)
        self.device = torch.device(device)
        self.generator = self._load_generator().to(self.device).eval()

    def _load_generator(self) -> torch.nn.Module:
        config_path = self.model_dir / "config.yaml"
        checkpoint_path = self.model_dir / "models/best.ckpt"
        if not config_path.exists():
            raise FileNotFoundError(f"LaMa config not found: {config_path}")
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"LaMa checkpoint not found: {checkpoint_path}")

        with config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)

        generator_config = resolve_config_value(config["generator"], config)
        kind = generator_config.pop("kind")
        generator = make_generator(config=None, kind=kind, **generator_config)

        safe_classes = install_lightning_checkpoint_stub()
        try:
            with torch.serialization.safe_globals(safe_classes):
                checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        except Exception:
            checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

        state_dict = checkpoint["state_dict"] if isinstance(checkpoint, dict) and "state_dict" in checkpoint else checkpoint
        generator_state = {
            key.removeprefix("generator."): value
            for key, value in state_dict.items()
            if key.startswith("generator.")
        }
        if not generator_state:
            generator_state = state_dict

        generator.load_state_dict(generator_state, strict=True)
        return generator

    @torch.inference_mode()
    def inpaint(self, image_rgb: np.ndarray, mask: np.ndarray, max_side: int = 1536) -> np.ndarray:
        original_height, original_width = image_rgb.shape[:2]
        work_image, work_mask, restore_size = resize_for_lama(image_rgb, mask, max_side=max_side)

        image_tensor = torch.from_numpy(work_image).float().permute(2, 0, 1).unsqueeze(0) / 255.0
        mask_tensor = torch.from_numpy((work_mask > 0).astype(np.float32)).unsqueeze(0).unsqueeze(0)

        image_tensor, unpad_size = pad_to_modulo(image_tensor, 8)
        mask_tensor, _ = pad_to_modulo(mask_tensor, 8)

        image_tensor = image_tensor.to(self.device)
        mask_tensor = mask_tensor.to(self.device)
        masked_image = image_tensor * (1 - mask_tensor)
        prediction = self.generator(torch.cat([masked_image, mask_tensor], dim=1))
        inpainted = mask_tensor * prediction + (1 - mask_tensor) * image_tensor
        inpainted = inpainted[:, :, : unpad_size[0], : unpad_size[1]]
        result = inpainted[0].permute(1, 2, 0).detach().cpu().numpy()
        result = np.clip(result * 255, 0, 255).astype(np.uint8)

        if restore_size is not None:
            result = np.asarray(
                Image.fromarray(result).resize(restore_size, pil_resampling("LANCZOS"))
            )

        return result[:original_height, :original_width]
