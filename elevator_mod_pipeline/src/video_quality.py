from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2


def validate_generated_video(
    path: str | Path,
    *,
    engine: str,
    expected_fps: int | None = None,
    expected_min_frames: int | None = None,
    expected_min_duration: float | None = None,
    min_size_bytes: int = 1_000_000,
) -> dict[str, Any]:
    video_path = Path(path)
    diagnostics: dict[str, Any] = {
        "path": str(video_path),
        "engine": engine,
        "expected_fps": expected_fps,
        "expected_min_frames": expected_min_frames,
        "expected_min_duration_seconds": expected_min_duration,
        "min_size_bytes": min_size_bytes,
    }
    if not video_path.exists():
        diagnostics["status"] = "failed_missing_file"
        raise RuntimeError(f"Video validation failed: output file missing: {video_path}")

    size = video_path.stat().st_size
    diagnostics["file_size_bytes"] = size
    if size < min_size_bytes:
        diagnostics["status"] = "failed_too_small"
        raise RuntimeError(
            f"Video validation failed: {video_path} is only {size} bytes; "
            f"expected at least {min_size_bytes} bytes for {engine}"
        )

    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()

    duration = frame_count / fps if fps > 0 else 0.0
    diagnostics.update(
        {
            "fps": fps,
            "frame_count": frame_count,
            "duration_seconds": duration,
            "width": width,
            "height": height,
        }
    )
    if fps <= 0 or frame_count <= 0 or duration <= 0 or width <= 0 or height <= 0:
        diagnostics["status"] = "failed_invalid_media"
        raise RuntimeError(f"Video validation failed: invalid media metadata for {video_path}: {diagnostics}")
    if expected_fps is not None and abs(fps - float(expected_fps)) > 1.0:
        diagnostics["status"] = "failed_wrong_fps"
        raise RuntimeError(f"Video validation failed: expected ~{expected_fps} fps, got {fps:.3f}: {video_path}")
    if expected_min_frames is not None and frame_count < expected_min_frames:
        diagnostics["status"] = "failed_too_few_frames"
        raise RuntimeError(
            f"Video validation failed: expected at least {expected_min_frames} frames, got {frame_count}: {video_path}"
        )
    if expected_min_duration is not None and duration < expected_min_duration:
        diagnostics["status"] = "failed_too_short"
        raise RuntimeError(
            f"Video validation failed: expected at least {expected_min_duration:.2f}s, got {duration:.2f}s: {video_path}"
        )

    diagnostics["status"] = "passed"
    return diagnostics
