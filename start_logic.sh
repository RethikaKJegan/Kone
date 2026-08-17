#!/usr/bin/env bash
set -e

echo "Waiting for FireRed..."

for i in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then
        echo "FireRed ready."
        break
    fi
    sleep 1
done

if ! curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then
    echo "FireRed did not become ready."
    exit 1
fi

cd /root/Kone/elevator_mod_pipeline/src

export FIRERED_PYTHON=/root/Kone/firered_venv/bin/python
export FIRERED_REPIN_SCRIPT=/root/Kone/fire_red_image_edit.py
export FIRERED_CUDA_VISIBLE_DEVICES=1
export FIRERED_SERVICE_URL=http://127.0.0.1:8010/edit
export FIRERED_SERVICE_TIMEOUT=900
export FIRERED_FACE_STRENGTH=0.25
export FIRERED_SHADOW_STRENGTH=0.60
export FIRERED_RING_WIDTH=11
export FIRERED_RING_BLUR=2.5
export FIRERED_STEPS=30
export FIRERED_TRUE_CFG_SCALE=1.8
export REPIN_ERASER_ENGINE=lama

export HF_HOME=/root/Kone/firered_hf_cache
export HF_HUB_CACHE=/root/Kone/firered_hf_cache/hub
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0,1
export PYTHONUNBUFFERED=1

export PYTHONPATH=/root/Kone/elevator_mod_pipeline/src:/root/Kone:/root/Kone/GroundingDINO:/root/Kone/sam2_src:/root/Kone/lama

exec python3 -m uvicorn server:app \
    --host 0.0.0.0 \
    --port 8001
