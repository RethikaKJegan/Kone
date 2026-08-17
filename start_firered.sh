#!/usr/bin/env bash
set -e

cd /root/Kone

export CUDA_VISIBLE_DEVICES=1
export FIRERED_IMAGE_EDIT_SCRIPT=/root/Kone/fire_red_image_edit.py
export FIRERED_MODEL_PATH=/root/Kone/models/FireRed-Image-Edit-1.1
export HF_HOME=/root/Kone/firered_hf_cache
export HF_HUB_CACHE=/root/Kone/firered_hf_cache/hub
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

exec /root/Kone/firered_venv/bin/python -m uvicorn \
    firered_service:app \
    --host 127.0.0.1 \
    --port 8010 \
    --workers 1
