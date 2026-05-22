from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ACTION_SECONDS = {"open": 1.25, "close": 1.75}
MID_HOLD_SECONDS = 0.7
END_HOLD_SECONDS = 0.9


def render_elevator_video(
    image_path: str | Path,
    detections: dict[str, Any],
    geometry: dict[str, Any],
    cfg: dict[str, Any],
    out_path: str | Path,
    depth_path: str | Path | None = None,
) -> Path:
    video_cfg = cfg.get("video", {})
    fps = int(video_cfg.get("fps", 30))
    action = video_cfg.get("action", "auto")
    bitrate = str(video_cfg.get("bitrate", "10000k"))
    no_audio = bool(video_cfg.get("no_audio", False))
    cycle = bool(video_cfg.get("cycle", True))
    refine_roi = bool(video_cfg.get("refine_elevator_roi", True))
    preserve_outside_roi = bool(video_cfg.get("preserve_static_wall_outside_roi", refine_roi))

    img = load_image_bgr(image_path)
    depth = load_depth(depth_path, img.shape[:2]) if depth_path else None
    best_detection = select_best_elevator_detection(detections)
    roi_debug: dict[str, Any] = {}
    box = detect_door_box(img, detections, geometry, depth, cfg, roi_debug)
    state, state_debug = classify_elevator_state(detections, depth, box, img)
    first_action = action if action in {"open", "close"} else ("close" if state == "open" else "open")
    actions = [(first_action, ACTION_SECONDS[first_action])]
    if cycle:
        second_action = "close" if first_action == "open" else "open"
        actions.append((second_action, ACTION_SECONDS[second_action]))

    open_state_img, closed_state_img, source_policy = select_state_images(img, cfg, state, box)
    source_policy.update(reference_usage_debug(source_policy))
    state_debug.update(detection_debug(best_detection, detections, geometry, img.shape[:2]))
    state_debug.update(
        {
            "used_open_reference_image": source_policy["open_reference_image_used"] == "true",
            "used_closed_reference_image": source_policy["closed_reference_image_used"] == "true",
        }
    )
    roi_debug.update(
        {
            "selected_elevator_roi": box,
            "depth_state": state,
            "depth_dark_ratio": state_debug.get("depth_dark_ratio"),
            "depth_contrast": state_debug.get("depth_contrast"),
            "used_open_reference_image": state_debug["used_open_reference_image"],
            "used_closed_reference_image": state_debug["used_closed_reference_image"],
        }
    )
    write_elevator_roi_debug(out_path, img, depth, roi_debug)
    panels = build_panel_texture(closed_state_img, box, "closed", depth)
    reveal_scene = build_reveal_scene(img, open_state_img, box, "open", first_action, depth)
    mid_hold_frames = max(4, int(fps * MID_HOLD_SECONDS))
    end_hold_frames = max(4, int(fps * END_HOLD_SECONDS))

    frames: list[np.ndarray] = []
    frame_index = 0
    for segment_index, (segment_action, seconds) in enumerate(actions):
        action_frames = max(24, int(fps * seconds))
        previous = 0.0
        for i in range(action_frames):
            t = i / max(action_frames - 1, 1)
            progress = motor_profile(t, segment_action)
            frames.append(
                render_frame(
                    img,
                    box,
                    panels,
                    reveal_scene,
                    progress,
                    segment_action,
                    frame_index,
                    previous,
                    depth,
                    preserve_outside_roi,
                )
            )
            previous = progress
            frame_index += 1

        hold_progress = 1.0
        hold_count = mid_hold_frames if segment_index == 0 else end_hold_frames
        for _ in range(hold_count):
            frames.append(
                render_frame(
                    img,
                    box,
                    panels,
                    reveal_scene,
                    hold_progress,
                    segment_action,
                    frame_index,
                    previous,
                    depth,
                    preserve_outside_roi,
                )
            )
            previous = hold_progress
            frame_index += 1

    if state == "closed":
        enforce_closed_branch_endpoints(frames, img, actions, fps)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    audio_debug = write_video(out, frames, fps, bitrate, no_audio, actions, state, video_cfg)
    state_debug.update(audio_debug)
    write_metadata(out.with_suffix(".json"), image_path, out, box, state, [action for action, _ in actions], fps, depth_path, source_policy, state_debug, audio_debug)
    write_state_debug(out.with_name("elevator_state_debug.json"), state_debug)
    return out


def write_video(
    out: Path,
    frames: list[np.ndarray],
    fps: int,
    bitrate: str,
    no_audio: bool,
    actions: list[tuple[str, float]],
    elevator_state: str,
    video_cfg: dict[str, Any],
) -> dict[str, Any]:
    frames = normalize_video_frames(frames)
    height, width = frames[0].shape[:2]
    out.parent.mkdir(parents=True, exist_ok=True)
    add_audio = bool(video_cfg.get("add_audio", False)) and not no_audio
    video_out = out.with_name(out.stem + ".silent.mp4") if add_audio else out
    codecs = ("mp4v", "avc1", "H264")
    writer = None
    for codec in codecs:
        candidate = cv2.VideoWriter(str(video_out), cv2.VideoWriter_fourcc(*codec), float(fps), (width, height))
        if candidate.isOpened():
            writer = candidate
            break
        candidate.release()
    if writer is None:
        raise RuntimeError(f"Could not open an MP4 writer for {video_out}")
    try:
        for frame in frames:
            writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()

    duration = len(frames) / float(fps)
    if not add_audio:
        return {
            "audio_enabled": False,
            "audio_sample_rate": int(video_cfg.get("audio_sample_rate", 44100)),
            "audio_layers": [],
            "audio_duration_seconds": 0.0,
            "video_duration_seconds": duration,
        }

    audio_debug = mux_generated_audio(video_out, out, duration, actions, elevator_state, video_cfg)
    safe_unlink(video_out)
    return audio_debug


def normalize_video_frames(frames: list[np.ndarray]) -> list[np.ndarray]:
    if not frames:
        raise ValueError("No frames were rendered for the elevator video")
    first = np.asarray(frames[0])
    if first.ndim != 3:
        raise ValueError(f"Expected RGB video frames, got shape {first.shape}")
    target_h, target_w = first.shape[:2]
    target_w -= target_w % 2
    target_h -= target_h % 2
    if target_w < 2 or target_h < 2:
        raise ValueError(f"Video frame is too small: {first.shape}")

    normalized: list[np.ndarray] = []
    for idx, frame in enumerate(frames):
        arr = np.asarray(frame)
        if arr.ndim == 2:
            arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
        elif arr.ndim != 3:
            raise ValueError(f"Frame {idx} has invalid shape {arr.shape}")
        elif arr.shape[2] == 4:
            arr = arr[:, :, :3]
        elif arr.shape[2] != 3:
            raise ValueError(f"Frame {idx} has invalid channel count {arr.shape[2]}")

        if arr.shape[:2] != (target_h, target_w):
            arr = cv2.resize(arr, (target_w, target_h), interpolation=cv2.INTER_AREA)
        if arr.dtype != np.uint8:
            arr = np.nan_to_num(arr, nan=0.0, posinf=255.0, neginf=0.0)
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        normalized.append(np.ascontiguousarray(arr))
    return normalized


def write_metadata(
    meta_path: Path,
    image_path: str | Path,
    out_path: Path,
    box: list[int],
    state: str,
    actions: list[str],
    fps: int,
    depth_path: str | Path | None,
    source_policy: dict[str, str],
    state_debug: dict[str, Any],
    audio_debug: dict[str, Any],
) -> None:
    meta_path.write_text(
        json.dumps(
            {
                "source_image": str(image_path),
                "output_video": str(out_path),
                "door_box_xyxy": box,
                "detected_initial_state": state,
                "actions": actions,
                "source_policy": source_policy,
                "state_debug": state_debug,
                "audio": audio_debug,
                "fps": fps,
                "depth_map_file": str(depth_path) if depth_path else None,
                "realism_features": [
                    "ease-in-out cubic motion",
                    "panel asymmetry",
                    "overshoot and settle",
                    "motion blur",
                    "animated reflection sweep",
                    "light spill and exposure adaptation",
                    "subtle camera shake and grain",
                    "generated mechanical audio",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def write_state_debug(meta_path: Path, state_debug: dict[str, Any]) -> None:
    meta_path.write_text(json.dumps(state_debug, indent=2), encoding="utf-8")


def write_elevator_roi_debug(out_path: str | Path, image_bgr: np.ndarray, depth: np.ndarray | None, debug: dict[str, Any]) -> None:
    out = Path(out_path)
    out_dir = out.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "elevator_roi_debug.json").write_text(json.dumps(debug, indent=2), encoding="utf-8")

    selected = debug.get("selected_elevator_roi")
    if selected:
        overlay = image_bgr.copy()
        x1, y1, x2, y2 = [int(v) for v in selected]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 3)
        cv2.imwrite(str(out_dir / "selected_elevator_roi.png"), overlay)
        cv2.imwrite(str(out_dir / "refined_animation_roi.png"), overlay)

    rejected_overlay = image_bgr.copy()
    for cand in debug.get("rejected_candidates", []):
        box = cand.get("box")
        if not box:
            continue
        x1, y1, x2, y2 = [int(v) for v in box]
        cv2.rectangle(rejected_overlay, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.imwrite(str(out_dir / "rejected_elevator_candidates.png"), rejected_overlay)

    if depth is not None:
        depth_vis = normalize_depth_roi(depth)
        depth_vis = cv2.applyColorMap(np.clip(depth_vis, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        if selected:
            x1, y1, x2, y2 = [int(v) for v in selected]
            cv2.rectangle(depth_vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.imwrite(str(out_dir / "depth_state_debug.png"), depth_vis)


def load_image_bgr(path: str | Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not load image: {path}")
    return img


def load_reference_image(cfg: dict[str, Any], kind: str) -> np.ndarray | None:
    video_cfg = cfg.get("video", {})
    path = video_cfg.get(f"{kind}_reference_image") or video_cfg.get("reference_image")
    if path is None:
        path = cfg.get("input_image") if kind == "closed" else None
    if not path:
        return None
    ref = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if ref is None:
        return None
    return ref


def select_state_images(final_img: np.ndarray, cfg: dict[str, Any], state: str, box: list[int]) -> tuple[np.ndarray, np.ndarray, dict[str, str]]:
    if state == "open":
        closed_ref = load_reference_image(cfg, "closed")
        closed_state = replace_box_with_reference(final_img, closed_ref, box) if closed_ref is not None else final_img
        return (
            final_img,
            closed_state,
            {
                "open_state_image": "final_image",
                "closed_state_image": "closed_reference_image_fitted_to_door_box" if closed_ref is not None else "final_image_fallback",
                "open_reference_image_used": "false",
                "closed_reference_image_used": "true" if closed_ref is not None else "false",
            },
        )

    open_ref = load_reference_image(cfg, "open")
    open_state = replace_box_with_reference(final_img, open_ref, box) if open_ref is not None else final_img
    return (
        open_state,
        final_img,
        {
            "open_state_image": "open_reference_image_fitted_to_door_box" if open_ref is not None else "final_image_fallback",
            "closed_state_image": "final_image",
            "open_reference_image_used": "true" if open_ref is not None else "false",
            "closed_reference_image_used": "false",
        },
    )


def replace_box_with_reference(final_img: np.ndarray, reference_img: np.ndarray, box: list[int]) -> np.ndarray:
    x1, y1, x2, y2 = box
    out = final_img.copy()
    target_h = y2 - y1
    target_w = x2 - x1
    if target_h <= 1 or target_w <= 1:
        return out
    out[y1:y2, x1:x2] = fit_reference_to_size(reference_img, target_w, target_h)
    return out


def fit_reference_to_size(reference_img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    ref_h, ref_w = reference_img.shape[:2]
    if ref_h <= 0 or ref_w <= 0:
        return np.zeros((target_h, target_w, 3), dtype=np.uint8)

    cover_scale = max(target_w / ref_w, target_h / ref_h)
    cover_w = max(1, int(round(ref_w * cover_scale)))
    cover_h = max(1, int(round(ref_h * cover_scale)))
    cover = cv2.resize(reference_img, (cover_w, cover_h), interpolation=cv2.INTER_AREA)
    cx = max(0, (cover_w - target_w) // 2)
    cy = max(0, (cover_h - target_h) // 2)
    background = cover[cy : cy + target_h, cx : cx + target_w].copy()
    if background.shape[:2] != (target_h, target_w):
        background = cv2.resize(background, (target_w, target_h), interpolation=cv2.INTER_AREA)
    background = cv2.GaussianBlur(background, (31, 31), 0)

    contain_scale = min(target_w / ref_w, target_h / ref_h)
    contain_w = max(1, int(round(ref_w * contain_scale)))
    contain_h = max(1, int(round(ref_h * contain_scale)))
    contain = cv2.resize(reference_img, (contain_w, contain_h), interpolation=cv2.INTER_AREA)
    ox = (target_w - contain_w) // 2
    oy = (target_h - contain_h) // 2
    background[oy : oy + contain_h, ox : ox + contain_w] = contain
    return background


def reference_usage_debug(source_policy: dict[str, str]) -> dict[str, str]:
    return {
        "branch_rule": (
            "final_image_open_uses_closed_reference_only"
            if source_policy.get("open_state_image") == "final_image"
            else "final_image_closed_uses_open_reference_only"
        )
    }


def enforce_closed_branch_endpoints(
    frames: list[np.ndarray],
    final_img_bgr: np.ndarray,
    actions: list[tuple[str, float]],
    fps: int,
) -> None:
    if not frames:
        return

    exact_closed_rgb = cv2.cvtColor(final_img_bgr, cv2.COLOR_BGR2RGB)
    frames[0] = exact_closed_rgb.copy()

    if actions and actions[-1][0] == "close":
        end_hold_frames = max(4, int(fps * END_HOLD_SECONDS))
        for idx in range(max(0, len(frames) - end_hold_frames), len(frames)):
            frames[idx] = exact_closed_rgb.copy()
        frames[-1] = exact_closed_rgb.copy()


def load_depth(path: str | Path, hw: tuple[int, int]) -> np.ndarray | None:
    p = Path(path)
    if not p.exists():
        return None
    data = np.load(p)
    depth = data["depth_relative"] if "depth_relative" in data else data[list(data.keys())[0]]
    depth = cv2.resize(depth.astype(np.float32), (hw[1], hw[0]), interpolation=cv2.INTER_CUBIC)
    return (depth - float(depth.min())) / max(float(depth.max() - depth.min()), 1e-6)


def scaled_box(box: list[float], src_w: int, src_h: int, dst_w: int, dst_h: int) -> list[int]:
    sx = dst_w / max(src_w, 1)
    sy = dst_h / max(src_h, 1)
    x1, y1, x2, y2 = box
    return [
        int(np.clip(round(x1 * sx), 0, dst_w - 1)),
        int(np.clip(round(y1 * sy), 0, dst_h - 1)),
        int(np.clip(round(x2 * sx), 1, dst_w)),
        int(np.clip(round(y2 * sy), 1, dst_h)),
    ]


def detect_door_box(
    img: np.ndarray,
    detections: dict[str, Any],
    geometry: dict[str, Any],
    depth_map: np.ndarray | None = None,
    cfg: dict[str, Any] | None = None,
    debug: dict[str, Any] | None = None,
) -> list[int]:
    selected, roi_debug = select_best_elevator_roi(img, detections, depth_map, geometry, cfg)
    if debug is not None:
        debug.update(roi_debug)
    if selected is not None:
        return selected

    h, w = img.shape[:2]
    inferred = infer_elevator_box_from_image(img, detections, geometry)
    return clamp_box(inferred or fallback_door_box(img), w, h)


def select_best_elevator_roi(
    image: np.ndarray,
    detections: dict[str, Any],
    depth_map: np.ndarray | None = None,
    geometry: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[int] | None, dict[str, Any]]:
    h, w = image.shape[:2]
    geometry = geometry or {}
    meta = detections.get("metadata", {})
    src_w = int(meta.get("image_width", geometry.get("metadata", {}).get("image_width", w)))
    src_h = int(meta.get("image_height", geometry.get("metadata", {}).get("image_height", h)))
    center_hint = _door_center_hint(w, detections, geometry)
    labels = (
        "elevator door",
        "elevator doors",
        "door frame",
        "elevator frame",
        "elevator opening",
        "elevator interior",
        "lift entrance",
        "elevator wall",
    )
    raw_candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    scored: list[tuple[float, list[int], dict[str, Any], str]] = []

    for det in detections.get("detections", []):
        phrase = str(det.get("phrase", "")).lower()
        if not any(label in phrase for label in labels):
            continue
        box = clamp_box(scaled_box(det["box_xyxy"], src_w, src_h, w, h), w, h)
        candidate = {
            "box": box,
            "phrase": phrase,
            "score": float(det.get("score", 0.0)),
        }
        raw_candidates.append(candidate)
        valid, reason = validate_elevator_candidate(box, phrase, w, h, center_hint)
        edge_score, refined = edge_alignment_score_and_refined_roi(image, box, cfg)
        candidate["edge_score"] = edge_score
        candidate["refined_box"] = refined
        if not valid:
            candidate["reason"] = reason
            rejected.append(candidate)
            continue
        depth_score = depth_roi_score(depth_map, refined) if depth_map is not None else 0.0
        interior_score = interior_overlap_score(refined, detections, src_w, src_h, w, h)
        x1, y1, x2, y2 = refined
        bw, bh = x2 - x1, y2 - y1
        aspect_score = min(1.0, max(0.0, (bh / max(bw, 1) - 1.15) / 2.2))
        center_score = 1.0 - min(1.0, abs(((x1 + x2) * 0.5) - center_hint) / max(w * 0.35, 1.0))
        area_ratio = (bw * bh) / max(w * h, 1)
        area_score = 1.0 - min(1.0, abs(area_ratio - 0.34) / 0.34)
        score = (
            float(det.get("score", 0.0)) * 1.4
            + edge_score * 1.25
            + center_score * 0.75
            + aspect_score * 0.55
            + area_score * 0.35
            + depth_score * 0.40
            + interior_score * 0.50
        )
        scored.append((score, refined, candidate, "geometry_validated_detection"))

    inferred = infer_elevator_box_from_image(image, detections, geometry)
    if inferred is not None:
        inferred = clamp_box(inferred, w, h)
        edge_score, refined = edge_alignment_score_and_refined_roi(image, inferred, cfg)
        score = 1.10 + edge_score * 1.35 + depth_roi_score(depth_map, refined) * 0.30
        scored.append(
            (
                score,
                refined,
                {
                    "box": inferred,
                    "phrase": "image_structure_fallback",
                    "score": score,
                    "edge_score": edge_score,
                    "refined_box": refined,
                },
                "image_edges_fallback",
            )
        )

    if not scored:
        return None, {"raw_candidates": raw_candidates, "rejected_candidates": rejected}

    selected_score, selected_box, selected_candidate, selected_reason = max(scored, key=lambda item: item[0])
    return selected_box, {
        "raw_candidates": raw_candidates,
        "rejected_candidates": rejected,
        "selected_elevator_roi": selected_box,
        "selected_score": float(selected_score),
        "selected_reason": selected_reason,
        "selected_candidate": selected_candidate,
    }


def validate_elevator_candidate(box: list[int], phrase: str, width: int, height: int, center_hint: float) -> tuple[bool, str]:
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    area_ratio = (bw * bh) / max(width * height, 1)
    if bw < width * 0.14 or bh < height * 0.32:
        return False, "too small for elevator opening"
    if bw > width * 0.72:
        return False, "too wide compared to visible opening"
    if area_ratio > 0.68:
        return False, "too much wall / oversized area"
    if y1 < height * 0.02 and "ceiling" not in phrase:
        return False, "starts too high above elevator opening"
    if y2 > height * 0.98:
        return False, "extends too far below threshold"
    if abs(((x1 + x2) * 0.5) - center_hint) > width * 0.36:
        return False, "too far left/right from expected opening"
    if bh / max(bw, 1) < 1.05:
        return False, "not a vertical/tall elevator ROI"
    return True, "valid"


def edge_alignment_score_and_refined_roi(
    image: np.ndarray,
    box: list[int],
    cfg: dict[str, Any] | None = None,
) -> tuple[float, list[int]]:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = clamp_box(box, w, h)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    sx = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    sy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    bw, bh = x2 - x1, y2 - y1
    search_pad_x = max(8, int(bw * 0.16))
    search_pad_y = max(8, int(bh * 0.10))
    y_a, y_b = max(0, y1 + int(bh * 0.08)), min(h, y2 - int(bh * 0.05))
    left_range = (max(0, x1 - search_pad_x), min(w, x1 + search_pad_x))
    right_range = (max(0, x2 - search_pad_x), min(w, x2 + search_pad_x))
    left_x = _best_projection_index(sx[y_a:y_b].mean(axis=0), left_range[0], left_range[1], x1)
    right_x = _best_projection_index(sx[y_a:y_b].mean(axis=0), right_range[0], right_range[1], x2)
    if right_x - left_x < max(12, int(w * 0.08)):
        left_x, right_x = x1, x2

    x_a, x_b = max(0, left_x + int((right_x - left_x) * 0.08)), min(w, right_x - int((right_x - left_x) * 0.08))
    top_y = _best_projection_index(sy[:, x_a:x_b].mean(axis=1), max(0, y1 - search_pad_y), min(h, y1 + search_pad_y * 2), y1)
    bottom_y = _best_projection_index(sy[:, x_a:x_b].mean(axis=1), max(0, y2 - search_pad_y * 2), min(h, y2 + search_pad_y), y2)
    refined = clamp_box([left_x, top_y, right_x, bottom_y], w, h)
    if cfg:
        max_wall_fraction = float(cfg.get("video", {}).get("max_wall_fraction_in_roi", 0.15))
        refined = shrink_oversized_roi(gray, refined, max_wall_fraction)

    rx1, ry1, rx2, ry2 = refined
    v_edge = float(sx[max(0, ry1):min(h, ry2), [max(0, rx1), min(w - 1, rx2 - 1)]].mean()) if ry2 > ry1 else 0.0
    h_edge = float(sy[[max(0, ry1), min(h - 1, ry2 - 1)], max(0, rx1):min(w, rx2)].mean()) if rx2 > rx1 else 0.0
    global_edge = float(np.mean(sx) + np.mean(sy) + 1e-6)
    return float(np.clip((v_edge + h_edge) / global_edge / 7.5, 0.0, 1.0)), refined


def _best_projection_index(projection: np.ndarray, start: int, end: int, default: int) -> int:
    start = max(0, min(len(projection) - 1, int(start)))
    end = max(start + 1, min(len(projection), int(end)))
    local = projection[start:end]
    if local.size == 0 or float(local.max()) <= 0:
        return int(default)
    return int(start + np.argmax(local))


def shrink_oversized_roi(gray: np.ndarray, box: list[int], max_wall_fraction: float) -> list[int]:
    del max_wall_fraction
    h, w = gray.shape[:2]
    x1, y1, x2, y2 = box
    bw = x2 - x1
    if bw <= 12:
        return box
    crop = gray[y1:y2, x1:x2]
    if crop.size == 0:
        return box
    sx = np.abs(cv2.Sobel(crop, cv2.CV_32F, 1, 0, ksize=3)).mean(axis=0)
    if sx.size < 10:
        return box
    threshold = max(float(np.percentile(sx, 78)), float(sx.mean() + sx.std() * 0.25))
    strong = np.where(sx >= threshold)[0]
    if len(strong) >= 2:
        left = int(strong[0])
        right = int(strong[-1])
        if right - left >= bw * 0.55:
            x1 = max(0, x1 + left)
            x2 = min(w, x1 + (right - left))
    return clamp_box([x1, y1, x2, y2], w, h)


def depth_roi_score(depth_map: np.ndarray | None, box: list[int]) -> float:
    if depth_map is None:
        return 0.0
    state, dbg = classify_elevator_state_from_depth(depth_map, box)
    if state == "open":
        return 1.0
    contrast = abs(float(dbg.get("depth_contrast") or 0.0))
    return float(np.clip(contrast / 42.0, 0.0, 0.7))


def interior_overlap_score(box: list[int], detections: dict[str, Any], src_w: int, src_h: int, width: int, height: int) -> float:
    interior_terms = ("elevator ceiling", "elevator wall", "elevator floor", "handrail", "mirror", "ventilation grille", "light fixture")
    best = 0.0
    for det in detections.get("detections", []):
        phrase = str(det.get("phrase", "")).lower()
        if not any(term in phrase for term in interior_terms):
            continue
        det_box = scaled_box(det["box_xyxy"], src_w, src_h, width, height)
        best = max(best, box_iou(box, det_box))
    return float(np.clip(best * 2.0, 0.0, 1.0))


def box_iou(a: list[int], b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / max(1, area_a + area_b - inter)


def correct_open_elevator_box_top(box: list[int], detections: dict[str, Any], geometry: dict[str, Any], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = box
    if y1 < height * 0.35:
        return box

    meta = detections.get("metadata", {})
    src_w = int(meta.get("image_width", geometry.get("metadata", {}).get("image_width", width)))
    src_h = int(meta.get("image_height", geometry.get("metadata", {}).get("image_height", height)))
    center_x = (x1 + x2) * 0.5
    candidates: list[tuple[float, int]] = []
    for det in detections.get("detections", []):
        phrase = det.get("phrase", "").lower()
        if "elevator ceiling" not in phrase and "door frame" not in phrase:
            continue
        cx1, cy1, cx2, cy2 = scaled_box(det["box_xyxy"], src_w, src_h, width, height)
        if cy2 >= y1 or cy2 > height * 0.45:
            continue
        if cx1 <= center_x <= cx2 or overlap_ratio((x1, x2), (cx1, cx2)) > 0.35:
            candidates.append((float(det.get("score", 0.0)), cy2))

    if not candidates:
        return box
    _, corrected_top = max(candidates, key=lambda item: item[0])
    return clamp_box([x1, max(0, corrected_top - max(6, int(height * 0.006))), x2, y2], width, height)


def overlap_ratio(a: tuple[float, float], b: tuple[float, float]) -> float:
    ax1, ax2 = a
    bx1, bx2 = b
    overlap = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    return overlap / max(1.0, ax2 - ax1)


def select_best_elevator_detection(detections: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for det in detections.get("detections", []):
        phrase = det.get("phrase", "").lower()
        if any(term in phrase for term in ("elevator door", "elevator doors", "door frame", "lift entrance")):
            candidates.append(det)
    if not candidates:
        return None
    return max(candidates, key=lambda det: float(det.get("score", 0)))


def classify_elevator_state(
    elevator_json: dict[str, Any],
    depth_map: np.ndarray | None,
    scaled_door_box: list[int],
    img: np.ndarray,
) -> tuple[str, dict[str, Any]]:
    best_det = select_best_elevator_detection(elevator_json)
    debug: dict[str, Any] = {
        "elevator_state": "unknown",
        "state_source": "unknown",
        "depth_dark_ratio": None,
        "depth_contrast": None,
    }

    detections = elevator_json.get("detections", [])
    interior_labels = {
        "elevator ceiling",
        "elevator wall",
        "elevator floor",
        "handrail",
        "mirror",
        "ventilation grille",
        "light fixture",
        "speaker",
        "security camera",
    }
    has_interior_detection = any(
        _is_reliable_interior_detection(det, elevator_json, scaled_door_box, img.shape[:2], interior_labels)
        for det in detections
    )

    image_state = classify_state(img, scaled_door_box)
    if depth_map is not None:
        depth_state, depth_debug = classify_elevator_state_from_depth(depth_map, scaled_door_box)
        debug.update(depth_debug)
        if depth_state == "open":
            debug["elevator_state"] = depth_state
            debug["state_source"] = "depth"
            return depth_state, debug
        if depth_state == "closed" and not (
            has_interior_detection and image_state == "open" and abs(float(depth_debug.get("depth_contrast") or 0.0)) < 6.0
        ):
            debug["elevator_state"] = depth_state
            debug["state_source"] = "depth"
            return depth_state, debug

    if has_interior_detection:
        debug["elevator_state"] = "open"
        debug["state_source"] = "interior_detection_fallback"
        return "open", debug

    debug["elevator_state"] = image_state
    debug["state_source"] = "image_fallback" if best_det is not None else "image_fallback_no_detection"
    return image_state, debug


def _scaled_detection_box(det: dict[str, Any], detections: dict[str, Any], fallback_box: list[int], hw: tuple[int, int]) -> list[int]:
    if "box_xyxy" not in det:
        return fallback_box
    h, w = hw
    meta = detections.get("metadata", {})
    src_w = int(meta.get("image_width", w))
    src_h = int(meta.get("image_height", h))
    return scaled_box(det["box_xyxy"], src_w, src_h, w, h)


def _is_reliable_interior_detection(
    det: dict[str, Any],
    detections: dict[str, Any],
    roi: list[int],
    hw: tuple[int, int],
    interior_labels: set[str],
) -> bool:
    phrase = str(det.get("phrase", "")).strip().lower()
    if phrase not in interior_labels:
        return False
    box = _scaled_detection_box(det, detections, roi, hw)
    if box_iou(box, roi) <= 0.05:
        return False
    rx1, ry1, rx2, ry2 = roi
    bx1, by1, bx2, by2 = box
    roi_area = max(1, (rx2 - rx1) * (ry2 - ry1))
    box_area = max(1, (bx2 - bx1) * (by2 - by1))
    if "elevator wall" in phrase and box_area > roi_area * 0.65:
        return False
    cx = (bx1 + bx2) * 0.5
    cy = (by1 + by2) * 0.5
    return rx1 <= cx <= rx2 and ry1 <= cy <= ry2


def classify_elevator_state_from_depth(
    depth_map: np.ndarray,
    door_box: list[float],
    dark_ratio_threshold: float = 0.28,
    contrast_threshold: float = 18.0,
) -> tuple[str, dict[str, Any]]:
    if depth_map.ndim == 3:
        depth_gray = cv2.cvtColor(depth_map, cv2.COLOR_RGB2GRAY)
    else:
        depth_gray = depth_map.copy()

    depth_gray = np.nan_to_num(depth_gray.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    finite_max = float(np.max(depth_gray)) if depth_gray.size else 0.0
    if finite_max <= 1.5:
        depth_gray = depth_gray * 255.0

    h, w = depth_gray.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in door_box]
    x1 = max(0, min(w - 1, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h - 1, y1))
    y2 = max(0, min(h, y2))
    debug: dict[str, Any] = {
        "depth_box_xyxy": [x1, y1, x2, y2],
        "depth_dark_ratio": None,
        "depth_contrast": None,
        "depth_center_median": None,
        "depth_border_median": None,
    }

    roi = depth_gray[y1:y2, x1:x2]
    if roi.size == 0:
        return "unknown", debug
    roi = normalize_depth_roi(roi)

    rh, rw = roi.shape[:2]
    cy1, cy2 = int(rh * 0.18), int(rh * 0.88)
    cx1, cx2 = int(rw * 0.22), int(rw * 0.78)
    center = roi[cy1:cy2, cx1:cx2]
    border_mask = np.ones((rh, rw), dtype=bool)
    border_mask[cy1:cy2, cx1:cx2] = False
    border = roi[border_mask]

    if center.size == 0 or border.size == 0:
        return "unknown", debug

    center_median = float(np.median(center))
    border_median = float(np.median(border))
    dark_threshold = float(np.percentile(roi, 25))
    dark_ratio = float(np.mean(center <= dark_threshold))
    contrast = border_median - center_median
    debug.update(
        {
            "depth_dark_ratio": dark_ratio,
            "depth_contrast": contrast,
            "depth_center_median": center_median,
            "depth_border_median": border_median,
            "depth_dark_threshold": dark_threshold,
        }
    )

    reverse_dark_ratio = float(np.mean(center >= float(np.percentile(roi, 75))))
    abs_contrast = abs(contrast)
    debug["depth_reverse_dark_ratio"] = reverse_dark_ratio
    debug["depth_abs_contrast"] = abs_contrast

    if (dark_ratio >= dark_ratio_threshold and contrast >= contrast_threshold) or (
        reverse_dark_ratio >= dark_ratio_threshold and contrast <= -contrast_threshold
    ):
        return "open", debug
    if dark_ratio < dark_ratio_threshold * 0.90 and reverse_dark_ratio < dark_ratio_threshold * 0.90:
        return "closed", debug
    return "unknown", debug


def normalize_depth_roi(roi: np.ndarray) -> np.ndarray:
    roi = np.nan_to_num(roi.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    lo = float(np.percentile(roi, 2))
    hi = float(np.percentile(roi, 98))
    if hi - lo < 1e-6:
        return roi
    return np.clip((roi - lo) / (hi - lo), 0.0, 1.0) * 255.0


def detection_debug(
    best_det: dict[str, Any] | None,
    detections: dict[str, Any],
    geometry: dict[str, Any],
    hw: tuple[int, int],
) -> dict[str, Any]:
    if best_det is None:
        return {
            "selected_detection_phrase": None,
            "selected_detection_score": None,
            "selected_detection_box_xyxy": None,
        }

    h, w = hw
    meta = detections.get("metadata", {})
    src_w = int(meta.get("image_width", geometry.get("metadata", {}).get("image_width", w)))
    src_h = int(meta.get("image_height", geometry.get("metadata", {}).get("image_height", h)))
    return {
        "selected_detection_phrase": best_det.get("phrase"),
        "selected_detection_score": float(best_det.get("score", 0.0)),
        "selected_detection_box_xyxy": best_det.get("box_xyxy"),
        "selected_detection_scaled_box_xyxy": scaled_box(best_det["box_xyxy"], src_w, src_h, w, h),
    }


def infer_elevator_box_from_image(img: np.ndarray, detections: dict[str, Any], geometry: dict[str, Any]) -> list[int] | None:
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    center_hint = _door_center_hint(w, detections, geometry)

    sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    y1_band, y2_band = int(h * 0.18), int(h * 0.82)
    projection = sobel_x[y1_band:y2_band].mean(axis=0)
    projection = cv2.GaussianBlur(projection.reshape(1, -1), (51, 1), 0).ravel()
    projection[: int(w * 0.08)] = 0
    projection[int(w * 0.92) :] = 0

    left_candidates = _top_projection_peaks(projection, int(w * 0.12), int(center_hint - w * 0.08), 10)
    right_candidates = _top_projection_peaks(projection, int(center_hint + w * 0.08), int(w * 0.90), 10)
    best_pair: tuple[float, int, int] | None = None
    for lx in left_candidates:
        for rx in right_candidates:
            box_w = rx - lx
            if box_w < w * 0.22 or box_w > w * 0.62:
                continue
            cx = (lx + rx) * 0.5
            score = projection[lx] + projection[rx] - abs(cx - center_hint) * 0.08
            if best_pair is None or score > best_pair[0]:
                best_pair = (float(score), int(lx), int(rx))
    if best_pair is None:
        return None

    _, x1, x2 = best_pair
    x_pad = max(8, int((x2 - x1) * 0.035))
    x1 = max(0, x1 - x_pad)
    x2 = min(w, x2 + x_pad)

    crop = gray[:, x1:x2]
    sobel_y = np.abs(cv2.Sobel(crop, cv2.CV_32F, 0, 1, ksize=3))
    hproj = sobel_y.mean(axis=1)
    hproj = cv2.GaussianBlur(hproj.reshape(-1, 1), (1, 41), 0).ravel()
    top_y = _best_y_peak(hproj, int(h * 0.15), int(h * 0.45), default=int(h * 0.24))
    bottom_y = _best_y_peak(hproj, int(h * 0.65), int(h * 0.88), default=int(h * 0.76))
    y_pad_top = max(6, int((bottom_y - top_y) * 0.02))
    y_pad_bottom = max(8, int((bottom_y - top_y) * 0.04))
    return [x1, max(0, top_y - y_pad_top), x2, min(h, bottom_y + y_pad_bottom)]


def _door_center_hint(width: int, detections: dict[str, Any], geometry: dict[str, Any]) -> float:
    del geometry
    panels = [
        det
        for det in detections.get("detections", [])
        if "button panel" in det.get("phrase", "").lower() or "call button" in det.get("phrase", "").lower()
    ]
    if panels:
        panel = max(panels, key=lambda d: float(d.get("score", 0)))
        x1, _, x2, _ = [float(v) for v in panel["box_xyxy"]]
        pcx = (x1 + x2) * 0.5
        if pcx < width * 0.45:
            return min(width * 0.72, x2 + width * 0.28)
        if pcx > width * 0.55:
            return max(width * 0.28, x1 - width * 0.28)
    return width * 0.5


def _top_projection_peaks(projection: np.ndarray, start: int, end: int, limit: int) -> list[int]:
    start = max(0, start)
    end = min(len(projection), end)
    if end <= start:
        return []
    values = projection[start:end].copy()
    peaks: list[int] = []
    min_sep = max(8, len(projection) // 40)
    for _ in range(limit):
        idx = int(np.argmax(values))
        if values[idx] <= 0:
            break
        x = start + idx
        peaks.append(x)
        lo = max(0, idx - min_sep)
        hi = min(len(values), idx + min_sep + 1)
        values[lo:hi] = 0
    return peaks


def _best_y_peak(projection: np.ndarray, start: int, end: int, default: int) -> int:
    start = max(0, start)
    end = min(len(projection), end)
    if end <= start:
        return default
    local = projection[start:end]
    if float(local.max()) <= 0:
        return default
    return int(start + np.argmax(local))


def fallback_door_box(img: np.ndarray) -> list[int]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 25))
    vertical = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = img.shape[:2]
    best = None
    best_score = -1e18
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bh < h * 0.35 or bw < w * 0.08:
            continue
        score = bw * bh * min(bh / max(bw, 1), 4) - abs((x + bw / 2) - w / 2) * h
        if score > best_score:
            best_score = score
            best = [x, y, x + bw, y + bh]
    return best or [int(w * 0.28), int(h * 0.20), int(w * 0.72), int(h * 0.86)]


def clamp_box(box: list[int], w: int, h: int) -> list[int]:
    x1, y1, x2, y2 = box
    x1 = int(np.clip(x1, 0, w - 2))
    y1 = int(np.clip(y1, 0, h - 2))
    x2 = int(np.clip(x2, x1 + 2, w))
    y2 = int(np.clip(y2, y1 + 2, h))
    return [x1, y1, x2, y2]


def classify_state(img: np.ndarray, box: list[int]) -> str:
    x1, y1, x2, y2 = box
    crop = img[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    center = gray[:, int(w * 0.41) : int(w * 0.59)]
    left = gray[:, int(w * 0.08) : int(w * 0.30)]
    right = gray[:, int(w * 0.70) : int(w * 0.92)]
    side = np.concatenate([left.reshape(-1), right.reshape(-1)])
    mean_delta = abs(float(center.mean()) - float(side.mean()))
    variance_ratio = float(center.std() / max(np.std(side), 1.0))
    edges = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    vertical_energy = np.mean(np.abs(edges), axis=0)
    middle_energy = float(vertical_energy[int(w * 0.38) : int(w * 0.62)].mean())
    outer_energy = float(np.r_[vertical_energy[int(w * 0.12) : int(w * 0.30)], vertical_energy[int(w * 0.70) : int(w * 0.88)]].mean())
    open_score = int(mean_delta > 22) + int(variance_ratio > 1.28 or variance_ratio < 0.72) + int(middle_energy > outer_energy * 1.18)
    open_score += int(_center_gap_score(gray) > 0.58)
    return "open" if open_score >= 2 else "closed"


def _center_gap_score(gray: np.ndarray) -> float:
    h, w = gray.shape
    mid = w // 2
    band = gray[int(h * 0.08) : int(h * 0.92), max(0, mid - w // 8) : min(w, mid + w // 8)]
    if band.size == 0:
        return 0.0
    col_std = band.std(axis=0)
    col_mean = band.mean(axis=0)
    active = (col_std > max(8.0, float(gray.std()) * 0.42)) | (np.abs(col_mean - float(gray.mean())) > max(14.0, float(gray.std()) * 0.50))
    return float(active.mean())


def ease_in_out_cubic(t: float) -> float:
    t = float(np.clip(t, 0.0, 1.0))
    if t < 0.5:
        return 4 * t * t * t
    return 1 - pow(-2 * t + 2, 3) / 2


def motor_profile(t: float, action: str) -> float:
    delay = 0.035 if action == "open" else 0.055
    t = max(0.0, (t - delay) / (1.0 - delay))
    eased = ease_in_out_cubic(t)
    if t > 0.92:
        eased += math.sin((t - 0.92) / 0.08 * math.pi) * (0.010 if action == "open" else -0.008)
    if t < 0.08:
        eased *= 0.98 + 0.02 * math.sin(t / 0.08 * math.pi * 3)
    return float(np.clip(eased, 0.0, 1.0))


def build_panel_texture(img: np.ndarray, box: list[int], state: str, depth: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    x1, y1, x2, y2 = box
    crop = img[y1:y2, x1:x2].copy()
    h, w = crop.shape[:2]
    half = w // 2
    if state == "closed":
        left, right = crop[:, :half].copy(), crop[:, half:].copy()
    else:
        strip = max(8, int(w * 0.18))
        left = cv2.resize(crop[:, :strip], (half, h), interpolation=cv2.INTER_LINEAR)
        right = cv2.resize(crop[:, w - strip :], (w - half, h), interpolation=cv2.INTER_LINEAR)
    if depth is not None:
        local = depth[y1:y2, x1:x2]
        weight = cv2.GaussianBlur(local, (0, 0), 5)
        left = np.clip(left.astype(np.float32) * (0.98 + 0.035 * weight[:, :half, None]), 0, 255).astype(np.uint8)
        right = np.clip(right.astype(np.float32) * (0.98 + 0.035 * weight[:, half:, None]), 0, 255).astype(np.uint8)
    return stabilize_metal(left, -1), stabilize_metal(right, 1)


def stabilize_metal(panel: np.ndarray, direction: int) -> np.ndarray:
    h, w = panel.shape[:2]
    x_grad = np.linspace(0.92, 1.08, w, dtype=np.float32)
    if direction > 0:
        x_grad = x_grad[::-1]
    y_grad = np.linspace(0.96, 1.04, h, dtype=np.float32)[:, None]
    gain = (x_grad[None, :] * y_grad)[:, :, None]
    return np.clip(panel.astype(np.float32) * gain, 0, 255).astype(np.uint8)


def build_reveal_scene(img: np.ndarray, reference_img: np.ndarray, box: list[int], state: str, target_action: str, depth: np.ndarray | None) -> np.ndarray:
    x1, y1, x2, y2 = box
    crop = img[y1:y2, x1:x2].copy()
    ref_crop = reference_img[y1:y2, x1:x2].copy()
    h, w = crop.shape[:2]
    if state == "open":
        return cv2.GaussianBlur(ref_crop, (3, 3), 0)
    scene = cv2.GaussianBlur(ref_crop, (31, 31), 0)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    vignette = 0.78 + 0.26 * (1 - np.abs(xx)) * (1 - yy * 0.35)
    cool_light = np.dstack([np.full((h, w), 1.10, np.float32), np.full((h, w), 1.04, np.float32), np.full((h, w), 0.96, np.float32)])
    if depth is not None:
        local = depth[y1:y2, x1:x2]
        vignette *= 0.96 + 0.08 * cv2.GaussianBlur(local, (0, 0), 8)
    scene = np.clip(scene.astype(np.float32) * vignette[:, :, None] * cool_light, 0, 255).astype(np.uint8)
    scene = add_soft_cabin_depth(scene)
    return scene


def add_soft_cabin_depth(scene: np.ndarray) -> np.ndarray:
    h, w = scene.shape[:2]
    out = scene.astype(np.float32)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    center_light = 1.0 + 0.10 * (1.0 - np.abs(np.linspace(-1, 1, w, dtype=np.float32))[None, :]) * (1.0 - yy * 0.35)
    floor_tint = np.clip((yy - 0.72) / 0.28, 0, 1)
    out *= center_light[:, :, None]
    out[:, :, 0] *= 1.0 - floor_tint * 0.06
    out[:, :, 1] *= 1.0 - floor_tint * 0.06
    out[:, :, 2] *= 1.0 - floor_tint * 0.04
    return np.clip(out, 0, 255).astype(np.uint8)


def alpha_blit(dst: np.ndarray, src: np.ndarray, x: int, y: int, alpha: np.ndarray | None = None) -> None:
    h, w = src.shape[:2]
    dst_h, dst_w = dst.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(dst_w, x + w), min(dst_h, y + h)
    if x2 <= x1 or y2 <= y1:
        return
    sx1, sy1 = x1 - x, y1 - y
    sx2, sy2 = sx1 + (x2 - x1), sy1 + (y2 - y1)
    patch = src[sy1:sy2, sx1:sx2]
    if alpha is None:
        dst[y1:y2, x1:x2] = patch
        return
    a = alpha[sy1:sy2, sx1:sx2].astype(np.float32)[:, :, None]
    dst[y1:y2, x1:x2] = (patch.astype(np.float32) * a + dst[y1:y2, x1:x2].astype(np.float32) * (1 - a)).astype(np.uint8)


def apply_motion_blur(panel: np.ndarray, velocity: float) -> np.ndarray:
    if abs(velocity) < 0.006:
        return panel
    kernel_w = int(np.clip(abs(velocity) * 52, 3, 17))
    if kernel_w % 2 == 0:
        kernel_w += 1
    return cv2.GaussianBlur(panel, (kernel_w, 1), 0)


def edge_alpha(shape: tuple[int, int], fade_left: bool) -> np.ndarray:
    h, w = shape
    alpha = np.ones((h, w), dtype=np.float32)
    fade = max(3, min(18, w // 12))
    ramp = np.linspace(0.70, 1.0, fade, dtype=np.float32)
    if fade_left:
        alpha[:, :fade] = ramp
    else:
        alpha[:, -fade:] = ramp[::-1]
    return alpha


def render_frame(
    base: np.ndarray,
    box: list[int],
    panels: tuple[np.ndarray, np.ndarray],
    reveal_scene: np.ndarray,
    progress: float,
    action: str,
    frame_index: int,
    previous_progress: float,
    depth: np.ndarray | None,
    preserve_outside_roi: bool = True,
) -> np.ndarray:
    x1, y1, x2, y2 = box
    door_w = x2 - x1
    door_h = y2 - y1
    half = door_w // 2
    opening = progress if action == "open" else 1 - progress
    offset = int(round(opening * half * 0.965))
    velocity = progress - previous_progress
    asym_delay_px = 3 if action == "open" else -2
    micro = int(round(math.sin(frame_index * 1.73) * max(0.0, abs(velocity)) * 7))
    vertical_jitter = int(round(math.sin(frame_index * 0.91) * max(0.0, abs(velocity)) * 2))

    frame = base.copy()
    roi = reveal_scene.copy()
    left_panel, right_panel = panels
    left = apply_motion_blur(left_panel, velocity)
    right = apply_motion_blur(right_panel, velocity * 0.94)

    lx = -offset + micro
    rx = half + offset + asym_delay_px - micro
    alpha_l = edge_alpha(left.shape[:2], fade_left=False)
    alpha_r = edge_alpha(right.shape[:2], fade_left=True)
    alpha_blit(roi, left, lx, vertical_jitter, alpha_l)
    alpha_blit(roi, right, rx, -vertical_jitter, alpha_r)

    roi = add_soft_contact_shading(roi, opening)

    frame[y1:y2, x1:x2] = roi
    frame = apply_lighting(frame, box, progress, action, depth)
    frame = apply_reflection_sweep(frame, box, progress, action)
    frame = apply_environment_reaction(frame, box, progress, action)
    frame = add_camera_imperfections(frame, frame_index)
    if preserve_outside_roi:
        restored = base.copy()
        restored[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
        frame = restored
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def add_soft_contact_shading(roi: np.ndarray, opening: float) -> np.ndarray:
    if opening > 0.12:
        return roi
    h, w = roi.shape[:2]
    out = roi.astype(np.float32)
    center = w // 2
    x = np.arange(w, dtype=np.float32)
    seam = np.exp(-0.5 * ((x - center) / max(1.5, w * 0.004)) ** 2)[None, :]
    amount = 0.045 * (1.0 - opening / 0.12)
    out *= 1.0 - seam[:, :, None] * amount
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_lighting(frame: np.ndarray, box: list[int], progress: float, action: str, depth: np.ndarray | None) -> np.ndarray:
    x1, y1, x2, y2 = box
    reveal = progress if action == "open" else 1 - progress
    overlay = frame.copy()
    spill = int(34 * reveal)
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (spill, spill, spill), -1)
    if depth is not None:
        depth_light = cv2.GaussianBlur(depth, (0, 0), 12)[:, :, None]
        overlay = np.clip(overlay.astype(np.float32) + depth_light * reveal * 8, 0, 255).astype(np.uint8)
    frame = cv2.addWeighted(overlay, 0.16, frame, 0.84, 0)
    exposure = 1.0 + 0.040 * reveal - 0.018 * (1 - reveal)
    return np.clip(frame.astype(np.float32) * exposure, 0, 255).astype(np.uint8)


def apply_environment_reaction(frame: np.ndarray, box: list[int], progress: float, action: str) -> np.ndarray:
    x1, y1, x2, y2 = box
    reveal = progress if action == "open" else 1 - progress
    h, w = frame.shape[:2]
    out = frame.astype(np.float32)
    floor_y = min(h - 1, y2)
    floor = out[floor_y:h]
    if floor.size:
        yy = np.linspace(1.0, 0.0, floor.shape[0], dtype=np.float32)[:, None]
        xx = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
        horizontal = np.clip(1.0 - np.abs(xx - ((x1 + x2) / (2 * w))) * 3.0, 0, 1)
        reflection = yy * horizontal * reveal * 5.5
        floor += reflection[:, :, None]
        out[floor_y:h] = floor
    wall_band = out[max(0, y1 - int((y2 - y1) * 0.08)) : min(h, y2 + int((y2 - y1) * 0.04)), max(0, x1 - int((x2 - x1) * 0.12)) : min(w, x2 + int((x2 - x1) * 0.12))]
    if wall_band.size:
        wall_band *= 1.0 + reveal * 0.010
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_reflection_sweep(frame: np.ndarray, box: list[int], progress: float, action: str) -> np.ndarray:
    x1, y1, x2, y2 = box
    door_w = x2 - x1
    sweep = progress if action == "open" else 1 - progress
    hx = int(x1 + door_w * (0.18 + 0.64 * sweep))
    overlay = frame.copy()
    cv2.rectangle(overlay, (max(x1, hx - 7), y1), (min(x2, hx + 7), y2), (255, 255, 255), -1)
    return cv2.addWeighted(overlay, 0.055, frame, 0.945, 0)


def add_camera_imperfections(frame: np.ndarray, frame_index: int) -> np.ndarray:
    rng = np.random.default_rng(9000 + frame_index)
    out = frame.astype(np.float32)
    out += rng.normal(0, 0.35, frame.shape)
    flicker = 1.0 + math.sin(frame_index * 0.37) * 0.002
    out *= flicker
    return np.clip(out, 0, 255).astype(np.uint8)


def mux_generated_audio(
    video_in: Path,
    video_out: Path,
    duration: float,
    actions: list[tuple[str, float]],
    elevator_state: str,
    video_cfg: dict[str, Any],
) -> dict[str, Any]:
    sample_rate = int(video_cfg.get("audio_sample_rate", 44100))
    volume = float(video_cfg.get("audio_volume", 0.35))
    audio, layers = generate_elevator_audio(duration, actions, elevator_state, video_cfg, sample_rate, volume)
    wav_path = video_out.with_name(video_out.stem + ".audio.wav")
    write_wav(wav_path, audio, sample_rate)

    cmd = [
        find_ffmpeg_executable(),
        "-y",
        "-i",
        str(video_in),
        "-i",
        str(wav_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(video_out),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        muxed = True
    except Exception:
        video_in.replace(video_out)
        muxed = False
    finally:
        safe_unlink(wav_path)

    return {
        "audio_enabled": bool(muxed),
        "audio_sample_rate": sample_rate,
        "audio_layers": layers if muxed else [],
        "audio_duration_seconds": duration if muxed else 0.0,
        "video_duration_seconds": duration,
        "audio_muxer": "ffmpeg" if muxed else "failed_silent_fallback",
    }


def find_ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def generate_elevator_audio(
    duration: float,
    actions: list[tuple[str, float]],
    elevator_state: str,
    video_cfg: dict[str, Any],
    sample_rate: int,
    volume: float,
) -> tuple[np.ndarray, list[str]]:
    n = max(1, int(round(duration * sample_rate)))
    t = np.arange(n, dtype=np.float32) / float(sample_rate)
    audio = np.zeros(n, dtype=np.float32)
    layers: list[str] = []
    spans = audio_action_spans(actions)

    if bool(video_cfg.get("motor_hum_enabled", True)):
        hum = 0.010 * np.sin(2 * np.pi * 64 * t) + 0.004 * np.sin(2 * np.pi * 87 * t + 0.4)
        hum *= 0.28 + 0.72 * movement_envelope(t, spans)
        audio += hum
        layers.append("motor_hum")

    if bool(video_cfg.get("door_slide_enabled", True)):
        rng = np.random.default_rng(12345)
        noise = rng.normal(0, 1, n).astype(np.float32)
        brown = np.cumsum(noise)
        brown -= float(brown.mean())
        brown /= max(float(np.max(np.abs(brown))), 1e-6)
        slide = 0.026 * brown * movement_envelope(t, spans)
        slide += 0.006 * np.sin(2 * np.pi * 310 * t + np.sin(t * 23)) * movement_envelope(t, spans)
        audio += slide
        layers.append("door_slide")

    if bool(video_cfg.get("ding_enabled", True)):
        for ding_time in ding_times(spans, elevator_state):
            audio += make_ding(t, ding_time)
        layers.append("ding")

    if bool(video_cfg.get("close_thud_enabled", True)):
        for thud_time in close_thud_times(spans):
            audio += make_thud(t, thud_time)
        layers.append("close_thud")

    audio += 0.0025 * np.sin(2 * np.pi * 34 * t)
    audio *= np.clip(volume, 0.0, 1.0)
    audio = np.clip(audio, -0.95, 0.95)
    return np.column_stack([audio, audio]).astype(np.float32), layers


def audio_action_spans(actions: list[tuple[str, float]]) -> list[tuple[str, float, float]]:
    spans: list[tuple[str, float, float]] = []
    cursor = 0.0
    for index, (action, seconds) in enumerate(actions):
        start = cursor
        end = start + seconds
        spans.append((action, start, end))
        cursor = end + (MID_HOLD_SECONDS if index == 0 else END_HOLD_SECONDS)
    return spans


def movement_envelope(t: np.ndarray, spans: list[tuple[str, float, float]]) -> np.ndarray:
    env = np.zeros_like(t, dtype=np.float32)
    for _, start, end in spans:
        local = np.clip((t - start) / max(end - start, 1e-6), 0.0, 1.0)
        active = ((t >= start) & (t <= end)).astype(np.float32)
        curve = np.maximum(np.sin(np.pi * local), 0.0).astype(np.float32) ** 0.45
        env = np.maximum(env, active * curve)
    return env


def ding_times(spans: list[tuple[str, float, float]], elevator_state: str) -> list[float]:
    if not spans:
        return []
    if elevator_state == "closed":
        return [max(0.05, spans[0][1] + 0.18)]
    for action, start, _ in spans:
        if action == "open":
            return [max(0.05, start - 0.22)]
    return []


def close_thud_times(spans: list[tuple[str, float, float]]) -> list[float]:
    return [end for action, _, end in spans if action == "close"]


def make_ding(t: np.ndarray, start: float) -> np.ndarray:
    y = np.zeros_like(t, dtype=np.float32)
    first = (t >= start) & (t < start + 0.32)
    second = (t >= start + 0.22) & (t < start + 0.72)
    x1 = t[first] - start
    x2 = t[second] - (start + 0.22)
    y[first] += 0.035 * np.sin(2 * np.pi * 880 * x1) * np.exp(-7.5 * x1)
    y[second] += 0.025 * np.sin(2 * np.pi * 1320 * x2) * np.exp(-6.0 * x2)
    return y


def make_thud(t: np.ndarray, center: float) -> np.ndarray:
    x = t - center
    env = np.exp(-0.5 * (x / 0.035) ** 2)
    return (0.050 * np.sin(2 * np.pi * 96 * np.maximum(x, 0)) * env).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm_i16 = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_i16.tobytes())


def safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def build_audio_clip(audio_clip_cls: Any, duration: float, actions: list[tuple[str, float]], sample_rate: int = 44100) -> Any:
    action_spans = []
    cursor = 0.0
    for action, seconds in actions:
        action_spans.append((action, cursor, cursor + seconds))
        cursor += seconds + MID_HOLD_SECONDS

    def envelope(t: np.ndarray) -> np.ndarray:
        total = np.zeros_like(np.asarray(t, dtype=np.float32), dtype=np.float32)
        for _, start, end in action_spans:
            x = np.clip((t - start) / max(end - start, 1e-6), 0, 1)
            total = np.maximum(total, np.maximum(np.sin(np.pi * x), 0) ** 0.55)
        return total

    def pulse(t: np.ndarray, center: float, width: float, amp: float) -> np.ndarray:
        return amp * np.exp(-0.5 * ((t - center) / width) ** 2)

    def audio_fn(t: Any) -> Any:
        t_arr = np.asarray(t, dtype=np.float32)
        env = envelope(t_arr)
        motor = (0.028 * np.sin(2 * np.pi * 72 * t_arr) + 0.012 * np.sin(2 * np.pi * 138 * t_arr + 0.4)) * env
        rail = 0.010 * np.sin(2 * np.pi * 460 * t_arr + np.sin(t_arr * 19)) * env
        hvac = 0.006 * np.sin(2 * np.pi * 31 * t_arr)
        impact = np.zeros_like(t_arr, dtype=np.float32)
        ding = np.zeros_like(t_arr, dtype=np.float32)
        for span_action, start, end in action_spans:
            if span_action == "close":
                impact += pulse(t_arr, end - 0.08, 0.018, 0.08)
            else:
                impact += pulse(t_arr, start + 0.12, 0.018, 0.028)
                ding += pulse(t_arr, end + 0.08, 0.14, 0.035) * np.sin(2 * np.pi * 880 * t_arr)
        mono = np.clip(motor + rail + hvac + impact + ding, -0.18, 0.18)
        if np.isscalar(t):
            return [float(mono), float(mono)]
        return np.column_stack([mono, mono])

    return audio_clip_cls(audio_fn, duration=duration, fps=sample_rate)
