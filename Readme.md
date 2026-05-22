# Object Removal with GroundingDINO, SAM2, and LaMa

## Overview

This is a simple CLI pipeline that removes objects from an image using a text prompt.

Pipeline:

```text
Image + object prompt
  -> GroundingDINO detects the prompted object
  -> SAM2 creates an accurate object mask
  -> LaMa fills the masked region
  -> Output images are saved locally
```

No training, web app, or database is required.

## Local Models

The pretrained assets are stored locally:

```text
weights/groundingdino_swint_ogc.pth
bert-base-uncased/
weights/sam2.1_hiera_large.pt
big-lama/config.yaml
big-lama/models/best.ckpt
```

`segment-anything/` and `weights/sam_vit_h_4b8939.pth` are legacy SAM1 files and are not used by the upgraded script.

## Setup

Create and activate an environment with Python 3.10+.

```bash
python3 -m pip install torch torchvision numpy pillow scipy transformers pyyaml tqdm
python3 -m pip install addict yapf timm pycocotools hydra-core iopath omegaconf
SAM2_BUILD_CUDA=0 python3 -m pip install -e sam2_src
```

The SAM2 CUDA extension is optional; disabling it keeps setup simpler and the image predictor still works.

## Usage

```bash
python3 main.py elephant --image input.jpeg
```

Useful options:

```bash
python3 main.py "dog" --image input2.jpeg --max-detections 1
python3 main.py "chair" --image room.jpg --box-threshold 0.20 --text-threshold 0.15
python3 main.py "person" --image photo.jpg --lama-max-side 1024
```

Lower `--lama-max-side` can be faster. Higher values usually preserve more detail for large removed objects.

## Output Files

The script saves:

```text
output_original.jpg
output_detected.jpg
output_mask.png
output_final.jpg
output_final_lama.jpg
```

The first four satisfy the assignment requirements: original image, highlighted selection, binary mask, and cleaned result.

## Notes

The script runs fully offline after setup because model paths are local. GroundingDINO may warn that custom C++ ops are unavailable; in this environment it falls back to CPU mode and still completes inference.
# Intern
