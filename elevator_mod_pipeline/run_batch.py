from __future__ import annotations

import argparse
import os
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
VIDEO_MODE_ALIASES = {
    "pan_lr": {"motion_style": "pan_l_r"},
    "panel_lr": {"motion_style": "pan_l_r"},
    "pane_lr": {"motion_style": "pan_l_r"},
    "panle_lr": {"motion_style": "pan_l_r"},
    "panel_l_r": {"motion_style": "pan_l_r"},
    "pan_l_r": {"motion_style": "pan_l_r"},
    "pan_rl": {"motion_style": "pan_r_l"},
    "panel_rl": {"motion_style": "pan_r_l"},
    "pane_rl": {"motion_style": "pan_r_l"},
    "panle_rl": {"motion_style": "pan_r_l"},
    "panel_r_l": {"motion_style": "pan_r_l"},
    "pan_r_l": {"motion_style": "pan_r_l"},
    "zoom": {"motion_style": "zoom_in"},
    "zoom_in": {"motion_style": "zoom_in"},
    "door": {"action": "auto", "cycle": True},
    "door_functionality": {"action": "auto", "cycle": True},
    "door_fuctionality": {"action": "auto", "cycle": True},
}
CAMERA_MODE_DEFAULTS = {
    "duration": 8.0,
    "fps": 30,
    "quality": "1080p",
    "preserve_source_aspect": True,
    "ffmpeg_temporal_smoothing": False,
    "ffmpeg_add_grain": False,
    "ffmpeg_sharpen": True,
}


def target_from(prompt: str) -> str:
    match = re.search(r"replace\s+(?:the\s+|a\s+|an\s+)?(.+?)\s+with", prompt, re.I)
    return (match.group(1) if match else prompt).strip()


def write_config(test: dict, idx: int, base: dict, *, no_video: bool = False, video_mode: str | None = None) -> Path:
    name = Path(test["input_image"]).stem or f"case_{idx}"
    mode_name = normalize_video_mode_name(video_mode or test.get("video_mode") or test.get("mode"))
    default_run_dir = f"tests/outputs/{idx:03d}_{name}" + (f"_{mode_name}" if mode_name and has_multiple_video_modes(test) else "")
    run_dir = Path(test.get("run_dir", default_run_dir))
    if video_mode and test.get("run_dir") and has_multiple_video_modes(test):
        run_dir = Path(f"{test['run_dir']}_{mode_name}")
    target = test.get("target", target_from(test["prompt"]))
    cfg = dict(base)
    cfg.update(input_image=test["input_image"], mod_panel=test["mod_panel"], run_dir=str(run_dir))
    removal_keywords = [target]
    if Path(test["mod_panel"]).stem == "mod_long" and target.lower() in {"door track", "threshold plate"}:
        removal_keywords = ["door track", "threshold plate"]
    cfg["removal"] = {**base["removal"], "target_keywords": removal_keywords}
    cfg["insertion"] = {**base["insertion"], "target_keywords": [target]}
    detection_labels = test.get("detection_labels", base["detection"]["labels"])
    detection_cfg = {**base["detection"], "labels": sorted(set(detection_labels + [target]))}
    for key in (
        "box_threshold",
        "text_threshold",
        "score_threshold",
        "nms_iou",
        "max_detections",
        "min_box_area_ratio",
        "max_box_area_ratio",
        "existing_json",
    ):
        if key in test:
            detection_cfg[key] = test[key]
    cfg["detection"] = detection_cfg
    cfg["refinement"] = {**base["refinement"], "prompt": test.get("prompt", base["refinement"]["prompt"])}
    video_cfg = dict(base.get("video", {}))
    for key in (
        "open_reference_image",
        "closed_reference_image",
        "reference_image",
        "action",
        "cycle",
        "fps",
        "bitrate",
        "no_audio",
        "motion_style",
        "door_functionality",
        "quality",
        "duration",
        "duration_seconds",
    ):
        if key in test:
            video_cfg[key] = test[key]
    if mode_name:
        video_cfg.update(video_config_for_mode(mode_name))
        video_cfg["mode"] = mode_name
    if no_video:
        video_cfg["enabled"] = False
    cfg["video"] = video_cfg
    out = ROOT / run_dir / "config.generated.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return out


def run_case(item: tuple[int, dict], base: dict, no_video: bool = False) -> int:
    cfg = write_config(item[1], item[0], base, no_video=no_video, video_mode=item[1].get("_expanded_video_mode"))
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore::UserWarning,ignore::FutureWarning"
    env.setdefault("TRANSFORMERS_VERBOSITY", "error")
    return subprocess.run([sys.executable, "-m", "src.pipeline", "--config", str(cfg)], cwd=ROOT, env=env).returncode


def normalize_video_mode_name(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return text or None


def has_multiple_video_modes(test: dict) -> bool:
    return bool(test.get("_multiple_video_modes")) or (isinstance(test.get("video_modes"), list) and len(test["video_modes"]) > 1)


def video_config_for_mode(mode_name: str) -> dict:
    if mode_name not in VIDEO_MODE_ALIASES:
        raise ValueError(f"Unsupported video_mode '{mode_name}'. Expected one of {sorted(VIDEO_MODE_ALIASES)}")
    cfg = dict(VIDEO_MODE_ALIASES[mode_name])
    if cfg.get("motion_style"):
        cfg = {**CAMERA_MODE_DEFAULTS, **cfg}
        cfg.pop("door_functionality", None)
        cfg["cycle"] = False
        cfg["no_audio"] = True
    else:
        cfg.pop("motion_style", None)
    return cfg


def expand_video_modes(tests: list[dict]) -> list[dict]:
    expanded: list[dict] = []
    for test in tests:
        modes = test.get("video_modes")
        if isinstance(modes, list) and modes:
            for mode in modes:
                item = dict(test)
                item.pop("video_modes", None)
                item["_expanded_video_mode"] = normalize_video_mode_name(mode)
                item["_multiple_video_modes"] = True
                expanded.append(item)
        else:
            item = dict(test)
            if "video_mode" in item or "mode" in item:
                item["_expanded_video_mode"] = normalize_video_mode_name(item.get("video_mode", item.get("mode")))
            expanded.append(item)
    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pipeline cases from tests/manifest.json.")
    parser.add_argument("--manifest", default="tests/manifest.json")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--no-video", action="store_true", help="Disable video generation in generated configs.")
    parser.add_argument("--prepare-only", action="store_true", help="Write generated configs without running the pipeline.")
    args = parser.parse_args()

    base = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    tests = expand_video_modes(json.loads((ROOT / args.manifest).read_text(encoding="utf-8")))
    if args.prepare_only:
        for item in enumerate(tests, 1):
            print(write_config(item[1], item[0], base, no_video=args.no_video, video_mode=item[1].get("_expanded_video_mode")))
        return
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        codes = list(pool.map(lambda item: run_case(item, base, args.no_video), enumerate(tests, 1)))
    raise SystemExit(0 if all(code == 0 for code in codes) else 1)


if __name__ == "__main__":
    main()
