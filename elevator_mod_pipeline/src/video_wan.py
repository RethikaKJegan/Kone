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
    "high_noise_model": "high_noise_model",
    "low_noise_model": "low_noise_model",
    "t5_checkpoint": "models_t5_umt5-xxl-enc-bf16.pth",
    "t5_tokenizer": "google/umt5-xxl",
    "vae_checkpoint": "Wan2.1_VAE.pth",
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
    checkpoint_dir = Path(wan_cfg.get("checkpoint_dir", "/root/wan22_install/Wan2.2/Wan2.2-I2V-A14B"))

    resolved = {}
    missing = []

    for key, default_name in REQUIRED_WAN22_14B_I2V_FILES.items():
        value = wan_cfg.get(key, default_name)
        path = Path(value)

        if not path.is_absolute():
            path = checkpoint_dir / value

        if not path.exists():
            missing.append(f"{key}: {path}")

        resolved[key] = path

    if missing:
        raise FileNotFoundError(
            "Missing Wan2.2 I2V-A14B checkpoint files for the installed Wan generate.py runner:\n"
            + "\n".join(missing)
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
    checkpoint_dir = Path(wan_cfg.get("checkpoint_dir", "/root/wan22_install/Wan2.2/Wan2.2-I2V-A14B"))

    wan_files = resolve_required_wan_files(wan_cfg)
    motion_style = normalize_wan_motion(video_cfg.get("motion_style", "zoom_in"))
    prompt = build_wan_prompt(motion_style, cfg)

    python_exe = wan_cfg.get("python_exe") or _default_python_exe(repo_dir)
    generated_dir = out_path.parent / "_wan_generation"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_file = generated_dir / "wan22_14b_i2v.mp4"
    error_path = out_path.with_name("wan_error.txt")

    if not image_path.exists():
        raise FileNotFoundError(f"Wan2.2 input image not found: {image_path}")
    if not (repo_dir / "generate.py").exists():
        raise FileNotFoundError(f"Wan2.2 runner not found: {repo_dir / 'generate.py'}")
    _validate_cuda_available(python_exe)

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
        "--save_file",
        str(generated_file),
    ]
    if wan_cfg.get("sample_guide_scale") is not None:
        cmd.extend(["--sample_guide_scale", str(wan_cfg["sample_guide_scale"])])

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
        _write_wan_error(error_path, cmd, result.stdout, result.stderr)
        reason = _summarize_wan_failure(result.stderr, result.stdout)
        raise RuntimeError(
            f"Wan2.2 generation failed: {reason}\n"
            f"Full Wan log: {error_path}\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    generated_mp4s = sorted(generated_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not generated_mp4s:
        _write_wan_error(error_path, cmd, result.stdout, result.stderr)
        raise RuntimeError(
            "Wan2.2 completed but no mp4 was found\n"
            f"Full Wan log: {error_path}\n"
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
        "t5_checkpoint": str(wan_files["t5_checkpoint"]),
        "t5_tokenizer": str(wan_files["t5_tokenizer"]),
        "vae_checkpoint": str(wan_files["vae_checkpoint"]),
        "size": wan_cfg.get("size", "1280*720"),
        "sample_steps": wan_cfg.get("sample_steps", 4),
        "sample_shift": wan_cfg.get("sample_shift", 5),
        "sample_guide_scale": wan_cfg.get("sample_guide_scale", "wan_default"),
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


def _validate_cuda_available(python_exe: str) -> None:
    result = subprocess.run(
        [
            python_exe,
            "-c",
            "import torch; print(torch.cuda.is_available()); print(torch.cuda.device_count())",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Wan2.2 CUDA preflight failed before generation.\n"
            f"Command: {python_exe} -c 'import torch; print(torch.cuda.is_available()); print(torch.cuda.device_count())'\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    cuda_available = lines[0].lower() == "true" if lines else False
    device_count = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0
    if not cuda_available or device_count < 1:
        raise RuntimeError(
            "Wan2.2 requires CUDA, but the Wan Python environment sees no GPU. "
            f"Run `{python_exe} -c \"import torch; print(torch.cuda.is_available()); print(torch.cuda.device_count())\"` "
            "and make sure it prints `True` and at least `1` before generating."
        )


def _write_wan_error(path: Path, cmd: list[str], stdout: str, stderr: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Command:\n"
        + " ".join(cmd)
        + "\n\nSTDOUT:\n"
        + stdout
        + "\n\nSTDERR:\n"
        + stderr,
        encoding="utf-8",
    )


def _summarize_wan_failure(stderr: str, stdout: str) -> str:
    combined = stderr.strip() or stdout.strip()
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    for line in reversed(lines):
        if any(token in line for token in ("Error:", "RuntimeError:", "ModuleNotFoundError:", "AssertionError:", "TypeError:", "CUDA out of memory")):
            return line[:500]
    return (lines[-1] if lines else "unknown error")[:500]
