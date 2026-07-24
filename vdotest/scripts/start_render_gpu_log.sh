#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/Kone/vdotest"
RENDER_DIR="$ROOT/logs/renders"

mkdir -p "$RENDER_DIR"

ID="$(date +%Y%m%d_%H%M%S)"
CSV="$RENDER_DIR/gpu_render_${ID}.csv"
ENV_FILE="$RENDER_DIR/current_render_gpu_log.env"

echo "timestamp,index,name,gpu_util_percent,mem_util_percent,mem_total_mib,mem_used_mib,mem_free_mib,power_watts" > "$CSV"

if command -v nvidia-smi >/dev/null 2>&1; then
  (
    while true; do
      nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,power.draw --format=csv,noheader,nounits >> "$CSV" || true
      sleep 2
    done
  ) &
  PID=$!
else
  PID=""
fi

cat > "$ENV_FILE" <<ENV
RENDER_ID="$ID"
RENDER_PID="$PID"
RENDER_CSV="$CSV"
ENV

echo "render gpu log started: $CSV"
