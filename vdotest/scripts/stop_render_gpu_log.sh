#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/Kone/vdotest"
RENDER_DIR="$ROOT/logs/renders"
ENV_FILE="$RENDER_DIR/current_render_gpu_log.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "no active render gpu log"
  exit 1
fi

source "$ENV_FILE"

if [ -n "${RENDER_PID:-}" ]; then
  kill "$RENDER_PID" 2>/dev/null || true
  sleep 1
fi

SUMMARY="$RENDER_DIR/gpu_render_${RENDER_ID}_summary.txt"

python3 - "$RENDER_CSV" "$SUMMARY" <<'PY'
import csv
import sys
from pathlib import Path

csv_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])

rows = []

with csv_path.open() as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

def nums(key):
    values = []
    for row in rows:
        raw = row.get(key, "").strip()
        try:
            values.append(float(raw))
        except ValueError:
            pass
    return values

gpu = nums("gpu_util_percent")
mem = nums("mem_used_mib")
power = nums("power_watts")

lines = [
    f"csv={csv_path}",
    f"samples={len(rows)}",
    f"max_gpu_util_percent={max(gpu) if gpu else 0:.2f}",
    f"avg_gpu_util_percent={sum(gpu) / len(gpu) if gpu else 0:.2f}",
    f"max_mem_used_mib={max(mem) if mem else 0:.2f}",
    f"avg_mem_used_mib={sum(mem) / len(mem) if mem else 0:.2f}",
    f"max_power_watts={max(power) if power else 0:.2f}",
    f"avg_power_watts={sum(power) / len(power) if power else 0:.2f}",
]

summary_path.write_text("\n".join(lines) + "\n")
print(summary_path.read_text())
PY

rm -f "$ENV_FILE"

echo "render gpu log stopped"
