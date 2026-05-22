# Elevator Mod Panel Replacement Pipeline

This directory combines the provided notebooks into a reusable end-to-end workflow:

1. Detect elevator components with OWLv2.
2. Segment detections with SAM2 when available, with bounding-box masks as a fallback.
3. Estimate wall geometry from the detected wall and Depth Anything V2.
4. Build a controllable mask for the object you want to remove.
5. Inpaint the masked area with BigLaMa, or OpenCV fallback for quick testing.
6. Insert `mod_panel.png` using detection and geometry.
7. Optionally run a Stable Diffusion local refinement pass only around the inserted panel.
8. Render a realistic elevator door open/close animation from the final MOD-inserted frame.

## Folder Layout

- `assets/` contains the sample elevator image and mod panel.
- `references/` contains the original notebooks and roadmap PDF.
- `src/` contains the pipeline implementation.
- `runs/` stores generated outputs.

## Install

```powershell
cd C:\Users\JKRFamily\Documents\Codex\2026-05-14\files-mentioned-by-the-user-kone\elevator_mod_pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For full SAM2 and BigLaMa quality, also clone/download the model repos into `third_party/`:

```powershell
mkdir third_party
git clone https://github.com/facebookresearch/sam2.git third_party/sam2
git clone https://github.com/advimman/lama.git third_party/lama
```

Download `sam2.1_hiera_large.pt` into `weights/` and BigLaMa into `third_party/lama/big-lama/`.
If those are missing, the pipeline can still run with bounding-box masks and OpenCV inpainting by setting:

```yaml
segmentation:
  enabled: false
inpainting:
  engine: opencv
```

## Run

```powershell
python -m src.pipeline --config config.yaml
```

For the reference workflow using the supplied detailed `elevator_detections.json`
and the supplied LaMa-cleaned background:

```powershell
python run_reference_final.py
```

Important outputs:

- `runs/sample_run/elevator_detections.json`
- `runs/sample_run/owlv2_output.png`
- `runs/sample_run/sam2_output.png`
- `runs/sample_run/geometry.json`
- `runs/sample_run/removal_mask.png`
- `runs/sample_run/cleaned_background.png`
- `runs/sample_run/composite.png`
- `runs/sample_run/harmonization_mask.png`
- `runs/sample_run/final_output.png`
- `runs/sample_run/elevator_animation.mp4`
- `runs/sample_run/elevator_animation.json`

## Control Points

Edit `config.yaml` for normal usage:

- `removal.target_keywords` controls what gets removed before insertion.
- `inpainting.cleaned_background` can point to a verified LaMa-cleaned image and skip cleanup.
- `insertion.target_keywords` controls which detection guides placement.
- `insertion.manual_box_xyxy` can force an exact placement box.
- `insertion.size_mode` controls whether the mod is fit to a box, fixed-height, or preserved.
- `inpainting.engine` switches between `lama` and `opencv`.
- `refinement.enabled` turns Stable Diffusion local refinement on or off.
- `video.enabled` controls whether the final MOD-inserted image is animated into `elevator_animation.mp4`.
"# kone_pipeline" 
