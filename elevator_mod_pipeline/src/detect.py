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
	"elevator_cabin": ["elevator cabin", "elevator interior", "inside elevator"],
	"threshold_plate": ["elevator threshold plate", "door sill", "metal threshold plate"],
	"handrail": ["elevator handrail", "handrail"],
	"security_camera": ["security camera", "surveillance camera"],
}
NORMALIZED_COMPONENT_TYPES = set(NORMALIZED_COMPONENT_PROMPTS)
CANONICAL_COMPONENT_LABELS = {
	"elevator interior",
	"elevator door",
	
	OPERATING_PANEL_CLASS,
	"elevator call button panel",
	"wheelchair button",
	"accessibility control panel",
	"security camera",
	"floor indicator",
	"elevator display",
	"handrail",
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
	LOGGER.info("[NORMALIZE] Mapping raw labels to normalized component types")
	if bool(cfg.get("detection", {}).get("enable_geometry_validation", True)):
		detections = _apply_cross_label_nms(
			detections,
			iou_threshold=float(cfg.get("detection", {}).get("cross_label_nms_iou", 0.35)),
		)
		detections = _apply_component_geometry_validation(detections, width, height)
	_repair_nested_elevator_door_detection(image_np, detections)
	_ensure_elevator_door_detection(image_np, detections)

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
	if lower in {"elevator_button_panel", "elevator button panel"}:
		return OPERATING_PANEL_CLASS
	if OPERATING_PANEL_CLASS in lower:
		return OPERATING_PANEL_CLASS
	if lower == "elevator call button panel":
		return "elevator call button panel"
	if lower == "wheelchair button":
		return "wheelchair button"
	if any(term in lower for term in ("accessibility control panel", "accessible elevator panel", "accessible panel")):
		return "accessibility_control_panel"
	if any(term in lower for term in ("capacity", "weight limit", "load limit", "maximum load")):
		return "weight_limit_sign"
	if any(term in lower for term in ("floor indicator", "indicator display", "digital floor display", "elevator display")):
		return "floor_indicator_display"
	if any(term in lower for term in ("elevator door", "elevator doors", "door frame", "elevator opening", "lift entrance")):
		return "elevator_door"
	if any(term in lower for term in ("threshold plate", "door sill", "metal threshold plate", "door track")):
		return "threshold_plate"
	if "handrail" in lower:
		return "handrail"
	if any(term in lower for term in ("security camera", "surveillance camera")):
		return "security_camera"
	if any(term in lower for term in ("elevator cabin", "elevator interior", "inside elevator", "elevator ceiling", "elevator floor", "mirror")):
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


def _apply_component_geometry_validation(detections: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
	door = _best_detection_of_type(detections, "elevator_door")
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

		if door:
			dx1, dy1, dx2, dy2 = [float(v) for v in door.get("box_xyxy", [0, 0, width, height])]
			dw, dh = max(1.0, dx2 - dx1), max(1.0, dy2 - dy1)
			in_door_x = dx1 <= cx <= dx2
			in_door_y = dy1 <= cy <= dy2
			overlap_door = _box_overlap_fraction(box, door["box_xyxy"])

			if "ceiling" in phrase and (cy < dy1 or not in_door_x or area_ratio > 0.08):
				_mark_rejected(det, "elevator_ceiling_outside_elevator_roi")
				continue
			if norm == "weight_limit_sign" and cy < dy1 and in_door_x and area_ratio <= 0.025:
				_remap_detection(det, "floor_indicator_display", "floor indicator display", "geometry_remap_top_indicator_not_weight_limit")
				kept.append(det)
				continue
			if ("emergency phone" in phrase or "emergency" in phrase) and overlap_door > 0.15 and area_ratio > 0.01:
				_mark_rejected(det, "poster_inside_cabin_not_emergency_phone")
				continue
			if norm == "floor_indicator_display" and not in_door_x and in_door_y and cy > dy1 + dh * 0.20:
				_remap_detection(det, "accessibility_control_panel", "accessibility control panel", "geometry_remap_side_accessibility_plate_not_display")
				kept.append(det)
				continue
			if norm == "handrail" and (cy > dy1 + dh * 0.62 or bh < dh * 0.025):
				_mark_rejected(det, "false_handrail_low_or_too_thin")
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


def _mark_rejected(det: dict[str, Any], reason: str) -> None:
	LOGGER.info("[DETECT] Rejected component: %s reason=%s", det.get("phrase"), reason)
	det["geometry_validation"] = {"status": "rejected", "reason": reason}


def _box_overlap_fraction(a: list[float], b: list[float]) -> float:
	ax1, ay1, ax2, ay2 = [float(v) for v in a]
	bx1, by1, bx2, by2 = [float(v) for v in b]
	inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
	area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
	return inter / area


def _component_group(phrase: str) -> str:
	if OPERATING_PANEL_CLASS in phrase:
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


def _ensure_elevator_door_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
	if any(det.get("normalized_component_type") == "elevator_door" for det in detections):
		return
	box = _infer_elevator_door_box(image_rgb, detections)
	if box is None:
		return
	x1, y1, x2, y2 = [float(v) for v in box]
	area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
	detections.append(
		{
			"id": len(detections),
			"phrase": "elevator door",
			"raw_detection_label": "image_structure_fallback",
			"source_prompt": "elevator door",
			"normalized_component_type": "elevator_door",
			"score": 0.24,
			"box_xyxy": [x1, y1, x2, y2],
			"box_xywh": [x1, y1, x2 - x1, y2 - y1],
			"box_area": float(area),
			"source": "image_structure_fallback",
		}
	)


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
	LOGGER.info("[DETECT] Repaired nested elevator door bbox: %s -> %s", [round(v) for v in current], inferred)
	door.setdefault("geometry_validation", {})
	door["geometry_validation"].update(
		{
			"status": "repaired",
			"reason": "nested_interior_panel_detected_as_elevator_door",
			"original_box_xyxy": current,
			"repaired_box_xyxy": inferred_f,
		}
	)
	door["box_xyxy"] = inferred_f
	door["box_xywh"] = [inferred_f[0], inferred_f[1], inferred_f[2] - inferred_f[0], inferred_f[3] - inferred_f[1]]
	door["box_area"] = float(inferred_area)
	door["source"] = "groundingdino_structural_door_repair"


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
