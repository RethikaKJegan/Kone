from __future__ import annotations

import importlib.util
import os
import threading
import time
from pathlib import Path
from typing import Optional

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


FIRERED_SCRIPT = Path(
    os.environ.get(
        "FIRERED_IMAGE_EDIT_SCRIPT",
        "/root/Kone/fire_red_image_edit.py",
    )
)

MODEL_PATH = os.environ.get(
    "FIRERED_MODEL_PATH",
    "/root/Kone/models/FireRed-Image-Edit-1.1",
)


def load_firered_module():
    if not FIRERED_SCRIPT.exists():
        raise FileNotFoundError(
            f"FireRed script does not exist: {FIRERED_SCRIPT}"
        )

    spec = importlib.util.spec_from_file_location(
        "firered_image_edit_runtime",
        FIRERED_SCRIPT,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load FireRed script: {FIRERED_SCRIPT}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


print("=" * 72, flush=True)
print("[FIRERED SERVICE] Starting persistent FireRed service", flush=True)
print(f"[FIRERED SERVICE] Script: {FIRERED_SCRIPT}", flush=True)
print(f"[FIRERED SERVICE] Model:  {MODEL_PATH}", flush=True)
print(
    f"[FIRERED SERVICE] CUDA_VISIBLE_DEVICES="
    f"{os.environ.get('CUDA_VISIBLE_DEVICES', '<not set>')}",
    flush=True,
)
print("=" * 72, flush=True)


firered = load_firered_module()

if not torch.cuda.is_available():
    raise RuntimeError(
        "CUDA is unavailable inside the persistent FireRed service."
    )

device = torch.device("cuda")

print(
    f"[FIRERED SERVICE] Visible GPU: "
    f"{torch.cuda.get_device_name(0)}",
    flush=True,
)
print("[FIRERED SERVICE] Loading model into GPU memory...", flush=True)

load_started = time.perf_counter()
pipeline = firered.load_pipeline(MODEL_PATH, device)
load_elapsed = time.perf_counter() - load_started

print(
    f"[FIRERED SERVICE] READY — model loaded in "
    f"{load_elapsed:.2f} seconds",
    flush=True,
)


app = FastAPI(
    title="Persistent FireRed Image Edit Service",
    version="1.0.0",
)

inference_lock = threading.Lock()


class EditRequest(BaseModel):
    image: str
    output: str
    prompt: str

    seed: int = 777
    steps: int = Field(default=30, ge=1, le=100)
    true_cfg_scale: float = Field(default=3.8, gt=0)

    use_blend_prompt: bool = False


@app.get("/health")
def health():
    return {
        "ok": True,
        "status": "ready",
        "model": MODEL_PATH,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0),
        "cuda_memory_allocated_gb": round(
            torch.cuda.memory_allocated(0) / 1024**3,
            3,
        ),
        "cuda_memory_reserved_gb": round(
            torch.cuda.memory_reserved(0) / 1024**3,
            3,
        ),
    }


@app.post("/edit")
def edit(request: EditRequest):
    input_path = Path(request.image)
    output_path = Path(request.output)

    if not input_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Input image does not exist: {input_path}",
        )

    started = time.perf_counter()

    try:
        image = firered.load_input_image(input_path)

        prompt = request.prompt
        if request.use_blend_prompt:
            prompt = firered.build_blend_prompt(prompt)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        lock_started = time.perf_counter()

        with inference_lock:
            queue_wait = time.perf_counter() - lock_started
            inference_started = time.perf_counter()

            output_image = firered.run_edit(
                pipe=pipeline,
                image=image,
                prompt=prompt,
                seed=request.seed,
                steps=request.steps,
                true_cfg_scale=request.true_cfg_scale,
            )

            inference_elapsed = (
                time.perf_counter() - inference_started
            )

        save_started = time.perf_counter()
        output_image.save(output_path)
        save_elapsed = time.perf_counter() - save_started

        total_elapsed = time.perf_counter() - started

        print(
            "[FIRERED SERVICE] Edit completed | "
            f"input={input_path.name} | "
            f"steps={request.steps} | "
            f"queue={queue_wait:.2f}s | "
            f"inference={inference_elapsed:.2f}s | "
            f"save={save_elapsed:.2f}s | "
            f"total={total_elapsed:.2f}s",
            flush=True,
        )

        return {
            "ok": True,
            "output": str(output_path.resolve()),
            "queue_wait_seconds": round(queue_wait, 3),
            "inference_seconds": round(inference_elapsed, 3),
            "save_seconds": round(save_elapsed, 3),
            "total_seconds": round(total_elapsed, 3),
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(
            f"[FIRERED SERVICE] ERROR: {exc}",
            flush=True,
        )
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
