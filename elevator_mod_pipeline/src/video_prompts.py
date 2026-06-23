WAN_MOTION_PROMPTS = {
    "zoom_in": "A realistic slow camera push-in inside a modern elevator cabin, stable geometry, natural lighting, subtle reflections, premium commercial video.",
    "pan_l_r": "A realistic smooth camera pan from left to right inside a modern elevator cabin, the elevator walls and control panel remain geometrically stable, natural lighting, subtle reflections.",
    "pan_r_l": "A realistic smooth camera pan from right to left inside a modern elevator cabin, stable elevator geometry, premium commercial showroom style.",
    "pan_t_b": "A realistic slow tilt from ceiling to floor inside a modern elevator cabin, stable perspective, natural indoor lighting.",
    "pan_b_t": "A realistic slow tilt from floor to ceiling inside a modern elevator cabin, stable perspective, premium commercial interior.",
    "door_functionality": "A realistic elevator door opening and closing sequence, smooth mechanical movement, stable cabin interior, natural lighting, no distortion.",
}


def build_wan_prompt(motion_style: str, cfg: dict) -> str:
    motion_style = motion_style or "zoom_in"
    return WAN_MOTION_PROMPTS.get(motion_style, WAN_MOTION_PROMPTS["zoom_in"])
