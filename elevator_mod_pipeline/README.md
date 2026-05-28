# Elevator Mod Panel Replacement Pipeline

This directory combines the provided notebooks into a reusable end-to-end workflow:

1. Detect elevator components with OWLv2.
2. Segment detections with SAM2 when available, with bounding-box masks as a fallback.
3. Estimate wall geometry from the detected wall and Depth Anything V2.
4. Build a controllable mask for the object you want to remove.
5. Inpaint the masked area with BigLaMa, or OpenCV fallback for quick testing.
6. Insert `mod_panel.png` using detection and geometry.
7. Optionally run the perspective-grid MOD placement handoff for manually defined wall planes.
8. Optionally run a Stable Diffusion local refinement pass only around the inserted panel seam.
9. Render a realistic elevator door open/close animation from the final MOD-inserted frame.

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
- `perspective_mod_placement.enabled` runs the automatic homography/grid placement handoff after normal MOD insertion.
- `inpainting.engine` switches between `lama` and `opencv`.
- `refinement.enabled` turns Stable Diffusion local refinement on or off.
- `video.enabled` controls whether the final MOD-inserted image is animated into `elevator_animation.mp4`.

## Perspective Grid MOD Placement

For tilted elevator walls, use the OpenCV-only perspective placer. In pipeline
runs it automatically infers the wall-plane corners and MOD grid box from the
geometry and placement debug data, draws a projected grid, warps the MOD panel
into a grid-space rectangle, and writes a seam-only inpainting mask for Stable
Diffusion handoff. Stable Diffusion is not used for geometry.

```powershell
python perspective_mod_placement.py ^
  --base elevator.jpg ^
  --panel mod_panel.png ^
  --out outputs ^
  --plane "420,180 780,220 750,680 390,640" ^
  --grid-cols 8 ^
  --grid-rows 12 ^
  --mod-box "5.2,4.0 6.5,7.2" ^
  --match-lighting
```

Plane point order is top-left, top-right, bottom-right, bottom-left. MOD box
order is top-left, bottom-right in grid coordinates.

Outputs:

- `01_original.jpg`
- `02_wall_plane_marked.jpg`
- `03_perspective_grid.jpg`
- `04_mod_panel_warped.png`
- `05_mod_panel_placed.jpg`
- `06_edge_refine_mask.png`
- `07_sd_ready_composite.jpg`

The pipeline enables auto mode by default:

```yaml
perspective_mod_placement:
  enabled: true
  auto: true
  grid_cols: 8
  grid_rows: 12
  match_lighting: true
```

## Multiple Replacement Components

Provide `replacements` to clean and place several MOD assets in one run. Detection
and inpainting are run once; each asset is then placed into its matching detected
component.

```yaml
replacements:
  - id: call_panel
    asset: tests/panels/mod_panel.png
    component_type: elevator_mod_panel
    target_keywords:
      - elevator button panel
      - elevator call button panel
  - id: floor_indicator
    asset: tests/panels/mod_up.png
    component_type: floor_indicator_display
    target_keywords:
      - floor indicator
      - elevator display
```

`mod_panel` remains supported for existing single-component configurations.

For batch runs, each JSON item can request one replacement with `mod_panel`, or
several with `replacements`:

```json
{
  "input_image": "tests/images/Sample11.jpg",
  "mod_panel": "tests/panels/mod_panel.png",
  "prompt": "replace the elevator button panel and floor indicator with mod components",
  "replacements": [
    {
      "id": "call_panel",
      "asset": "tests/panels/mod_panel.png",
      "component_type": "elevator_mod_panel",
      "target_keywords": ["elevator button panel"]
    },
    {
      "id": "floor_indicator",
      "asset": "tests/panels/mod_up.png",
      "component_type": "floor_indicator_display",
      "target_keywords": ["floor indicator", "elevator display"]
    }
  ]
}
```

Batch door videos default to `tests/images/Sample2_open_interior.jpg` when a
closed lift must open, and `tests/images/Sample2_closed_exterior.jpg` when an
open lift must close. Set either reference path in a JSON entry to override it.
Batch image-quality failures are reported but do not stop output generation by
default; set `"fail_on_invalid": true` on an entry to require strict rejection.
"# kone_pipeline" 
