from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = ROOT / "tests" / "outputs" / "004_Sample6" / "final_output.png"
DEFAULT_OUTPUT_DIR = ROOT / "tests" / "outputs" / "004_Sample6" / "video_modes_ltx"
LTX_IMAGE_TO_VIDEO_URL = "https://api.ltx.video/v1/image-to-video"


PROMPTS = {
    "panel_left_to_right": (
        "Realistic product video shot from the provided elevator image. A slow, natural camera move "
        "pans left to right across the installed elevator mod panel and surrounding elevator wall. "
        "Preserve the exact panel design, logo, text, wall layout, colors, and elevator geometry. "
        "No morphing, no extra buttons, no changed text, no new objects. Smooth real camera motion, "
        "subtle parallax, natural lighting, stable commercial product footage."
    ),
    "panel_right_to_left": (
        "Realistic product video shot from the provided elevator image. A slow, natural camera move "
        "pans right to left across the installed elevator mod panel and surrounding elevator wall. "
        "Preserve the exact panel design, logo, text, wall layout, colors, and elevator geometry. "
        "No morphing, no extra buttons, no changed text, no new objects. Smooth real camera motion, "
        "subtle parallax, natural lighting, stable commercial product footage."
    ),
    "zoom_in": (
        "Realistic product video shot from the provided elevator image. Start from the full final image "
        "and perform a slow natural camera zoom toward the installed elevator mod panel. Preserve the "
        "exact panel design, logo, text, wall layout, colors, and elevator geometry. No morphing, no "
        "extra buttons, no changed text, no new objects. Smooth real camera motion, natural lighting, "
        "stable commercial product footage."
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Sample6 LTX cloud image-to-video variants.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help="Input final output image.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated videos.")
    parser.add_argument("--model", default="ltx-2-3-pro", choices=["ltx-2-fast", "ltx-2-pro", "ltx-2-3-fast", "ltx-2-3-pro"])
    parser.add_argument("--duration", type=int, default=5, help="Video duration in seconds.")
    parser.add_argument("--resolution", default="1920x1080", help="LTX output resolution, e.g. 1920x1080.")
    parser.add_argument("--fps", type=int, default=24, help="Requested frame rate.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per mode.")
    args = parser.parse_args()

    api_key = os.environ.get("LTX_API_KEY")
    if not api_key:
        raise SystemExit("Missing LTX_API_KEY. Set it in the environment before running this script.")

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Input image not found: {image_path}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    image_uri = image_to_data_uri(image_path)
    summary: dict[str, dict[str, object]] = {}

    for mode, prompt in PROMPTS.items():
        mode_dir = out_dir / mode
        mode_dir.mkdir(parents=True, exist_ok=True)
        out_path = mode_dir / f"{mode}.mp4"
        payload = {
            "image_uri": image_uri,
            "prompt": prompt,
            "model": args.model,
            "duration": args.duration,
            "resolution": args.resolution,
            "fps": args.fps,
            "generate_audio": False,
        }
        result = call_ltx(payload, api_key, out_path, args.retries)
        meta = {
            "mode": mode,
            "model": args.model,
            "duration": args.duration,
            "resolution": args.resolution,
            "fps": args.fps,
            "output_video": str(out_path),
            "prompt": prompt,
            **result,
        }
        (mode_dir / f"{mode}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        summary[mode] = meta
        print(f"[LTX] Wrote {mode}: {out_path}")

    (out_dir / "ltx_generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[LTX] Summary: {out_dir / 'ltx_generation_summary.json'}")


def image_to_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def call_ltx(payload: dict[str, object], api_key: str, out_path: Path, retries: int) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error = ""
    for attempt in range(retries + 1):
        request = urllib.request.Request(LTX_IMAGE_TO_VIDEO_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                content_type = response.headers.get("Content-Type", "")
                request_id = response.headers.get("x-request-id")
                data = response.read()
            if not data:
                raise RuntimeError("LTX API returned an empty response body")
            out_path.write_bytes(data)
            return {
                "status": "completed",
                "content_type": content_type,
                "request_id": request_id,
                "file_size_bytes": out_path.stat().st_size,
            }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {detail}"
            if exc.code not in {429, 500, 503, 504} or attempt >= retries:
                break
        except Exception as exc:
            last_error = str(exc)
            if attempt >= retries:
                break
        time.sleep(2 + attempt * 4)
    raise RuntimeError(f"LTX generation failed for {out_path.name}: {last_error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[LTX] ERROR: {exc}", file=sys.stderr)
        raise
