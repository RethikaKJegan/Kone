from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from .inpaint import build_removal_mask, inpaint_background
from .insert_mod import insert_mod_panel
from .preprocess import run_preprocessing
from .refine import maybe_refine
from .resource_monitor import ResourceMonitor
from .utils import load_config, load_image_rgb, load_json, save_rgb
from .video import render_elevator_video
from .visualize import save_detection_visuals


def run(config_path: str | Path) -> None:
    cfg = load_config(config_path)
    run_dir = Path(cfg["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)

    input_image = Path(cfg["input_image"])
    mod_panel = Path(cfg["mod_panel"])
    preprocessed_path = run_dir / "preprocessed_input.png"
    preprocessing_path = run_dir / "preprocessing.json"
    detections_path = run_dir / "elevator_detections.json"
    geometry_path = run_dir / "geometry.json"
    depth_path = run_dir / "depth_map.npz"
    resource_log_path = run_dir / "pipeline_resource_log.txt"
    removal_mask_path = run_dir / "removal_mask.png"
    cleaned_path = run_dir / "cleaned_background.png"
    composite_path = run_dir / "composite.png"
    panel_mask_path = run_dir / "harmonization_mask.png"
    final_path = run_dir / "final_output.png"
    video_path = run_dir / "elevator_animation.mp4"

    with ResourceMonitor(resource_log_path, float(cfg.get("monitoring", {}).get("interval_s", 1.0))) as monitor:
        monitor.mark("pipeline_start")
        if cfg.get("preprocessing", {}).get("enabled", True):
            monitor.mark("preprocessing_start")
            working_image = run_preprocessing(input_image, cfg, preprocessed_path, preprocessing_path)
            monitor.mark("preprocessing_done")
        else:
            working_image = input_image

        existing_detections = cfg["detection"].get("existing_json")
        if existing_detections:
            detections = load_json(existing_detections)
            detections_path.write_text(Path(existing_detections).read_text(encoding="utf-8"), encoding="utf-8")
        elif cfg["detection"].get("enabled", True):
            from .detect import add_sam2_masks, run_detection

            monitor.mark("detection_start")
            detections = run_detection(working_image, cfg, detections_path)
            monitor.mark("sam2_start")
            detections = add_sam2_masks(working_image, cfg, detections, detections_path)
            monitor.mark("detection_done")
        elif detections_path.exists():
            detections = load_json(detections_path)
        else:
            raise FileNotFoundError(f"Detection disabled but {detections_path} does not exist")

        if cfg["geometry"].get("enabled", True):
            from .geometry import run_geometry

            monitor.mark("geometry_start")
            geometry = run_geometry(working_image, detections, cfg, geometry_path, depth_path)
            monitor.mark("geometry_done")
        elif geometry_path.exists():
            geometry = load_json(geometry_path)
        else:
            geometry = {"wall_plane": {"normal": [0, 0, 1]}, "homography": {"matrix_3x3": None}}

        original = load_image_rgb(working_image)
        save_detection_visuals(working_image, detections, run_dir)
        monitor.mark("inpaint_start")
        removal_mask = build_removal_mask(original, detections, cfg)
        cv2.imwrite(str(removal_mask_path), removal_mask)
        cleaned_override = cfg["inpainting"].get("cleaned_background")
        if cleaned_override:
            save_rgb(cleaned_path, load_image_rgb(cleaned_override))
        else:
            inpaint_background(working_image, removal_mask, cfg, cleaned_path)
        monitor.mark("inpaint_done")
        monitor.mark("insertion_start")
        insert_mod_panel(cleaned_path, mod_panel, detections, geometry, cfg, composite_path, panel_mask_path, removal_mask)
        maybe_refine(composite_path, panel_mask_path, cfg, final_path)
        monitor.mark("insertion_done")
        if cfg.get("video", {}).get("enabled", False):
            monitor.mark("video_start")
            render_elevator_video(final_path, detections, geometry, cfg, video_path, depth_path)
            monitor.mark("video_done")
        monitor.mark("pipeline_done")

    print(f"Pipeline complete: {final_path}")
    if cfg.get("video", {}).get("enabled", False):
        print(f"Video output: {video_path}")
    print(f"Run artifacts: {run_dir}")
    print(f"Resource log: {resource_log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect elevator components, clean background, and insert a mod panel.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
