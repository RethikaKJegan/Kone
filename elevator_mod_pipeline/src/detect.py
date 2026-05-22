from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .utils import load_image_rgb, mask_to_rle, save_json, utc_now


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        if (parent / "main2.py").exists():
            return parent
    raise FileNotFoundError("Could not find main2.py from detect.py location")


ROOT = _find_repo_root()
MAIN2_PATH = ROOT / "main2.py"

_MAIN2: Any | None = None
_GDINO_CACHE: dict[str, Any] = {}
_SAM2_CACHE: dict[str, Any] = {}


def run_detection(image_path: str | Path, cfg: dict[str, Any], out_json: str | Path) -> dict[str, Any]:
    main2 = _load_main2()
    image_np, image_tensor = main2.load_rgb_image(_resolve_path(image_path))
    height, width = image_np.shape[:2]
    labels = cfg["detection"]["labels"]
    prompt = _labels_to_prompt(labels)
    device = main2.select_device(cfg["detection"].get("device", "auto"))
    model = _load_groundingdino(device)

    with torch.inference_mode():
        boxes, logits, phrases = main2.predict_groundingdino(
            model=model,
            image=image_tensor,
            caption=prompt,
            box_threshold=float(cfg["detection"].get("box_threshold", cfg["detection"].get("score_threshold", 0.25))),
            text_threshold=float(cfg["detection"].get("text_threshold", 0.20)),
            device=device,
        )

    chosen = main2.choose_detections(
        boxes,
        logits,
        phrases,
        int(cfg["detection"].get("max_detections", 50)),
        width,
        height,
        prompt,
        nms_threshold=float(cfg["detection"].get("nms_iou", cfg["detection"].get("nms_threshold", 0.65))),
        min_area_ratio=float(cfg["detection"].get("min_box_area_ratio", 0.00005)),
    )
    detections = [_detection_to_dict(det, idx, labels) for idx, det in enumerate(chosen)]
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
            "prompt": prompt,
            "score_threshold": float(cfg["detection"].get("box_threshold", cfg["detection"].get("score_threshold", 0.25))),
            "text_threshold": float(cfg["detection"].get("text_threshold", 0.20)),
            "nms_iou": float(cfg["detection"].get("nms_iou", cfg["detection"].get("nms_threshold", 0.65))),
            "num_detections": len(detections),
            "mask_format": None,
        },
        "detections": detections,
    }
    save_json(out_json, output)
    return output


def add_sam2_masks(image_path: str | Path, cfg: dict[str, Any], detection_data: dict[str, Any], out_json: str | Path) -> dict[str, Any]:
    main2 = _load_main2()
    sam_cfg = cfg["segmentation"]
    if not sam_cfg.get("enabled", True) or not detection_data.get("detections"):
        return detection_data
    if not main2.SAM2_DIR.exists() or not main2.SAM2_WEIGHTS.exists():
        if sam_cfg.get("fallback_to_boxes", True):
            return detection_data
        raise FileNotFoundError("SAM2 repo or weights missing.")

    device = main2.select_device(sam_cfg.get("device", cfg["detection"].get("device", "auto")))
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
        )
        with main2.autocast_for(device):
            mask = main2.make_mask(
                predictor,
                image_np,
                [main2_det],
                multimask=bool(sam_cfg.get("sam2_multimask", True)),
                use_center_point=bool(sam_cfg.get("sam2_center_point", True)),
                close_radius=int(sam_cfg.get("mask_close", 3)),
                dilate_radius=int(sam_cfg.get("mask_dilate", 2)),
                min_component_area=int(sam_cfg.get("mask_min_component_area", 64)),
                fill_holes=bool(sam_cfg.get("fill_holes", True)),
            ) > 127
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
        _GDINO_CACHE[device] = main2.load_groundingdino_model(main2.CONFIG_PATH, main2.DINO_WEIGHTS, device=device)
    return _GDINO_CACHE[device]


def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else Path.cwd() / p


def _labels_to_prompt(labels: list[str]) -> str:
    prompt = " . ".join(label.strip().lower() for label in labels if label.strip()).rstrip(". ")
    return prompt if prompt.endswith(".") else f"{prompt}."


def _detection_to_dict(det: Any, idx: int, labels: list[str]) -> dict[str, Any]:
    phrase = _canonical_phrase(str(det.phrase), labels)
    x1, y1, x2, y2 = [float(v) for v in det.box_xyxy]
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return {
        "id": idx,
        "phrase": phrase,
        "score": float(det.score),
        "box_xyxy": [x1, y1, x2, y2],
        "box_xywh": [x1, y1, x2 - x1, y2 - y1],
        "box_area": float(area),
    }


def _canonical_phrase(phrase: str, labels: list[str]) -> str:
    lower = phrase.lower().strip()
    label_lowers = [label.lower() for label in labels]
    if lower in label_lowers:
        return lower
    matches = [label.lower() for label in labels if label.lower() in lower or lower in label.lower()]
    return max(matches, key=len) if matches else lower or "elevator component"


def _ensure_elevator_door_detection(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> None:
    if any(det.get("phrase", "").lower() == "elevator door" for det in detections):
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
            "score": 0.24,
            "box_xyxy": [x1, y1, x2, y2],
            "box_xywh": [x1, y1, x2 - x1, y2 - y1],
            "box_area": float(area),
            "source": "image_structure_fallback",
        }
    )


def _infer_elevator_door_box(image_rgb: np.ndarray, detections: list[dict[str, Any]]) -> list[int] | None:
    h, w = image_rgb.shape[:2]
    gray = np.asarray(image_rgb)
    if gray.ndim == 3:
        import cv2

        gray = cv2.cvtColor(gray, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
        sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    else:
        return None

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
    top = _correct_open_elevator_top(top, x1, x2, detections, h)
    return [x1, max(0, top - 8), x2, min(h, bottom + 16)]


def _correct_open_elevator_top(top: int, x1: int, x2: int, detections: list[dict[str, Any]], height: int) -> int:
    if top < height * 0.35:
        return top

    door_cx = (x1 + x2) * 0.5
    ceiling_candidates = []
    for det in detections:
        phrase = det.get("phrase", "").lower()
        if "elevator ceiling" not in phrase and "door frame" not in phrase:
            continue
        bx1, by1, bx2, by2 = [float(v) for v in det.get("box_xyxy", [0, 0, 0, 0])]
        if by2 >= top or by2 > height * 0.45:
            continue
        if bx1 <= door_cx <= bx2 or _x_overlap_ratio((x1, x2), (bx1, bx2)) > 0.35:
            ceiling_candidates.append((float(det.get("score", 0.0)), int(round(by2))))

    if not ceiling_candidates:
        return top
    _, ceiling_bottom = max(ceiling_candidates, key=lambda item: item[0])
    return max(0, min(top, ceiling_bottom))


def _x_overlap_ratio(a: tuple[float, float], b: tuple[float, float]) -> float:
    ax1, ax2 = a
    bx1, bx2 = b
    overlap = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    return overlap / max(1.0, ax2 - ax1)


def _door_center_hint(width: int, detections: list[dict[str, Any]]) -> float:
    panels = [
        det
        for det in detections
        if "button panel" in det.get("phrase", "").lower() or "call button" in det.get("phrase", "").lower()
    ]
    if panels:
        panel = max(panels, key=lambda d: float(d.get("score", 0)))
        x1, _, x2, _ = [float(v) for v in panel["box_xyxy"]]
        if (x1 + x2) * 0.5 < width * 0.45:
            return min(width * 0.72, x2 + width * 0.28)
        return max(width * 0.28, x1 - width * 0.28)
    return width * 0.5


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
