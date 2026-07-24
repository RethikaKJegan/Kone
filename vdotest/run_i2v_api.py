#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'elevator_mod_pipeline' / 'src'
for item in (str(SRC), str(ROOT)):
    if item not in sys.path:
        sys.path.insert(0, item)

from video_comfy import render_comfy_video


def main() -> None:
    parser = argparse.ArgumentParser(description='Run Kone Wan/Comfy image-to-video generation.')
    parser.add_argument('--image', required=True)
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--negative', default='')
    parser.add_argument('--comfy-url', default='http://127.0.0.1:8188')
    parser.add_argument('--width', type=int, default=720)
    parser.add_argument('--height', type=int, default=960)
    parser.add_argument('--length', type=int, default=81)
    parser.add_argument('--fps', type=int, default=16)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--motion', default='zoom-in')
    parser.add_argument('--wait', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    del args.wait
    cfg = {
        'video': {
            'engine': 'comfy_i2v',
            'motion_style': args.motion,
            'prompt': args.prompt,
            'negative_prompt': args.negative,
            'width': args.width,
            'height': args.height,
            'length': args.length,
            'fps': args.fps,
            'seed': args.seed,
            'comfy': {
                'url': args.comfy_url,
                'root_dir': str(ROOT / 'vdotest' / 'ComfyUI'),
                'workflow_dir': str(ROOT / 'vdotest' / 'workflows'),
                'i2v_workflow': 'wan22_14b_i2v.json',
                'flf2v_workflow': 'wan22_14b_flf2v.json',
                'input_dir': str(ROOT / 'vdotest' / 'ComfyUI' / 'input'),
                'output_dir': str(ROOT / 'vdotest' / 'ComfyUI' / 'output'),
                'quality_mode': 'best',
                'timeout_seconds': 3600,
                'min_size_bytes': 100000,
                'enable_turbo_mode': True,
            },
        }
    }
    out = render_comfy_video(args.image, cfg=cfg, out_path=args.output)
    print(out)


if __name__ == '__main__':
    main()
