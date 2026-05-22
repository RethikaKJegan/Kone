from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent


def target_from(prompt: str) -> str:
    match = re.search(r"replace\s+(?:the\s+|a\s+|an\s+)?(.+?)\s+with", prompt, re.I)
    return (match.group(1) if match else prompt).strip()


def write_config(test: dict, idx: int, base: dict) -> Path:
    name = Path(test["input_image"]).stem or f"case_{idx}"
    run_dir = Path(test.get("run_dir", f"tests/outputs/{idx:03d}_{name}"))
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
    ):
        if key in test:
            detection_cfg[key] = test[key]
    cfg["detection"] = detection_cfg
    cfg["refinement"] = {**base["refinement"], "prompt": test.get("prompt", base["refinement"]["prompt"])}
    video_cfg = dict(base.get("video", {}))
    for key in ("open_reference_image", "closed_reference_image", "reference_image", "action", "cycle", "fps", "bitrate", "no_audio"):
        if key in test:
            video_cfg[key] = test[key]
    cfg["video"] = video_cfg
    out = ROOT / run_dir / "config.generated.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return out


def run_case(item: tuple[int, dict], base: dict) -> int:
    cfg = write_config(item[1], item[0], base)
    return subprocess.run([sys.executable, "-m", "src.pipeline", "--config", str(cfg)], cwd=ROOT).returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pipeline cases from tests/manifest.json.")
    parser.add_argument("--manifest", default="tests/manifest.json")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--prepare-only", action="store_true", help="Write generated configs without running the pipeline.")
    args = parser.parse_args()

    base = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    tests = json.loads((ROOT / args.manifest).read_text(encoding="utf-8"))
    if args.prepare_only:
        for item in enumerate(tests, 1):
            print(write_config(item[1], item[0], base))
        return
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        codes = list(pool.map(lambda item: run_case(item, base), enumerate(tests, 1)))
    raise SystemExit(0 if all(code == 0 for code in codes) else 1)


if __name__ == "__main__":
    main()
