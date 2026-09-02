from __future__ import annotations

import argparse
import copy
import logging
import time
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import cv2
import numpy as np

from .input_validation import merged_validation_config, validate_elevator_presence, validate_input_image
from .inpaint import build_removal_mask, inpaint_background
from .insert_mod import insert_mod_panel, localized_mask_from_preselected_detection, preselect_mod_panel_placement
from .preprocess import run_preprocessing
from .refine import maybe_refine
from .resource_monitor import ResourceMonitor
from .utils import load_config, load_image_rgb, load_json, save_json, save_rgb
from .video_router import render_video
from .visualize import save_detection_visuals


def _save_repin_layer_outputs(
    run_dir: Path,
    component_id: str,
    before_path: Path,
    after_path: Path,
    mask_path: Path,
    placement_debug: dict[str, Any],
) -> dict[str, Any]:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    before = load_image_rgb(before_path)
    after = load_image_rgb(after_path)
    if mask is None or mask.shape[:2] != after.shape[:2]:
        mask = np.any(np.abs(after.astype(np.int16) - before.astype(np.int16)) > 3, axis=2).astype(np.uint8) * 255
    bbox = placement_debug.get("final_insertion_bbox") or placement_debug.get("final_component_placement", {}).get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0 or len(ys) == 0:
            return {}
        bbox = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
    h, w = after.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, min(w - 1, x1)), max(0, min(h - 1, y1))
    x2, y2 = max(x1 + 1, min(w, x2)), max(y1 + 1, min(h, y2))
    crop_rgb = after[y1:y2, x1:x2]
    crop_alpha = mask[y1:y2, x1:x2]
    rgba = np.dstack([crop_rgb, crop_alpha])
    layer_dir = run_dir / "repin" / "layers"
    layer_dir.mkdir(parents=True, exist_ok=True)
    layer_path = layer_dir / f"{component_id}.png"
    cv2.imwrite(str(layer_path), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    return {"editable_layer_path": str(layer_path), "editable_layer_bbox": [x1, y1, x2, y2]}


def _save_repin_background_outputs(run_dir: Path, layer_records: list[dict[str, Any]], final_composite_path: Path) -> None:
    if not layer_records or not final_composite_path.exists():
        return
    final_rgb = load_image_rgb(final_composite_path)
    bg_dir = run_dir / "repin" / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    for record in layer_records:
        component_id = record.get("id")
        mask_path = Path(record.get("mask_path", ""))
        before_path = Path(record.get("before_path", ""))
        if not component_id or not mask_path.exists() or not before_path.exists():
            continue
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        before = load_image_rgb(before_path)
        if mask is None or mask.shape[:2] != final_rgb.shape[:2] or before.shape[:2] != final_rgb.shape[:2]:
            continue
        restore_mask = cv2.dilate((mask > 0).astype(np.uint8) * 255, np.ones((9, 9), np.uint8), iterations=1)
        restored = final_rgb.copy()
        restored[restore_mask > 0] = before[restore_mask > 0]
        background_path = bg_dir / f"{component_id}.png"
        background_web_path = bg_dir / f"{component_id}_web.jpg"
        save_rgb(background_path, restored)
        preview = restored.copy()
        max_side = 1400
        scale = min(1.0, max_side / max(preview.shape[:2]))
        if scale < 1.0:
            preview = cv2.resize(preview, (max(1, int(preview.shape[1] * scale)), max(1, int(preview.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(background_web_path), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 86])
        record["placement_debug"]["repin_background_path"] = str(background_path)
        record["placement_debug"]["repin_background_web_path"] = str(background_web_path)



class PipelineValidationError(RuntimeError):
    pass


KDS_INSTANCE_KEYS: set[str] = {"kds", "kds_2", "kds_3"}
DCS_INSTANCE_KEYS: set[str] = {"dcs1020", "dcs1020_2", "dcs1020_3"}


def semantic_component_key(component: str) -> str:
    normalized = str(component or "").strip().lower()
    if normalized in KDS_INSTANCE_KEYS:
        return "kds"
    if normalized in DCS_INSTANCE_KEYS:
        return "dcs1020"
    return normalized


def _instance_family(instance_id: str) -> str | None:
    normalized = str(instance_id or "").strip().lower()
    if normalized in KDS_INSTANCE_KEYS:
        return "kds"
    if normalized in DCS_INSTANCE_KEYS:
        return "dcs1020"
    return None


def _placement_bbox_from_debug(placement_debug: dict[str, Any], fallback_bbox: list[int] | tuple[int, int, int, int] | None = None) -> list[int] | None:
    candidates: list[Any] = [
        placement_debug.get("final_insertion_bbox"),
        (placement_debug.get("final_component_placement") or {}).get("bbox") if isinstance(placement_debug.get("final_component_placement"), dict) else None,
        placement_debug.get("insert_bbox"),
        placement_debug.get("inpaint_bbox"),
        placement_debug.get("selected_target_bbox"),
        placement_debug.get("selected_replacement_target_bbox"),
        fallback_bbox,
    ]
    for candidate in candidates:
        if isinstance(candidate, (list, tuple)) and len(candidate) == 4:
            try:
                return [int(round(float(value))) for value in candidate]
            except (TypeError, ValueError):
                continue
    return None


COMPONENT_REPLACEMENT_PRESETS: dict[str, dict[str, Any]] = {
    "cop": {
        "id": "cop",
        "asset": "tests/panels/mod_long.png",
        "component_type": "elevator_mod_panel",
        "target_keywords": [
            "car operating panel",
            "tall stainless steel elevator operating panel with round buttons",
        ],
        "detection_labels": [
            "tall stainless steel elevator operating panel with round buttons",
            "floor_indicator_display",
            "wheelchair button",
            "accessibility control panel",
            "emergency_phone",
        ],
    },
    "lci": {
        "id": "lci",
        "asset": "tests/panels/mod_up.png",
        "component_type": "landing_call_indicator",
        "target_keywords": [
            "elevator button panel",
            "elevator call button panel",
            "elevator call button",
            "call button",
        ],
        "detection_labels": ["elevator_button_panel", "elevator call button panel", "elevator_door"],
    },
    "kds": {
        "id": "kds",
        "asset": "tests/panels/mod_up.png",
        "component_type": "landing_call_indicator",
        "target_keywords": [
            "elevator button panel",
            "elevator call button panel",
            "elevator call button",
            "call button",
        ],
        "detection_labels": ["elevator_button_panel", "elevator call button panel", "elevator_door"],
    },
    "dcs1020": {
        "id": "dcs1020",
        "asset": "tests/panels/mod_up.png",
        "component_type": "destination_guidance_indicator",
        "target_keywords": [
            "floor indicator display",
            "destination operating panel",
            "destination guidance panel",
            "elevator header sign",
            "above elevator door",
        ],
        "detection_labels": ["floor_indicator_display", "floor indicator display", "elevator_door"],
    },
    "door": {
        "id": "door",
        "asset": "tests/panels/door_mod.png",
        "component_type": "elevator_door",
        "target_keywords": ["elevator door", "elevator doors", "elevator_door"],
        "detection_labels": ["elevator_door"],
    },
    "ceiling": {
        "id": "ceiling",
        "asset": "__generated_ceiling_panel__",
        "component_type": "elevator_cabin",
        "target_keywords": ["elevator interior", "elevator cabin", "inside elevator", "elevator_cabin"],
        "detection_labels": ["elevator interior", "elevator cabin", "inside elevator", "elevator_door", "elevator_cabin"],
    },
}


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
    replacements = replacement_configs(cfg)
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
                raise PipelineValidationError(f"Image is not valid: {message}")
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
                for stale in (
                    geometry_path,
                    depth_path,
                    removal_mask_path,
                    cleaned_path,
                    final_path,
                    video_path,
                    video_path.with_suffix(".json"),
                    run_dir / "component_placements.json",
                    run_dir / "component_placement_debug.json",
                ):
                    stale.unlink(missing_ok=True)
                for pattern in ("composite*.png", "harmonization_mask*.png"):
                    for stale in run_dir.glob(pattern):
                        stale.unlink(missing_ok=True)
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
                raise PipelineValidationError(f"Image is not valid: {elevator_presence['reason']}")
            status(
                "elevator_presence_passed",
                f"[VALIDATION] Elevator presence validation: PASS components={len(elevator_presence['matched_elevator_components'])}",
            )

        if cfg["geometry"].get("enabled", True):
            from .geometry import run_geometry

            monitor.mark("geometry_start")
            geometry_start = time.perf_counter()
            print("[PERF][GEOMETRY] start pass=render", flush=True)
            geometry = run_geometry(working_image, detections, cfg, geometry_path, depth_path)
            print(
                f"[PERF][GEOMETRY] done pass=render duration_s={time.perf_counter() - geometry_start:.3f}",
                flush=True,
            )
            monitor.mark("geometry_done")
        elif geometry_path.exists():
            geometry = load_json(geometry_path)
        else:
            geometry = {"wall_plane": {"normal": [0, 0, 1]}, "homography": {"matrix_3x3": None}}

        original = load_image_rgb(working_image)
        save_detection_visuals(working_image, detections, run_dir)
        monitor.mark("inpaint_start")
        component_cfgs: list[dict[str, Any]] = []
        removal_mask = None
        for replacement in replacements:
            component_cfg = component_config(cfg, replacement)
            component_cfgs.append(component_cfg)
            mod_path = Path(replacement["asset"])
            preselected_bbox = preselect_mod_panel_placement(original, mod_path, detections, component_cfg)
            if preselected_bbox is not None:
                pad = int(component_cfg.get("removal", {}).get("box_mask_padding_px", 2))
                component_mask = localized_mask_from_preselected_detection(original.shape, detections, component_cfg, preselected_bbox, pad=pad)
            else:
                component_mask = build_removal_mask(original, detections, component_cfg)
            removal_mask = component_mask if removal_mask is None else cv2.max(removal_mask, component_mask)
        if removal_mask is None:
            raise RuntimeError("No configured components were available for replacement")
        status("inpaint", f"[INPAINT] Running inpainting for {len(replacements)} component(s)")
        cv2.imwrite(str(removal_mask_path), removal_mask)
        cleaned_override = cfg["inpainting"].get("cleaned_background")
        if cleaned_override:
            save_rgb(cleaned_path, load_image_rgb(cleaned_override))
        else:
            inpaint_background(working_image, removal_mask, cfg, cleaned_path)
        monitor.mark("inpaint_done")
        shared_background_path = run_dir / "repin" / "backgrounds" / "shared_background.png"
        shared_background_path.parent.mkdir(parents=True, exist_ok=True)
        save_rgb(shared_background_path, load_image_rgb(cleaned_path))
        monitor.mark("insertion_start")
        current_background = cleaned_path
        combined_panel_mask = None
        component_placements: list[dict[str, Any]] = []
        repin_layer_records: list[dict[str, Any]] = []
        insertion_all_start = time.perf_counter()
        for index, (replacement, component_cfg) in enumerate(zip(replacements, component_cfgs), start=1):
            replacement_id = replacement["id"]
            semantic_key = str(replacement.get("component_key") or replacement_id)
            component_out = composite_path if index == len(replacements) else run_dir / f"composite_{replacement_id}.png"
            component_mask_path = run_dir / f"harmonization_mask_{replacement_id}.png"
            before_component_path = Path(current_background)
            status("place", f"[PLACE] Placing component: {replacement_id}")
            insert_start = time.perf_counter()
            print(f"[PERF][INSERT] start id={replacement_id} semantic={semantic_key}", flush=True)
            insert_mod_panel(
                current_background,
                Path(replacement["asset"]),
                detections,
                geometry,
                component_cfg,
                component_out,
                component_mask_path,
                removal_mask,
            )
            print(
                f"[PERF][INSERT] done id={replacement_id} duration_s={time.perf_counter() - insert_start:.3f}",
                flush=True,
            )
            mask = cv2.imread(str(component_mask_path), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                combined_panel_mask = mask if combined_panel_mask is None else cv2.max(combined_panel_mask, mask)
            placement_debug = _load_optional_json(run_dir / "component_placement_debug.json")
            placement_debug["id"] = replacement_id
            placement_debug["asset"] = replacement["asset"]
            layer_info = _save_repin_layer_outputs(
                run_dir,
                replacement_id,
                before_component_path,
                component_out,
                component_mask_path,
                placement_debug,
            )
            placement_debug.update(layer_info)
            component_placements.append(placement_debug)
            repin_layer_records.append({
                "id": replacement_id,
                "before_path": str(before_component_path),
                "mask_path": str(component_mask_path),
                "placement_debug": placement_debug,
            })
            current_background = component_out
        print(
            f"[PERF][INSERT] all_done count={len(replacements)} duration_s={time.perf_counter() - insertion_all_start:.3f}",
            flush=True,
        )
        _save_repin_background_outputs(run_dir, repin_layer_records, composite_path)
        if combined_panel_mask is not None:
            cv2.imwrite(str(panel_mask_path), combined_panel_mask)
        save_json(run_dir / "component_placements.json", component_placements)
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
                if cfg.get("video", {}).get("engine") == "wan2.2":
                    cfg["video"] = _wan22_video_config()
                render_video(final_path, detections, geometry, cfg, video_path, depth_path)
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


def replacement_configs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    configured = cfg.get("replacements")
    if not configured:
        selected = [
            str(component).strip().lower()
            for component in cfg.get("selected_components", [])
            if str(component).strip()
        ]
        replacements: list[dict[str, Any]] = []
        missing_components: list[str] = []
        selected_ids = set(selected)
        component_instances = []
        instance_by_id: dict[str, dict[str, Any]] = {}
        kds_instances: list[dict[str, Any]] = []
        dcs_instances: list[dict[str, Any]] = []

        for item in cfg.get("component_instances") or []:
            if not isinstance(item, dict):
                continue
            instance_id = str(item.get("id") or "").strip().lower()
            if selected_ids and instance_id not in selected_ids:
                continue
            component = semantic_component_key(str(item.get("componentType") or item.get("component_type") or "kds"))
            expected_component = _instance_family(instance_id)
            if expected_component is None and instance_id:
                raise ValueError(f"Unsupported component instance: {instance_id}")
            if expected_component and expected_component != component:
                raise ValueError(f"Component instance {instance_id} must use componentType {expected_component}")
            component_instances.append(item)
            if instance_id:
                instance_by_id[instance_id] = item
            if expected_component == "kds":
                kds_instances.append(item)
            elif expected_component == "dcs1020":
                dcs_instances.append(item)

        if selected:
            kds_keys = [component for component in selected if component in KDS_INSTANCE_KEYS]
            dcs_keys = [component for component in selected if component in DCS_INSTANCE_KEYS]
            unsupported_equipment = [
                component for component in selected
                if component.startswith("kds_") or component.startswith("dcs1020_")
                if component not in KDS_INSTANCE_KEYS and component not in DCS_INSTANCE_KEYS
            ]
            if unsupported_equipment:
                raise ValueError(f"Unsupported selected component(s): {', '.join(unsupported_equipment)}")
        else:
            kds_keys = [str(item.get("id") or "").strip().lower() for item in kds_instances]
            dcs_keys = [str(item.get("id") or "").strip().lower() for item in dcs_instances]

        if len(kds_keys) > 3 or len(dcs_keys) > 3 or len(kds_keys) + len(dcs_keys) > 4:
            raise ValueError("A maximum of 3 KDS, 3 DCS, and 4 total KDS/DCS instances may be selected")

        for family_name, family_instances in (("KDS", kds_instances), ("DCS", dcs_instances)):
            family_variants = [str(item.get("variantId") or item.get("variant_id") or "").strip() for item in family_instances]
            if len(set(family_variants)) != len(family_variants):
                raise ValueError(f"The same {family_name} variant cannot be selected more than once")

        if selected:
            replacement_sources = []
            for component in selected:
                semantic_component = semantic_component_key(component)
                instance = instance_by_id.get(component)
                if instance is None and component != semantic_component:
                    instance = {"id": component, "componentType": semantic_component}
                replacement_sources.append((component, semantic_component, instance))
        else:
            replacement_sources = []
            for instance in component_instances:
                instance_id = str(instance.get("id") or "").strip().lower()
                semantic_component = semantic_component_key(str(instance.get("componentType") or instance.get("component_type") or "kds"))
                replacement_sources.append((instance_id or semantic_component, semantic_component, instance))

        for component, semantic_component, instance in replacement_sources:
            replacement = _component_replacement(semantic_component, cfg, instance)
            if replacement is None:
                missing_components.append(component)
            else:
                replacements.append(replacement)
        if missing_components:
            raise ValueError(f"Unsupported selected component(s): {', '.join(missing_components)}")
        if replacements:
            _extend_detection_labels(cfg, replacements)
            return replacements
        return [{"id": "mod_panel", "asset": str(cfg["mod_panel"])}]
    replacements: list[dict[str, Any]] = []
    for index, item in enumerate(configured, start=1):
        if not isinstance(item, dict) or not item.get("asset"):
            raise ValueError(f"Replacement #{index} must define an asset")
        replacement = dict(item)
        replacement["id"] = str(replacement.get("id") or f"component_{index}")
        replacements.append(replacement)
    _extend_detection_labels(cfg, replacements)
    return replacements


def _component_replacement(component: str, cfg: dict[str, Any], instance: dict[str, Any] | None = None) -> dict[str, Any] | None:
    preset = COMPONENT_REPLACEMENT_PRESETS.get(component)
    if preset is None:
        return None
    replacement = {key: value for key, value in preset.items() if key != "detection_labels"}
    replacement["component_key"] = component
    if instance:
        replacement["id"] = str(instance.get("id") or replacement["id"])
    instance_id = str((instance or {}).get("id") or "").strip().lower()
    exact_asset = (cfg.get("component_assets") or {}).get(replacement["id"]) or (instance or {}).get("assetUrl") or (instance or {}).get("asset_url")
    if instance_id in {"dcs1020_2", "dcs1020_3"} and not exact_asset:
        return None
    asset_override = exact_asset or (cfg.get("component_assets") or {}).get(component)
    if asset_override:
        replacement["asset"] = str(asset_override)
    elif component == "ceiling":
        replacement["asset"] = str(_ensure_generated_ceiling_asset(cfg))
    return replacement


def _ensure_generated_ceiling_asset(cfg: dict[str, Any]) -> Path:
    asset_path = Path(cfg["run_dir"]) / "generated_assets" / "ceiling_mod.png"
    if asset_path.exists():
        return asset_path

    asset_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = 180, 640
    panel = np.full((height, width, 3), 218, dtype=np.uint8)
    for y in range(0, height, 36):
        cv2.line(panel, (0, y), (width, y), (190, 190, 190), 1)
    for x in range(0, width, 80):
        cv2.line(panel, (x, 0), (x, height), (202, 202, 202), 1)
    cv2.rectangle(panel, (0, 0), (width - 1, height - 1), (168, 168, 168), 3)
    cv2.imwrite(str(asset_path), panel)
    return asset_path


def _extend_detection_labels(cfg: dict[str, Any], replacements: list[dict[str, Any]]) -> None:
    detection_cfg = cfg.setdefault("detection", {})
    labels = list(detection_cfg.get("labels") or [])
    for replacement in replacements:
        component_key = str(replacement.get("component_key") or replacement.get("id", "")).lower()
        preset = COMPONENT_REPLACEMENT_PRESETS.get(component_key)
        labels.extend(replacement.get("target_keywords", []))
        if preset:
            labels.extend(preset.get("detection_labels", []))
    detection_cfg["labels"] = list(dict.fromkeys(label for label in labels if label))


def component_config(cfg: dict[str, Any], replacement: dict[str, Any]) -> dict[str, Any]:
    component_cfg = copy.deepcopy(cfg)
    component_cfg.pop("replacements", None)
    component_cfg["mod_panel"] = replacement["asset"]
    component_cfg["removal"].update(replacement.get("removal", {}))
    component_cfg["insertion"].update(replacement.get("insertion", {}))
    if replacement.get("target_keywords"):
        keywords = list(replacement["target_keywords"])
        component_cfg["removal"]["target_keywords"] = keywords
        component_cfg["insertion"]["target_keywords"] = keywords
    if "manual_box_xyxy" in replacement:
        component_cfg["insertion"]["manual_box_xyxy"] = replacement["manual_box_xyxy"]
    if replacement.get("component_type"):
        component_cfg["_requested_component_type"] = replacement["component_type"]
    component_cfg["_replacement_id"] = replacement["id"]
    return component_cfg


def discover_placements(config_path: str | Path) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config(config_path)
    run_dir = Path(cfg["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)

    input_image = Path(cfg["input_image"])
    replacements = replacement_configs(cfg)
    preprocessed_path = run_dir / "preprocessed_input.png"
    preprocessing_path = run_dir / "preprocessing.json"
    detections_path = run_dir / "elevator_detections.json"
    geometry_path = run_dir / "geometry.json"
    depth_path = run_dir / "depth_map.npz"

    if cfg.get("preprocessing", {}).get("enabled", True):
        working_image = run_preprocessing(input_image, cfg, preprocessed_path, preprocessing_path)
    else:
        working_image = input_image

    existing_detections = cfg["detection"].get("existing_json")
    if existing_detections:
        detections = load_json(existing_detections)
        detections_path.write_text(Path(existing_detections).read_text(encoding="utf-8"), encoding="utf-8")
    elif cfg["detection"].get("enabled", True):
        from .detect import add_sam2_masks, run_detection

        detections = run_detection(working_image, cfg, detections_path)
        detections = add_sam2_masks(working_image, cfg, detections, detections_path)
    elif detections_path.exists():
        detections = load_json(detections_path)
    else:
        raise FileNotFoundError(f"Detection disabled but {detections_path} does not exist")

    if cfg["geometry"].get("enabled", True):
        from .geometry import run_geometry

        geometry_start = time.perf_counter()
        print("[PERF][GEOMETRY] start pass=discovery", flush=True)
        geometry = run_geometry(working_image, detections, cfg, geometry_path, depth_path)
        print(
            f"[PERF][GEOMETRY] done pass=discovery duration_s={time.perf_counter() - geometry_start:.3f}",
            flush=True,
        )
    elif geometry_path.exists():
        geometry = load_json(geometry_path)
    else:
        geometry = {"wall_plane": {"normal": [0, 0, 1]}, "homography": {"matrix_3x3": None}}

    original = load_image_rgb(working_image)
    placements: list[dict[str, Any]] = []
    seen_semantic_components: set[str] = set()
    for replacement in replacements:
        semantic_key = semantic_component_key(str(replacement.get("component_key") or replacement.get("id") or ""))
        if not semantic_key or semantic_key in seen_semantic_components:
            continue
        seen_semantic_components.add(semantic_key)
        component_cfg = component_config(cfg, replacement)
        bbox = preselect_mod_panel_placement(original, Path(replacement["asset"]), detections, component_cfg)
        placement_debug = dict(component_cfg.get("_placement_debug") or {})
        placements.append({
            "id": semantic_key,
            "component_key": semantic_key,
            "component_type": replacement.get("component_type"),
            "asset": replacement.get("asset"),
            "bbox": _placement_bbox_from_debug(placement_debug, bbox),
            "placement_debug": placement_debug,
        })

    return {
        "placements": placements,
        "detections": detections,
        "geometry": geometry,
        "working_image": str(working_image),
    }


def _wan22_video_config() -> dict[str, Any]:
    return {
        "engine": "wan2.2",
        "mode": "motion",
        "motion_style": "pan",
        "fps": 16,
        "duration_seconds": 5,
        "wan": {
            "enabled": True,
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
        },
    }


def write_pipeline_manifest(path: Path, detections: dict, run_dir: Path, status_entries: list[dict[str, str]]) -> None:
    input_validation = _load_optional_json(run_dir / "input_validation.json")
    elevator_presence_validation = _load_optional_json(run_dir / "elevator_presence_validation.json")
    roi_debug = _load_optional_json(run_dir / "elevator_roi_debug.json")
    placement_debug = _load_optional_json(run_dir / "component_placement_debug.json")
    component_placements = _load_optional_list(run_dir / "component_placements.json")
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
        "component_placements": component_placements,
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


def _load_optional_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = load_json(path)
        return data if isinstance(data, list) else []
    except Exception:
        return []


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
        str(det.get("normalized_component_type") or "").lower()
        in {
            "tall stainless steel elevator operating panel with round buttons",
            "elevator call button panel",
            "wheelchair button",
            "accessibility_control_panel",
        }
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
        source = str(det.get("source", "")).lower()
        min_score = 0.22 if source in {"closed_door_header_recovery", "groundingdino_open_door_entrance_repair"} else 0.28
        if score < min_score:
            continue
        x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
        bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
        area_ratio = (bw * bh) / max(width * height, 1)
        aspect = bh / bw
        if norm == "elevator_door" and 0.05 <= area_ratio <= 0.65 and aspect >= 0.85:
            return True
        if norm == "elevator_cabin" and 0.08 <= area_ratio <= 0.65 and aspect >= 0.85:
            return True
        if norm == "elevator_cabin" and area_ratio > 0.65 and aspect >= 1.05 and not has_valid_panel_target:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect elevator components, clean background, and insert a mod panel.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()
    try:
        run(args.config)
    except PipelineValidationError as exc:
        print(f"[VALIDATION] {exc}")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
