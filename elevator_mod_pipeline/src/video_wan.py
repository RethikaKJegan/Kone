from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .video_prompts import build_wan_prompt
except ImportError:
    from video_prompts import build_wan_prompt


REQUIRED_WAN22_14B_I2V_FILES = {
    "high_noise_model": "wan2.2_i2v_high_noise_14B_fp16.safetensors",
    "low_noise_model": "wan2.2_i2v_low_noise_14B_fp16.safetensors",
    "high_noise_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
    "low_noise_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
    "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "vae_name": "wan_2.1_vae.safetensors",
}

WAN_MOTION_ALIASES = {
    "zoom": "zoom_in",
    "zoom-in": "zoom_in",
    "zoom_in": "zoom_in",
    "pan-lr": "pan_l_r",
    "pan_lr": "pan_l_r",
    "pan-l-r": "pan_l_r",
    "pan_l_r": "pan_l_r",
    "pan-rl": "pan_r_l",
    "pan_rl": "pan_r_l",
    "pan-r-l": "pan_r_l",
    "pan_r_l": "pan_r_l",
    "pan-t-b": "pan_t_b",
    "pan_t_b": "pan_t_b",
    "pan-b-t": "pan_b_t",
    "pan_b_t": "pan_b_t",
    "door-functionality": "door_functionality",
    "door_functionality": "door_functionality",
}


def resolve_required_wan_files(wan_cfg: dict) -> dict:
    checkpoint_dir = Path(wan_cfg.get("checkpoint_dir", "/root/wan22_install/Wan2.2/models"))

    resolved = {}
    missing = []

    for key, default_name in REQUIRED_WAN22_14B_I2V_FILES.items():
        value = wan_cfg.get(key, default_name)
        path = Path(value)

        if not path.is_absolute():
            matches = list(checkpoint_dir.rglob(value))
            if matches:
                path = matches[0]
            else:
                path = checkpoint_dir / value

        if not path.exists():
            missing.append(f"{key}: {path}")

        resolved[key] = path

    if missing:
        raise FileNotFoundError(
            "Missing Wan2.2 14B I2V model files:\n" + "\n".join(missing)
        )

    return resolved


def render_wan_video(image_path, detections=None, geometry=None, cfg=None, out_path=None, depth_path=None):
    cfg = cfg or {}
    image_path = Path(image_path)
    out_path = Path(out_path or image_path.with_name("elevator_animation.mp4"))

    video_cfg = cfg.get("video", {})
    wan_cfg = video_cfg.get("wan", {})

    if not wan_cfg.get("enabled", False):
        raise RuntimeError("Wan2.2 video engine selected but video.wan.enabled is false")

    model_key = wan_cfg.get("model_key", "wan22_14b_i2v")
    if model_key != "wan22_14b_i2v":
        raise RuntimeError(f"Unsupported Wan model_key: {model_key}")

    repo_dir = Path(wan_cfg.get("repo_dir", "/root/wan22_install/Wan2.2"))
    checkpoint_dir = Path(wan_cfg.get("checkpoint_dir", "/root/wan22_install/Wan2.2/models"))

    wan_files = resolve_required_wan_files(wan_cfg)
    motion_style = normalize_wan_motion(video_cfg.get("motion_style", "zoom_in"))
    prompt = build_wan_prompt(motion_style, cfg)

    python_exe = wan_cfg.get("python_exe") or _default_python_exe(repo_dir)
    generated_dir = out_path.parent / "_wan_generation"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_file = generated_dir / "wan22_14b_i2v.mp4"

    if not image_path.exists():
        raise FileNotFoundError(f"Wan2.2 input image not found: {image_path}")
    if not (repo_dir / "generate.py").exists():
        raise FileNotFoundError(f"Wan2.2 runner not found: {repo_dir / 'generate.py'}")

    task = normalize_wan_task(wan_cfg.get("task", "i2v-14B"))
    cmd = [
        python_exe,
        str(repo_dir / "generate.py"),
        "--task",
        task,
        "--size",
        wan_cfg.get("size", "1280*720"),
        "--ckpt_dir",
        str(checkpoint_dir),
        "--image",
        str(image_path),
        "--prompt",
        prompt,
        "--sample_steps",
        str(wan_cfg.get("sample_steps", 4)),
        "--sample_shift",
        str(wan_cfg.get("sample_shift", 5)),
        "--sample_guide_scale",
        str(wan_cfg.get("sample_guide_scale", 5)),
        "--save_file",
        str(generated_file),
    ]

    if "offload_model" in wan_cfg:
        cmd.extend(["--offload_model", str(bool(wan_cfg.get("offload_model")))])

    if wan_cfg.get("t5_cpu", False):
        cmd.append("--t5_cpu")

    if wan_cfg.get("prompt_extension", False):
        cmd.append("--use_prompt_extend")

    seed = video_cfg.get("seed")
    if seed is not None:
        cmd.extend(["--base_seed", str(seed)])

    result = subprocess.run(
        cmd,
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Wan2.2 generation failed\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    generated_mp4s = sorted(generated_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not generated_mp4s:
        raise RuntimeError(
            "Wan2.2 completed but no mp4 was found\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated_mp4s[0], out_path)

    metadata = {
        "engine": "wan2.2",
        "model_key": "wan22_14b_i2v",
        "model": "Wan2.2 14B FP16 I2V",
        "input_image": str(image_path),
        "output_video": str(out_path),
        "motion_style": motion_style,
        "prompt": prompt,
        "repo_dir": str(repo_dir),
        "checkpoint_dir": str(checkpoint_dir),
        "high_noise_model": str(wan_files["high_noise_model"]),
        "low_noise_model": str(wan_files["low_noise_model"]),
        "high_noise_lora": str(wan_files["high_noise_lora"]),
        "low_noise_lora": str(wan_files["low_noise_lora"]),
        "clip_name": str(wan_files["clip_name"]),
        "vae_name": str(wan_files["vae_name"]),
        "size": wan_cfg.get("size", "1280*720"),
        "sample_steps": wan_cfg.get("sample_steps", 4),
        "sample_shift": wan_cfg.get("sample_shift", 5),
        "sample_guide_scale": wan_cfg.get("sample_guide_scale", 5),
        "runner_task": task,
        "runner_command": cmd,
    }

    out_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return out_path


def normalize_wan_motion(motion_style: str | None) -> str:
    motion = str(motion_style or "zoom_in").strip().lower()
    return WAN_MOTION_ALIASES.get(motion, motion)


def normalize_wan_task(task: str) -> str:
    task = str(task or "i2v-14B")
    return "i2v-A14B" if task == "i2v-14B" else task


def _default_python_exe(repo_dir: Path) -> str:
    venv_python = repo_dir.parent / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable
