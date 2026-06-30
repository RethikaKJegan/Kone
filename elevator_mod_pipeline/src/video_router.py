try:
    from .video import render_elevator_video
except ImportError:
    from video import render_elevator_video

try:
    from .video_comfy import COMFY_ENGINES, render_comfy_video
except ImportError:
    try:
        from video_comfy import COMFY_ENGINES, render_comfy_video
    except ImportError:
        COMFY_ENGINES = set()
        render_comfy_video = None

try:
    from .video_wan import render_wan_video
except ImportError:
    try:
        from video_wan import render_wan_video
    except ImportError:
        render_wan_video = None


WAN_ENGINES = {"wan", "wan2.2", "wan22"}


def render_video(image_path, detections=None, geometry=None, cfg=None, out_path=None, depth_path=None):
    cfg = cfg or {}
    video_cfg = cfg.get("video", {})
    engine = str(video_cfg.get("engine", "opencv")).strip().lower()

    if engine in COMFY_ENGINES:
        if render_comfy_video is None:
            raise RuntimeError("Comfy video engine requested, but video_comfy.py is not available")
        return render_comfy_video(
            image_path=image_path,
            detections=detections,
            geometry=geometry,
            cfg=cfg,
            out_path=out_path,
            depth_path=depth_path,
        )

    if engine in WAN_ENGINES:
        if render_wan_video is None:
            raise RuntimeError(
                "Wan video engine requested in the logic pipeline, but video_wan.py is not available. "
                "Use the API Step 5 ComfyUI path or set video.engine to a supported engine."
            )
        return render_wan_video(
            image_path=image_path,
            detections=detections,
            geometry=geometry,
            cfg=cfg,
            out_path=out_path,
            depth_path=depth_path,
        )

    return render_elevator_video(
        image_path=image_path,
        detections=detections,
        geometry=geometry,
        cfg=cfg,
        out_path=out_path,
        depth_path=depth_path,
    )
