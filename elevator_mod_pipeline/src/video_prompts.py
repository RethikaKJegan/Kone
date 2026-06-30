WAN_POSITIVE_PROMPTS = {
    "lci_right_arc": (
        "locked-off tripod shot of an elevator lobby from the exact original front-facing viewpoint, "
        "no camera pan, no camera arc, no zoom, no push-in, no perspective change. Preserve the input "
        "image architecture exactly: elevator doorway, wall tiles, stainless steel door frame, signage, "
        "call buttons, display panels, water bottles, floor, ceiling, and all straight vertical and "
        "horizontal edges must remain fixed, sharp, readable, and geometrically stable for the full "
        "video. Only very subtle natural changes are allowed: tiny exposure breathing, faint realistic "
        "reflections on metal, and slight sensor noise. Photorealistic indoor lighting, documentary "
        "security-camera style, stable single-view video, no object morphing, no texture smearing"
    ),
    "door_open": (
        "locked-off tripod shot of an elevator door in an indoor building corridor, fixed camera "
        "position, no pan, no zoom, no perspective change. The elevator doors open smoothly from fully "
        "closed to fully open while the wall tiles, door frame, signage, call buttons, floor, ceiling, "
        "and background remain perfectly fixed and geometrically stable. Brushed stainless steel doors "
        "move mechanically and cleanly, with realistic reflections on metal, natural indoor lighting, "
        "subtle sensor noise, photorealistic documentary style. Preserve all straight lines and readable "
        "details; no warping, no melting, no texture smearing"
    ),
    "door_close": (
        "locked-off tripod shot of an elevator door in an indoor building corridor, fixed camera "
        "position, no pan, no zoom, no perspective change. The elevator doors close smoothly from fully "
        "open to fully closed while the wall tiles, door frame, signage, call buttons, floor, ceiling, "
        "and background remain perfectly fixed and geometrically stable. Brushed stainless steel doors "
        "move mechanically and cleanly, with realistic reflections on metal, natural indoor lighting, "
        "subtle sensor noise, photorealistic documentary style. Preserve all straight lines and readable "
        "details; no warping, no melting, no texture smearing"
    ),
}

WAN_NEGATIVE_PROMPTS = {
    "lci_right_arc": (
        "cartoon, animation, CGI, 3d render, fake render, warped elevator, distorted LCI panel, "
        "changing LCI shape, unreadable display, flickering numbers, broken display, distorted wall "
        "tiles, bending metal, impossible geometry, heavy camera shake, fast pan, camera arc, zoom, "
        "push-in, zoom jump, blurry, motion blur streaks, texture smear, melted surfaces, stretched "
        "door frame, vertical banding, duplicated panels, extra elevator doors, object morphing, "
        "low quality, sudden lighting change, text changing, people appearing, watermark, logo"
    ),
    "door_open": (
        "cartoon, animation, CGI, 3d render, artificial render, warped elevator doors, bending metal, "
        "distorted reflections, changing camera angle, pan, zoom, perspective shift, flicker, jitter, "
        "blurry, motion blur streaks, texture smear, melted surfaces, stretched door frame, low quality, "
        "text changing, watermark, logo, people appearing, duplicated doors, impossible geometry, "
        "sudden lighting change, overexposed, underexposed"
    ),
    "door_close": (
        "cartoon, animation, CGI, 3d render, artificial render, warped elevator doors, bending metal, "
        "distorted reflections, changing camera angle, pan, zoom, perspective shift, flicker, jitter, "
        "blurry, motion blur streaks, texture smear, melted surfaces, stretched door frame, low quality, "
        "text changing, watermark, logo, people appearing, duplicated doors, impossible geometry, "
        "sudden lighting change, overexposed, underexposed"
    ),
}

WAN_PROMPT_ALIASES = {
    "zoom": "lci_right_arc",
    "zoom-in": "lci_right_arc",
    "zoom_in": "lci_right_arc",
    "pan_l_r": "lci_right_arc",
    "pan-l-r": "lci_right_arc",
    "pan_lr": "lci_right_arc",
    "pan_r_l": "lci_right_arc",
    "pan-r-l": "lci_right_arc",
    "pan_rl": "lci_right_arc",
    "lci": "lci_right_arc",
    "lci_right_arc": "lci_right_arc",
    "rightward_arc": "lci_right_arc",
    "door": "door_open",
    "door_functionality": "door_open",
    "door-open": "door_open",
    "door_open": "door_open",
    "open": "door_open",
    "door-close": "door_close",
    "door_close": "door_close",
    "close": "door_close",
}


def normalize_wan_prompt_key(motion_style: str | None, cfg: dict) -> str:
    video_cfg = cfg.get("video", {}) if cfg else {}
    door_functionality = video_cfg.get("door_functionality")

    if door_functionality:
        action = str(door_functionality).strip().lower()
        if action == "close":
            return "door_close"
        return "door_open"

    requested = motion_style or video_cfg.get("motion_style") or video_cfg.get("mode") or "lci_right_arc"
    requested = str(requested).strip().lower()
    return WAN_PROMPT_ALIASES.get(requested, "lci_right_arc")


def build_wan_prompt_pack(motion_style: str | None, cfg: dict) -> dict:
    prompt_key = normalize_wan_prompt_key(motion_style, cfg)
    return {
        "prompt_key": prompt_key,
        "positive": WAN_POSITIVE_PROMPTS[prompt_key],
        "negative": WAN_NEGATIVE_PROMPTS[prompt_key],
    }


def build_wan_prompt(motion_style: str, cfg: dict) -> str:
    return build_wan_prompt_pack(motion_style, cfg)["positive"]
