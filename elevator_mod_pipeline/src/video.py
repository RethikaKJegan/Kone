from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ACTION_SECONDS = {"open": 1.25, "close": 1.75}
MID_HOLD_SECONDS = 0.7
END_HOLD_SECONDS = 0.9
LOGGER = logging.getLogger(__name__)
MOTION_STYLES = {"zoom_in", "pan_l_r", "pan_r_l", "pan_t_b", "pan_b_t"}
MOTION_STYLE_ALIASES = {
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
    "left": "pan_r_l",
    "right": "pan_l_r",
    "pan_left": "pan_r_l",
    "pan_right": "pan_l_r",
}
DOOR_FUNCTIONALITY = {"open", "close"}
QUALITY_SIZES = {
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}


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
    if fps <= 0:
        raise ValueError(f"Video fps must be positive, got {fps}")
    quality = normalize_video_quality(video_cfg.get("quality", "1080p"))
    duration = float(video_cfg.get("duration_seconds", video_cfg.get("duration", 3.0)))
    if duration <= 0:
        duration = 3.0
    mode_request = normalize_video_mode_request(video_cfg)
    LOGGER.info(
        "[VIDEO] Requested motion_style=%s door_functionality=%s",
        mode_request["requested_motion_style"],
        mode_request["requested_door_functionality"],
    )
    LOGGER.info("[VIDEO] Normalized video mode: %s", mode_request["normalized_video_mode"])
    LOGGER.info("[VIDEO] Output settings: quality=%s fps=%s duration=%.3f", quality, fps, duration)
    if mode_request["requested_door_functionality"]:
        LOGGER.info("[VIDEO] Door functionality selected; camera motion disabled")
    elif mode_request["requested_motion_style"]:
        return render_motion_style_video(image_path, cfg, out_path, fps, duration, quality, mode_request)

    action = video_cfg.get("action", "auto")
    if mode_request["requested_door_functionality"]:
        action = mode_request["requested_door_functionality"]
    bitrate = str(video_cfg.get("bitrate", "10000k"))
    no_audio = bool(video_cfg.get("no_audio", False))
    auto_door_functionality = mode_request["requested_video_mode"] in {"door", "door_functionality", "door_fuctionality"}
    cycle = bool(video_cfg.get("cycle", True)) and not mode_request["requested_door_functionality"] and not auto_door_functionality
    refine_roi = bool(video_cfg.get("refine_elevator_roi", True))
    preserve_outside_roi = bool(video_cfg.get("preserve_static_wall_outside_roi", refine_roi))

    img = load_image_bgr(image_path)
    depth = load_depth(depth_path, img.shape[:2]) if depth_path else None
    best_detection = select_best_elevator_detection(detections)
    roi_debug: dict[str, Any] = {}
    LOGGER.info("[ROI] Scoring elevator candidates")
    box = detect_door_box(img, detections, geometry, depth, cfg, roi_debug)
    state, state_debug = classify_elevator_state(detections, depth, box, img)
    LOGGER.info("[ROI] Selected elevator ROI: %s score=%s", box, roi_debug.get("selected_score"))
    for rejected in roi_debug.get("rejected_candidates", []):
        LOGGER.info("[ROI] Rejected candidate: %s reason=%s", rejected.get("box"), rejected.get("reason"))
    LOGGER.info("[STATE] Elevator state detected: %s", state)
    if mode_request["requested_door_functionality"]:
        requested_action = mode_request["requested_door_functionality"]
        LOGGER.info("[VIDEO] Using existing door-%s animation pipeline", requested_action)
        if requested_action == "open":
            actions = [("open", ACTION_SECONDS["open"])] if state == "closed" else [("close", ACTION_SECONDS["close"]), ("open", ACTION_SECONDS["open"])]
        else:
            actions = [("close", ACTION_SECONDS["close"])] if state == "open" else [("open", ACTION_SECONDS["open"]), ("close", ACTION_SECONDS["close"])]
        first_action = actions[0][0]
    else:
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
    LOGGER.info("[ANIMATION] Refining animation ROI")
    if state == "open":
        LOGGER.info("[ANIMATION] Final image already contains open elevator; using final image as open state")
        LOGGER.info("[ANIMATION] Open reference image disabled for open-state final image")
        LOGGER.info("[ANIMATION] Building closed-door state from closed_reference_image")
        if actions and actions[0][0] == "close" and actions[-1][0] == "open":
            LOGGER.info("[ANIMATION] Rendering open \u2192 close \u2192 open sequence")
            animation_mode = "open_close_open_from_existing_interior"
        else:
            LOGGER.info("[ANIMATION] Rendering open \u2192 close sequence")
            animation_mode = "closing_from_existing_interior"
    else:
        animation_mode = "opening" if first_action == "open" else "closing"
    LOGGER.info("[ANIMATION] Choosing animation mode: %s", animation_mode)
    LOGGER.info("[ANIMATION] Generating frames")
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
    elif state == "open":
        if actions and actions[0][0] == "close" and actions[-1][0] == "open":
            enforce_open_branch_endpoints(frames, img, actions, fps)
            validate_open_branch_motion(frames, img, closed_state_img, box, fps)
        else:
            validate_roi_motion(frames, box, min_diff=3.0)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    video_write_cfg = dict(video_cfg)
    video_write_cfg["_quality_resize_mode"] = "preserve_aspect"
    audio_debug = write_video(out, frames, fps, bitrate, no_audio, actions, state, video_write_cfg)
    audio_debug["animation_mode"] = animation_mode
    audio_debug.update(mode_request)
    if audio_debug.get("requested_video_mode") in {"door", "door_functionality", "door_fuctionality"} and not audio_debug.get("normalized_video_mode"):
        audio_debug["normalized_video_mode"] = f"door_{first_action}"
    audio_debug.update(
        {
            "video_source": "door_animation_pipeline",
            "door_animation_used": True,
            "camera_motion_used": False,
            "open_reference_image_used": state_debug["used_open_reference_image"],
            "closed_reference_image_used": state_debug["used_closed_reference_image"],
        }
    )
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
    quality = normalize_video_quality(video_cfg.get("quality", "1080p"))
    frames = resize_frames_for_quality(frames, quality, str(video_cfg.get("_quality_resize_mode", "cover")))
    height, width = frames[0].shape[:2]
    if fps <= 0:
        raise ValueError(f"Video fps must be positive, got {fps}")
    out.parent.mkdir(parents=True, exist_ok=True)
    add_audio = bool(video_cfg.get("add_audio", False)) and not no_audio
    video_out = out.with_name(out.stem + ".silent.mp4") if add_audio else out.with_name(out.stem + ".opencv.mp4")
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
        LOGGER.info("[VIDEO] Writing video: %s", video_out)
        for frame in frames:
            writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()

    duration = len(frames) / float(fps)
    if not add_audio:
        crf = str(video_cfg.get("ffmpeg_crf", 18))
        browser_safe = transcode_browser_mp4(video_out, out, fps, crf)
        if not browser_safe:
            video_out.replace(out)
        validation = validate_video_output(out, fps, len(frames), duration)
        return {
            "audio_enabled": False,
            "audio_sample_rate": int(video_cfg.get("audio_sample_rate", 44100)),
            "audio_layers": [],
            "audio_duration_seconds": 0.0,
            "video_duration_seconds": duration,
            "video_path": str(out),
            "fps": fps,
            "frame_count": len(frames),
            "duration_seconds": duration,
            "video_validation_status": validation["status"],
            "video_validation": validation,
            "quality": quality,
            "browser_safe_h264": browser_safe,
        }

    audio_debug = mux_generated_audio(video_out, out, duration, actions, elevator_state, video_cfg)
    safe_unlink(video_out)
    validation = validate_video_output(out, fps, len(frames), duration)
    audio_debug.update(
        {
            "video_path": str(out),
            "fps": fps,
            "frame_count": len(frames),
            "duration_seconds": duration,
            "video_validation_status": validation["status"],
            "video_validation": validation,
            "quality": quality,
        }
    )
    return audio_debug


def normalize_video_quality(value: Any) -> str:
    quality = str(value or "1080p").lower()
    if quality not in QUALITY_SIZES:
        raise ValueError(f"Unsupported video quality: {value}. Expected one of {sorted(QUALITY_SIZES)}")
    return quality


def normalize_video_mode_request(video_cfg: dict[str, Any]) -> dict[str, Any]:
    requested_video_mode = video_cfg.get("mode")
    if requested_video_mode is not None:
        requested_video_mode = str(requested_video_mode).strip().lower()
    motion_style = video_cfg.get("motion_style")
    door_functionality = video_cfg.get("door_functionality")
    if motion_style is not None:
        motion_style = str(motion_style).strip().lower()
        motion_style = MOTION_STYLE_ALIASES.get(motion_style, motion_style)
        if motion_style not in MOTION_STYLES:
            raise ValueError(f"Unsupported motion_style: {motion_style}")
    if door_functionality is not None:
        door_functionality = str(door_functionality).strip().lower()
        if door_functionality not in DOOR_FUNCTIONALITY:
            raise ValueError(f"Unsupported door_functionality: {door_functionality}")
    conflict_resolution = None
    if door_functionality:
        normalized = f"door_{door_functionality}"
        if motion_style:
            conflict_resolution = "door_functionality_preferred"
    else:
        normalized = motion_style
    return {
        "requested_video_mode": requested_video_mode,
        "requested_motion_style": motion_style,
        "requested_door_functionality": door_functionality,
        "normalized_video_mode": normalized,
        "video_mode_conflict_resolution": conflict_resolution,
    }


def resize_frames_for_quality(frames: list[np.ndarray], quality: str, mode: str = "cover") -> list[np.ndarray]:
    target_w, target_h = QUALITY_SIZES[quality]
    if mode == "preserve_aspect":
        source_h, source_w = frames[0].shape[:2]
        target_w, target_h = preserve_aspect_output_size(source_w, source_h, target_w, target_h)
        return [resize_exact_rgb(frame, target_w, target_h) for frame in frames]
    if mode == "contain":
        return [resize_contain_rgb(frame, target_w, target_h) for frame in frames]
    return [resize_cover_rgb(frame, target_w, target_h) for frame in frames]


def preserve_aspect_output_size(source_w: int, source_h: int, max_w: int, max_h: int) -> tuple[int, int]:
    source_w, source_h = max(1, int(source_w)), max(1, int(source_h))
    if source_h >= source_w:
        out_h = max_h
        out_w = int(round(out_h * source_w / source_h))
    else:
        out_w = max_w
        out_h = int(round(out_w * source_h / source_w))
    out_w = max(2, min(max_w, out_w))
    out_h = max(2, min(max_h, out_h))
    if out_w % 2:
        out_w -= 1
    if out_h % 2:
        out_h -= 1
    return max(2, out_w), max(2, out_h)


def resize_cover_rgb(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = max(target_w / max(w, 1), target_h / max(h, 1))
    resized = cv2.resize(frame, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    rh, rw = resized.shape[:2]
    x1 = max(0, (rw - target_w) // 2)
    y1 = max(0, (rh - target_h) // 2)
    crop = resized[y1 : y1 + target_h, x1 : x1 + target_w]
    if crop.shape[:2] != (target_h, target_w):
        crop = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(crop)


def resize_contain_rgb(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    h, w = frame.shape[:2]
    background = resize_cover_rgb(frame, target_w, target_h)
    background = cv2.GaussianBlur(background, (0, 0), 18)
    scale = min(target_w / max(w, 1), target_h / max(h, 1))
    resized_w = max(1, int(round(w * scale)))
    resized_h = max(1, int(round(h * scale)))
    foreground = cv2.resize(frame, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    x1 = (target_w - resized_w) // 2
    y1 = (target_h - resized_h) // 2
    background[y1 : y1 + resized_h, x1 : x1 + resized_w] = foreground
    return np.ascontiguousarray(background)


def render_motion_style_video(
    image_path: str | Path,
    cfg: dict[str, Any],
    out_path: str | Path,
    fps: int,
    duration: float,
    quality: str,
    mode_request: dict[str, Any],
) -> Path:
    img_bgr = load_image_bgr(image_path)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    target_w, target_h = motion_output_size(img_rgb, quality, cfg)
    focus, focus_source = motion_focus_point(cfg, img_rgb.shape[:2])
    motion_style = mode_request["requested_motion_style"]
    if motion_style == "zoom_in":
        LOGGER.info("[VIDEO] Generating centered zoom-in from final output image")
    elif motion_style == "pan_l_r":
        LOGGER.info("[VIDEO] Generating panorama pan L-R from final output image")
        LOGGER.info("[VIDEO] Pan uses crop-window viewport; no blank borders")
    elif motion_style == "pan_r_l":
        LOGGER.info("[VIDEO] Generating panorama pan R-L from final output image")
        LOGGER.info("[VIDEO] Pan uses crop-window viewport; no blank borders")
    elif motion_style == "pan_t_b":
        LOGGER.info("[VIDEO] Generating vertical panorama pan T-B from final output image")
        LOGGER.info("[VIDEO] Pan uses crop-window viewport; no blank borders")
    elif motion_style == "pan_b_t":
        LOGGER.info("[VIDEO] Generating vertical panorama pan B-T from final output image")
        LOGGER.info("[VIDEO] Pan uses crop-window viewport; no blank borders")
    pan_axis, pan_direction = pan_metadata(motion_style)
    frame_count = max(2, int(round(fps * duration)))
    if motion_style in {"zoom_in", "pan_l_r", "pan_r_l"}:
        ffmpeg_debug = render_ffmpeg_camera_motion(
            img_rgb,
            Path(image_path),
            Path(out_path),
            fps,
            frame_count,
            duration,
            quality,
            motion_style,
            mode_request,
            focus_source,
            pan_axis,
            pan_direction,
            cfg,
        )
        if ffmpeg_debug is not None:
            write_motion_metadata(Path(out_path).with_suffix(".json"), image_path, Path(out_path), ffmpeg_debug)
            return Path(out_path)

    frames = [
        render_motion_style_frame(img_rgb, target_w, target_h, focus, motion_style, i / max(frame_count - 1, 1))
        for i in range(frame_count)
    ]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    audio_debug = write_video(out, frames, fps, str(cfg.get("video", {}).get("bitrate", "10000k")), True, [], "none", cfg.get("video", {}))
    audio_debug.update(
        {
            **mode_request,
            "video_source": "final_output_image",
            "door_animation_used": False,
            "camera_motion_used": True,
            "open_reference_image_used": False,
            "closed_reference_image_used": False,
            "focus_point_source": focus_source,
            "pan_axis": pan_axis,
            "pan_direction": pan_direction,
            "video_generated": True,
        }
    )
    write_motion_metadata(out.with_suffix(".json"), image_path, out, audio_debug)
    return out


def render_ffmpeg_camera_motion(
    img_rgb: np.ndarray,
    image_path: Path,
    out_path: Path,
    fps: int,
    frame_count: int,
    duration: float,
    quality: str,
    motion_style: str,
    mode_request: dict[str, Any],
    focus_source: str,
    pan_axis: str | None,
    pan_direction: str | None,
    cfg: dict[str, Any],
) -> dict[str, Any] | None:
    target_w, target_h = motion_output_size(img_rgb, quality, cfg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base_path = out_path.with_name(out_path.stem + ".ffmpeg_input.png")
    try:
        if motion_style == "zoom_in":
            return render_stable_cpu_zoom_motion(
                img_rgb,
                out_path,
                fps,
                frame_count,
                duration,
                quality,
                target_w,
                target_h,
                mode_request,
                focus_source,
                cfg,
            )

        base = build_ffmpeg_pan_base(img_rgb, target_w, target_h, axis="x", cfg=cfg)
        ease = ffmpeg_smoothstep_expr(frame_count, "n")
        if motion_style == "pan_l_r":
            x_expr = f"(iw-ow)*({ease})"
        else:
            x_expr = f"(iw-ow)*(1-({ease}))"
        filter_expr = (
            f"fps={fps},crop={target_w}:{target_h}:x='{x_expr}':y='(ih-oh)/2',"
            f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
            f"{ffmpeg_finish_filters(cfg)}"
        )

        cv2.imwrite(str(base_path), cv2.cvtColor(base, cv2.COLOR_RGB2BGR))
        cmd = [
            find_ffmpeg_executable(),
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-i",
            str(base_path),
            "-frames:v",
            str(frame_count),
            "-vf",
            filter_expr,
            "-r",
            str(fps),
            "-fps_mode",
            "cfr",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            str((cfg.get("video", {}) or {}).get("ffmpeg_crf", 18)),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        LOGGER.info("[VIDEO] Rendering camera motion with FFmpeg: %s", motion_style)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        validation = validate_video_output(out_path, fps, frame_count, duration)
        return {
            **mode_request,
            "video_source": "final_output_image",
            "video_renderer": "ffmpeg_cinematic_cpu",
            "door_animation_used": False,
            "camera_motion_used": True,
            "open_reference_image_used": False,
            "closed_reference_image_used": False,
            "focus_point_source": focus_source,
            "pan_axis": pan_axis,
            "pan_direction": pan_direction,
            "video_generated": True,
            "audio_enabled": False,
            "video_path": str(out_path),
            "fps": fps,
            "frame_count": frame_count,
            "duration_seconds": duration,
            "video_duration_seconds": duration,
            "quality": quality,
            "output_width": target_w,
            "output_height": target_h,
            "video_validation_status": validation["status"],
            "video_validation": validation,
        }
    except Exception as exc:
        LOGGER.warning("[VIDEO] FFmpeg camera-motion render failed; falling back to OpenCV renderer: %s", exc)
        return None
    finally:
        safe_unlink(base_path)


def render_stable_cpu_zoom_motion(
    img_rgb: np.ndarray,
    out_path: Path,
    fps: int,
    frame_count: int,
    duration: float,
    quality: str,
    target_w: int,
    target_h: int,
    mode_request: dict[str, Any],
    focus_source: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    video_settings = cfg.get("video", {}) or {}
    zoom_amount = float(video_settings.get("ffmpeg_zoom_amount", 0.22))
    focus_x = float(np.clip(float(video_settings.get("ffmpeg_zoom_focus_x", 0.50)), 0.05, 0.95))
    focus_y = float(np.clip(float(video_settings.get("ffmpeg_zoom_focus_y", 0.50)), 0.05, 0.95))
    base = resize_exact_rgb(img_rgb, target_w, target_h)
    frames: list[np.ndarray] = []
    den = max(frame_count - 1, 1)
    for idx in range(frame_count):
        t = idx / den
        eased = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
        zoom = 1.0 + zoom_amount * eased
        cx = target_w * focus_x
        cy = target_h * focus_y
        matrix = np.array([[zoom, 0.0, (1.0 - zoom) * cx], [0.0, zoom, (1.0 - zoom) * cy]], dtype=np.float32)
        frame = cv2.warpAffine(
            base,
            matrix,
            (target_w, target_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        if bool(video_settings.get("ffmpeg_zoom_sharpen", False)):
            blur = cv2.GaussianBlur(frame, (0, 0), 0.9)
            frame = cv2.addWeighted(frame, 1.06, blur, -0.06, 0)
        frames.append(np.ascontiguousarray(np.clip(frame, 0, 255).astype(np.uint8)))

    video_debug = write_frames_mp4(
        out_path,
        frames,
        fps,
        str(video_settings.get("ffmpeg_crf", 18)),
        renderer="stable_cpu_zoom",
    )
    validation = validate_video_output(out_path, fps, frame_count, duration)
    video_debug.update(
        {
            **mode_request,
            "video_source": "final_output_image",
            "video_renderer": "stable_cpu_zoom",
            "door_animation_used": False,
            "camera_motion_used": True,
            "open_reference_image_used": False,
            "closed_reference_image_used": False,
            "focus_point_source": focus_source,
            "pan_axis": None,
            "pan_direction": None,
            "video_generated": True,
            "audio_enabled": False,
            "duration_seconds": duration,
            "video_duration_seconds": duration,
            "quality": quality,
            "output_width": target_w,
            "output_height": target_h,
            "video_validation_status": validation["status"],
            "video_validation": validation,
        }
    )
    return video_debug


def write_frames_mp4(out_path: Path, frames: list[np.ndarray], fps: int, crf: str, renderer: str) -> dict[str, Any]:
    del renderer
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = out_path.with_name(out_path.stem + ".opencv.mp4")
    height, width = frames[0].shape[:2]
    writer = None
    for codec in ("mp4v", "avc1", "H264"):
        candidate = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*codec), float(fps), (width, height))
        if candidate.isOpened():
            writer = candidate
            break
        candidate.release()
    if writer is None:
        raise RuntimeError(f"Could not open an MP4 writer for {raw_path}")
    try:
        for frame in frames:
            writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    finally:
        writer.release()
    browser_safe = transcode_browser_mp4(raw_path, out_path, fps, crf)
    if not browser_safe:
        raw_path.replace(out_path)
    return {
        "video_path": str(out_path),
        "fps": fps,
        "frame_count": len(frames),
        "browser_safe_h264": browser_safe,
    }


def transcode_browser_mp4(raw_path: Path, out_path: Path, fps: int, crf: str) -> bool:
    ffmpeg = find_ffmpeg_executable()
    if ffmpeg == "ffmpeg" and shutil.which("ffmpeg") is None:
        return False
    tmp_out = out_path.with_name(out_path.stem + ".h264.mp4")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(raw_path),
        "-r",
        str(fps),
        "-an",
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-crf",
        str(crf),
        "-movflags",
        "+faststart",
        str(tmp_out),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tmp_out.replace(out_path)
        safe_unlink(raw_path)
        return True
    except Exception as exc:
        LOGGER.warning("[VIDEO] H.264 browser transcode failed; using OpenCV MP4: %s", exc)
        safe_unlink(tmp_out)
        return False


def resize_exact_rgb(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    return np.ascontiguousarray(cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4))


def build_ffmpeg_pan_base(img_rgb: np.ndarray, target_w: int, target_h: int, axis: str, cfg: dict[str, Any] | None = None) -> np.ndarray:
    h, w = img_rgb.shape[:2]
    video_settings = (cfg or {}).get("video", {}) or {}
    overscan = float(np.clip(float(video_settings.get("ffmpeg_pan_overscan", 0.06)), 0.0, 0.25))
    if axis == "x":
        desired_w = int(round(target_w * (1.0 + overscan)))
        scale = max(desired_w / max(w, 1), target_h / max(h, 1))
    else:
        desired_h = int(round(target_h * (1.0 + overscan)))
        scale = max(target_w / max(w, 1), desired_h / max(h, 1))
    resized_w = max(target_w + 2, int(round(w * scale)))
    resized_h = max(target_h + 2, int(round(h * scale)))
    return cv2.resize(img_rgb, (resized_w, resized_h), interpolation=cv2.INTER_LANCZOS4)


def motion_output_size(img_rgb: np.ndarray, quality: str, cfg: dict[str, Any]) -> tuple[int, int]:
    target_w, target_h = QUALITY_SIZES[quality]
    if not bool((cfg.get("video", {}) or {}).get("preserve_source_aspect", False)):
        return target_w, target_h
    h, w = img_rgb.shape[:2]
    if h <= 0 or w <= 0:
        return target_w, target_h
    if h >= w:
        out_h = target_h
        out_w = int(round(out_h * w / h))
    else:
        out_w = target_w
        out_h = int(round(out_w * h / w))
    out_w = max(2, out_w - out_w % 2)
    out_h = max(2, out_h - out_h % 2)
    return out_w, out_h


def ffmpeg_smoothstep_expr(frame_count: int, variable: str = "on") -> str:
    den = max(frame_count - 1, 1)
    p = f"({variable}/{den})"
    return f"({p}*{p}*(3-2*{p}))"


def ffmpeg_finish_filters(cfg: dict[str, Any]) -> str:
    video_settings = cfg.get("video", {}) or {}
    filters = []
    if bool(video_settings.get("ffmpeg_temporal_smoothing", False)):
        filters.append("tmix=frames=3:weights='1 2 1'")
    if bool(video_settings.get("ffmpeg_sharpen", True)):
        filters.append("unsharp=5:5:0.25:3:3:0.08")
    if bool(video_settings.get("ffmpeg_add_grain", False)):
        filters.append("noise=alls=0.35:allf=t+u")
    return ",".join(filters) if filters else "null"


def motion_focus_point(cfg: dict[str, Any], hw: tuple[int, int]) -> tuple[tuple[float, float], str]:
    h, w = hw
    return (w * 0.5, h * 0.5), "image_center"


def render_motion_style_frame(
    img_rgb: np.ndarray,
    target_w: int,
    target_h: int,
    focus: tuple[float, float],
    motion_style: str,
    t: float,
) -> np.ndarray:
    if motion_style == "zoom_in":
        return render_zoom_in_frame(img_rgb, target_w, target_h, t)
    if motion_style in {"pan_l_r", "pan_r_l", "pan_t_b", "pan_b_t"}:
        return render_pan_frame(img_rgb, target_w, target_h, motion_style, t)
    raise ValueError(f"Unsupported motion_style: {motion_style}")


def render_zoom_in_frame(img_rgb: np.ndarray, target_w: int, target_h: int, t: float) -> np.ndarray:
    fitted = resize_contain_rgb(img_rgb, target_w, target_h)
    eased = ease_in_out_cubic(t)
    if eased <= 0:
        return fitted
    zoom = 1.0 + 0.16 * eased
    crop_w = max(2, int(round(target_w / zoom)))
    crop_h = max(2, int(round(target_h / zoom)))
    x1 = (target_w - crop_w) // 2
    y1 = (target_h - crop_h) // 2
    crop = fitted[y1 : y1 + crop_h, x1 : x1 + crop_w]
    return cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_AREA)


def render_pan_frame(img_rgb: np.ndarray, target_w: int, target_h: int, motion_style: str, t: float) -> np.ndarray:
    h, w = img_rgb.shape[:2]
    scale = max(target_w / max(w, 1), target_h / max(h, 1)) * 1.06
    resized_w = max(target_w + 2, int(round(w * scale)))
    resized_h = max(target_h + 2, int(round(h * scale)))
    resized = cv2.resize(img_rgb, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    pan = ease_in_out_cubic(t)
    if motion_style in {"pan_l_r", "pan_r_l"}:
        y1 = int(np.clip(round((resized_h - target_h) * 0.5), 0, max(0, resized_h - target_h)))
        travel = max(0, resized_w - target_w)
        x_start = 0 if motion_style == "pan_l_r" else travel
        x_end = travel if motion_style == "pan_l_r" else 0
        x1 = int(round(x_start + (x_end - x_start) * pan))
    else:
        x1 = int(np.clip(round((resized_w - target_w) * 0.5), 0, max(0, resized_w - target_w)))
        travel = max(0, resized_h - target_h)
        y_start = 0 if motion_style == "pan_t_b" else travel
        y_end = travel if motion_style == "pan_t_b" else 0
        y1 = int(round(y_start + (y_end - y_start) * pan))
    crop = resized[y1 : y1 + target_h, x1 : x1 + target_w]
    if crop.shape[:2] != (target_h, target_w):
        crop = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(crop)


def pan_metadata(motion_style: str | None) -> tuple[str | None, str | None]:
    return {
        "pan_l_r": ("x", "left_to_right"),
        "pan_r_l": ("x", "right_to_left"),
        "pan_t_b": ("y", "top_to_bottom"),
        "pan_b_t": ("y", "bottom_to_top"),
    }.get(str(motion_style), (None, None))


def write_motion_metadata(meta_path: Path, image_path: str | Path, out_path: Path, audio_debug: dict[str, Any]) -> None:
    meta_path.write_text(
        json.dumps(
            {
                "source_image": str(image_path),
                "output_video": str(out_path),
                "video_path": str(out_path),
                "requested_motion_style": audio_debug.get("requested_motion_style"),
                "requested_video_mode": audio_debug.get("requested_video_mode"),
                "requested_door_functionality": audio_debug.get("requested_door_functionality"),
                "normalized_video_mode": audio_debug.get("normalized_video_mode"),
                "video_generated": True,
                "fps": audio_debug.get("fps"),
                "frame_count": audio_debug.get("frame_count"),
                "duration_seconds": audio_debug.get("duration_seconds"),
                "quality": audio_debug.get("quality"),
                "output_width": audio_debug.get("output_width"),
                "output_height": audio_debug.get("output_height"),
                "video_validation_status": audio_debug.get("video_validation_status"),
                "video_source": audio_debug.get("video_source"),
                "video_renderer": audio_debug.get("video_renderer"),
                "door_animation_used": False,
                "camera_motion_used": True,
                "open_reference_image_used": False,
                "closed_reference_image_used": False,
                "video_mode_conflict_resolution": audio_debug.get("video_mode_conflict_resolution"),
                "focus_point_source": audio_debug.get("focus_point_source"),
                "pan_axis": audio_debug.get("pan_axis"),
                "pan_direction": audio_debug.get("pan_direction"),
                "audio": audio_debug,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def validate_video_output(path: Path, expected_fps: int, expected_frames: int, expected_duration: float) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "path": str(path),
        "expected_fps": expected_fps,
        "expected_frame_count": expected_frames,
        "expected_duration_seconds": expected_duration,
    }
    if not path.exists():
        diagnostics["status"] = "failed_missing_file"
        raise RuntimeError(f"Video validation failed: output file missing: {path}")
    size = path.stat().st_size
    diagnostics["file_size_bytes"] = size
    if size <= 0:
        diagnostics["status"] = "failed_empty_file"
        raise RuntimeError(f"Video validation failed: output file is empty: {path}")

    cap = cv2.VideoCapture(str(path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        cap.release()
    duration = frame_count / fps if fps > 0 else 0.0
    diagnostics.update({"fps": fps, "frame_count": frame_count, "duration_seconds": duration})
    if fps <= 0 or frame_count <= 0 or duration <= 0:
        diagnostics["status"] = "failed_zero_duration"
        raise RuntimeError(f"Video validation failed: zero/invalid duration for {path}: {diagnostics}")
    diagnostics["status"] = "passed"
    LOGGER.info("[VIDEO] Validation passed: fps=%.3f frames=%s duration=%.3f", fps, frame_count, duration)
    return diagnostics


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
                "elevator_state": state,
                "actions": actions,
                "skipped_animation_reason": state_debug.get("skipped_animation_reason"),
                "skipped_or_alternate_animation_reason": state_debug.get("skipped_or_alternate_animation_reason"),
                "animation_mode": state_debug.get("animation_mode") or audio_debug.get("animation_mode"),
                "video_path": str(out_path),
                "frame_count": audio_debug.get("frame_count"),
                "duration_seconds": audio_debug.get("duration_seconds", audio_debug.get("video_duration_seconds")),
                "video_validation_status": audio_debug.get("video_validation_status"),
                "requested_motion_style": audio_debug.get("requested_motion_style"),
                "requested_video_mode": audio_debug.get("requested_video_mode"),
                "requested_door_functionality": audio_debug.get("requested_door_functionality"),
                "normalized_video_mode": audio_debug.get("normalized_video_mode"),
                "video_mode_conflict_resolution": audio_debug.get("video_mode_conflict_resolution"),
                "video_generated": True,
                "video_source": audio_debug.get("video_source"),
                "door_animation_used": audio_debug.get("door_animation_used"),
                "camera_motion_used": audio_debug.get("camera_motion_used"),
                "pan_axis": audio_debug.get("pan_axis"),
                "pan_direction": audio_debug.get("pan_direction"),
                "quality": audio_debug.get("quality"),
                "open_reference_image_used": audio_debug.get("open_reference_image_used"),
                "closed_reference_image_used": audio_debug.get("closed_reference_image_used"),
                "open_state_source": source_policy.get("open_state_image"),
                "closed_state_source": source_policy.get("closed_state_image"),
                "used_open_reference_image": source_policy.get("open_reference_image_used") == "true",
                "used_closed_reference_image": source_policy.get("closed_reference_image_used") == "true",
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
        cv2.imwrite(str(out_dir / "nested_frame_depth_evidence.png"), overlay)

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
                "closed_state_image": "closed_reference_image" if closed_ref is not None else "final_image_fallback",
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


def enforce_open_branch_endpoints(
    frames: list[np.ndarray],
    final_img_bgr: np.ndarray,
    actions: list[tuple[str, float]],
    fps: int,
) -> None:
    if not frames:
        return

    exact_open_rgb = cv2.cvtColor(final_img_bgr, cv2.COLOR_BGR2RGB)
    frames[0] = exact_open_rgb.copy()

    if actions and actions[-1][0] == "open":
        end_hold_frames = max(4, int(fps * END_HOLD_SECONDS))
        for idx in range(max(0, len(frames) - end_hold_frames), len(frames)):
            frames[idx] = exact_open_rgb.copy()
        frames[-1] = exact_open_rgb.copy()


def validate_open_branch_motion(
    frames: list[np.ndarray],
    final_img_bgr: np.ndarray,
    closed_state_bgr: np.ndarray,
    box: list[int],
    fps: int,
) -> None:
    if fps <= 0:
        raise ValueError(f"Video fps must be positive, got {fps}")
    if len(frames) < max(3, int(fps * 2.0)):
        raise RuntimeError(f"Open elevator animation is too short: {len(frames)} frames at {fps} fps")

    x1, y1, x2, y2 = [int(v) for v in box]
    if x2 <= x1 or y2 <= y1:
        raise RuntimeError(f"Open elevator animation ROI is invalid: {box}")

    open_start = frames[0][y1:y2, x1:x2]
    close_frames = max(24, int(fps * ACTION_SECONDS["close"]))
    closed_midpoint = frames[min(len(frames) - 1, close_frames)][y1:y2, x1:x2]
    open_end = frames[-1][y1:y2, x1:x2]
    original_open = cv2.cvtColor(final_img_bgr, cv2.COLOR_BGR2RGB)[y1:y2, x1:x2]
    closed_reference_state = cv2.cvtColor(closed_state_bgr, cv2.COLOR_BGR2RGB)[y1:y2, x1:x2]

    start_error = mean_absdiff(open_start, original_open)
    end_error = mean_absdiff(open_end, original_open)
    close_motion = mean_absdiff(open_start, closed_midpoint)
    closed_error = mean_absdiff(closed_midpoint, closed_reference_state)

    if start_error > 1.0 or end_error > 1.0:
        raise RuntimeError(
            "Open elevator animation failed to preserve final_image interior at endpoints: "
            f"start_error={start_error:.3f} end_error={end_error:.3f}"
        )
    if close_motion < 3.0:
        raise RuntimeError(f"Open elevator animation is static/no-op in ROI: mean_diff={close_motion:.3f}")
    if closed_error > 45.0:
        raise RuntimeError(
            "Open elevator animation closed midpoint does not match closed-door reference state closely enough: "
            f"mean_error={closed_error:.3f}"
        )


def mean_absdiff(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    return float(np.mean(cv2.absdiff(a, b)))


def validate_roi_motion(frames: list[np.ndarray], box: list[int], min_diff: float = 3.0) -> None:
    if len(frames) < 2:
        raise RuntimeError("Door animation rendered too few frames")
    x1, y1, x2, y2 = [int(v) for v in box]
    start = frames[0][y1:y2, x1:x2]
    end = frames[-1][y1:y2, x1:x2]
    diff = mean_absdiff(start, end)
    if diff < min_diff:
        raise RuntimeError(f"Door animation is static/no-op in ROI: mean_diff={diff:.3f}")


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
    candidate_scores: list[dict[str, Any]] = []
    scored: list[tuple[float, list[int], dict[str, Any], str]] = []
    LOGGER.info("[ROI] Checking nested frame/depth evidence")

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
        refined, refinement_policy = constrain_animation_roi_to_detection_box(box, refined, w, h, cfg)
        candidate["edge_score"] = edge_score
        candidate["refined_box"] = refined
        candidate["refinement_policy"] = refinement_policy
        if not valid and not recoverable_elevator_candidate(box, refined, phrase, reason, w, h, edge_score):
            candidate["reason"] = reason
            rejected.append(candidate)
            continue
        depth_score = depth_roi_score(depth_map, refined) if depth_map is not None else 0.0
        interior_score = interior_overlap_score(refined, detections, src_w, src_h, w, h)
        component_score = adjacent_component_score(refined, detections, src_w, src_h, w, h)
        nested_score, nested_evidence = nested_frame_depth_score(image, refined, depth_map)
        rejection_penalty = candidate_penalty(box, refined, reason, w, h) if not valid else 0.0
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
            + component_score * 0.45
            + nested_score * 0.75
            - rejection_penalty
        )
        score_detail = {
            "box": refined,
            "raw_box": box,
            "phrase": phrase,
            "score": float(score),
            "raw_detection_score": float(det.get("score", 0.0)),
            "edge_score": edge_score,
            "depth_score": depth_score,
            "interior_score": interior_score,
            "component_score": component_score,
            "nested_frame_depth_score": nested_score,
            "nested_frame_depth_evidence": nested_evidence,
            "penalty": rejection_penalty,
            "refinement_policy": refinement_policy,
        }
        candidate_scores.append(score_detail)
        candidate["candidate_score_detail"] = score_detail
        if not valid:
            candidate["recovered_rejection_reason"] = reason
        scored.append((score, refined, candidate, "geometry_validated_detection" if valid else "recovered_geometry_candidate"))

    inferred = infer_elevator_box_from_image(image, detections, geometry)
    if inferred is not None:
        inferred = clamp_box(inferred, w, h)
        edge_score, refined = edge_alignment_score_and_refined_roi(image, inferred, cfg)
        nested_score, nested_evidence = nested_frame_depth_score(image, refined, depth_map)
        score = 0.82 + edge_score * 1.05 + depth_roi_score(depth_map, refined) * 0.25 + nested_score * 0.35
        score_detail = {
            "box": refined,
            "raw_box": inferred,
            "phrase": "image_structure_fallback",
            "score": float(score),
            "edge_score": edge_score,
            "nested_frame_depth_score": nested_score,
            "nested_frame_depth_evidence": nested_evidence,
        }
        candidate_scores.append(score_detail)
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
                    "candidate_score_detail": score_detail,
                },
                "image_edges_fallback",
            )
        )

    if not scored:
        return None, {"raw_candidates": raw_candidates, "rejected_candidates": rejected, "candidate_scores": candidate_scores}

    selected_score, selected_box, selected_candidate, selected_reason = max(scored, key=lambda item: item[0])
    selected_detail = selected_candidate.get("candidate_score_detail", {})
    LOGGER.info("[ROI] Selected full doorway/cabin ROI: %s score=%.3f", selected_box, selected_score)
    return selected_box, {
        "raw_candidates": raw_candidates,
        "rejected_candidates": rejected,
        "candidate_scores": candidate_scores,
        "candidate_rejection_reasons": [{"box": item.get("box"), "reason": item.get("reason")} for item in rejected],
        "nested_frame_depth_evidence": selected_detail.get("nested_frame_depth_evidence", {}),
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


def recoverable_elevator_candidate(
    box: list[int],
    refined: list[int],
    phrase: str,
    reason: str,
    width: int,
    height: int,
    edge_score: float,
) -> bool:
    if "elevator" not in phrase and "door" not in phrase and "frame" not in phrase:
        return False
    x1, y1, x2, y2 = refined
    bw, bh = x2 - x1, y2 - y1
    if reason == "extends too far below threshold":
        return edge_score >= 0.58 and bh >= height * 0.48 and bw <= width * 0.58
    if reason == "starts too high above elevator opening":
        return edge_score >= 0.70 and y2 >= height * 0.45
    return False


def candidate_penalty(box: list[int], refined: list[int], reason: str, width: int, height: int) -> float:
    del box
    if reason == "extends too far below threshold":
        overflow = max(0.0, refined[3] - height * 0.96) / max(height * 0.08, 1.0)
        return min(0.32, overflow * 0.10)
    if reason == "starts too high above elevator opening":
        return 0.18
    return 0.40


def adjacent_component_score(box: list[int], detections: dict[str, Any], src_w: int, src_h: int, width: int, height: int) -> float:
    operating_panel = "tall stainless steel elevator operating panel with round buttons"
    terms = (operating_panel, "elevator call button panel", "wheelchair button", "floor indicator", "weight limit", "capacity")
    x1, y1, x2, y2 = box
    score = 0.0
    for det in detections.get("detections", []):
        phrase = str(det.get("phrase", "")).lower()
        norm = str(det.get("normalized_component_type", "")).lower()
        if not any(term in phrase for term in terms) and norm not in {
            operating_panel,
            "elevator call button panel",
            "wheelchair button",
            "floor_indicator_display",
            "weight_limit_sign",
        }:
            continue
        bx1, by1, bx2, by2 = scaled_box(det["box_xyxy"], src_w, src_h, width, height)
        bcx, bcy = (bx1 + bx2) * 0.5, (by1 + by2) * 0.5
        horizontal_gap = min(abs(bx1 - x2), abs(x1 - bx2), abs(bcx - ((x1 + x2) * 0.5)))
        beside = (y1 - height * 0.10) <= bcy <= (y2 + height * 0.10) and horizontal_gap < width * 0.28
        above = y1 - height * 0.18 <= bcy <= y1 + height * 0.12 and x1 - width * 0.15 <= bcx <= x2 + width * 0.15
        if beside or above:
            score = max(score, 1.0 if norm in {operating_panel, "elevator call button panel", "floor_indicator_display"} else 0.65)
    return score


def nested_frame_depth_score(image: np.ndarray, box: list[int], depth_map: np.ndarray | None) -> tuple[float, dict[str, Any]]:
    x1, y1, x2, y2 = box
    h, w = image.shape[:2]
    bw, bh = x2 - x1, y2 - y1
    if bw <= 4 or bh <= 4:
        return 0.0, {}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    roi = gray[y1:y2, x1:x2]
    sx = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    sy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    left_edge = float(sx[y1:y2, max(0, x1 - 1) : min(w, x1 + 2)].mean())
    right_edge = float(sx[y1:y2, max(0, x2 - 2) : min(w, x2 + 1)].mean())
    top_edge = float(sy[max(0, y1 - 1) : min(h, y1 + 2), x1:x2].mean())
    bottom_edge = float(sy[max(0, y2 - 2) : min(h, y2 + 1), x1:x2].mean())
    edge_norm = float(np.mean(sx) + np.mean(sy) + 1e-6)
    boundary_coverage = float(np.clip((left_edge + right_edge + top_edge + bottom_edge) / edge_norm / 12.0, 0.0, 1.0))
    center = roi[int(bh * 0.20) : int(bh * 0.88), int(bw * 0.25) : int(bw * 0.75)]
    border = roi.copy()
    border[int(bh * 0.20) : int(bh * 0.88), int(bw * 0.25) : int(bw * 0.75)] = 0
    center_dark_ratio = float(np.mean(center < np.percentile(roi, 38))) if center.size else 0.0
    interior_contrast = float(np.median(border[border > 0]) - np.median(center)) if center.size and np.any(border > 0) else 0.0
    depth_contrast = 0.0
    if depth_map is not None:
        d = depth_map[y1:y2, x1:x2]
        if d.size:
            dh, dw = d.shape[:2]
            dc = d[int(dh * 0.22) : int(dh * 0.86), int(dw * 0.28) : int(dw * 0.72)]
            db = d.copy()
            db[int(dh * 0.22) : int(dh * 0.86), int(dw * 0.28) : int(dw * 0.72)] = np.nan
            depth_contrast = float(np.nanmedian(db) - np.median(dc)) if dc.size else 0.0
    scale_score = 1.0 - min(1.0, abs((bw * bh) / max(w * h, 1) - 0.34) / 0.34)
    open_cabin_score = float(np.clip(center_dark_ratio * 1.2 + max(interior_contrast, 0.0) / 80.0 + abs(depth_contrast) * 0.8, 0.0, 1.0))
    score = float(np.clip(boundary_coverage * 0.45 + scale_score * 0.25 + open_cabin_score * 0.30, 0.0, 1.0))
    return score, {
        "boundary_coverage": boundary_coverage,
        "center_dark_ratio": center_dark_ratio,
        "interior_contrast": interior_contrast,
        "depth_contrast": depth_contrast,
        "scale_score": scale_score,
        "open_cabin_score": open_cabin_score,
    }


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


def constrain_animation_roi_to_detection_box(
    raw_box: list[int],
    refined_box: list[int],
    width: int,
    height: int,
    cfg: dict[str, Any] | None = None,
) -> tuple[list[int], dict[str, Any]]:
    video_cfg = (cfg or {}).get("video", {}) if cfg else {}
    if not bool(video_cfg.get("prefer_groundingdino_door_roi", True)):
        return refined_box, {"status": "refinement_allowed"}
    rx1, ry1, rx2, ry2 = clamp_box(raw_box, width, height)
    fx1, fy1, fx2, fy2 = clamp_box(refined_box, width, height)
    raw_w, raw_h = max(1, rx2 - rx1), max(1, ry2 - ry1)
    refined_w, refined_h = max(1, fx2 - fx1), max(1, fy2 - fy1)
    expanded = (
        fx1 < rx1 - raw_w * 0.04
        or fy1 < ry1 - raw_h * 0.04
        or fx2 > rx2 + raw_w * 0.04
        or fy2 > ry2 + raw_h * 0.04
        or refined_w * refined_h > raw_w * raw_h * 1.18
    )
    if not expanded:
        return [fx1, fy1, fx2, fy2], {"status": "refinement_kept_inside_detection"}

    inset_ratio = float(video_cfg.get("groundingdino_door_roi_inset_ratio", 0.018))
    inset_x = max(1, int(round(raw_w * inset_ratio)))
    inset_y = max(1, int(round(raw_h * inset_ratio)))
    constrained = clamp_box([rx1 + inset_x, ry1 + inset_y, rx2 - inset_x, ry2 - inset_y], width, height)
    LOGGER.info("[ROI] Using inset GroundingDINO door ROI: %s raw=%s refined=%s", constrained, raw_box, refined_box)
    return constrained, {
        "status": "constrained_to_groundingdino_detection",
        "reason": "refinement_expanded_outside_detected_door",
        "raw_detection_box": [rx1, ry1, rx2, ry2],
        "edge_refined_box": [fx1, fy1, fx2, fy2],
        "inset_ratio": inset_ratio,
    }


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
        "elevator cabin",
        "elevator ceiling",
        "elevator interior",
        "elevator wall",
        "elevator floor",
        "inside elevator",
        "handrail",
        "elevator handrail",
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
    visual_open_score, visual_evidence = open_elevator_visual_evidence(img, scaled_door_box)
    debug["visual_open_score"] = visual_open_score
    debug["elevator_state_evidence"] = visual_evidence
    if depth_map is not None:
        depth_state, depth_debug = classify_elevator_state_from_depth(depth_map, scaled_door_box)
        debug.update(depth_debug)
        if depth_state == "open":
            debug["elevator_state"] = depth_state
            debug["state_source"] = "depth"
            return depth_state, debug
        if depth_state == "closed":
            weak_depth_closed = abs(float(depth_debug.get("depth_contrast") or 0.0)) < 6.0
            roi_height_ratio = (scaled_door_box[3] - scaled_door_box[1]) / max(img.shape[0], 1)
            open_override = has_interior_detection or visual_open_score >= 2.0 or (
                weak_depth_closed and visual_open_score >= 1.5 and roi_height_ratio >= 0.68
            )
            if not open_override:
                debug["elevator_state"] = depth_state
                debug["state_source"] = "depth"
                return depth_state, debug
            if weak_depth_closed and visual_open_score >= 1.5 and roi_height_ratio >= 0.68:
                debug["elevator_state"] = "open"
                debug["state_source"] = "weak_depth_visual_open_evidence"
                return "open", debug

    if visual_open_score >= 2.0:
        debug["elevator_state"] = "open"
        debug["state_source"] = "visual_open_evidence"
        return "open", debug

    if has_interior_detection:
        debug["elevator_state"] = "open"
        debug["state_source"] = "interior_detection_fallback"
        return "open", debug

    debug["elevator_state"] = image_state
    debug["state_source"] = "image_fallback" if best_det is not None else "image_fallback_no_detection"
    return image_state, debug


def open_elevator_visual_evidence(img: np.ndarray, box: list[int]) -> tuple[float, dict[str, Any]]:
    x1, y1, x2, y2 = box
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0, {}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape[:2]
    if h < 10 or w < 10:
        return 0.0, {}
    center = gray[int(h * 0.12) : int(h * 0.90), int(w * 0.32) : int(w * 0.68)]
    sides = np.concatenate(
        [
            gray[int(h * 0.12) : int(h * 0.90), int(w * 0.05) : int(w * 0.22)].reshape(-1),
            gray[int(h * 0.12) : int(h * 0.90), int(w * 0.78) : int(w * 0.95)].reshape(-1),
        ]
    )
    edges_x = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)).mean(axis=0)
    mid_edges = float(edges_x[int(w * 0.38) : int(w * 0.62)].mean())
    side_edges = float(np.r_[edges_x[int(w * 0.08) : int(w * 0.24)], edges_x[int(w * 0.76) : int(w * 0.92)]].mean())
    center_dark = float(np.mean(center < np.percentile(gray, 35))) if center.size else 0.0
    center_delta = float(np.median(sides) - np.median(center)) if center.size and sides.size else 0.0
    texture_ratio = float(np.std(center) / max(float(np.std(sides)), 1.0)) if center.size and sides.size else 1.0
    score = 0.0
    score += 1.0 if center_dark > 0.36 else 0.0
    score += 1.0 if center_delta > 18.0 else 0.0
    score += 0.75 if mid_edges > side_edges * 1.08 else 0.0
    score += 0.75 if texture_ratio > 1.18 or texture_ratio < 0.72 else 0.0
    return score, {
        "center_dark_ratio": center_dark,
        "center_vs_side_delta": center_delta,
        "mid_vertical_edge_energy": mid_edges,
        "side_vertical_edge_energy": side_edges,
        "center_texture_ratio": texture_ratio,
    }


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
    normalized = str(det.get("normalized_component_type", "")).strip().lower()
    if phrase not in interior_labels and normalized not in {"elevator_cabin", "handrail", "security_camera"}:
        return False
    box = _scaled_detection_box(det, detections, roi, hw)
    iou_with_roi = box_iou(box, roi)
    rx1, ry1, rx2, ry2 = roi
    bx1, by1, bx2, by2 = box
    roi_area = max(1, (rx2 - rx1) * (ry2 - ry1))
    box_area = max(1, (bx2 - bx1) * (by2 - by1))
    if "elevator wall" in phrase and box_area > roi_area * 0.65:
        return False
    if normalized == "elevator_cabin" and iou_with_roi > 0.75 and float(det.get("score", 0.0)) < 0.35:
        return False
    cx = (bx1 + bx2) * 0.5
    cy = (by1 + by2) * 0.5
    center_inside_roi = rx1 <= cx <= rx2 and ry1 <= cy <= ry2
    if normalized == "handrail" or "handrail" in phrase:
        return center_inside_roi and float(det.get("score", 0.0)) >= 0.24
    if iou_with_roi <= 0.05:
        return False
    return center_inside_roi


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
