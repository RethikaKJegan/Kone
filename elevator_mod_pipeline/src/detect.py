from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageOps


def _find_repo_root() -> Path:
	here = Path(__file__).resolve()
	for parent in (here.parent, *here.parents):
		if (parent / "main2.py").exists():
			return parent
	raise FileNotFoundError("Could not find main2.py from detect.py location")


ROOT = _find_repo_root()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN2_PATH = ROOT / "main2.py"

_MAIN2: Any | None = None
_GDINO_CACHE: dict[str, Any] = {}
_SAM2_CACHE: dict[str, Any] = {}
LOGGER = logging.getLogger(__name__)
OPERATING_PANEL_CLASS = "tall stainless steel elevator operating panel with round buttons"

NORMALIZED_COMPONENT_PROMPTS: dict[str, list[str]] = {
	OPERATING_PANEL_CLASS: [OPERATING_PANEL_CLASS],
	"elevator call button panel": ["elevator call button panel"],
	"wheelchair button": ["wheelchair button"],
	"wheelchair_indicator": ["wheelchair indicator", "accessibility indicator"],
	"floor_indicator_display": [
    "floor indicator display",
    "elevator floor indicator",
    "elevator display",
    "landing floor indicator",
    "hall position indicator",
    "elevator level indicator",
    "floor number display",
    "floor number sign",
],
	"weight_limit_sign": ["weight limit sign", "elevator capacity sign", "capacity sign"],
	"accessibility_control_panel": ["accessibility control panel"],
	"elevator_door": ["elevator door", "elevator doors"],
	"elevator_ceiling": ["elevator ceiling", "ceiling light", "lift ceiling", "ceiling panel"],
	"elevator_cabin": ["elevator cabin", "elevator interior", "inside elevator"],
	"threshold_plate": ["elevator threshold plate", "door sill", "metal threshold plate"],
	"handrail": ["elevator handrail", "handrail"],
	"security_camera": ["security camera", "surveillance camera"],
	"emergency_phone": ["emergency phone", "elevator emergency phone", "intercom phone", "emergency call phone"],
}
NORMALIZED_COMPONENT_TYPES = set(NORMALIZED_COMPONENT_PROMPTS)
CANONICAL_COMPONENT_LABELS = {
	"elevator interior",
	"elevator door",
	"car operating panel",
	
	OPERATING_PANEL_CLASS,
	"elevator call button panel",
	"wheelchair button",
	"wheelchair indicator",
	"accessibility control panel",
	"security camera",
	"floor indicator",
	"elevator display",
	"handrail",
	"emergency phone",
	"elevator floor",
	"elevator wall",
	"door frame",
}


def run_detection(image_path: str | Path, cfg: dict[str, Any], out_json: str | Path) -> dict[str, Any]:
	main2 = _load_main2()
	LOGGER.info("[LOAD] Loading input image: %s", image_path)
	image_np, image_tensor = main2.load_rgb_image(_resolve_path(image_path))
	height, width = image_np.shape[:2]

	labels = cfg.get("detection", {}).get("labels") or list(NORMALIZED_COMPONENT_PROMPTS)
	prompt = _labels_to_prompt(labels)
	detection_caption = prompt
	device = main2.select_device(cfg.get("detection", {}).get("device", "auto"))
	LOGGER.info("[MODEL] Loading GroundingDINO detector")
	model = _load_groundingdino(device)

	LOGGER.info("[DETECT] Running component detection: %s", ", ".join(labels))
	with torch.inference_mode():
		boxes, logits, phrases = main2.predict_groundingdino(
			model=model,
			image=image_tensor,
			caption=detection_caption,
			box_threshold=float(cfg.get("detection", {}).get("box_threshold", cfg.get("detection", {}).get("score_threshold", 0.20))),
			text_threshold=float(cfg.get("detection", {}).get("text_threshold", 0.15)),
			device=device,
		)

	chosen = main2.choose_detections(
		boxes,
		logits,
		phrases,
		int(cfg.get("detection", {}).get("max_detections", 12)),
		width,
		height,
		prompt,
		nms_threshold=float(cfg.get("detection", {}).get("nms_iou", cfg.get("detection", {}).get("nms_threshold", 0.65))),
		min_area_ratio=float(cfg.get("detection", {}).get("min_box_area_ratio", 0.00005)),
		component_mode=True,
		remove_prompt=cfg.get("removal", {}).get("target") or cfg.get("detection", {}).get("remove_prompt"),
	)

	detections = [_detection_to_dict(det, idx, labels) for idx, det in enumerate(chosen)]
	detections = _filter_unmapped_component_detections(detections)
	LOGGER.info("[NORMALIZE] Mapping raw labels to normalized component types")
	if bool(cfg.get("detection", {}).get("enable_geometry_validation", True)):
		detections = _apply_cross_label_nms(
			detections,
			iou_threshold=float(cfg.get("detection", {}).get("cross_label_nms_iou", 0.35)),
		)
		detections = _apply_component_geometry_validation(detections, width, height, image_np)
	_refine_closed_elevator_door_detection(image_np, detections)
	_recover_elevator_door_header(image_np, detections)
	_promote_visual_floor_indicator_detections(image_np, detections)
	_add_structural_floor_indicator_detection(image_np, detections)
	_add_structural_call_panel_detection(image_np, detections)
	_split_stacked_accessibility_panel_detection(image_np, detections)
	detections = _dedupe_contained_component_detections(detections)
	detections = _suppress_conflicting_panel_part_labels(detections)
	_filter_false_elevator_interior_detections(image_np, detections)
	_repair_nested_elevator_door_detection(image_np, detections)
	_add_confirmed_open_interior_detection(image_np, detections)
	_expand_car_operating_panels(image_np, detections)

	output = {
		"metadata": {
			"image_path": str(image_path),
			"image_width": width,
			"image_height": height,
			"timestamp": utc_now(),
			"detector": "main2.py GroundingDINO",
			"main2_file": str(MAIN2_PATH),
			"model_config": str(main2.CONFIG_PATH),
			"model_weights": str(main2.DINO_WEIGHTS),
			"text_encoder": str(main2.BERT_DIR),
			"prompt": detection_caption,
			"requested_labels": labels,
			"score_threshold": float(cfg.get("detection", {}).get("box_threshold", cfg.get("detection", {}).get("score_threshold", 0.20))),
			"text_threshold": float(cfg.get("detection", {}).get("text_threshold", 0.15)),
			"nms_iou": float(cfg.get("detection", {}).get("nms_iou", cfg.get("detection", {}).get("nms_threshold", 0.65))),
			"num_detections": len(detections),
			"mask_format": None,
		},
		"detections": detections,
	}
	save_json(out_json, output)
	return output


def add_sam2_masks(image_path: str | Path, cfg: dict[str, Any], detection_data: dict[str, Any], out_json: str | Path) -> dict[str, Any]:
	main2 = _load_main2()
	sam_cfg = cfg.get("segmentation", {})
	if not sam_cfg.get("enabled", True) or not detection_data.get("detections"):
		save_json(out_json, detection_data)
		return detection_data
	if not main2.SAM2_DIR.exists() or not main2.SAM2_WEIGHTS.exists():
		if sam_cfg.get("fallback_to_boxes", True):
			save_json(out_json, detection_data)
			return detection_data
		raise FileNotFoundError("SAM2 repo or weights missing.")

	device = main2.select_device(sam_cfg.get("device", cfg.get("detection", {}).get("device", "auto")))
	if device not in _SAM2_CACHE:
		main2.ensure_file(main2.SAM2_WEIGHTS, "SAM2 weights")
		_SAM2_CACHE[device] = main2.load_sam2_predictor(
			sam_cfg.get("sam2_config", main2.SAM2_CONFIG),
			main2.SAM2_WEIGHTS,
			device=device,
		)

	predictor = _SAM2_CACHE[device]
	image_np = load_image_rgb(image_path)
	for det in detection_data["detections"]:
		if det.get("source") in {
			"open_door_interior_inset",
			"expanded_car_operating_panel_plate",
			"closed_door_header_recovery",
			"split_operating_panel_fixture",
			"split_wheelchair_indicator",
			"image_structure_call_panel",
		}:
			mask = _box_mask(det["box_xyxy"], image_np.shape[:2])
			det["mask_area_px"] = int(mask.sum())
			det["mask"] = mask_to_rle(mask)
			continue
		main2_det = main2.Detection(
			box_xyxy=np.array(det["box_xyxy"], dtype=np.float32),
			phrase=str(det.get("phrase", "")),
			score=float(det.get("score", 0.0)),
			remove=True,
		)
		with main2.autocast_for(device):
			combined_mask, component_masks = main2.make_mask(
				predictor,
				image_np,
				[main2_det],
				multimask=bool(sam_cfg.get("sam2_multimask", True)),
				use_center_point=bool(sam_cfg.get("sam2_center_point", True)),
				close_radius=int(sam_cfg.get("mask_close", 3)),
				dilate_radius=int(sam_cfg.get("mask_dilate", 2)),
				min_component_area=int(sam_cfg.get("mask_min_component_area", 64)),
				fill_holes=bool(sam_cfg.get("fill_holes", True)),
			)
		mask = (component_masks[0] if component_masks else combined_mask) > 127
		det["mask_area_px"] = int(mask.sum())
		det["mask"] = mask_to_rle(mask)

	detection_data["metadata"]["segmenter"] = "main2.py SAM2"
	detection_data["metadata"]["sam2_weights"] = str(main2.SAM2_WEIGHTS)
	detection_data["metadata"]["mask_format"] = "rle"
	save_json(out_json, detection_data)
	return detection_data


def _box_mask(box: list[float], shape: tuple[int, int]) -> np.ndarray:
	height, width = shape
	x1, y1, x2, y2 = [int(round(v)) for v in box]
	x1, y1 = max(0, x1), max(0, y1)
	x2, y2 = min(width, x2), min(height, y2)
	mask = np.zeros((height, width), dtype=bool)
	if x2 > x1 and y2 > y1:
		mask[y1:y2, x1:x2] = True
	return mask


def _load_main2() -> Any:
	global _MAIN2
	if _MAIN2 is None:
		if str(ROOT) not in sys.path:
			sys.path.insert(0, str(ROOT))
		spec = importlib.util.spec_from_file_location("elevator_pipeline_main2", MAIN2_PATH)
		if spec is None or spec.loader is None:
			raise ImportError(f"Could not load {MAIN2_PATH}")
		module = importlib.util.module_from_spec(spec)
		sys.modules.setdefault("elevator_pipeline_main2", module)
		spec.loader.exec_module(module)
		_MAIN2 = module
	return _MAIN2


def _load_groundingdino(device: str) -> Any:
	if device not in _GDINO_CACHE:
		main2 = _load_main2()
		with contextlib.redirect_stdout(io.StringIO()):
			_GDINO_CACHE[device] = main2.load_groundingdino_model(main2.CONFIG_PATH, main2.DINO_WEIGHTS, device=device)
	return _GDINO_CACHE[device]


def _resolve_path(path: str | Path) -> Path:
	p = Path(path)
	if p.is_absolute():
		return p
	for base in (Path.cwd(), PROJECT_ROOT, ROOT):
		candidate = base / p
		if candidate.exists():
			return candidate
	return PROJECT_ROOT / p


def _labels_to_prompt(labels: list[str]) -> str:
	prompt_labels: list[str] = []
	for label in labels:
		normalized = label.strip().lower()
		prompt_labels.extend(NORMALIZED_COMPONENT_PROMPTS.get(normalized, [normalized]))
	prompt = " . ".join(label for label in dict.fromkeys(prompt_labels) if label).rstrip(". ")
	return prompt if prompt.endswith(".") else f"{prompt}."


def _detection_to_dict(det: Any, idx: int, labels: list[str]) -> dict[str, Any]:
	raw_label = str(det.phrase).lower().strip()
	phrase = _canonical_phrase(raw_label, labels)
	x1, y1, x2, y2 = [float(v) for v in det.box_xyxy]
	area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
	normalized_type = _normalized_component_type(phrase)
	if normalized_type == "weight_limit_sign":
		phrase = "weight limit sign"
	return {
		"id": idx,
		"phrase": phrase,
		"raw_detection_label": raw_label,
		"source_prompt": phrase,
		"normalized_component_type": normalized_type,
		"score": float(det.score),
		"box_xyxy": [x1, y1, x2, y2],
		"box_xywh": [x1, y1, x2 - x1, y2 - y1],
		"box_area": float(area),
	}


def _canonical_phrase(phrase: str, labels: list[str]) -> str:
	lower = phrase.lower().strip()
	if lower in {"elevator elevator", "elevator doors door", "lift lift"}:
		return "elevator door"
	if lower in {"elevator_button_panel", "elevator button panel"}:
		return OPERATING_PANEL_CLASS
	if lower in CANONICAL_COMPONENT_LABELS:
		return lower
	label_lowers: list[str] = []
	for label in labels:
		normalized = label.lower().strip()
		label_lowers.append(normalized)
		label_lowers.extend(NORMALIZED_COMPONENT_PROMPTS.get(normalized, []))
	if lower in label_lowers:
		return lower
	matches = [label.lower() for label in labels if label.lower() in lower or lower in label.lower()]
	for normalized, prompts in NORMALIZED_COMPONENT_PROMPTS.items():
		if normalized in lower:
			matches.append(normalized)
		matches.extend(prompt for prompt in prompts if prompt.lower() in lower or lower in prompt.lower())
	return max(matches, key=len) if matches else lower or "elevator component"


def _normalized_component_type(phrase: str) -> str | None:
	lower = phrase.lower().strip()
	if lower in {"elevator elevator", "elevator doors door", "lift lift"}:
		return "elevator_door"
	if lower in {"elevator_button_panel", "elevator button panel", "car operating panel", "cop"}:
		return OPERATING_PANEL_CLASS
	if OPERATING_PANEL_CLASS in lower:
		return OPERATING_PANEL_CLASS
	if lower == "elevator call button panel":
		return "elevator call button panel"
	if lower == "wheelchair button":
		return "wheelchair button"
	if any(term in lower for term in ("wheelchair indicator", "accessibility indicator")):
		return "wheelchair_indicator"
	if any(term in lower for term in ("accessibility control panel", "accessible elevator panel", "accessible panel")):
		return "accessibility_control_panel"
	if any(term in lower for term in ("capacity", "weight limit", "load limit", "maximum load")):
		return "weight_limit_sign"
	if any(term in lower for term in ("floor indicator", "indicator display", "digital floor display", "elevator display")):
		return "floor_indicator_display"
	if any(term in lower for term in ("elevator door", "elevator doors", "door frame", "elevator opening", "lift entrance")):
		return "elevator_door"
	if any(term in lower for term in ("elevator ceiling", "ceiling light", "lift ceiling", "ceiling panel")):
		return "elevator_ceiling"
	if any(term in lower for term in ("threshold plate", "door sill", "metal threshold plate", "door track")):
		return "threshold_plate"
	if "handrail" in lower:
		return "handrail"
	if any(term in lower for term in ("security camera", "surveillance camera")):
		return "security_camera"
	if any(term in lower for term in ("emergency phone", "intercom phone", "emergency call phone")):
		return "emergency_phone"
	if any(term in lower for term in ("elevator cabin", "elevator interior", "inside elevator", "elevator floor", "mirror")):
		return "elevator_cabin"
	return None


def _apply_cross_label_nms(detections: list[dict[str, Any]], iou_threshold: float) -> list[dict[str, Any]]:
	if not detections:
		return detections
	kept: list[dict[str, Any]] = []
	for det in sorted(detections, key=lambda item: float(item.get("score", 0.0)), reverse=True):
		phrase = str(det.get("phrase", "")).lower()
		suppress = False
		for existing in kept:
			existing_phrase = str(existing.get("phrase", "")).lower()
			if _component_group(phrase) != _component_group(existing_phrase):
				continue
			if _box_iou(det["box_xyxy"], existing["box_xyxy"]) >= iou_threshold:
				suppress = True
				break
		if not suppress:
			det["id"] = len(kept)
			kept.append(det)
	return kept


def _apply_component_geometry_validation(
	detections: list[dict[str, Any]],
	width: int,
	height: int,
	image_rgb: np.ndarray | None = None,
) -> list[dict[str, Any]]:
	door = _best_detection_of_type(detections, "elevator_door")
	opening_box = door.get("box_xyxy") if door else None
	if image_rgb is not None:
		inferred_opening = _infer_elevator_door_box(image_rgb, detections)
		if inferred_opening is not None and (
			opening_box is None or _box_area(inferred_opening) > _box_area(opening_box) * 1.35
		):
			opening_box = inferred_opening
	kept: list[dict[str, Any]] = []
	for det in detections:
		phrase = str(det.get("phrase", "")).lower()
		norm = str(det.get("normalized_component_type") or "").lower()
		box = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
		x1, y1, x2, y2 = box
		bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
		cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
		area_ratio = (bw * bh) / max(width * height, 1)

		if "ventilation grille" in phrase:
			_mark_rejected(det, "ventilation_grille_not_standard_component")
			continue

		if norm == "elevator_cabin" and (bh / bw < 0.85 or cy < height * 0.14):
			_mark_rejected(det, "overhead_or_horizontal_region_not_elevator_cabin")
			continue
		if norm == "threshold_plate" and bh > bw * 0.35:
			_mark_rejected(det, "floor_region_not_thin_elevator_threshold")
			continue
		if norm == "floor_indicator_display" and bh > bw * 1.80:
			_mark_rejected(det, "vertical_wall_fixture_not_floor_indicator_display")
			continue
		if norm == OPERATING_PANEL_CLASS:
			if x1 <= width * 0.01 or x2 >= width * 0.99:
				_mark_rejected(det, "cropped_image_edge_not_complete_operating_panel")
				continue
			if _image_has_many_cop_buttons(image_rgb, width, height):
				det.setdefault("geometry_validation", {})
				det["geometry_validation"].update({"status": "accepted", "reason": "many_floor_buttons_confirm_cop_image"})
				kept.append(det)
				continue
			fixture = _dark_wall_fixture_box(image_rgb, box, width, height) if image_rgb is not None else None
			if fixture is not None:
				_remap_detection(det, "elevator call button panel", "elevator call button panel", "geometry_refine_dark_wall_call_panel")
				_update_detection_box(det, fixture)
			elif not _is_plausible_operating_panel_detection(det, width, height, image_rgb):
				_mark_rejected(det, "wall_region_without_operating_panel_evidence")
				continue

		if opening_box:
			dx1, dy1, dx2, dy2 = [float(v) for v in opening_box]
			dw, dh = max(1.0, dx2 - dx1), max(1.0, dy2 - dy1)
			in_door_x = dx1 <= cx <= dx2
			in_door_y = dy1 <= cy <= dy2
			overlap_door = _box_overlap_fraction(box, opening_box)

			if "ceiling" in phrase and (cy < dy1 or not in_door_x or area_ratio > 0.08):
				_mark_rejected(det, "elevator_ceiling_outside_elevator_roi")
				continue
			if norm == "weight_limit_sign" and cy < dy1 and in_door_x and area_ratio <= 0.025:
				_remap_detection(det, "floor_indicator_display", "floor indicator display", "geometry_remap_top_indicator_not_weight_limit")
				kept.append(det)
				continue
			if norm == "emergency_phone" and overlap_door > 0.45:
				_mark_rejected(det, "interior_control_detail_not_emergency_phone")
				continue
			if norm == "floor_indicator_display" and not in_door_x and in_door_y and cy > dy1 + dh * 0.20:
				_remap_detection(det, "accessibility_control_panel", "accessibility control panel", "geometry_remap_side_accessibility_plate_not_display")
				kept.append(det)
				continue
			if norm == "floor_indicator_display":
				over_door = dx1 + dw * 0.25 <= cx <= dx2 - dw * 0.25 and cy < dy1
				reasonable_gap = (dy1 - cy) <= max(height * 0.13, dh * 0.24)
				if not (over_door and reasonable_gap):
					_mark_rejected(det, "display_not_landing_floor_indicator_above_door")
					continue
			if norm == "handrail" and (cy > dy1 + dh * 0.62 or bh < dh * 0.025):
				_mark_rejected(det, "false_handrail_low_or_too_thin")
				continue
			if norm == "handrail" and overlap_door > 0.55 and cy < dy1 + dh * 0.34:
				_mark_rejected(det, "closed_door_reflection_not_handrail")
				continue
			if norm == "threshold_plate":
				overlap_width = max(0.0, min(x2, dx2) - max(x1, dx1))
				near_sill = abs(cy - dy2) <= max(height * 0.045, bh * 1.25)
				if overlap_width < dw * 0.55 or not near_sill:
					_mark_rejected(det, "floor_tile_not_full_width_elevator_threshold")
					continue
			if norm == "security_camera" and float(det.get("score", 0.0)) < 0.40:
				opening_x = (cx - dx1) / dw
				if in_door_y and (opening_x < 0.12 or opening_x > 0.88):
					_mark_rejected(det, "door_frame_edge_not_security_camera")
					continue

		kept.append(det)

	for idx, det in enumerate(kept):
		det["id"] = idx
	return kept


def _best_detection_of_type(detections: list[dict[str, Any]], normalized_type: str) -> dict[str, Any] | None:
	candidates = [det for det in detections if det.get("normalized_component_type") == normalized_type]
	return max(candidates, key=lambda det: float(det.get("score", 0.0))) if candidates else None


def _remap_detection(det: dict[str, Any], normalized_type: str, phrase: str, reason: str) -> None:
	det.setdefault("geometry_validation", {})
	det["geometry_validation"].update({"status": "remapped", "reason": reason, "original_phrase": det.get("phrase"), "original_normalized_component_type": det.get("normalized_component_type")})
	det["phrase"] = phrase
	det["source_prompt"] = phrase
	det["normalized_component_type"] = normalized_type


def _update_detection_box(det: dict[str, Any], box: list[float]) -> None:
	box_f = [float(v) for v in box]
	det["box_xyxy"] = box_f
	det["box_xywh"] = [box_f[0], box_f[1], box_f[2] - box_f[0], box_f[3] - box_f[1]]
	det["box_area"] = float(_box_area(box_f))


def _mark_rejected(det: dict[str, Any], reason: str) -> None:
	LOGGER.info("[DETECT] Rejected component: %s reason=%s", det.get("phrase"), reason)
	det["geometry_validation"] = {"status": "rejected", "reason": reason}


def _filter_unmapped_component_detections(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	kept: list[dict[str, Any]] = []
	for det in detections:
		if det.get("normalized_component_type") is None:
			_mark_rejected(det, "grounding_phrase_not_a_requested_component")
			continue
		det["id"] = len(kept)
		kept.append(det)
	return kept


def _box_overlap_fraction(a: list[float], b: list[float]) -> float:
	ax1, ay1, ax2, ay2 = [float(v) for v in a]
	bx1, by1, bx2, by2 = [float(v) for v in b]
	inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
	area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
	return inter / area


def _component_group(phrase: str) -> str:
	if OPERATING_PANEL_CLASS in phrase or "car operating panel" in phrase:
		return OPERATING_PANEL_CLASS
	if "accessibility control panel" in phrase:
		return "accessibility_control_panel"
	if "wheelchair button" in phrase:
		return "wheelchair button"
	if "elevator call button panel" in phrase:
		return "elevator call button panel"
	if any(term in phrase for term in ("floor indicator", "display")):
		return "floor_indicator"
	if any(term in phrase for term in ("door", "frame", "opening", "interior")):
		return "elevator_opening"
	if "emergency" in phrase:
		return "emergency"
	return phrase


def _box_iou(a: list[float], b: list[float]) -> float:
	ax1, ay1, ax2, ay2 = [float(v) for v in a]
	bx1, by1, bx2, by2 = [float(v) for v in b]
	inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
	area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
	area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
	return inter / max(1.0, area_a + area_b - inter)


def _expand_car_operating_panels(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	height, width = image_rgb.shape[:2]
	for det in detections:
		if det.get("normalized_component_type") != OPERATING_PANEL_CLASS:
			continue
		seed = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
		sx1, sy1, sx2, sy2 = seed
		sw, sh = max(1.0, sx2 - sx1), max(1.0, sy2 - sy1)
		aligned_displays: list[dict[str, Any]] = []
		for candidate in detections:
			if candidate.get("normalized_component_type") != "floor_indicator_display":
				continue
			cx1, cy1, cx2, cy2 = [float(v) for v in candidate.get("box_xyxy", [0, 0, 0, 0])]
			overlap = max(0.0, min(sx2, cx2) - max(sx1, cx1)) / max(1.0, min(sw, cx2 - cx1))
			gap = sy1 - cy2
			if overlap >= 0.45 and 0 <= gap <= max(sh * 0.62, height * 0.22):
				aligned_displays.append(candidate)
		if aligned_displays:
			display = max(aligned_displays, key=lambda item: float(item.get("score", 0.0)))
			display_box = [float(v) for v in display["box_xyxy"]]
			union = [
				min(sx1, display_box[0]),
				min(sy1, display_box[1]),
				max(sx2, display_box[2]),
				max(sy2, display_box[3]),
			]
			expanded = _fit_car_operating_panel_plate(image_rgb, union, display_box)
			reason = "aligned_display_and_button_cluster_form_full_cop_plate"
			extra = {"aligned_display_box_xyxy": display_box}
		else:
			expanded = _fit_car_operating_panel_plate_from_buttons(image_rgb, seed)
			reason = "button_cluster_expanded_to_full_cop_plate"
			extra = {}
			if expanded is None:
				continue
		if _box_area(expanded) <= _box_area(seed) * 1.25:
			continue
		LOGGER.info("[DETECT] Expanded car operating panel plate: %s -> %s", [round(v) for v in seed], [round(v) for v in expanded])
		det["box_xyxy"] = expanded
		det["box_xywh"] = [expanded[0], expanded[1], expanded[2] - expanded[0], expanded[3] - expanded[1]]
		det["box_area"] = float(_box_area(expanded))
		det["source"] = "expanded_car_operating_panel_plate"
		det.setdefault("geometry_validation", {})
		det["geometry_validation"].update(
			{
				"status": "expanded",
				"reason": reason,
				"original_box_xyxy": seed,
				"expanded_box_xyxy": expanded,
				**extra,
			}
		)


def _is_plausible_operating_panel_detection(
	det: dict[str, Any],
	width: int,
	height: int,
	image_rgb: np.ndarray | None,
) -> bool:
	x1, y1, x2, y2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
	bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
	aspect = bh / bw
	area_ratio = (bw * bh) / max(width * height, 1)
	if aspect < 1.65 or bh < height * 0.12 or bw < width * 0.025 or area_ratio > 0.22:
		return False
	if image_rgb is None:
		return True
	try:
		import cv2
	except ImportError:
		return True
	ix1, iy1, ix2, iy2 = [int(round(v)) for v in (x1, y1, x2, y2)]
	ix1, iy1 = max(0, ix1), max(0, iy1)
	ix2, iy2 = min(width, ix2), min(height, iy2)
	if ix2 <= ix1 or iy2 <= iy1:
		return False
	crop = np.asarray(image_rgb)[iy1:iy2, ix1:ix2]
	gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
	edge_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
	edge_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
	edge_density = float(((edge_x + edge_y) > 90).mean())
	bright_fraction = float((gray > 210).mean())
	dark_fraction = float((gray < 75).mean())
	if area_ratio > 0.025 and bright_fraction > 0.35 and dark_fraction < 0.20 and edge_density < 0.16:
		return False
	return True


def _image_has_many_cop_buttons(image_rgb: np.ndarray | None, width: int, height: int, min_buttons: int = 5) -> bool:
	if image_rgb is None:
		return False
	try:
		import cv2
	except ImportError:
		return False
	gray = cv2.cvtColor(np.asarray(image_rgb), cv2.COLOR_RGB2GRAY)
	blur = cv2.GaussianBlur(gray, (5, 5), 0)
	circles = cv2.HoughCircles(
		blur,
		cv2.HOUGH_GRADIENT,
		dp=1.2,
		minDist=max(10, int(min(width, height) * 0.035)),
		param1=80,
		param2=14,
		minRadius=max(3, int(min(width, height) * 0.006)),
		maxRadius=max(8, int(min(width, height) * 0.045)),
	)
	return bool(circles is not None and int(circles.shape[1]) >= min_buttons)


def _dark_wall_fixture_box(
	image_rgb: np.ndarray | None,
	seed_box: list[float],
	width: int,
	height: int,
	max_aspect: float = 2.2,
) -> list[float] | None:
	if image_rgb is None:
		return None
	try:
		import cv2
	except ImportError:
		return None
	x1, y1, x2, y2 = [float(v) for v in seed_box]
	bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
	pad_x = max(10, int(round(bw * 0.35)))
	pad_y = max(10, int(round(bh * 0.16)))
	left_pad = pad_x if bw < width * 0.09 else 0
	sx1, sy1 = max(0, int(round(x1 - left_pad))), max(0, int(round(y1 - pad_y)))
	sx2, sy2 = min(width, int(round(x2 + pad_x))), min(height, int(round(y2 + pad_y)))
	if sx2 <= sx1 or sy2 <= sy1:
		return None
	gray = cv2.cvtColor(np.asarray(image_rgb)[sy1:sy2, sx1:sx2], cv2.COLOR_RGB2GRAY)
	mask = (gray < 85).astype(np.uint8)
	num, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
	best: tuple[int, list[float]] | None = None
	for idx in range(1, num):
		cx, cy, cw, ch, area = [int(v) for v in stats[idx]]
		if area < 120:
			continue
		fx1, fy1, fx2, fy2 = sx1 + cx, sy1 + cy, sx1 + cx + cw, sy1 + cy + ch
		fw, fh = max(1, fx2 - fx1), max(1, fy2 - fy1)
		aspect = fh / fw
		if not (0.55 <= aspect <= max_aspect):
			continue
		if fw < width * 0.035 or fw > width * 0.22 or fh < height * 0.035 or fh > height * 0.20:
			continue
		overlap = _box_overlap_fraction([fx1, fy1, fx2, fy2], seed_box)
		if overlap < 0.08 and not _box_center_inside([fx1, fy1, fx2, fy2], [sx1, sy1, sx2, sy2]):
			continue
		if best is None or area > best[0]:
			best = (area, _trim_dark_fixture_box(image_rgb, [float(fx1), float(fy1), float(fx2), float(fy2)]))
	return best[1] if best is not None else None


def _trim_dark_fixture_box(image_rgb: np.ndarray, box: list[float]) -> list[float]:
	try:
		import cv2
	except ImportError:
		return box
	height, width = image_rgb.shape[:2]
	x1, y1, x2, y2 = [int(round(v)) for v in box]
	x1, y1 = max(0, x1), max(0, y1)
	x2, y2 = min(width, x2), min(height, y2)
	if x2 <= x1 or y2 <= y1:
		return box
	gray = cv2.cvtColor(np.asarray(image_rgb)[y1:y2, x1:x2], cv2.COLOR_RGB2GRAY)
	mask = gray < 85
	if not mask.any():
		return [float(x1), float(y1), float(x2), float(y2)]
	rows = np.where(mask.mean(axis=1) > 0.12)[0]
	cols = np.where(mask.mean(axis=0) > 0.12)[0]
	if rows.size:
		y1, y2 = y1 + int(rows[0]), y1 + int(rows[-1]) + 1
	if cols.size:
		x1, x2 = x1 + int(cols[0]), x1 + int(cols[-1]) + 1
	return [float(x1), float(y1), float(x2), float(y2)]


def _fit_car_operating_panel_plate(
	image_rgb: np.ndarray,
	union_box: list[float],
	display_box: list[float],
) -> list[float]:
	import cv2

	height, width = image_rgb.shape[:2]
	ux1, uy1, ux2, uy2 = union_box
	panel_width = max(1.0, ux2 - ux1)
	gray = cv2.cvtColor(np.asarray(image_rgb), cv2.COLOR_RGB2GRAY)
	edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)

	side_search = max(8.0, panel_width * 0.16)
	search_x1 = max(0, int(round(ux1 - side_search)))
	search_x2 = min(width, int(round(ux2 + side_search)))
	search_y1 = max(0, int(round(display_box[1] - max(panel_width * 0.85, height * 0.08))))
	search_y2 = min(height, int(round(uy2 + height * 0.06)))
	column_energy = edges[search_y1:search_y2, search_x1:search_x2].mean(axis=0)
	left = _outer_panel_edge(column_energy, search_x1, int(round(ux1)) - search_x1, from_start=False)
	right = _outer_panel_edge(column_energy, search_x1, int(round(ux2)) - search_x1, from_start=True)
	if left >= ux1:
		left = int(round(ux1))
	if right <= ux2:
		right = int(round(ux2))

	top_end = max(search_y1 + 1, int(round(display_box[1] - max(8.0, (display_box[3] - display_box[1]) * 0.45))))
	row_energy = edges[search_y1:top_end, max(0, left):min(width, right)].mean(axis=1)
	threshold = max(9.0, float(np.percentile(row_energy, 62))) if row_energy.size else 9.0
	top_candidates = np.where(row_energy >= threshold)[0]
	top = search_y1 + int(top_candidates[0]) if top_candidates.size else int(round(uy1 - panel_width * 0.65))
	top = int(np.clip(top, 0, int(round(uy1))))

	bottom = int(round(uy2))
	return [float(left), float(top), float(right), float(np.clip(bottom, top + 2, height))]


def _fit_car_operating_panel_plate_from_buttons(image_rgb: np.ndarray, seed_box: list[float]) -> list[float] | None:
	import cv2

	height, width = image_rgb.shape[:2]
	sx1, sy1, sx2, sy2 = [float(v) for v in seed_box]
	sw, sh = max(1.0, sx2 - sx1), max(1.0, sy2 - sy1)
	cx = (sx1 + sx2) * 0.5
	search_x1 = max(0, int(round(cx - max(sw * 2.0, width * 0.09))))
	search_x2 = min(width, int(round(cx + max(sw * 2.0, width * 0.09))))
	search_y1 = max(0, int(round(sy1 - max(sh * 2.5, height * 0.35))))
	search_y2 = min(height, int(round(sy2 + max(sh * 1.4, height * 0.16))))
	if search_x2 <= search_x1 or search_y2 <= search_y1:
		return None

	gray = cv2.cvtColor(np.asarray(image_rgb), cv2.COLOR_RGB2GRAY)
	roi = cv2.GaussianBlur(gray[search_y1:search_y2, search_x1:search_x2], (5, 5), 0)
	circles = cv2.HoughCircles(
		roi,
		cv2.HOUGH_GRADIENT,
		dp=1.2,
		minDist=max(10, int(min(width, height) * 0.035)),
		param1=80,
		param2=14,
		minRadius=max(3, int(min(width, height) * 0.006)),
		maxRadius=max(8, int(min(width, height) * 0.045)),
	)
	ys1 = [sy1]
	ys2 = [sy2]
	if circles is not None and circles.shape[1] >= 3:
		points = np.round(circles[0]).astype(int)
		max_circle_dx = max(sw * 1.8, width * 0.080)
		points = np.array([point for point in points if abs((search_x1 + int(point[0])) - cx) <= max_circle_dx])
		if len(points) >= 3:
			ys1 = [search_y1 + int(y - r) for _, y, r in points]
			ys2 = [search_y1 + int(y + r) for _, y, r in points]

	button_top = min(float(min(ys1)), sy1)
	button_bottom = max(float(max(ys2)), sy2)
	panel_h = max(1.0, button_bottom - button_top)
	side_pad = max(sw * 0.75, width * 0.025)
	top_pad = max(panel_h * 0.55, height * 0.090)
	bottom_pad = max(panel_h * 0.18, height * 0.035)
	left = int(np.clip(round(sx1 - side_pad), 0, width - 2))
	right = int(np.clip(round(sx2 + side_pad), left + 2, width))
	top = int(np.clip(round(button_top - top_pad), 0, height - 2))
	bottom = int(np.clip(round(button_bottom + bottom_pad), top + 2, height))
	edge_x1 = max(0, int(round(cx - max(sw * 3.0, width * 0.12))))
	edge_x2 = min(width, int(round(cx + max(sw * 3.0, width * 0.12))))
	edge_roi = gray[top:bottom, edge_x1:edge_x2]
	if edge_roi.size:
		edges = cv2.Canny(cv2.GaussianBlur(edge_roi, (5, 5), 0), 35, 110)
		col_energy = edges.mean(axis=0)
		col_threshold = max(float(np.percentile(col_energy, 78)), float(col_energy.mean() * 1.25))
		strong_cols = np.where(col_energy >= col_threshold)[0]
		if strong_cols.size:
			cand_left = edge_x1 + int(strong_cols[0])
			cand_right = edge_x1 + int(strong_cols[-1])
			cand_w = cand_right - cand_left
			if max(sw * 1.1, width * 0.035) <= cand_w <= width * 0.28:
				left = int(np.clip(cand_left, 0, right - 2))
				right = int(np.clip(cand_right, left + 2, width))
		row_energy = edges[:, max(0, left - edge_x1):max(1, right - edge_x1)].mean(axis=1)
		row_threshold = max(float(np.percentile(row_energy, 75)), float(row_energy.mean() * 1.2)) if row_energy.size else 0.0
		strong_rows = np.where(row_energy >= row_threshold)[0]
		if strong_rows.size:
			cand_top = top + int(strong_rows[0])
			cand_bottom = top + int(strong_rows[-1])
			if cand_bottom - cand_top >= max(panel_h * 1.10, height * 0.16):
				top = int(np.clip(min(top, cand_top), 0, bottom - 2))
				bottom = int(np.clip(max(bottom, cand_bottom), top + 2, height))
	return [float(left), float(top), float(right), float(bottom)]


def _outer_panel_edge(energy: np.ndarray, offset: int, split: int, *, from_start: bool) -> int:
	if energy.size == 0:
		return offset + split
	split = int(np.clip(split, 0, len(energy) - 1))
	local = energy[split:] if from_start else energy[: split + 1]
	if local.size == 0:
		return offset + split
	index = int(np.argmax(local))
	return offset + (split + index if from_start else index)


def _dedupe_contained_component_detections(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	kept: list[dict[str, Any]] = []
	for det in sorted(detections, key=lambda item: float(item.get("score", 0.0)), reverse=True):
		norm = det.get("normalized_component_type")
		box = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
		area = _box_area(box)
		if area <= 0:
			continue
		duplicate = False
		for existing in kept:
			if existing.get("normalized_component_type") != norm:
				continue
			existing_box = [float(v) for v in existing.get("box_xyxy", [0, 0, 0, 0])]
			contained = _box_overlap_fraction(box, existing_box)
			contains_existing = _box_overlap_fraction(existing_box, box)
			if _box_iou(box, existing_box) > 0.35 or contained > 0.65 or contains_existing > 0.65:
				duplicate = True
				break
		if not duplicate:
			kept.append(det)
	for idx, det in enumerate(kept):
		det["id"] = idx
	return kept


def _suppress_conflicting_panel_part_labels(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	panels = [
		det
		for det in detections
		if det.get("normalized_component_type") in {OPERATING_PANEL_CLASS, "elevator call button panel"}
	]
	displays = [det for det in detections if det.get("normalized_component_type") == "floor_indicator_display"]
	if not panels and not displays:
		return detections
	kept: list[dict[str, Any]] = []
	for det in detections:
		norm = det.get("normalized_component_type")
		box = det.get("box_xyxy", [0, 0, 0, 0])
		if norm == "emergency_phone" and any(
			_box_overlap_fraction(box, candidate.get("box_xyxy", [0, 0, 0, 0])) > 0.20
			or _box_overlap_fraction(candidate.get("box_xyxy", [0, 0, 0, 0]), box) > 0.20
			for candidate in panels + displays
		):
			_mark_rejected(det, "overlapping_verified_control_panel_not_emergency_phone")
			continue
		if norm == "wheelchair button" and any(
			_box_overlap_fraction(box, panel.get("box_xyxy", [0, 0, 0, 0])) > 0.60 for panel in panels
		):
			_mark_rejected(det, "button_is_part_of_detected_control_panel")
			continue
		kept.append(det)
	for idx, det in enumerate(kept):
		det["id"] = idx
	return kept


def _refine_closed_elevator_door_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None:
		return
	if door.get("source") == "groundingdino_open_door_entrance_repair":
		return
	try:
		import cv2
	except ImportError:
		return
	height, width = image_rgb.shape[:2]
	x1, y1, x2, y2 = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
	search = [
		max(0, int(round(x1 - bw * 0.08))),
		max(0, int(round(y1 - bh * 0.04))),
		min(width, int(round(x2 + bw * 0.08))),
		min(height, int(round(y2 + bh * 0.04))),
	]
	sx1, sy1, sx2, sy2 = search
	if sx2 <= sx1 or sy2 <= sy1:
		return
	gray = cv2.cvtColor(np.asarray(image_rgb)[sy1:sy2, sx1:sx2], cv2.COLOR_RGB2GRAY)
	gray = cv2.GaussianBlur(gray, (5, 5), 0)
	edge_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
	edge_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
	hh, ww = gray.shape
	mid_y1, mid_y2 = int(hh * 0.20), int(hh * 0.88)
	vproj = edge_x[mid_y1:mid_y2].mean(axis=0)
	left_candidates = _top_peaks(vproj, 0, max(1, int(ww * 0.35)), 4)
	right_candidates = _top_peaks(vproj, min(ww - 1, int(ww * 0.65)), ww, 4)
	if left_candidates and right_candidates:
		lx = min(left_candidates, key=lambda x: abs((sx1 + x) - x1))
		rx = min(right_candidates, key=lambda x: abs((sx1 + x) - x2))
		if width * 0.18 <= rx - lx <= width * 0.42:
			x1, x2 = float(sx1 + lx), float(sx1 + rx)
	xi1 = max(0, int(round(x1 - sx1)))
	xi2 = min(ww, int(round(x2 - sx1)))
	if xi2 > xi1:
		hproj = edge_y[:, xi1:xi2].mean(axis=1)
		top = _best_peak(hproj, 0, int(hh * 0.20), int(y1 - sy1))
		bottom = _best_peak(hproj, int(hh * 0.82), hh, int(y2 - sy1))
		refined = [
			float(np.clip(x1, 0, width - 2)),
			float(np.clip(sy1 + top, 0, height - 2)),
			float(np.clip(x2, x1 + 2, width)),
			float(np.clip(sy1 + bottom, y1 + 2, height)),
		]
		if 0.55 <= _box_area(refined) / max(_box_area(door["box_xyxy"]), 1.0) <= 1.18:
			door.setdefault("geometry_validation", {})
			door["geometry_validation"].update(
				{
					"status": "refined",
					"reason": "closed_door_edges_refined_to_visible_leaf",
					"original_box_xyxy": door.get("box_xyxy"),
					"refined_box_xyxy": refined,
				}
			)
			_update_detection_box(door, refined)


def _recover_elevator_door_header(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None or door.get("source") == "groundingdino_open_door_entrance_repair":
		return
	try:
		import cv2
	except ImportError:
		return
	height, width = image_rgb.shape[:2]
	x1, y1, x2, y2 = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
	if bw < width * 0.18 or bh < height * 0.42 or y2 < height * 0.78:
		return
	if _has_open_elevator_interior_evidence(image_rgb, [x1, y1, x2, y2]):
		return
	search_top = max(0, int(round(y1 - height * 0.20)))
	search_bottom = max(search_top + 1, int(round(y1 - height * 0.025)))
	search_left = max(0, int(round(x1 - bw * 0.07)))
	search_right = min(width, int(round(x2 + bw * 0.07)))
	if search_bottom <= search_top or search_right <= search_left:
		return
	gray = cv2.cvtColor(np.asarray(image_rgb)[search_top:search_bottom, search_left:search_right], cv2.COLOR_RGB2GRAY)
	edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 110)
	min_span = max(24, int(round(bw * 0.68)))
	lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(16, min_span // 5), minLineLength=min_span, maxLineGap=12)
	if lines is None:
		return
	candidates: list[tuple[float, float, int]] = []
	for line in lines[:, 0]:
		lx1, ly1, lx2, ly2 = [int(v) for v in line]
		span = abs(lx2 - lx1)
		if span < min_span or abs(ly2 - ly1) > max(3, int(span * 0.04)):
			continue
		global_x1 = search_left + min(lx1, lx2)
		global_x2 = search_left + max(lx1, lx2)
		overlap = max(0.0, min(x2, global_x2) - max(x1, global_x1))
		if overlap < bw * 0.65:
			continue
		header_y = search_top + int(round((ly1 + ly2) * 0.5))
		candidates.append((overlap, -abs((global_x1 + global_x2) * 0.5 - (x1 + x2) * 0.5), header_y))
	if not candidates:
		return
	header_y = max(candidates, key=lambda item: (item[0], item[1], item[2]))[2]
	if not (height * 0.02 <= y1 - header_y <= height * 0.20):
		return
	original = list(door.get("box_xyxy", [x1, y1, x2, y2]))
	recovered = [x1, float(header_y), x2, y2]
	door.setdefault("geometry_validation", {})
	door["geometry_validation"].update(
		{
			"status": "recovered",
			"reason": "horizontal_header_edge_extends_closed_door_to_full_height",
			"original_box_xyxy": original,
			"recovered_box_xyxy": recovered,
		}
	)
	door["source"] = "closed_door_header_recovery"
	LOGGER.info("[DETECT] Recovered full door height from header edge: %s -> %s", [round(v) for v in original], [round(v) for v in recovered])
	_update_detection_box(door, recovered)


def _add_structural_floor_indicator_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None:
		return
	height, width = image_rgb.shape[:2]
	dx1, dy1, dx2, _ = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	door_cx = (dx1 + dx2) * 0.5
	try:
		import cv2
	except ImportError:
		return
	gray = cv2.cvtColor(np.asarray(image_rgb), cv2.COLOR_RGB2GRAY)
	search_x1 = max(0, int(round(door_cx - width * 0.14)))
	search_x2 = min(width, int(round(door_cx + width * 0.14)))
	search_y1 = max(0, int(round(dy1 - height * 0.18)))
	search_y2 = max(search_y1 + 1, int(round(dy1 - height * 0.035)))
	roi = gray[search_y1:search_y2, search_x1:search_x2]
	mask = (roi < 85).astype(np.uint8)
	num, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
	best: tuple[int, list[float]] | None = None
	for idx in range(1, num):
		x, y, w, h, area = [int(v) for v in stats[idx]]
		if area < 120:
			continue
		aspect = h / max(w, 1)
		if not (0.70 <= aspect <= 1.45):
			continue
		if not (width * 0.035 <= w <= width * 0.095 and height * 0.035 <= h <= height * 0.085):
			continue
		box = [float(search_x1 + x), float(search_y1 + y), float(search_x1 + x + w), float(search_y1 + y + h)]
		cx = (box[0] + box[2]) * 0.5
		score = int(area - abs(cx - door_cx) * 8)
		if best is None or score > best[0]:
			best = (score, box)
	if best is None:
		return
	box = best[1]
	for det in detections:
		if det.get("normalized_component_type") == "floor_indicator_display" and _box_iou(det.get("box_xyxy", [0, 0, 0, 0]), box) > 0.20:
			_update_detection_box(det, box)
			det["phrase"] = "floor indicator"
			det.setdefault("geometry_validation", {})
			det["geometry_validation"].update({"status": "refined", "reason": "dark_landing_indicator_above_door"})
			return
	detections.append(
		{
			"id": len(detections),
			"phrase": "floor indicator",
			"raw_detection_label": "image_structure_floor_indicator",
			"source_prompt": "floor indicator display",
			"normalized_component_type": "floor_indicator_display",
			"score": 0.46,
			"box_xyxy": box,
			"box_xywh": [box[0], box[1], box[2] - box[0], box[3] - box[1]],
			"box_area": float(_box_area(box)),
			"source": "image_structure_floor_indicator",
			"geometry_validation": {"status": "derived", "reason": "dark_landing_indicator_above_door"},
		}
	)
	for idx, det in enumerate(detections):
		det["id"] = idx


def _promote_visual_floor_indicator_detections(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	"""Promote a side-mounted digital position display before generic wall panels win."""
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None:
		return
	try:
		import cv2
	except ImportError:
		return
	height, width = image_rgb.shape[:2]
	door_box = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	dx1, dy1, dx2, dy2 = door_box
	dh = max(1.0, dy2 - dy1)
	promoted: list[dict[str, Any]] = []
	for det in detections:
		norm = det.get("normalized_component_type")
		if norm not in {"accessibility_control_panel", "emergency_phone"}:
			continue
		box = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
		x1, y1, x2, y2 = [int(round(v)) for v in box]
		x1, y1 = max(0, x1), max(0, y1)
		x2, y2 = min(width, x2), min(height, y2)
		cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
		beside_door = cx < dx1 or cx > dx2
		upper_fixture = dy1 + dh * 0.18 <= cy <= dy1 + dh * 0.54
		if x2 <= x1 or y2 <= y1 or not (beside_door and upper_fixture):
			continue
		hsv = cv2.cvtColor(np.asarray(image_rgb)[y1:y2, x1:x2], cv2.COLOR_RGB2HSV)
		red = cv2.inRange(hsv, np.array([0, 65, 55]), np.array([12, 255, 255]))
		red |= cv2.inRange(hsv, np.array([165, 65, 55]), np.array([179, 255, 255]))
		if int(np.count_nonzero(red)) < max(5, int(red.size * 0.006)):
			continue
		_remap_detection(det, "floor_indicator_display", "floor indicator display", "visual_red_digits_on_side_floor_indicator")
		promoted.append(det)
	if not promoted:
		return
	# A prominent sign above the opening is often mistaken for the indicator
	# when the actual numeric landing display is mounted on the side jamb.
	promoted_best = max(promoted, key=lambda det: float(det.get("score", 0.0)))
	detections[:] = [
		det
		for det in detections
		if det is promoted_best
		or det.get("normalized_component_type") != "floor_indicator_display"
		or det in promoted
	]
	for idx, det in enumerate(detections):
		det["id"] = idx


def _add_structural_call_panel_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None:
		return
	height, width = image_rgb.shape[:2]
	dx1, dy1, dx2, dy2 = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	search_box = [
		max(0.0, dx1 - width * 0.205),
		dy1 + (dy2 - dy1) * 0.28,
		max(1.0, dx1 - width * 0.035),
		dy1 + (dy2 - dy1) * 0.72,
	]
	box = _dark_wall_fixture_box(image_rgb, search_box, width, height)
	if box is not None:
		for det in detections:
			if det.get("normalized_component_type") in {"emergency_phone", OPERATING_PANEL_CLASS, "elevator call button panel", "wheelchair button"} and _box_iou(det.get("box_xyxy", [0, 0, 0, 0]), box) > 0.10:
				_remap_detection(det, "elevator call button panel", "elevator call button panel", "dark_wall_call_panel_left_of_door")
				_update_detection_box(det, box)
				return
	for det in detections:
		if det.get("normalized_component_type") != "wheelchair button":
			continue
		bx1, by1, bx2, by2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
		button_center = [(bx1 + bx2) * 0.5, (by1 + by2) * 0.5]
		if dx1 <= button_center[0] <= dx2 and dy1 <= button_center[1] <= dy2:
			continue
		button_search = [
			bx1 - width * 0.055,
			by1 - height * 0.16,
			bx2 + width * 0.055,
			by2 + height * 0.12,
		]
		panel_box = _dark_wall_fixture_box(image_rgb, button_search, width, height, max_aspect=5.5)
		if panel_box is None or _box_overlap_fraction(det.get("box_xyxy", [0, 0, 0, 0]), panel_box) < 0.55:
			button_w, button_h = max(1.0, bx2 - bx1), max(1.0, by2 - by1)
			panel_box = [
				max(0.0, bx1 - max(button_w * 0.42, width * 0.012)),
				max(0.0, by1 - max(button_h * 1.70, height * 0.035)),
				min(float(width), bx2 + max(button_w * 0.42, width * 0.012)),
				min(float(height), by2 + max(button_h * 0.82, height * 0.020)),
			]
		_remap_detection(det, "elevator call button panel", "elevator call button panel", "button_nested_in_dark_call_panel_fixture")
		_update_detection_box(det, panel_box)
		return


def _split_stacked_accessibility_panel_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	try:
		import cv2
	except ImportError:
		return
	height, width = image_rgb.shape[:2]
	new_indicators: list[dict[str, Any]] = []
	nested_button_ids: set[int] = set()
	for det in detections:
		if det.get("normalized_component_type") != OPERATING_PANEL_CLASS:
			continue
		x1, y1, x2, y2 = [int(round(v)) for v in det.get("box_xyxy", [0, 0, 0, 0])]
		x1, y1 = max(0, x1), max(0, y1)
		x2, y2 = min(width, x2), min(height, y2)
		if x2 <= x1 or y2 <= y1:
			continue
		roi = np.asarray(image_rgb)[y1:y2, x1:x2]
		hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
		blue_mask = cv2.inRange(hsv, np.array([85, 40, 40]), np.array([135, 255, 255]))
		indicator = _best_stacked_indicator_component(blue_mask, x1, y1, width, height)
		if indicator is None:
			continue
		control_box = _lower_control_fixture_box(image_rgb, [x1, y1, x2, y2], indicator)
		if control_box is None:
			continue
		original = [float(v) for v in det.get("box_xyxy", [x1, y1, x2, y2])]
		LOGGER.info("[DETECT] Split stacked accessibility fixture: %s -> panel=%s wheelchair_indicator=%s", [round(v) for v in original], [round(v) for v in control_box], [round(v) for v in indicator])
		det.setdefault("geometry_validation", {})
		det["geometry_validation"].update(
			{
				"status": "split",
				"reason": "separated_wheelchair_indicator_above_operating_panel",
				"original_box_xyxy": original,
				"operating_panel_box_xyxy": control_box,
				"wheelchair_indicator_box_xyxy": indicator,
			}
		)
		det["source"] = "split_operating_panel_fixture"
		_update_detection_box(det, control_box)
		new_indicators.append(
			{
				"id": len(detections) + len(new_indicators),
				"phrase": "wheelchair indicator",
				"raw_detection_label": "image_structure_wheelchair_indicator",
				"source_prompt": "wheelchair indicator",
				"normalized_component_type": "wheelchair_indicator",
				"score": float(det.get("score", 0.0)),
				"box_xyxy": indicator,
				"box_xywh": [indicator[0], indicator[1], indicator[2] - indicator[0], indicator[3] - indicator[1]],
				"box_area": float(_box_area(indicator)),
				"source": "split_wheelchair_indicator",
				"geometry_validation": {"status": "derived", "reason": "separated_from_stacked_operating_panel_detection"},
			}
		)
		for candidate in detections:
			if candidate.get("normalized_component_type") != "wheelchair button":
				continue
			if _box_overlap_fraction(candidate.get("box_xyxy", [0, 0, 0, 0]), control_box) > 0.50:
				nested_button_ids.add(id(candidate))
	if nested_button_ids:
		detections[:] = [det for det in detections if id(det) not in nested_button_ids]
	detections.extend(new_indicators)
	for idx, det in enumerate(detections):
		det["id"] = idx


def _best_stacked_indicator_component(mask: np.ndarray, offset_x: int, offset_y: int, width: int, height: int) -> list[float] | None:
	import cv2

	num, _, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
	best: tuple[int, list[float]] | None = None
	for idx in range(1, num):
		x, y, w, h, area = [int(v) for v in stats[idx]]
		if area < 60 or w < width * 0.025 or h < height * 0.025:
			continue
		aspect = h / max(w, 1)
		if not 0.55 <= aspect <= 1.70:
			continue
		box = [float(offset_x + x), float(offset_y + y), float(offset_x + x + w), float(offset_y + y + h)]
		if best is None or area > best[0]:
			best = (area, box)
	return best[1] if best is not None else None


def _lower_control_fixture_box(image_rgb: np.ndarray, stacked_box: list[int], indicator_box: list[float]) -> list[float] | None:
	import cv2

	height, width = image_rgb.shape[:2]
	x1, _, x2, y2 = stacked_box
	indicator_x1, _, indicator_x2, indicator_y2 = indicator_box
	fixture_x1 = max(x1, int(round(indicator_x1)) + 1)
	fixture_x2 = min(x2, int(round(indicator_x2)) - 1)
	start_y = max(0, int(round(indicator_y2 + height * 0.04)))
	if y2 <= start_y or fixture_x2 <= fixture_x1:
		return None
	# The stacked GroundingDINO box can touch the dark door surround. Restrict
	# the lower search to the indicator column so the frame is not merged in.
	roi = np.asarray(image_rgb)[start_y:y2, fixture_x1:fixture_x2]
	gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
	mask = (gray < 140).astype(np.uint8)
	num, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
	indicator_cx = (indicator_box[0] + indicator_box[2]) * 0.5
	best: tuple[float, list[float]] | None = None
	for idx in range(1, num):
		x, y, w, h, area = [int(v) for v in stats[idx]]
		if area < 80 or h < height * 0.045 or w < width * 0.018:
			continue
		box = [float(fixture_x1 + x), float(start_y + y), float(fixture_x1 + x + w), float(start_y + y + h)]
		cx = (box[0] + box[2]) * 0.5
		score = float(area) - abs(cx - indicator_cx) * 6.0
		if best is None or score > best[0]:
			best = (score, box)
	return best[1] if best is not None else None


def _filter_false_elevator_interior_detections(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None:
		return
	height, width = image_rgb.shape[:2]
	door_box = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	opening = _open_entrance_box(door_box, width, height)
	has_open_interior = _has_open_elevator_interior_evidence(image_rgb, opening)
	kept: list[dict[str, Any]] = []
	for det in detections:
		if det.get("normalized_component_type") != "elevator_cabin" or det.get("source") == "open_door_interior_inset":
			kept.append(det)
			continue
		box = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
		overlaps_opening = (
			_box_overlap_fraction(box, opening) >= 0.35
			or _box_overlap_fraction(opening, box) >= 0.35
		)
		if has_open_interior and overlaps_opening:
			kept.append(det)
			continue
		_mark_rejected(det, "cabin_without_confirmed_open_elevator_interior")
	detections[:] = kept
	for idx, det in enumerate(detections):
		det["id"] = idx


def _repair_nested_elevator_door_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None:
		return
	inferred = _infer_elevator_door_box(image_rgb, detections)
	if inferred is None:
		return
	current = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	inferred_f = [float(v) for v in inferred]
	current_area = _box_area(current)
	inferred_area = _box_area(inferred_f)
	if inferred_area <= current_area * 1.75:
		return
	if not _box_center_inside(current, inferred_f) and _box_overlap_fraction(current, inferred_f) < 0.40:
		return
	h, w = image_rgb.shape[:2]
	inferred_w = inferred_f[2] - inferred_f[0]
	inferred_h = inferred_f[3] - inferred_f[1]
	inferred_ratio = inferred_area / max(w * h, 1)
	if inferred_w < w * 0.20 or inferred_h < h * 0.45 or inferred_ratio > 0.72:
		return
	opening = _open_entrance_box(inferred_f, w, h)
	if not _has_open_elevator_interior_evidence(image_rgb, opening):
		LOGGER.info(
			"[DETECT] Skipped door/interior split for closed or exterior door structure: current=%s structural=%s",
			[round(v) for v in current],
			[round(v) for v in inferred_f],
		)
		return
	interior = _cabin_interior_box(image_rgb, opening, w, h)
	LOGGER.info(
		"[DETECT] Split open elevator door/interior regions: %s -> door=%s interior=%s",
		[round(v) for v in current],
		[round(v) for v in opening],
		[round(v) for v in interior],
	)
	door.setdefault("geometry_validation", {})
	door["geometry_validation"].update(
		{
			"status": "repaired",
			"reason": "nested_region_expanded_to_visible_open_door_entrance",
			"original_box_xyxy": current,
			"structural_box_xyxy": inferred_f,
			"repaired_box_xyxy": opening,
		}
	)
	door["box_xyxy"] = opening
	door["box_xywh"] = [opening[0], opening[1], opening[2] - opening[0], opening[3] - opening[1]]
	door["box_area"] = float(_box_area(opening))
	door["source"] = "groundingdino_open_door_entrance_repair"
	interior_det = {
		"id": len(detections),
		"phrase": "elevator interior",
		"raw_detection_label": "derived_from_open_door_entrance",
		"source_prompt": "elevator interior",
		"normalized_component_type": "elevator_cabin",
		"score": float(door.get("score", 0.0)),
		"box_xyxy": interior,
		"box_xywh": [interior[0], interior[1], interior[2] - interior[0], interior[3] - interior[1]],
		"box_area": float(_box_area(interior)),
		"source": "open_door_interior_inset",
		"geometry_validation": {
			"status": "derived",
			"reason": "cabin_region_inset_from_visible_open_door_entrance",
			"door_box_xyxy": opening,
		},
	}
	detections.append(interior_det)
	for idx, det in enumerate(detections):
		det["id"] = idx


def _add_confirmed_open_interior_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	if _best_detection_of_type(detections, "elevator_cabin") is not None:
		return
	door = _best_detection_of_type(detections, "elevator_door")
	if door is None:
		return
	height, width = image_rgb.shape[:2]
	door_box = [float(v) for v in door.get("box_xyxy", [0, 0, 0, 0])]
	bw, bh = door_box[2] - door_box[0], door_box[3] - door_box[1]
	if bw < width * 0.18 or bh < height * 0.35 or not _has_open_elevator_interior_evidence(image_rgb, door_box):
		return
	interior = _cabin_interior_box(image_rgb, door_box, width, height)
	detections.append(
		{
			"id": len(detections),
			"phrase": "elevator interior",
			"raw_detection_label": "derived_from_confirmed_open_door",
			"source_prompt": "elevator interior",
			"normalized_component_type": "elevator_cabin",
			"score": float(door.get("score", 0.0)),
			"box_xyxy": interior,
			"box_xywh": [interior[0], interior[1], interior[2] - interior[0], interior[3] - interior[1]],
			"box_area": float(_box_area(interior)),
			"source": "open_door_interior_inset",
			"geometry_validation": {
				"status": "derived",
				"reason": "cabin_region_inset_from_confirmed_open_door",
				"door_box_xyxy": door_box,
			},
		}
	)


def _open_entrance_box(structural_box: list[float], width: int, height: int) -> list[float]:
	x1, y1, x2, y2 = structural_box
	bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
	return [
		float(np.clip(x1 + bw * 0.135, 0, width - 2)),
		float(np.clip(y1 + bh * 0.08, 0, height - 2)),
		float(np.clip(x2 - bw * 0.075, x1 + 2, width)),
		float(np.clip(y2 + bh * 0.06, y1 + 2, height)),
	]


def _cabin_interior_box(image_rgb: np.ndarray, door_box: list[float], width: int, height: int) -> list[float]:
	x1, y1, x2, y2 = door_box
	bw, bh = max(1.0, x2 - x1), max(1.0, y2 - y1)
	inner_x1 = float(np.clip(x1 + bw * 0.055, 0, width - 2))
	inner_x2 = float(np.clip(x2 - bw * 0.055, x1 + 2, width))
	inner_bottom = float(np.clip(y2 - bh * 0.12, y1 + 2, height))
	try:
		import cv2

		gray = cv2.cvtColor(np.asarray(image_rgb), cv2.COLOR_RGB2GRAY)
		gray = cv2.GaussianBlur(gray, (5, 5), 0)
		sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
		xa, xb = int(round(inner_x1)), int(round(inner_x2))
		start = int(round(y1 + bh * 0.70))
		end = int(round(y2 - bh * 0.06))
		if xb > xa and end > start:
			projection = sobel_y[start:end, xa:xb].mean(axis=1)
			if projection.size and float(projection.max()) > 0:
				inner_bottom = float(start + int(np.argmax(projection)))
	except ImportError:
		pass
	return [
		inner_x1,
		float(y1),
		inner_x2,
		inner_bottom,
	]


def _has_open_elevator_interior_evidence(image_rgb: np.ndarray, door_box: list[float]) -> bool:
	try:
		import cv2
	except ImportError:
		return True
	h, w = image_rgb.shape[:2]
	x1, y1, x2, y2 = [int(round(v)) for v in door_box]
	x1, y1 = max(0, x1), max(0, y1)
	x2, y2 = min(w, x2), min(h, y2)
	if x2 <= x1 or y2 <= y1:
		return False
	crop = np.asarray(image_rgb)[y1:y2, x1:x2]
	gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
	ch, cw = gray.shape
	if ch < 8 or cw < 8:
		return False
	inner = gray[int(ch * 0.12) : max(int(ch * 0.88), int(ch * 0.12) + 1), int(cw * 0.12) : max(int(cw * 0.88), int(cw * 0.12) + 1)]
	if inner.size == 0:
		return False
	sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
	sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
	vertical_energy = float(sobel_x.mean())
	horizontal_energy = float(sobel_y.mean())
	edge_ratio = horizontal_energy / max(vertical_energy, 1e-6)
	dark_fraction = float((inner < 75).mean())
	texture = float(inner.std())
	center = gray[:, int(cw * 0.42) : max(int(cw * 0.58), int(cw * 0.42) + 1)]
	center_seam = sobel_x[:, int(cw * 0.47) : max(int(cw * 0.53), int(cw * 0.47) + 1)]
	side_width = max(1, int(cw * 0.12))
	sides = np.concatenate([gray[:, :side_width].ravel(), gray[:, cw - side_width :].ravel()])
	center_side_delta = float(center.mean() - sides.mean()) if sides.size else 0.0
	center_seam_energy = float(center_seam.mean()) if center_seam.size else 0.0
	if dark_fraction > 0.65 and texture < 24.0:
		return False
	if dark_fraction < 0.08 and center_side_delta < -5.0:
		return False
	if dark_fraction < 0.03 and center_seam_energy > max(60.0, vertical_energy * 2.2):
		return False
	if edge_ratio < 0.70 and center_seam_energy > vertical_energy * 1.55:
		return False
	if center_seam_energy > 45.0 and center_seam_energy > vertical_energy * 1.70:
		return False
	return texture >= 24.0 and (edge_ratio >= 0.85 or dark_fraction >= 0.08)


def _infer_elevator_door_box(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> list[int] | None:
	try:
		import cv2
	except ImportError:
		return None
	h, w = image_rgb.shape[:2]
	gray = cv2.cvtColor(np.asarray(image_rgb), cv2.COLOR_RGB2GRAY)
	gray = cv2.GaussianBlur(gray, (5, 5), 0)
	sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
	sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))

	center_hint = _door_center_hint(w, detections)
	y1_band, y2_band = int(h * 0.18), int(h * 0.82)
	projection = sobel_x[y1_band:y2_band].mean(axis=0)
	projection = cv2.GaussianBlur(projection.reshape(1, -1), (51, 1), 0).ravel()
	projection[: int(w * 0.08)] = 0
	projection[int(w * 0.92) :] = 0
	lefts = _top_peaks(projection, int(w * 0.10), int(center_hint - w * 0.08), 12)
	rights = _top_peaks(projection, int(center_hint + w * 0.08), int(w * 0.92), 12)
	best: tuple[float, int, int] | None = None
	for lx in lefts:
		for rx in rights:
			bw = rx - lx
			if bw < w * 0.20 or bw > w * 0.65:
				continue
			score = projection[lx] + projection[rx] - abs(((lx + rx) * 0.5) - center_hint) * 0.08
			if best is None or score > best[0]:
				best = (float(score), int(lx), int(rx))
	if best is None:
		return None
	_, x1, x2 = best
	x_pad = max(8, int((x2 - x1) * 0.035))
	x1 = max(0, x1 - x_pad)
	x2 = min(w, x2 + x_pad)
	hproj = sobel_y[:, x1:x2].mean(axis=1)
	hproj = cv2.GaussianBlur(hproj.reshape(-1, 1), (1, 41), 0).ravel()
	top = _best_peak(hproj, int(h * 0.14), int(h * 0.45), int(h * 0.25))
	bottom = _best_peak(hproj, int(h * 0.62), int(h * 0.90), int(h * 0.78))
	return [x1, max(0, top - 8), x2, min(h, bottom + 16)]


def _door_center_hint(width: int, detections: list[dict[str, Any]]) -> float:
	panels = [
		det
		for det in detections
		if (
			"button panel" in det.get("phrase", "").lower()
			or "call button" in det.get("phrase", "").lower()
			or "wheelchair button" in det.get("phrase", "").lower()
			or "accessibility control panel" in det.get("phrase", "").lower()
			or det.get("normalized_component_type") in {"wheelchair button", "accessibility_control_panel", OPERATING_PANEL_CLASS, "elevator call button panel"}
		)
	]
	if panels:
		panel = max(panels, key=lambda d: float(d.get("score", 0)))
		x1, _, x2, _ = [float(v) for v in panel["box_xyxy"]]
		if (x1 + x2) * 0.5 < width * 0.45:
			return min(width * 0.72, x2 + width * 0.46)
		return max(width * 0.28, x1 - width * 0.46)
	return width * 0.5


def _box_area(box: list[float]) -> float:
	x1, y1, x2, y2 = [float(v) for v in box]
	return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _box_center_inside(inner: list[float], outer: list[float]) -> bool:
	x1, y1, x2, y2 = [float(v) for v in inner]
	ox1, oy1, ox2, oy2 = [float(v) for v in outer]
	cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
	return ox1 <= cx <= ox2 and oy1 <= cy <= oy2


def _top_peaks(projection: np.ndarray, start: int, end: int, limit: int) -> list[int]:
	start = max(0, start)
	end = min(len(projection), end)
	if end <= start:
		return []
	vals = projection[start:end].copy()
	peaks: list[int] = []
	min_sep = max(8, len(projection) // 40)
	for _ in range(limit):
		idx = int(np.argmax(vals))
		if vals[idx] <= 0:
			break
		peaks.append(start + idx)
		vals[max(0, idx - min_sep) : min(len(vals), idx + min_sep + 1)] = 0
	return peaks


def _best_peak(projection: np.ndarray, start: int, end: int, default: int) -> int:
	start = max(0, start)
	end = min(len(projection), end)
	if end <= start:
		return default
	local = projection[start:end]
	return int(start + np.argmax(local)) if float(local.max()) > 0 else default


def load_image_rgb(path: str | Path) -> np.ndarray:
	return np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))


def mask_to_rle(mask: np.ndarray) -> dict[str, Any]:
	mask = np.asarray(mask, dtype=np.uint8)
	pixels = mask.T.flatten()
	counts: list[int] = []
	last = 0
	run = 0
	for pixel in pixels:
		value = int(pixel > 0)
		if value == last:
			run += 1
		else:
			counts.append(run)
			run = 1
			last = value
	counts.append(run)
	return {"size": list(mask.shape), "counts": counts}


def save_json(path: str | Path, data: dict[str, Any]) -> None:
	out = Path(path)
	out.parent.mkdir(parents=True, exist_ok=True)
	out.write_text(json.dumps(data, indent=2), encoding="utf-8")


def utc_now() -> str:
	return datetime.now(timezone.utc).isoformat()
