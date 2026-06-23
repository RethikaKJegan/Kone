try:
    from .video import render_elevator_video
    from .video_wan import render_wan_video
except ImportError:
    from video import render_elevator_video
    from video_wan import render_wan_video


def render_video(image_path, detections=None, geometry=None, cfg=None, out_path=None, depth_path=None):
    cfg = cfg or {}
    video_cfg = cfg.get("video", {})
    engine = video_cfg.get("engine", "opencv")

    if engine == "wan2.2":
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
