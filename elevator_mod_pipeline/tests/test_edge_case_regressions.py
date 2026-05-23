from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.video import normalize_video_mode_request, pan_metadata, render_motion_style_frame


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "tests" / "outputs"


def load_manifest(sample: str) -> dict:
    path = OUTPUTS / sample / "pipeline_manifest.json"
    if not path.exists():
        pytest.skip(f"{sample} has not been regenerated with pipeline_manifest.json")
    return json.loads(path.read_text(encoding="utf-8"))


def area(box: list[int | float]) -> float:
    return max(0.0, float(box[2]) - float(box[0])) * max(0.0, float(box[3]) - float(box[1]))


def image_area(sample: str) -> int:
    image = cv2.imread(str(OUTPUTS / sample / "final_output.png"), cv2.IMREAD_COLOR)
    assert image is not None
    return int(image.shape[0] * image.shape[1])


def test_sample5_uses_existing_panel_bbox_for_replacement() -> None:
    manifest = load_manifest("002_Sample5")
    target = manifest.get("selected_replacement_target_bbox")
    inserted = manifest.get("final_insertion_bbox")
    assert manifest.get("selected_replacement_target_type") in {"accessibility_control_panel", "elevator_button_panel"}
    assert isinstance(target, list) and isinstance(inserted, list)
    assert area(inserted) <= area(target) * 1.35
    assert area(inserted) / image_area("002_Sample5") < 0.10
    assert manifest.get("insertion_size_validation_status") == "passed"


def test_sample6_harmonization_mask_and_composite_are_not_full_image() -> None:
    manifest = load_manifest("004_Sample6")
    assert float(manifest.get("harmonization_mask_white_area_ratio") or 0) <= 0.35
    assert manifest.get("harmonization_mask_validation_status") in {"passed", "rebuilt"}
    mask = cv2.imread(str(OUTPUTS / "004_Sample6" / "harmonization_mask.png"), cv2.IMREAD_GRAYSCALE)
    composite = cv2.imread(str(OUTPUTS / "004_Sample6" / "composite.png"), cv2.IMREAD_COLOR)
    assert mask is not None and composite is not None
    assert float(np.mean(mask > 127)) <= 0.35
    assert float(np.std(composite)) > 2.0


def test_sample8_rejects_weight_limit_sign_for_mod_panel() -> None:
    manifest = load_manifest("005_Sample8")
    assert manifest.get("requested_component_type") == "elevator_mod_panel"
    assert manifest.get("selected_replacement_target_type") != "weight_limit_sign"
    rejected = manifest.get("rejected_replacement_targets") or []
    assert any(item.get("normalized_component_type") == "weight_limit_sign" for item in rejected)
    steps = [item.get("step") for item in manifest.get("pipeline_steps", [])]
    assert "detect_components" in steps and "inpaint" in steps and "place" in steps
    assert steps.index("detect_components") < steps.index("inpaint") < steps.index("place")


def test_cop_replaced_without_video_when_no_real_elevator_door() -> None:
    manifest = load_manifest("001_COP")
    assert manifest.get("selected_replacement_target_type") in {"accessibility_control_panel", "elevator_button_panel"}
    assert manifest.get("inpaint_completed") is True
    assert manifest.get("elevator_present") is False
    assert manifest.get("selected_elevator_roi") is None
    assert manifest.get("video_generated") is False
    assert manifest.get("video_skipped_reason") == "no elevator door detected"


def test_component_detection_vocabulary_is_normalized() -> None:
    allowed = {
        "elevator_button_panel",
        "floor_indicator_display",
        "weight_limit_sign",
        "accessibility_control_panel",
        "elevator_door",
        "elevator_cabin",
        "threshold_plate",
        "handrail",
        "security_camera",
    }
    for sample_dir in OUTPUTS.glob("*"):
        manifest_path = sample_dir / "pipeline_manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        normalized = {
            det.get("normalized_component_type")
            for det in manifest.get("component_detections", [])
            if det.get("normalized_component_type")
        }
        assert normalized <= allowed


def test_door_functionality_wins_over_motion_style() -> None:
    request = normalize_video_mode_request({"motion_style": "zoom_in", "door_functionality": "open"})
    assert request["requested_motion_style"] == "zoom_in"
    assert request["requested_door_functionality"] == "open"
    assert request["normalized_video_mode"] == "door_open"
    assert request["video_mode_conflict_resolution"] == "door_functionality_preferred"


def test_zoom_in_starts_with_full_centered_image_and_changes() -> None:
    image = np.zeros((80, 120, 3), dtype=np.uint8)
    image[:, :40] = (255, 0, 0)
    image[:, 40:80] = (0, 255, 0)
    image[:, 80:] = (0, 0, 255)
    first = render_motion_style_frame(image, 160, 90, (60, 40), "zoom_in", 0.0)
    last = render_motion_style_frame(image, 160, 90, (60, 40), "zoom_in", 1.0)
    assert first.shape == (90, 160, 3)
    assert last.shape == (90, 160, 3)
    assert np.mean(np.abs(first.astype(np.int16) - last.astype(np.int16))) > 1.0
    assert np.mean(first[:, :40, 0]) > 40
    assert np.mean(first[:, 60:100, 1]) > 40
    assert np.mean(first[:, 120:, 2]) > 40


def test_pan_l_r_and_pan_r_l_use_crop_window_direction() -> None:
    image = np.zeros((90, 240, 3), dtype=np.uint8)
    image[:, :80] = (255, 0, 0)
    image[:, 80:160] = (0, 255, 0)
    image[:, 160:] = (0, 0, 255)
    lr_first = render_motion_style_frame(image, 120, 90, (120, 45), "pan_l_r", 0.0)
    lr_last = render_motion_style_frame(image, 120, 90, (120, 45), "pan_l_r", 1.0)
    rl_first = render_motion_style_frame(image, 120, 90, (120, 45), "pan_r_l", 0.0)
    rl_last = render_motion_style_frame(image, 120, 90, (120, 45), "pan_r_l", 1.0)
    assert np.mean(np.abs(lr_first.astype(np.int16) - lr_last.astype(np.int16))) > 5.0
    assert np.mean(lr_first[:, :, 0]) > np.mean(lr_last[:, :, 0])
    assert np.mean(lr_last[:, :, 2]) > np.mean(lr_first[:, :, 2])
    assert np.mean(rl_first[:, :, 2]) > np.mean(rl_last[:, :, 2])
    assert np.mean(rl_last[:, :, 0]) > np.mean(rl_first[:, :, 0])


def test_pan_t_b_and_pan_b_t_use_vertical_crop_window_direction() -> None:
    image = np.zeros((240, 90, 3), dtype=np.uint8)
    image[:80, :] = (255, 0, 0)
    image[80:160, :] = (0, 255, 0)
    image[160:, :] = (0, 0, 255)
    tb_first = render_motion_style_frame(image, 90, 120, (45, 120), "pan_t_b", 0.0)
    tb_last = render_motion_style_frame(image, 90, 120, (45, 120), "pan_t_b", 1.0)
    bt_first = render_motion_style_frame(image, 90, 120, (45, 120), "pan_b_t", 0.0)
    bt_last = render_motion_style_frame(image, 90, 120, (45, 120), "pan_b_t", 1.0)
    assert np.mean(np.abs(tb_first.astype(np.int16) - tb_last.astype(np.int16))) > 5.0
    assert np.mean(tb_first[:, :, 0]) > np.mean(tb_last[:, :, 0])
    assert np.mean(tb_last[:, :, 2]) > np.mean(tb_first[:, :, 2])
    assert np.mean(bt_first[:, :, 2]) > np.mean(bt_last[:, :, 2])
    assert np.mean(bt_last[:, :, 0]) > np.mean(bt_first[:, :, 0])
    assert tb_first.shape == (120, 90, 3)
    assert bt_first.shape == (120, 90, 3)


def test_vertical_pan_metadata_and_door_conflict_routing() -> None:
    assert normalize_video_mode_request({"motion_style": "pan_t_b"})["normalized_video_mode"] == "pan_t_b"
    assert normalize_video_mode_request({"motion_style": "pan_b_t"})["normalized_video_mode"] == "pan_b_t"
    assert pan_metadata("pan_t_b") == ("y", "top_to_bottom")
    assert pan_metadata("pan_b_t") == ("y", "bottom_to_top")
    request = normalize_video_mode_request({"motion_style": "pan_t_b", "door_functionality": "close"})
    assert request["normalized_video_mode"] == "door_close"
    assert request["video_mode_conflict_resolution"] == "door_functionality_preferred"
