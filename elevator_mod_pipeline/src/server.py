from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from fastapi import FastAPI
from PIL import Image
from pydantic import BaseModel

from input_validation import validate_elevator_or_cop_upload, validate_input_image
from video import render_elevator_video

app = FastAPI()


class ProjectPayload(BaseModel):
    session_id: str
    project_id: str
    project_name: str | None = None
    storage_dir: str
    selected_components: list[str] | None = None
    environments: list[str] | None = None
    video_options: dict[str, Any] | None = None


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
    image_array = np.asarray(image)
    result = validate_input_image(image_array, {})
    relevance = validate_elevator_or_cop_upload(image_array, result)
    ok = bool(relevance.get("valid"))
    write_status(payload.storage_dir, public_status("precheck_passed" if ok else "precheck_failed", None if ok else relevance))
    return {
        "ok": ok,
        "next_action": "continue" if ok else "reupload",
        "image_type": relevance.get("image_type"),
        "message": relevance.get("reason"),
        "reason": None if ok else relevance.get("reason", "Image failed precheck"),
        "validation": result,
        "relevance": relevance,
    }


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
    cfg.update(
        {
            "run_dir": str(pipeline_dir),
            "input_image": str(input_image),
            "mod_panel": str(panel_path if panel_path.exists() else repo_root() / str(cfg.get("mod_panel", ""))),
            "input_validation": {"enabled": False},
            "video": {**cfg.get("video", {}), "enabled": False},
            "selected_components": payload.selected_components or [],
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


@app.post("/generate-video")
def generate_video(payload: ProjectPayload):
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
        cfg["video"] = {
            **cfg.get("video", {}),
            "enabled": True,
            "quality": video_options.get("quality", cfg.get("video", {}).get("quality", "1080p")),
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
        detections = json.loads(detections_path.read_text(encoding="utf-8")) if detections_path.exists() else {}
        geometry = json.loads(geometry_path.read_text(encoding="utf-8")) if geometry_path.exists() else {}
        render_elevator_video(
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
