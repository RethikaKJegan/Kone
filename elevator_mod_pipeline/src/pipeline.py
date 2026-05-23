from __future__ import annotations

import argparse
import logging
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import cv2

from .input_validation import merged_validation_config, validate_elevator_presence, validate_input_image
from .inpaint import build_removal_mask, inpaint_background
from .insert_mod import insert_mod_panel, localized_mask_from_bbox, preselect_mod_panel_placement
from .preprocess import run_preprocessing
from .refine import maybe_refine
from .resource_monitor import ResourceMonitor
from .utils import load_config, load_image_rgb, load_json, save_json, save_rgb
from .video import render_elevator_video
from .visualize import save_detection_visuals


def run(config_path: str | Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)
    status_entries: list[dict[str, str]] = []

    def status(step: str, message: str) -> None:
        logger.info(message)
        status_entries.append({"step": step, "message": message})

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
    manifest_path = run_dir / "pipeline_manifest.json"
    input_validation_path = run_dir / "input_validation.json"
    elevator_presence_path = run_dir / "elevator_presence_validation.json"

    with ResourceMonitor(resource_log_path, float(cfg.get("monitoring", {}).get("interval_s", 1.0))) as monitor:
        monitor.mark("pipeline_start")
        status("load", f"[LOAD] Loading input image: {input_image}")
        validation_cfg = merged_validation_config(cfg)
        if validation_cfg.get("enabled", True):
            monitor.mark("input_validation_start")
            status("validation", "[VALIDATION] Checking input image quality and perspective")
            input_validation = validate_input_image(load_image_rgb(input_image), cfg)
            save_json(input_validation_path, input_validation)
            status(
                "validation_result",
                f"[VALIDATION] Input image validation: {input_validation['result']} score={input_validation['final_score']}",
            )
            if input_validation["result"] == "FAIL" and validation_cfg.get("fail_on_invalid", True):
                message = validation_failure_message(input_validation)
                status("validation_failed", f"[VALIDATION] Image is not valid: {message}")
                save_json(
                    manifest_path,
                    {
                        "pipeline_status": "failed_input_validation",
                        "input_validation": input_validation,
                        "pipeline_steps": status_entries,
                    },
                )
                raise RuntimeError(f"Image is not valid: {message}")
            monitor.mark("input_validation_done")
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
            status("model", "[MODEL] Loading GroundingDINO detector")
            status("detect_elevator", "[DETECT] Running elevator detection")
            status("detect_components", "[DETECT] Running component detection")
            status("normalize", "[NORMALIZE] Mapping raw labels to normalized component types")
            detections = run_detection(working_image, cfg, detections_path)
            monitor.mark("sam2_start")
            detections = add_sam2_masks(working_image, cfg, detections, detections_path)
            monitor.mark("detection_done")
        elif detections_path.exists():
            detections = load_json(detections_path)
        else:
            raise FileNotFoundError(f"Detection disabled but {detections_path} does not exist")

        if validation_cfg.get("enabled", True) and validation_cfg.get("require_elevator", True):
            status("elevator_presence", "[VALIDATION] Checking elevator presence")
            elevator_presence = validate_elevator_presence(detections, cfg)
            save_json(elevator_presence_path, elevator_presence)
            if not elevator_presence["valid"]:
                status("elevator_presence_failed", f"[VALIDATION] Image is not valid: {elevator_presence['reason']}")
                save_json(
                    manifest_path,
                    {
                        "pipeline_status": "failed_elevator_presence_validation",
                        "input_validation": _load_optional_json(input_validation_path),
                        "elevator_presence_validation": elevator_presence,
                        "pipeline_steps": status_entries,
                    },
                )
                raise RuntimeError(f"Image is not valid: {elevator_presence['reason']}")
            status(
                "elevator_presence_passed",
                f"[VALIDATION] Elevator presence validation: PASS components={len(elevator_presence['matched_elevator_components'])}",
            )

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
        preselected_bbox = preselect_mod_panel_placement(original, mod_panel, detections, cfg)
        if preselected_bbox is not None:
            pad = int(cfg.get("removal", {}).get("box_mask_padding_px", 2))
            removal_mask = localized_mask_from_bbox(original.shape, preselected_bbox, pad=pad)
            status("inpaint", f"[INPAINT] Running inpaint.py on bbox={preselected_bbox}")
        else:
            status("inpaint", "[INPAINT] Running inpainting")
            removal_mask = build_removal_mask(original, detections, cfg)
        cv2.imwrite(str(removal_mask_path), removal_mask)
        cleaned_override = cfg["inpainting"].get("cleaned_background")
        if cleaned_override:
            save_rgb(cleaned_path, load_image_rgb(cleaned_override))
        else:
            inpaint_background(working_image, removal_mask, cfg, cleaned_path)
        monitor.mark("inpaint_done")
        monitor.mark("insertion_start")
        status("place", "[PLACE] Placing elevator_mod_panel")
        insert_mod_panel(cleaned_path, mod_panel, detections, geometry, cfg, composite_path, panel_mask_path, removal_mask)
        maybe_refine(composite_path, panel_mask_path, cfg, final_path)
        monitor.mark("insertion_done")
        if cfg.get("video", {}).get("enabled", False):
            monitor.mark("video_start")
            status("roi", "[ROI] Scoring elevator candidates")
            status("state", "[STATE] Detecting open/closed elevator state")
            status("animation", "[ANIMATION] Choosing animation mode")
            motion_style_requested = cfg.get("video", {}).get("motion_style") is not None
            if not motion_style_requested and not elevator_present_for_video(detections):
                for stale in (video_path, video_path.with_suffix(".json"), run_dir / "elevator_state_debug.json", run_dir / "elevator_roi_debug.json"):
                    stale.unlink(missing_ok=True)
                video_debug = {
                    "elevator_present": False,
                    "selected_elevator_roi": None,
                    "video_generated": False,
                    "video_skipped_reason": "no elevator door detected",
                }
                save_json(run_dir / "video_skip_debug.json", video_debug)
                status("video_skip", "[VIDEO] Skipping video generation: no elevator door detected")
            else:
                render_elevator_video(final_path, detections, geometry, cfg, video_path, depth_path)
                video_debug = _load_optional_json(video_path.with_suffix(".json"))
                video_debug["elevator_present"] = True
                video_debug["video_generated"] = True
            if video_debug.get("elevator_state"):
                status("state_result", f"[STATE] Elevator state detected: {video_debug.get('elevator_state')}")
            if video_debug.get("elevator_state") == "open" and video_debug.get("animation_mode") == "open_close_open_from_existing_interior":
                status("open_state_source", "[ANIMATION] Final image already contains open elevator; using final image as open state")
                status("open_reference_disabled", "[ANIMATION] Open reference image disabled for open-state final image")
                status("closed_state_source", "[ANIMATION] Building closed-door state from closed_reference_image")
                status("open_close_open", "[ANIMATION] Rendering open \u2192 close \u2192 open sequence")
            if video_debug.get("animation_mode"):
                status("animation_result", f"[ANIMATION] Animation mode: {video_debug.get('animation_mode')}")
            if video_debug.get("video_validation_status"):
                status(
                    "video_validation",
                    f"[VIDEO] Validation {video_debug.get('video_validation_status')}: fps={video_debug.get('fps')} "
                    f"frames={video_debug.get('frame_count')} duration={video_debug.get('duration_seconds')}",
                )
            monitor.mark("video_done")
        status("debug", "[DEBUG] Writing candidate score visualization")
        status("manifest", f"[MANIFEST] Writing manifest: {manifest_path}")
        write_pipeline_manifest(manifest_path, detections, run_dir, status_entries)
        status("save", f"[SAVE] Final output saved: {final_path}")
        monitor.mark("pipeline_done")

    print(f"Pipeline complete: {final_path}")
    if cfg.get("video", {}).get("enabled", False) and video_path.exists():
        print(f"Video output: {video_path}")
    print(f"Run artifacts: {run_dir}")
    print(f"Resource log: {resource_log_path}")


def write_pipeline_manifest(path: Path, detections: dict, run_dir: Path, status_entries: list[dict[str, str]]) -> None:
    input_validation = _load_optional_json(run_dir / "input_validation.json")
    elevator_presence_validation = _load_optional_json(run_dir / "elevator_presence_validation.json")
    roi_debug = _load_optional_json(run_dir / "elevator_roi_debug.json")
    placement_debug = _load_optional_json(run_dir / "component_placement_debug.json")
    video_debug = _load_optional_json(run_dir / "elevator_animation.json")
    video_skip_debug = _load_optional_json(run_dir / "video_skip_debug.json")
    if video_skip_debug:
        video_debug = {}
    state_debug = _load_optional_json(run_dir / "elevator_state_debug.json")
    video_generated = bool(video_debug.get("video_path") or video_debug.get("output_video")) and not video_skip_debug
    payload = {
        "selected_elevator_roi": None
        if video_skip_debug.get("selected_elevator_roi") is None and video_skip_debug
        else roi_debug.get("selected_elevator_roi") or video_debug.get("door_box_xyxy"),
        "rejected_elevator_candidates": roi_debug.get("rejected_candidates", []),
        "candidate_scores": roi_debug.get("candidate_scores", []),
        "candidate_rejection_reasons": roi_debug.get("candidate_rejection_reasons", []),
        "nested_frame_depth_evidence": roi_debug.get("nested_frame_depth_evidence", {}),
        "input_validation": input_validation,
        "input_validation_status": input_validation.get("result"),
        "input_validation_score": input_validation.get("final_score"),
        "elevator_presence_validation": elevator_presence_validation,
        "elevator_presence_validation_status": elevator_presence_validation.get("result"),
        "elevator_state": video_debug.get("elevator_state") or video_debug.get("detected_initial_state") or state_debug.get("elevator_state", "unknown"),
        "elevator_state_evidence": state_debug.get("elevator_state_evidence", {}),
        "animation_mode": video_debug.get("animation_mode") or state_debug.get("animation_mode"),
        "requested_video_mode": video_debug.get("requested_video_mode"),
        "requested_motion_style": video_debug.get("requested_motion_style"),
        "requested_door_functionality": video_debug.get("requested_door_functionality"),
        "normalized_video_mode": video_debug.get("normalized_video_mode"),
        "video_mode_conflict_resolution": video_debug.get("video_mode_conflict_resolution"),
        "skipped_animation_reason": video_debug.get("skipped_animation_reason") or state_debug.get("skipped_animation_reason"),
        "skipped_or_alternate_animation_reason": video_debug.get("skipped_or_alternate_animation_reason")
        or state_debug.get("skipped_or_alternate_animation_reason"),
        "elevator_present": video_skip_debug.get("elevator_present", bool(video_debug.get("door_box_xyxy") or roi_debug.get("selected_elevator_roi"))),
        "video_generated": video_skip_debug.get("video_generated", video_generated),
        "video_skipped_reason": video_skip_debug.get("video_skipped_reason"),
        "video_path": None if video_skip_debug else video_debug.get("video_path") or video_debug.get("output_video"),
        "fps": None if video_skip_debug else video_debug.get("fps"),
        "frame_count": None if video_skip_debug else video_debug.get("frame_count"),
        "duration_seconds": None if video_skip_debug else video_debug.get("duration_seconds"),
        "quality": None if video_skip_debug else video_debug.get("quality"),
        "video_validation_status": None if video_skip_debug else video_debug.get("video_validation_status"),
        "video_source": video_debug.get("video_source"),
        "video_renderer": video_debug.get("video_renderer"),
        "door_animation_used": video_debug.get("door_animation_used"),
        "camera_motion_used": video_debug.get("camera_motion_used"),
        "pan_axis": video_debug.get("pan_axis"),
        "pan_direction": video_debug.get("pan_direction"),
        "open_reference_image_used": video_debug.get("open_reference_image_used"),
        "closed_reference_image_used": video_debug.get("closed_reference_image_used"),
        "focus_point_source": video_debug.get("focus_point_source"),
        "open_state_source": video_debug.get("open_state_source") or (video_debug.get("source_policy") or {}).get("open_state_image"),
        "closed_state_source": video_debug.get("closed_state_source") or (video_debug.get("source_policy") or {}).get("closed_state_image"),
        "used_open_reference_image": video_debug.get("used_open_reference_image"),
        "used_closed_reference_image": video_debug.get("used_closed_reference_image"),
        "requested_component_type": placement_debug.get("requested_component_type"),
        "valid_replacement_targets": placement_debug.get("valid_replacement_targets", []),
        "rejected_replacement_targets": placement_debug.get("rejected_replacement_targets", []),
        "selected_replacement_target_type": placement_debug.get("selected_replacement_target_type"),
        "selected_replacement_target_bbox": placement_debug.get("selected_replacement_target_bbox"),
        "inpaint_bbox": placement_debug.get("inpaint_bbox"),
        "inpaint_completed": placement_debug.get("inpaint_completed"),
        "final_insertion_bbox": placement_debug.get("final_insertion_bbox"),
        "insertion_scale_factor": placement_debug.get("insertion_scale_factor"),
        "insertion_size_validation_status": placement_debug.get("insertion_size_validation_status"),
        "harmonization_mask_bbox": placement_debug.get("harmonization_mask_bbox"),
        "harmonization_mask_white_area_ratio": placement_debug.get("harmonization_mask_white_area_ratio"),
        "harmonization_mask_validation_status": placement_debug.get("harmonization_mask_validation_status"),
        "mask_rebuilt_reason": placement_debug.get("mask_rebuilt_reason"),
        "component_detections": [
            {
                "bbox": det.get("box_xyxy"),
                "normalized_component_type": det.get("normalized_component_type"),
                "raw_detection_label": det.get("raw_detection_label", det.get("phrase")),
                "source_prompt": det.get("source_prompt", det.get("phrase")),
                "score": det.get("score"),
            }
            for det in detections.get("detections", [])
        ],
        "rejected_component_detections": placement_debug.get("rejected_component_detections", []),
        "final_component_placement": placement_debug.get("final_component_placement"),
        "pipeline_steps": status_entries,
    }
    save_json(path, payload)


def _load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = load_json(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def validation_failure_message(validation: dict) -> str:
    reasons = validation.get("reasons", {})
    hard_fail = reasons.get("hard_fail") or []
    suggestions = reasons.get("suggestions") or []
    parts = [str(item) for item in hard_fail[:3]]
    if suggestions:
        parts.append(f"Suggestion: {suggestions[0]}")
    return " ".join(parts) if parts else f"validation result={validation.get('result')}"


def elevator_present_for_video(detections: dict) -> bool:
    meta = detections.get("metadata", {})
    width = int(meta.get("image_width", 0) or 0)
    height = int(meta.get("image_height", 0) or 0)
    if width <= 0 or height <= 0:
        return False
    has_valid_panel_target = any(
        str(det.get("normalized_component_type") or "").lower() in {"accessibility_control_panel", "elevator_button_panel"}
        and float(det.get("score", 0.0)) >= 0.25
        for det in detections.get("detections", [])
    )
    for det in detections.get("detections", []):
        norm = str(det.get("normalized_component_type") or "").lower()
        if norm not in {"elevator_door", "elevator_cabin"}:
            continue
        if det.get("source") == "image_structure_fallback":
            continue
        score = float(det.get("score", 0.0))
        if score < 0.28:
            continue
        x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
        bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
        area_ratio = (bw * bh) / max(width * height, 1)
        aspect = bh / bw
        if norm == "elevator_door" and 0.03 <= area_ratio <= 0.65 and aspect >= 1.05:
            return True
        if norm == "elevator_cabin" and 0.08 <= area_ratio <= 0.65 and aspect >= 1.05:
            return True
        if norm == "elevator_cabin" and area_ratio > 0.65 and aspect >= 1.05 and not has_valid_panel_target:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect elevator components, clean background, and insert a mod panel.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
