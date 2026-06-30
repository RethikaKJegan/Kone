from __future__ import annotations

import copy
import json
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

try:
    from .video_prompts import build_wan_prompt_pack
    from .video_quality import validate_generated_video
except ImportError:
    from video_prompts import build_wan_prompt_pack
    from video_quality import validate_generated_video


COMFY_ENGINES = {"comfy", "comfy_wan", "comfy_i2v", "comfy_flf2v", "wan_comfy"}
DEFAULT_COMFY_ROOT = Path("/root/vdotest/ComfyUI")
DEFAULT_WORKFLOW_DIR = Path("/root/vdotest/workflows")
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"


def render_comfy_video(image_path, detections=None, geometry=None, cfg=None, out_path=None, depth_path=None):
    del detections, geometry, depth_path
    cfg = cfg or {}
    image_path = Path(image_path)
    out_path = Path(out_path or image_path.with_name("elevator_animation.mp4"))
    video_cfg = cfg.get("video", {})
    comfy_cfg = merged_comfy_config(video_cfg)
    engine = str(video_cfg.get("engine", "comfy_i2v")).strip().lower()
    mode = normalize_comfy_mode(engine, video_cfg)

    if not image_path.exists():
        raise FileNotFoundError(f"ComfyUI input image not found: {image_path}")

    workflow_path = resolve_workflow_path(comfy_cfg, mode)
    workflow = load_workflow(workflow_path)
    run_id = uuid.uuid4().hex[:12]
    work_dir = out_path.parent / "_comfy_generation" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    prompt_pack = build_wan_prompt_pack(video_cfg.get("motion_style"), cfg)
    positive_prompt = str(comfy_cfg.get("positive_prompt") or video_cfg.get("prompt") or prompt_pack["positive"])
    negative_prompt = str(comfy_cfg.get("negative_prompt") or video_cfg.get("negative_prompt") or prompt_pack["negative"])
    preset = quality_preset(mode, video_cfg, comfy_cfg)

    image_refs = prepare_comfy_inputs(image_path, video_cfg, comfy_cfg, mode, run_id)
    patched, patch_debug = patch_workflow(
        workflow,
        mode=mode,
        image_refs=image_refs,
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        preset=preset,
        comfy_cfg=comfy_cfg,
        filename_prefix=f"kone_{mode}_{run_id}",
    )

    patched_path = work_dir / "patched_workflow.json"
    patched_path.write_text(json.dumps(patched, indent=2), encoding="utf-8")

    base_url = str(comfy_cfg.get("url", DEFAULT_COMFY_URL)).rstrip("/")
    started_at = time.time()
    prompt_id = queue_prompt(base_url, patched)
    history = wait_for_history(base_url, prompt_id, timeout_s=float(comfy_cfg.get("timeout_seconds", 3600)))
    generated = find_generated_video(history, prompt_id, comfy_cfg, work_dir, started_at)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated, out_path)

    validation = validate_generated_video(
        out_path,
        engine=f"comfy_{mode}",
        expected_fps=int(preset["fps"]),
        expected_min_frames=max(1, int(preset["length"]) - 2),
        expected_min_duration=max(1.0, (int(preset["length"]) - 2) / float(preset["fps"])),
        min_size_bytes=int(comfy_cfg.get("min_size_bytes", 1_000_000)),
    )
    metadata = {
        "engine": f"comfy_{mode}",
        "requested_engine": engine,
        "workflow_path": str(workflow_path),
        "patched_workflow": str(patched_path),
        "prompt_id": prompt_id,
        "input_image": str(image_path),
        "output_video": str(out_path),
        "comfy_output_video": str(generated),
        "prompt_key": prompt_pack["prompt_key"],
        "prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "quality": video_cfg.get("quality", comfy_cfg.get("quality", "best")),
        "quality_mode": comfy_cfg.get("quality_mode", video_cfg.get("quality_mode", "best")),
        "width": preset["width"],
        "height": preset["height"],
        "length": preset["length"],
        "fps": preset["fps"],
        "seed": preset.get("seed"),
        "models": comfy_model_metadata(comfy_cfg),
        "patch_debug": patch_debug,
        "video_validation": validation,
        "video_validation_status": validation["status"],
    }
    out_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return out_path


def merged_comfy_config(video_cfg: dict[str, Any]) -> dict[str, Any]:
    comfy_cfg = copy.deepcopy(video_cfg.get("comfy", {}) or {})
    comfy_cfg.setdefault("url", DEFAULT_COMFY_URL)
    comfy_cfg.setdefault("root_dir", str(DEFAULT_COMFY_ROOT))
    comfy_cfg.setdefault("workflow_dir", str(DEFAULT_WORKFLOW_DIR))
    comfy_cfg.setdefault("i2v_workflow", "wan22_14b_i2v.json")
    comfy_cfg.setdefault("flf2v_workflow", "wan22_14b_flf2v.json")
    comfy_cfg.setdefault("input_dir", str(Path(comfy_cfg["root_dir"]) / "input"))
    comfy_cfg.setdefault("output_dir", str(Path(comfy_cfg["root_dir"]) / "output"))
    comfy_cfg.setdefault("quality_mode", video_cfg.get("quality_mode", "best"))
    comfy_cfg.setdefault("min_size_bytes", 1_000_000)
    return comfy_cfg


def normalize_comfy_mode(engine: str, video_cfg: dict[str, Any]) -> str:
    requested = str(video_cfg.get("mode") or video_cfg.get("comfy_mode") or "").strip().lower()
    if engine == "comfy_flf2v" or requested in {"flf2v", "door_open", "door_close", "door_functionality"}:
        return "flf2v"
    return "i2v"


def resolve_workflow_path(comfy_cfg: dict[str, Any], mode: str) -> Path:
    key = "flf2v_workflow" if mode == "flf2v" else "i2v_workflow"
    workflow = Path(str(comfy_cfg.get(key)))
    if not workflow.is_absolute():
        workflow = Path(str(comfy_cfg.get("workflow_dir", DEFAULT_WORKFLOW_DIR))) / workflow
    if not workflow.exists():
        raise FileNotFoundError(
            f"ComfyUI workflow not found for {mode}: {workflow}. "
            "Mount or install the documented /root/vdotest workflows before using the Comfy engine."
        )
    return workflow


def load_workflow(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"ComfyUI workflow must be a JSON object: {path}")
    return data


def quality_preset(mode: str, video_cfg: dict[str, Any], comfy_cfg: dict[str, Any]) -> dict[str, Any]:
    quality_mode = str(comfy_cfg.get("quality_mode", video_cfg.get("quality_mode", "best"))).lower()
    if quality_mode in {"fast", "preview"}:
        defaults = {"width": 480, "height": 832, "length": 49, "fps": 16}
    elif mode == "flf2v":
        defaults = {"width": 720, "height": 1280, "length": 81, "fps": 16}
    else:
        defaults = {"width": 720, "height": 960, "length": 81, "fps": 16}

    return {
        "width": int(comfy_cfg.get("width", video_cfg.get("width", defaults["width"]))),
        "height": int(comfy_cfg.get("height", video_cfg.get("height", defaults["height"]))),
        "length": int(comfy_cfg.get("length", video_cfg.get("frame_num", video_cfg.get("length", defaults["length"])))),
        "fps": int(comfy_cfg.get("fps", video_cfg.get("fps", defaults["fps"]))),
        "seed": comfy_cfg.get("seed", video_cfg.get("seed")),
    }


def prepare_comfy_inputs(
    image_path: Path,
    video_cfg: dict[str, Any],
    comfy_cfg: dict[str, Any],
    mode: str,
    run_id: str,
) -> dict[str, str]:
    input_dir = Path(str(comfy_cfg.get("input_dir")))
    input_dir.mkdir(parents=True, exist_ok=True)

    def copy_input(src: Path, label: str) -> str:
        if not src.exists():
            raise FileNotFoundError(f"ComfyUI {label} image not found: {src}")
        dst = input_dir / f"kone_{run_id}_{label}{src.suffix or '.png'}"
        shutil.copy2(src, dst)
        return dst.name

    refs = {"input": copy_input(image_path, "input")}
    if mode == "flf2v":
        start = Path(str(video_cfg.get("start_image") or video_cfg.get("closed_reference_image") or image_path))
        end_value = video_cfg.get("end_image") or video_cfg.get("open_reference_image")
        if not end_value:
            raise ValueError(
                "Comfy FLF2V requires video.start_image/end_image or closed_reference_image/open_reference_image. "
                "Use comfy_i2v for one-image LCI motion."
            )
        refs["start"] = copy_input(start, "start")
        refs["end"] = copy_input(Path(str(end_value)), "end")
    return refs


def patch_workflow(
    workflow: dict[str, Any],
    *,
    mode: str,
    image_refs: dict[str, str],
    positive_prompt: str,
    negative_prompt: str,
    preset: dict[str, Any],
    comfy_cfg: dict[str, Any],
    filename_prefix: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(workflow)
    nodes = patched.get("nodes") if isinstance(patched.get("nodes"), list) else patched
    if not isinstance(nodes, dict) and not isinstance(nodes, list):
        raise ValueError("Unsupported ComfyUI workflow format: expected API prompt object or nodes list")

    load_image_index = 0
    text_index = 0
    debug = {"patched_nodes": []}

    for node_id, node in iter_nodes(nodes):
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = str(node.get("class_type") or node.get("type") or "")
        title = str((node.get("_meta") or {}).get("title") or node.get("title") or "").lower()

        if "image" in inputs and ("loadimage" in class_type.lower() or class_type.lower() == "load image"):
            image_name = select_image_for_node(mode, image_refs, title, load_image_index)
            inputs["image"] = image_name
            load_image_index += 1
            debug["patched_nodes"].append({"node": node_id, "field": "image", "value": image_name})

        if "text" in inputs and "text" in class_type.lower() or ("text" in inputs and "cliptextencode" in class_type.lower()):
            value = negative_prompt if is_negative_text_node(title, text_index) else positive_prompt
            inputs["text"] = value
            text_index += 1
            debug["patched_nodes"].append({"node": node_id, "field": "text", "negative": value == negative_prompt})

        patch_numeric(inputs, node_id, preset, debug)
        patch_models(inputs, node_id, comfy_cfg, debug)
        patch_filename(inputs, node_id, filename_prefix, debug)

    debug["load_image_nodes"] = load_image_index
    debug["text_nodes"] = text_index
    return patched, debug


def iter_nodes(nodes: Any):
    if isinstance(nodes, dict):
        for node_id, node in nodes.items():
            if isinstance(node, dict):
                yield str(node_id), node
    elif isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                yield str(node.get("id", "")), node


def select_image_for_node(mode: str, refs: dict[str, str], title: str, index: int) -> str:
    if mode == "flf2v":
        if "end" in title or "last" in title or "open" in title:
            return refs["end"]
        if "start" in title or "first" in title or "closed" in title:
            return refs["start"]
        return refs["start"] if index == 0 else refs["end"]
    return refs["input"]


def is_negative_text_node(title: str, text_index: int) -> bool:
    if any(term in title for term in ("negative", "neg", "bad")):
        return True
    if any(term in title for term in ("positive", "prompt", "pos")):
        return False
    return text_index == 1


def patch_numeric(inputs: dict[str, Any], node_id: str, preset: dict[str, Any], debug: dict[str, Any]) -> None:
    mapping = {
        "width": "width",
        "height": "height",
        "length": "length",
        "frame_num": "length",
        "frames": "length",
        "fps": "fps",
        "frame_rate": "fps",
        "noise_seed": "seed",
        "seed": "seed",
    }
    for key, preset_key in mapping.items():
        if key in inputs and preset.get(preset_key) is not None:
            inputs[key] = preset[preset_key]
            debug["patched_nodes"].append({"node": node_id, "field": key, "value": preset[preset_key]})


def patch_models(inputs: dict[str, Any], node_id: str, comfy_cfg: dict[str, Any], debug: dict[str, Any]) -> None:
    model_keys = {
        "high_noise_model": "wan2.2_i2v_high_noise_14B_fp16.safetensors",
        "low_noise_model": "wan2.2_i2v_low_noise_14B_fp16.safetensors",
        "high_noise_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
        "low_noise_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
        "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "vae_name": "wan_2.1_vae.safetensors",
    }
    for key, default in model_keys.items():
        if key in inputs:
            inputs[key] = comfy_cfg.get(key, default)
            debug["patched_nodes"].append({"node": node_id, "field": key, "value": inputs[key]})


def patch_filename(inputs: dict[str, Any], node_id: str, filename_prefix: str, debug: dict[str, Any]) -> None:
    for key in ("filename_prefix", "filename", "prefix"):
        if key in inputs and isinstance(inputs[key], str):
            inputs[key] = filename_prefix
            debug["patched_nodes"].append({"node": node_id, "field": key, "value": filename_prefix})


def queue_prompt(base_url: str, workflow: dict[str, Any]) -> str:
    payload = json.dumps({"prompt": workflow, "client_id": uuid.uuid4().hex}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not submit workflow to ComfyUI at {base_url}: {exc}") from exc
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return a prompt_id: {data}")
    return str(prompt_id)


def wait_for_history(base_url: str, prompt_id: str, timeout_s: float) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/history/{prompt_id}", timeout=30) as response:
                history = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not read ComfyUI history from {base_url}: {exc}") from exc
        if prompt_id in history:
            prompt_history = history[prompt_id]
            status = (prompt_history.get("status") or {}).get("status_str")
            if status == "error":
                raise RuntimeError(f"ComfyUI render failed: {prompt_history.get('status')}")
            if prompt_history.get("outputs"):
                return prompt_history
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id} after {timeout_s:.0f}s")


def find_generated_video(
    history: dict[str, Any],
    prompt_id: str,
    comfy_cfg: dict[str, Any],
    work_dir: Path,
    started_at: float,
) -> Path:
    output_dir = Path(str(comfy_cfg.get("output_dir")))
    candidates: list[Path] = []
    for output in (history.get("outputs") or {}).values():
        for key in ("videos", "gifs", "animated", "files"):
            for item in output.get(key, []) if isinstance(output.get(key), list) else []:
                filename = item.get("filename") if isinstance(item, dict) else None
                subfolder = item.get("subfolder", "") if isinstance(item, dict) else ""
                if filename and Path(filename).suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}:
                    candidates.append(output_dir / subfolder / filename)
    if not candidates:
        candidates.extend(
            p
            for p in sorted(output_dir.rglob("*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)[:10]
            if p.stat().st_mtime >= started_at - 1
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    debug_path = work_dir / "comfy_history.json"
    debug_path.write_text(json.dumps({prompt_id: history}, indent=2), encoding="utf-8")
    raise FileNotFoundError(f"ComfyUI completed but no MP4 was found. History written to {debug_path}")


def comfy_model_metadata(comfy_cfg: dict[str, Any]) -> dict[str, Any]:
    keys = ("high_noise_model", "low_noise_model", "high_noise_lora", "low_noise_lora", "clip_name", "vae_name")
    return {key: comfy_cfg.get(key) for key in keys if comfy_cfg.get(key)}
