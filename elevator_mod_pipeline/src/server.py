from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from fastapi import FastAPI
from PIL import Image, ImageOps
from pydantic import BaseModel

from input_validation import validate_elevator_or_cop_upload, validate_input_image

app = FastAPI()


class ProjectPayload(BaseModel):
    session_id: str
    project_id: str
    project_name: str | None = None
    storage_dir: str
    selected_components: list[str] | None = None
    component_assets: dict[str, str] | None = None
    environments: list[str] | None = None
    video_options: dict[str, Any] | None = None
    transform: dict[str, Any] | None = None


def write_status(storage_dir: str, data: dict[str, Any]) -> None:
    path = Path(storage_dir) / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"status.{os.getpid()}.{time.time_ns()}.tmp.json")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for _ in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.05)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.unlink(missing_ok=True)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def workspace_root() -> Path:
    return repo_root().parent


def selected_component_asset_paths(component_assets: dict[str, str] | None) -> dict[str, str]:
    default_dir = workspace_root() / "Frontend" / "kone-ui-master" / "public" / "components"
    default_files = {
        "ceiling": default_dir / "ceiling.jpg",
        "lci": default_dir / "lci.png",
        "door": default_dir / "door.jpg",
        "cop": default_dir / "cop.png",
    }
    resolved: dict[str, str] = {}
    for component, default_path in default_files.items():
        raw = (component_assets or {}).get(component)
        candidates: list[Path] = []
        if raw and raw.startswith("/components/"):
            candidates.append(workspace_root() / "Frontend" / "kone-ui-master" / "public" / raw.lstrip("/"))
        candidates.append(default_path)
        for candidate in candidates:
            if candidate.exists():
                resolved[component] = str(candidate)
                break
    return resolved



def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _transform_box_px(transform: dict[str, Any], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    x1 = round(_clamp_float(transform.get("x")) / 100.0 * width)
    y1 = round(_clamp_float(transform.get("y")) / 100.0 * height)
    x2 = round((_clamp_float(transform.get("x")) + _clamp_float(transform.get("width"), 10.0)) / 100.0 * width)
    y2 = round((_clamp_float(transform.get("y")) + _clamp_float(transform.get("height"), 10.0)) / 100.0 * height)
    x1, y1 = max(0, min(width - 1, x1)), max(0, min(height - 1, y1))
    x2, y2 = max(x1 + 1, min(width, x2)), max(y1 + 1, min(height, y2))
    return x1, y1, x2, y2


def _perspective_points_px(transform: dict[str, Any], image_size: tuple[int, int]) -> list[tuple[float, float]] | None:
    points = transform.get("perspective")
    if not isinstance(points, list) or len(points) != 4:
        return None
    width, height = image_size
    result = []
    for point in points:
        if not isinstance(point, dict):
            return None
        result.append((_clamp_float(point.get("x")) / 100.0 * width, _clamp_float(point.get("y")) / 100.0 * height))
    return result



def _perspective_differs_from_box(transform: dict[str, Any], perspective: list[tuple[float, float]] | None, image_size: tuple[int, int]) -> bool:
    if perspective is None:
        return False
    x1, y1, x2, y2 = _transform_box_px(transform, image_size)
    default = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return any(abs(px - dx) > 2 or abs(py - dy) > 2 for (px, py), (dx, dy) in zip(perspective, default))

def _component_asset_for_transform(transform: dict[str, Any], component_assets: dict[str, str] | None) -> Path:
    component_key = str(transform.get("componentKey") or transform.get("componentType") or "").lower()
    assets = selected_component_asset_paths(component_assets)
    if component_key not in assets:
        raise ValueError(f"Unsupported repin component: {component_key}")
    return Path(assets[component_key])


def _warp_component(component: Image.Image, transform: dict[str, Any], image_size: tuple[int, int]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    x1, y1, x2, y2 = _transform_box_px(transform, image_size)
    target_w, target_h = x2 - x1, y2 - y1
    fitted = ImageOps.contain(component.convert("RGBA"), (target_w, target_h), method=Image.Resampling.LANCZOS)
    slot = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    slot.paste(fitted, ((target_w - fitted.width) // 2, (target_h - fitted.height) // 2), fitted)

    skew_x = _clamp_float(transform.get("skewX"))
    skew_y = _clamp_float(transform.get("skewY"))
    if abs(skew_x) > 0.01 or abs(skew_y) > 0.01:
        slot = slot.transform(
            slot.size,
            Image.Transform.AFFINE,
            (1, -skew_x / 100.0, 0, -skew_y / 100.0, 1, 0),
            resample=Image.Resampling.BICUBIC,
        )

    rotation = _clamp_float(transform.get("rotation"))
    if abs(rotation) > 0.01:
        slot = slot.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        x1 = round(cx - slot.width / 2)
        y1 = round(cy - slot.height / 2)
        x2 = x1 + slot.width
        y2 = y1 + slot.height

    return slot, (x1, y1, x2, y2)


def _place_manual_component(base_image: Image.Image, component_image: Image.Image, transform: dict[str, Any]) -> tuple[Image.Image, tuple[int, int, int, int], list[tuple[float, float]] | None]:
    perspective = _perspective_points_px(transform, base_image.size)
    result = base_image.convert("RGBA")
    if _perspective_differs_from_box(transform, perspective, base_image.size):
        src = np.array(component_image.convert("RGBA"))
        src_h, src_w = src.shape[:2]
        source_quad = np.array([[0, 0], [src_w - 1, 0], [src_w - 1, src_h - 1], [0, src_h - 1]], dtype=np.float32)
        destination_quad = np.array(perspective, dtype=np.float32)
        homography = cv2.getPerspectiveTransform(source_quad, destination_quad)
        warped = cv2.warpPerspective(src, homography, base_image.size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_TRANSPARENT)
        warped_image = Image.fromarray(warped, "RGBA")
        result.alpha_composite(warped_image)
        xs = [point[0] for point in perspective]
        ys = [point[1] for point in perspective]
        bbox = (
            max(0, round(min(xs))),
            max(0, round(min(ys))),
            min(base_image.width, round(max(xs))),
            min(base_image.height, round(max(ys))),
        )
        return result.convert("RGB"), bbox, perspective

    warped, bbox = _warp_component(component_image, transform, base_image.size)
    x1, y1, x2, y2 = bbox
    paste_x, paste_y = max(0, x1), max(0, y1)
    crop_l, crop_t = max(0, -x1), max(0, -y1)
    crop_r, crop_b = warped.width - max(0, x2 - base_image.width), warped.height - max(0, y2 - base_image.height)
    if crop_r <= crop_l or crop_b <= crop_t:
        raise ValueError("Repin transform places the component outside the image")
    visible = warped.crop((crop_l, crop_t, crop_r, crop_b))
    result.paste(visible, (paste_x, paste_y), visible)
    px_bbox = (paste_x, paste_y, paste_x + visible.width, paste_y + visible.height)
    return result.convert("RGB"), px_bbox, perspective


def _firered_prompt(transform: dict[str, Any]) -> str:
    feedback = str(transform.get("feedbackOption") or "").replace("_", " ")
    component = str(transform.get("componentKey") or transform.get("componentType") or "component")
    feedback_sentence = f" Address this user feedback: {feedback}." if feedback else ""
    return (
        f"Make the inserted KONE {component} look realistically installed at its current exact position and geometry. "
        "Preserve the exact component design, dimensions, orientation, and placement chosen by the user. "
        "Refine only lighting, shadows, edge blending, wall contact, texture match, reflections, and perspective realism. "
        "Do not redesign the component, do not move it, do not resize it, and do not alter the surrounding elevator scene."
        f"{feedback_sentence}"
    )


def _run_firered_if_available(input_path: Path, output_path: Path, transform: dict[str, Any]) -> bool:
    script = os.environ.get("FIRERED_REPIN_SCRIPT") or os.environ.get("FIRERED_IMAGE_EDIT_SCRIPT")
    if not script:
        return False
    script_path = Path(script)
    if not script_path.exists():
        return False
    subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--image",
            str(input_path),
            "--prompt",
            _firered_prompt(transform),
            "--output",
            str(output_path),
        ],
        check=True,
    )
    return output_path.exists()


def public_status(status: str, error: Any = None) -> dict[str, Any]:
    return {
        "status": status,
        "preview_url": "preview/final_output.png" if status in {"preview_ready", "video_ready"} else None,
        "video_url": "video/elevator_animation.mp4" if status == "video_ready" else None,
        "download_url": None,
        "error": error,
    }


@app.post("/precheck")
def precheck(payload: ProjectPayload):
    image_path = Path(payload.storage_dir) / "uploads" / "input.jpg"
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((900, 900), Image.Resampling.LANCZOS)
    image_array = np.asarray(image)
    result = validate_input_image(image_array, {})
    if not result.get("valid", False):
        reason = _validation_message(result)
        failure = {
            "reason": reason,
            "validation": result,
        }
        write_status(payload.storage_dir, public_status("precheck_failed", failure))
        return {
            "ok": False,
            "next_action": "reupload",
            "image_type": "UNUSABLE",
            "message": reason,
            "reason": reason,
            "validation": result,
            "relevance": None,
        }
    relevance = validate_elevator_or_cop_upload(image_array, result)
    ok = bool(relevance.get("valid"))
    reason = None
    if not ok:
        reason = relevance.get("reason") or "Invalid image. Please upload a valid elevator image."
    failure = None if ok else {
        "reason": reason,
        "relevance": relevance,
    }
    write_status(payload.storage_dir, public_status("precheck_passed" if ok else "precheck_failed", failure))
    return {
        "ok": ok,
        "next_action": "continue" if ok else "reupload",
        "image_type": "ELEVATOR_IMAGE" if ok else relevance.get("image_type"),
        "message": None if ok else reason,
        "reason": None if ok else reason,
        "validation": result,
        "relevance": relevance,
    }


def _validation_message(validation: dict[str, Any]) -> str:
    reasons = validation.get("reasons", {}) or {}
    hard_fail = reasons.get("hard_fail") or []
    if hard_fail:
        return str(hard_fail[0])
    suggestions = reasons.get("suggestions") or []
    if suggestions:
        return str(suggestions[0])
    return "Invalid image. Please upload a valid elevator image."


@app.post("/run-components")
def run_components(payload: ProjectPayload):
    storage = Path(payload.storage_dir)
    input_image = storage / "uploads" / "input.jpg"
    preview_dir = storage / "preview"
    pipeline_dir = storage / "pipeline"
    preview_dir.mkdir(parents=True, exist_ok=True)
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    write_status(payload.storage_dir, public_status("processing"))

    cfg_path = repo_root() / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    panel_path = repo_root() / "tests" / "panels" / "mod_panel.png"
    component_assets = selected_component_asset_paths(payload.component_assets)
    cfg.update(
        {
            "run_dir": str(pipeline_dir),
            "input_image": str(input_image),
            "mod_panel": str(panel_path if panel_path.exists() else repo_root() / str(cfg.get("mod_panel", ""))),
            "input_validation": {"enabled": False},
            "video": {**cfg.get("video", {}), "enabled": False},
            "selected_components": payload.selected_components or [],
            "component_assets": component_assets,
            "environment": payload.environments or [],
        }
    )
    config_path = pipeline_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    try:
        subprocess.run(
            [sys.executable, "-m", "src.pipeline", "--config", str(config_path)],
            cwd=repo_root(),
            check=True,
        )
        final_output = pipeline_dir / "final_output.png"
        shutil.copy2(final_output if final_output.exists() else input_image, preview_dir / "final_output.png")
        write_status(payload.storage_dir, public_status("preview_ready"))
        return {"ok": True, "status": "preview_ready"}
    except Exception as exc:
        write_status(payload.storage_dir, public_status("failed", str(exc)))
        return {"ok": False, "status": "failed", "error": str(exc)}



@app.post("/repin-components")
def repin_components(payload: ProjectPayload):
    storage = Path(payload.storage_dir)
    preview_dir = storage / "preview"
    pipeline_dir = storage / "pipeline"
    preview_dir.mkdir(parents=True, exist_ok=True)
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    write_status(payload.storage_dir, public_status("processing"))

    try:
        transform = payload.transform or {}
        source_version = int(transform.get("sourceVersion") or 1)
        target_version = int(transform.get("targetVersion") or 2)
        if target_version > 5:
            raise ValueError("Version limit reached. Choose the best saved version to continue.")

        source_candidates = [
            preview_dir / f"final_output_v{source_version}.png",
            storage / "uploads" / f"repin_source_v{source_version}.png",
            preview_dir / "final_output.png",
            storage / "uploads" / "input.jpg",
        ]
        source_image_path = next((candidate for candidate in source_candidates if candidate.exists()), None)
        if source_image_path is None:
            raise FileNotFoundError("Repin source preview was not found")

        base_image = Image.open(source_image_path).convert("RGB")
        component_image = Image.open(_component_asset_for_transform(transform, payload.component_assets)).convert("RGBA")
        placed_image, bbox, perspective = _place_manual_component(base_image, component_image, transform)

        placed_path = pipeline_dir / f"repin_v{target_version}_placed.png"
        output_path = preview_dir / f"final_output_v{target_version}.png"
        placed_image.save(placed_path)
        used_firered = _run_firered_if_available(placed_path, output_path, transform)
        if not used_firered:
            placed_image.save(output_path)
        shutil.copy2(output_path, preview_dir / "final_output.png")

        placement = {
            "id": transform.get("componentKey"),
            "component_type": transform.get("componentType"),
            "manual_repin": True,
            "source_version": source_version,
            "target_version": target_version,
            "feedback_option": transform.get("feedbackOption"),
            "transform": transform,
            "final_insertion_bbox": list(bbox),
            "final_component_placement": {"bbox": list(bbox), "reason": "manual_repin_transform"},
            "perspective_corner_points": perspective,
            "firered_realism_refine": used_firered,
            "lama_used": False,
        }
        existing = []
        placements_path = pipeline_dir / "component_placements.json"
        if placements_path.exists():
            try:
                loaded = json.loads(placements_path.read_text(encoding="utf-8"))
                existing = loaded if isinstance(loaded, list) else []
            except json.JSONDecodeError:
                existing = []
        existing = [item for item in existing if item.get("id") != transform.get("componentKey")]
        existing.append(placement)
        placements_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        (pipeline_dir / f"repin_transform_v{target_version}.json").write_text(json.dumps(placement, indent=2), encoding="utf-8")

        status = public_status("preview_ready")
        status.update({
            "preview_url": f"preview/final_output_v{target_version}.png",
            "current_preview_url": "preview/final_output.png",
            "repin_pass": target_version,
            "preview_versions": [{"version": target_version, "url": f"preview/final_output_v{target_version}.png"}],
        })
        write_status(payload.storage_dir, status)
        return {"ok": True, "status": "preview_ready", "preview_url": status["preview_url"], "repin_pass": target_version}
    except Exception as exc:
        write_status(payload.storage_dir, public_status("failed", str(exc)))
        return {"ok": False, "status": "failed", "error": str(exc)}

@app.post("/generate-video")
def generate_video(payload: ProjectPayload):
    from video_router import render_video

    storage = Path(payload.storage_dir)
    preview_image = storage / "preview" / "final_output.png"
    pipeline_dir = storage / "pipeline"
    video_dir = storage / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / "elevator_animation.mp4"
    cfg_path = pipeline_dir / "config.yaml"
    detections_path = pipeline_dir / "elevator_detections.json"
    geometry_path = pipeline_dir / "geometry.json"
    depth_path = pipeline_dir / "depth_map.npz"

    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else yaml.safe_load((repo_root() / "config.yaml").read_text(encoding="utf-8"))
        video_options = payload.video_options or {}
        motion = video_options.get("motion") or video_options.get("motion_style")
        video_cfg = cfg.get("video", {})
        requested_engine = str(video_options.get("engine", video_cfg.get("engine", "opencv"))).strip().lower()
        wan_engines = {"wan", "wan2.2", "wan22"}
        comfy_engines = {"comfy", "comfy_wan", "comfy_i2v", "comfy_flf2v", "wan_comfy"}
        effective_engine = (
            requested_engine
            if requested_engine in comfy_engines
            else "wan2.2"
            if requested_engine in wan_engines
            else "opencv"
        )
        cfg["video"] = {
            **video_cfg,
            "enabled": True,
            "engine": effective_engine,
            "requested_engine": requested_engine,
            "quality": video_options.get("quality", video_cfg.get("quality", "720p")),
            "duration_seconds": video_options.get("duration_seconds", video_options.get("duration", 9.0)),
            "preserve_source_aspect": True,
            "ffmpeg_pan_overscan": 0.20,
            "ffmpeg_zoom_amount": 0.35,
        }
        if video_options.get("mode") == "door_functionality":
            cfg["video"].update({"mode": "door_functionality"})
            cfg["video"].pop("motion_style", None)
        elif motion:
            cfg["video"].update({"motion_style": motion, "mode": "motion"})
        elif requested_engine in {"wan", "wan2.2", "wan22", "comfy", "comfy_wan", "comfy_i2v", "wan_comfy"}:
            cfg["video"].setdefault("motion_style", "zoom_in")
        if cfg["video"].get("engine") in comfy_engines:
            cfg["video"].setdefault("fps", 16)
            cfg["video"].setdefault("duration_seconds", 5)
            cfg["video"].setdefault("quality_mode", video_options.get("quality_mode", "best"))
            cfg["video"]["comfy"] = {
                **cfg["video"].get("comfy", {}),
                **video_options.get("comfy", {}),
                "quality_mode": video_options.get("quality_mode", cfg["video"].get("quality_mode", "best")),
            }
        if cfg["video"].get("engine") == "wan2.2":
            cfg["video"].setdefault("fps", 16)
            cfg["video"].setdefault("duration_seconds", 5)
            wan_defaults = {
                "model_key": "wan22_14b_i2v",
                "task": "i2v-14B",
                "size": "832*480",
                "frame_num": 81,
                "sample_steps": 40,
                "sample_shift": 3.0,
                "sample_guide_scale": None,
                "repo_dir": "/root/wan22_install/Wan2.2",
                "checkpoint_dir": "/root/wan22_install/Wan2.2/Wan2.2-I2V-A14B",
                "offload_model": False,
                "t5_cpu": False,
                "convert_model_dtype": True,
                "min_size_bytes": 1_000_000,
            }
            cfg["video"]["wan"] = {
                **cfg["video"].get("wan", {}),
                **wan_defaults,
                **video_options.get("wan", {}),
                "enabled": True,
            }
        detections = json.loads(detections_path.read_text(encoding="utf-8")) if detections_path.exists() else {}
        geometry = json.loads(geometry_path.read_text(encoding="utf-8")) if geometry_path.exists() else {}
        render_video(
            preview_image,
            detections,
            geometry,
            cfg,
            video_path,
            depth_path if depth_path.exists() else None,
        )
        write_status(payload.storage_dir, public_status("video_ready"))
        return {"ok": True, "status": "video_ready"}
    except Exception as exc:
        write_status(payload.storage_dir, public_status("failed", str(exc)))
        return {"ok": False, "status": "failed", "error": str(exc)}
