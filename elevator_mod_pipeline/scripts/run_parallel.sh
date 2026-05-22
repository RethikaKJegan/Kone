#!/usr/bin/env bash
set -euo pipefail

python run_batch.py --prepare-only
parallel --lb 'python -m src.pipeline --config {}/config.generated.yaml' ::: tests/outputs/[0-9][0-9][0-9]_*
