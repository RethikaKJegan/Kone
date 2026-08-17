#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/Kone/vdotest"
COMFY="$ROOT/ComfyUI"
LOG_DIR="$ROOT/logs"
GPU_LOG="$LOG_DIR/gpu_usage.csv"

mkdir -p "$LOG_DIR"

if [ ! -f "$GPU_LOG" ]; then
  echo "timestamp,index,name,gpu_util_percent,mem_util_percent,mem_total_mib,mem_used_mib,mem_free_mib,power_watts" > "$GPU_LOG"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  if [ ! -f "$LOG_DIR/gpu_global.pid" ] || ! kill -0 "$(cat "$LOG_DIR/gpu_global.pid")" 2>/dev/null; then
    (
      while true; do
        nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,power.draw --format=csv,noheader,nounits >> "$GPU_LOG" || true
        sleep 2
      done
    ) &
    echo $! > "$LOG_DIR/gpu_global.pid"
  fi
fi

cd "$COMFY"

SESSION_LOG="$LOG_DIR/comfyui_$(date +%Y%m%d_%H%M%S).log"

PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True "$COMFY/.venv/bin/python" main.py --listen 0.0.0.0 --port 8188 >> "$SESSION_LOG" 2>&1
