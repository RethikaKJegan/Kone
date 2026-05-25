from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

import src.detect as detect
from src.insert_mod import expand_control_panel_bbox, invalid_mod_panel_target_reason
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
    assert manifest.get("selected_replacement_target_type") == detect.OPERATING_PANEL_CLASS
    assert manifest.get("inpaint_completed") is True
    assert manifest.get("elevator_present") is False
    assert manifest.get("selected_elevator_roi") is None
    assert manifest.get("video_generated") is False
    assert manifest.get("video_skipped_reason") == "no elevator door detected"


def test_component_detection_vocabulary_is_normalized() -> None:
    allowed = {
        "elevator_button_panel",
        detect.OPERATING_PANEL_CLASS,
        "wheelchair button",
        "floor_indicator_display",
        "weight_limit_sign",
        "accessibility_control_panel",
        "elevator_door",
        "elevator_cabin",
        "threshold_plate",
        "handrail",
        "security_camera",
        "emergency_phone",
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


def test_open_elevator_false_components_are_rejected() -> None:
    detections = [
        {"phrase": "elevator door", "normalized_component_type": "elevator_door", "score": 0.41, "box_xyxy": [40, 104, 276, 509]},
        {"phrase": "metal threshold plate", "normalized_component_type": "threshold_plate", "score": 0.43, "box_xyxy": [159, 527, 261, 555]},
        {"phrase": "elevator cabin", "normalized_component_type": "elevator_cabin", "score": 0.28, "box_xyxy": [47, 1, 268, 121]},
        {"phrase": "elevator display", "normalized_component_type": "floor_indicator_display", "score": 0.31, "box_xyxy": [20, 99, 46, 168]},
        {"phrase": "security camera", "normalized_component_type": "security_camera", "score": 0.34, "box_xyxy": [251, 132, 264, 150]},
    ]

    kept = detect._apply_component_geometry_validation(detections, 451, 602)
    kept_types = {item.get("normalized_component_type") for item in kept}

    assert kept_types == {"elevator_door"}


def test_nested_door_region_is_split_into_door_and_inset_cabin(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.zeros((602, 451, 3), dtype=np.uint8)
    image[:, :] = 90
    image[136:534, 82:248] = 125
    image[136:534, 82:118] = 70
    image[136:534, 212:248] = 75
    image[136:534, 130:200] = 145
    image[486:492, 82:248] = 240
    image[190:196, 82:248] = 35
    detections = [
        {
            "phrase": "elevator door",
            "normalized_component_type": "elevator_door",
            "score": 0.41,
            "box_xyxy": [127, 178, 222, 387],
        }
    ]
    monkeypatch.setattr(detect, "_infer_elevator_door_box", lambda image, items: [40, 104, 276, 509])

    detect._repair_nested_elevator_door_detection(image, detections)

    assert detections[0]["normalized_component_type"] == "elevator_door"
    assert detections[0]["phrase"] == "elevator door"
    assert detections[0]["box_xyxy"] == pytest.approx([71.86, 136.40, 258.30, 533.30])
    assert detections[1]["normalized_component_type"] == "elevator_cabin"
    assert detections[1]["phrase"] == "elevator interior"
    assert detections[1]["box_xyxy"] == pytest.approx([82.11, 136.40, 248.05, 486.0], abs=0.02)


def test_closed_sample_door_is_not_split_into_false_interior(monkeypatch: pytest.MonkeyPatch) -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {
            "phrase": "elevator door",
            "normalized_component_type": "elevator_door",
            "score": 0.50,
            "box_xyxy": [212.9, 256.7, 389.3, 672.8],
        }
    ]
    monkeypatch.setattr(detect, "_infer_elevator_door_box", lambda image, items: [208, 253, 527, 685])

    detect._repair_nested_elevator_door_detection(image, detections)

    assert len(detections) == 1
    assert detections[0]["box_xyxy"] == pytest.approx([212.9, 256.7, 389.3, 672.8])


def test_open_cabin_interior_includes_ceiling_and_stops_at_inner_sill() -> None:
    image = np.zeros((602, 451, 3), dtype=np.uint8)
    image[490:493, 82:249] = 255

    interior = detect._cabin_interior_box(image, [71.86, 136.40, 258.30, 533.30], 451, 602)

    assert interior[1] == pytest.approx(136.40)
    assert 488 <= interior[3] <= 493


def test_derived_interior_mask_keeps_ceiling_lights_inside_box() -> None:
    mask = detect._box_mask([82, 136, 248, 491], (602, 451))

    assert mask[145, 165]
    assert mask[170, 130]
    assert mask[170, 213]
    assert not mask[500, 130]


def test_panel_expansion_ignores_off_column_same_type_detection() -> None:
    seed = [20, 100, 40, 160]
    detections = [
        {"normalized_component_type": detect.OPERATING_PANEL_CLASS, "phrase": detect.OPERATING_PANEL_CLASS, "score": 0.4, "box_xyxy": seed},
        {"normalized_component_type": detect.OPERATING_PANEL_CLASS, "phrase": detect.OPERATING_PANEL_CLASS, "score": 0.3, "box_xyxy": [350, 100, 380, 170]},
    ]

    expanded, debug = expand_control_panel_bbox(None, detections, seed, 451, 602, detect.OPERATING_PANEL_CLASS)

    assert expanded[0] < seed[0] and expanded[2] > seed[2]
    assert len(debug["member_detections"]) == 1


def test_car_operating_panel_is_a_replaceable_cop_target() -> None:
    assert detect._normalized_component_type("car operating panel") == detect.OPERATING_PANEL_CLASS


def test_sample_wall_fixture_is_emergency_phone_not_blank_operating_panel() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {
            "phrase": "car operating panel",
            "normalized_component_type": detect.OPERATING_PANEL_CLASS,
            "score": 0.36,
            "box_xyxy": [82.2, 416.9, 187.1, 721.2],
        },
        {
            "phrase": detect.OPERATING_PANEL_CLASS,
            "normalized_component_type": detect.OPERATING_PANEL_CLASS,
            "score": 0.33,
            "box_xyxy": [137.1, 422.7, 165.2, 497.7],
        },
    ]

    kept = detect._apply_component_geometry_validation(detections, image.shape[1], image.shape[0], image)

    assert len(kept) == 1
    assert kept[0]["normalized_component_type"] == "emergency_phone"
    assert kept[0]["box_xyxy"] == pytest.approx([127, 425, 164, 496])


def test_sample_structural_indicator_and_emergency_phone_are_added() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {
            "phrase": "elevator door",
            "normalized_component_type": "elevator_door",
            "score": 0.50,
            "box_xyxy": [212.9, 256.7, 389.3, 672.8],
        }
    ]

    detect._add_structural_floor_indicator_detection(image, detections)
    detect._add_structural_emergency_phone_detection(image, detections)

    indicator = next(item for item in detections if item.get("normalized_component_type") == "floor_indicator_display")
    phone = next(item for item in detections if item.get("normalized_component_type") == "emergency_phone")
    assert indicator["box_xyxy"] == pytest.approx([275, 151, 313, 194])
    assert phone["box_xyxy"] == pytest.approx([90, 425, 164, 496])


def test_cop_panel_expands_to_include_aligned_display_plate() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "COP.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {
            "phrase": "elevator display",
            "normalized_component_type": "floor_indicator_display",
            "score": 0.34,
            "box_xyxy": [242, 208, 273, 227],
        },
        {
            "phrase": "car operating panel",
            "normalized_component_type": detect.OPERATING_PANEL_CLASS,
            "score": 0.31,
            "box_xyxy": [212, 347, 302, 584],
        },
    ]

    detect._expand_car_operating_panels(image, detections)
    panel = detections[1]
    x1, y1, x2, y2 = panel["box_xyxy"]

    assert panel["source"] == "expanded_car_operating_panel_plate"
    assert 200 <= x1 <= 220
    assert 130 <= y1 <= 155
    assert 300 <= x2 <= 320
    assert y2 >= 580
    assert invalid_mod_panel_target_reason(panel, image.shape[1], image.shape[0], None) is None


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
