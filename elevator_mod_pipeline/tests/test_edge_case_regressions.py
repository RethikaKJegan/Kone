from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

import src.detect as detect
import run_batch
from src.input_validation import validate_elevator_presence
from src.insert_mod import (
    expand_control_panel_bbox,
    extend_inpaint_bbox_for_aligned_panel_artifacts,
    invalid_mod_panel_target_reason,
    preselect_mod_panel_placement,
    select_valid_component_detection,
)
from src.perspective_mod_placement import parse_points, run_perspective_mod_placement
from src.pipeline import component_config, elevator_present_for_video, replacement_configs
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


def test_perspective_mod_placement_writes_sd_handoff_outputs(tmp_path: Path) -> None:
    base = np.full((160, 220, 3), 180, dtype=np.uint8)
    cv2.rectangle(base, (25, 20), (190, 145), (150, 150, 150), -1)
    panel = np.zeros((70, 28, 4), dtype=np.uint8)
    panel[:, :, :3] = (205, 205, 205)
    panel[:, :, 3] = 255
    cv2.circle(panel, (14, 22), 6, (30, 30, 30, 255), -1)
    cv2.circle(panel, (14, 46), 6, (30, 30, 30, 255), -1)
    base_path = tmp_path / "elevator.jpg"
    panel_path = tmp_path / "mod_panel.png"
    cv2.imwrite(str(base_path), base)
    cv2.imwrite(str(panel_path), panel)

    outputs = run_perspective_mod_placement(
        base_path,
        panel_path,
        tmp_path / "outputs",
        parse_points("30,20 190,35 175,145 25,130", 4),
        8,
        12,
        parse_points("5.2,4.0 6.5,7.2", 2),
        match_lighting=True,
    )

    for name in (
        "original",
        "wall_plane_marked",
        "perspective_grid",
        "mod_panel_warped",
        "mod_panel_placed",
        "edge_refine_mask",
        "sd_ready_composite",
    ):
        assert outputs[name].exists()
    mask = cv2.imread(str(outputs["edge_refine_mask"]), cv2.IMREAD_GRAYSCALE)
    assert mask is not None
    assert 0 < float(np.mean(mask > 0)) < 0.12


def test_multi_component_config_preserves_legacy_and_overrides_targets() -> None:
    base = {
        "mod_panel": "tests/panels/mod_panel.png",
        "removal": {"target_keywords": ["button"]},
        "insertion": {"target_keywords": ["button"], "manual_box_xyxy": None},
    }
    assert replacement_configs(base) == [{"id": "mod_panel", "asset": "tests/panels/mod_panel.png"}]

    replacement = {
        "id": "indicator",
        "asset": "tests/panels/mod_up.png",
        "component_type": "floor_indicator_display",
        "target_keywords": ["floor indicator"],
    }
    cfg = component_config(base, replacement)
    assert cfg["mod_panel"] == "tests/panels/mod_up.png"
    assert cfg["removal"]["target_keywords"] == ["floor indicator"]
    assert cfg["insertion"]["target_keywords"] == ["floor indicator"]
    assert cfg["_requested_component_type"] == "floor_indicator_display"

    lci_cfg = component_config(base, replacement_configs({"selected_components": ["lci"], **base})[0])
    assert lci_cfg["_requested_component_type"] == "landing_call_indicator"
    assert "floor indicator" not in " ".join(lci_cfg["insertion"]["target_keywords"]).lower()
    assert "elevator button panel" in " ".join(lci_cfg["insertion"]["target_keywords"]).lower()


def test_batch_component_and_video_defaults_support_manifest_requests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = {
        "input_validation": {"enabled": True, "fail_on_invalid": True},
        "detection": {"labels": ["elevator_door"]},
        "removal": {"target_keywords": ["button"]},
        "insertion": {"target_keywords": ["button"]},
        "refinement": {"prompt": "replace"},
        "video": {"enabled": True, "cycle": True},
    }
    monkeypatch.setattr(run_batch, "ROOT", tmp_path)
    test = {
        "input_image": "tests/images/example.jpg",
        "mod_panel": "tests/panels/mod_panel.png",
        "prompt": "replace the elevator button panel with the mod panel",
        "replacements": [
            {
                "asset": "tests/panels/mod_up.png",
                "target_keywords": ["floor indicator"],
            }
        ],
    }

    path = run_batch.write_config(test, 1, base)
    cfg = run_batch.yaml.safe_load(path.read_text(encoding="utf-8"))

    assert cfg["input_validation"]["fail_on_invalid"] is False
    assert cfg["video"]["cycle"] is False
    assert cfg["video"]["open_reference_image"] == "tests/images/Sample2_open_interior.jpg"
    assert cfg["video"]["closed_reference_image"] == "tests/images/Sample2_closed_exterior.jpg"
    assert cfg["replacements"][0]["asset"] == "tests/panels/mod_up.png"


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
        "wheelchair_indicator",
        "landing_call_indicator",
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
        {"phrase": "elevator emergency phone", "normalized_component_type": "emergency_phone", "score": 0.31, "box_xyxy": [150, 220, 170, 255]},
    ]

    kept = detect._apply_component_geometry_validation(detections, 451, 602)
    kept_types = {item.get("normalized_component_type") for item in kept}

    assert kept_types == {"elevator_door"}


def test_recovered_full_door_is_validated_at_lower_detector_confidence() -> None:
    detections = {
        "metadata": {"image_width": 447, "image_height": 597},
        "detections": [
            {
                "phrase": "elevator door",
                "normalized_component_type": "elevator_door",
                "raw_detection_label": "elevator door",
                "source": "closed_door_header_recovery",
                "score": 0.271,
                "box_xyxy": [108, 63, 324, 560],
            }
        ],
    }

    result = validate_elevator_presence(detections, {})

    assert result["valid"] is True
    assert result["matched_elevator_components"][0]["normalized_component_type"] == "elevator_door"
    assert elevator_present_for_video(detections) is True


def test_room_fixture_door_and_weak_panels_do_not_validate_as_elevator() -> None:
    detections = {
        "metadata": {"image_width": 7875, "image_height": 4429},
        "detections": [
            {
                "phrase": "elevator door",
                "normalized_component_type": "elevator_door",
                "raw_detection_label": "elevator door",
                "score": 0.349,
                "box_xyxy": [3281, 1564, 3918, 2725],
            },
            {
                "phrase": detect.OPERATING_PANEL_CLASS,
                "normalized_component_type": detect.OPERATING_PANEL_CLASS,
                "raw_detection_label": "car operating panel",
                "score": 0.295,
                "box_xyxy": [2848, 909, 3221, 2515],
            },
        ],
    }

    result = validate_elevator_presence(detections, {})

    assert result["valid"] is False
    assert elevator_present_for_video(detections) is False


def test_close_up_operating_panel_remains_a_valid_standalone_elevator_component() -> None:
    detections = {
        "metadata": {"image_width": 493, "image_height": 652},
        "detections": [
            {
                "phrase": detect.OPERATING_PANEL_CLASS,
                "normalized_component_type": detect.OPERATING_PANEL_CLASS,
                "raw_detection_label": "car operating panel",
                "score": 0.305,
                "box_xyxy": [212, 347, 302, 584],
            }
        ],
    }

    assert validate_elevator_presence(detections, {})["valid"] is True


def test_wide_open_elevator_door_remains_eligible_for_video() -> None:
    detections = {
        "metadata": {"image_width": 1536, "image_height": 2048},
        "detections": [
            {
                "phrase": "elevator door",
                "normalized_component_type": "elevator_door",
                "score": 0.394,
                "source": "groundingdino_open_door_entrance_repair",
                "box_xyxy": [331, 341, 1154, 1119],
            }
        ],
    }

    assert elevator_present_for_video(detections) is True


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


def test_closed_sample_rejects_raw_elevator_interior_detection() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {"phrase": "elevator door", "normalized_component_type": "elevator_door", "score": 0.50, "box_xyxy": [209, 259, 386, 670]},
        {"phrase": "elevator interior", "normalized_component_type": "elevator_cabin", "score": 0.31, "box_xyxy": [220, 270, 370, 650]},
    ]

    detect._filter_false_elevator_interior_detections(image, detections)

    assert [det["normalized_component_type"] for det in detections] == ["elevator_door"]


def test_sample11_door_header_is_recovered_to_full_door_height() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample11.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {
            "phrase": "elevator door",
            "normalized_component_type": "elevator_door",
            "score": 0.50,
            "box_xyxy": [125.9, 215.0, 331.4, 580.0],
        }
    ]

    detect._recover_elevator_door_header(image, detections)

    door = detections[0]
    assert door["source"] == "closed_door_header_recovery"
    assert door["box_xyxy"][1] < 165
    assert door["box_xyxy"][3] == pytest.approx(580.0)
    assert door["geometry_validation"]["reason"] == "horizontal_header_edge_extends_closed_door_to_full_height"


def test_sample11_stacked_indicator_is_split_from_operating_panel() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample11.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {
            "phrase": detect.OPERATING_PANEL_CLASS,
            "normalized_component_type": detect.OPERATING_PANEL_CLASS,
            "score": 0.45,
            "box_xyxy": [41.4, 273.5, 75.8, 439.9],
        },
        {
            "phrase": "wheelchair button",
            "normalized_component_type": "wheelchair button",
            "score": 0.29,
            "box_xyxy": [53.9, 412.2, 66.7, 426.7],
        },
    ]

    detect._split_stacked_accessibility_panel_detection(image, detections)

    panel = next(item for item in detections if item.get("normalized_component_type") == detect.OPERATING_PANEL_CLASS)
    indicator = next(item for item in detections if item.get("normalized_component_type") == "wheelchair_indicator")
    assert panel["box_xyxy"][1] > 375
    assert panel["box_xyxy"][3] < 445
    assert indicator["box_xyxy"][3] < panel["box_xyxy"][1]
    assert not any(item.get("normalized_component_type") == "wheelchair button" for item in detections)


def test_sample11_button_anchor_recovers_replaceable_call_panel() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample11.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {"phrase": "elevator door", "normalized_component_type": "elevator_door", "score": 0.50, "box_xyxy": [126, 137, 331, 580]},
        {"phrase": "wheelchair button", "normalized_component_type": "wheelchair button", "score": 0.29, "box_xyxy": [53.9, 412.2, 66.7, 426.7]},
    ]

    detect._add_structural_call_panel_detection(image, detections)

    panel = detections[1]
    assert panel["normalized_component_type"] == "elevator call button panel"
    assert panel["box_xyxy"][1] < 395
    assert panel["box_xyxy"][3] > 430


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


def test_lci_targets_elevator_button_panel_not_floor_display() -> None:
    detections = [
        {
            "phrase": "floor indicator display",
            "normalized_component_type": "floor_indicator_display",
            "score": 0.9,
            "box_xyxy": [54, 20, 106, 42],
        },
        {
            "phrase": "elevator call button panel",
            "normalized_component_type": "elevator call button panel",
            "score": 0.7,
            "box_xyxy": [52, 110, 90, 166],
        },
    ]

    selected = select_valid_component_detection(
        detections,
        ["elevator button panel", "elevator call button panel", "call button"],
        240,
        160,
        (90, 30),
    )

    assert detect._normalized_component_type("elevator call button panel") == "elevator call button panel"
    assert selected is detections[1]


def test_duplicate_elevator_label_is_normalized_as_elevator_door() -> None:
    assert detect._canonical_phrase("elevator elevator", ["elevator_door"]) == "elevator door"
    assert detect._normalized_component_type("elevator elevator") == "elevator_door"


def test_unmapped_prompt_fragment_is_not_returned_as_component() -> None:
    detections = [
        {"phrase": "tall stainless steel elevator elevator elevator", "normalized_component_type": None},
        {"phrase": "elevator door", "normalized_component_type": "elevator_door"},
    ]

    kept = detect._filter_unmapped_component_detections(detections)

    assert [det["normalized_component_type"] for det in kept] == ["elevator_door"]


def test_sample_wall_fixture_is_replaceable_call_panel_not_emergency_phone() -> None:
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
    assert kept[0]["normalized_component_type"] == "elevator call button panel"
    assert kept[0]["box_xyxy"] == pytest.approx([127, 425, 164, 496])


def test_sample_structural_indicator_and_mod_panel_are_added() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {
            "phrase": "elevator door",
            "normalized_component_type": "elevator_door",
            "score": 0.50,
            "box_xyxy": [212.9, 256.7, 389.3, 672.8],
        },
        {
            "phrase": "emergency phone",
            "normalized_component_type": "emergency_phone",
            "score": 0.45,
            "box_xyxy": [86, 425, 164, 496],
        },
    ]

    detect._add_structural_floor_indicator_detection(image, detections)
    detect._add_structural_call_panel_detection(image, detections)

    indicator = next(item for item in detections if item.get("normalized_component_type") == "floor_indicator_display")
    panel = next(item for item in detections if item.get("normalized_component_type") == "elevator call button panel")
    assert indicator["box_xyxy"] == pytest.approx([275, 151, 313, 194])
    assert panel["box_xyxy"] == pytest.approx([90, 425, 164, 496])


def test_unmatched_dark_wall_fixture_does_not_invent_call_panel() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample9.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {"phrase": "elevator door", "normalized_component_type": "elevator_door", "score": 0.61, "box_xyxy": [169, 214, 291, 494]},
    ]

    detect._add_structural_call_panel_detection(image, detections)

    assert [det["normalized_component_type"] for det in detections] == ["elevator_door"]


def test_sample8_side_floor_display_replaces_false_overhead_indicator() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample8.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {"phrase": "elevator door", "normalized_component_type": "elevator_door", "score": 0.32, "box_xyxy": [158, 75, 351, 525]},
        {"phrase": "floor indicator display", "normalized_component_type": "floor_indicator_display", "score": 0.51, "box_xyxy": [184, 12, 311, 41]},
        {"phrase": "accessibility control panel", "normalized_component_type": "accessibility_control_panel", "score": 0.36, "box_xyxy": [368, 225, 405, 275]},
    ]

    detect._promote_visual_floor_indicator_detections(image, detections)

    indicators = [det for det in detections if det.get("normalized_component_type") == "floor_indicator_display"]
    assert len(indicators) == 1
    assert indicators[0]["box_xyxy"] == [368, 225, 405, 275]
    assert indicators[0]["geometry_validation"]["reason"] == "visual_red_digits_on_side_floor_indicator"


def test_open_full_door_detection_derives_interior_without_header_expansion() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample8.jpg")), cv2.COLOR_BGR2RGB)
    detections = [
        {"phrase": "elevator door", "normalized_component_type": "elevator_door", "score": 0.32, "box_xyxy": [158, 75, 351, 525]},
    ]

    detect._recover_elevator_door_header(image, detections)
    detect._add_confirmed_open_interior_detection(image, detections)

    assert detections[0]["box_xyxy"] == [158, 75, 351, 525]
    assert any(det.get("normalized_component_type") == "elevator_cabin" for det in detections)


def test_sample9_closed_textured_door_is_not_open_interior() -> None:
    image = cv2.cvtColor(cv2.imread(str(ROOT / "tests" / "images" / "Sample9.jpg")), cv2.COLOR_BGR2RGB)
    false_opening = [72.0, 119.7, 276.6, 532.3]

    assert detect._has_open_elevator_interior_evidence(image, false_opening) is False


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


def test_cop_preselection_preserves_floor_indicator_by_default(tmp_path: Path) -> None:
    image = np.full((240, 160, 3), 180, dtype=np.uint8)
    mod_path = tmp_path / "mod_panel.png"
    cv2.imwrite(str(mod_path), np.full((90, 30, 4), 255, dtype=np.uint8))
    detections = {
        "detections": [
            {
                "phrase": "floor indicator display",
                "normalized_component_type": "floor_indicator_display",
                "score": 0.6,
                "box_xyxy": [55, 40, 105, 62],
            },
            {
                "phrase": detect.OPERATING_PANEL_CLASS,
                "normalized_component_type": detect.OPERATING_PANEL_CLASS,
                "score": 0.7,
                "box_xyxy": [50, 80, 110, 190],
            },
        ]
    }
    cfg = {
        "_requested_component_type": "elevator_mod_panel",
        "removal": {"box_mask_padding_px": 0},
        "insertion": {
            "placement": "detection",
            "target_keywords": ["car operating panel"],
            "existing_panel_padding_px": 0,
            "max_existing_panel_target_area_ratio": 0.50,
        },
    }

    bbox = preselect_mod_panel_placement(image, mod_path, detections, cfg)

    assert bbox[1] > 70
    assert bbox[3] >= 190
    assert cfg["_placement_debug"]["aligned_artifact_cleanup"]["status"] == "preserved_floor_indicator_display"


def test_floor_indicator_cleanup_extension_requires_explicit_opt_in() -> None:
    target = [50, 80, 110, 190]
    detections = [
        {
            "phrase": "floor indicator display",
            "normalized_component_type": "floor_indicator_display",
            "score": 0.6,
            "box_xyxy": [55, 40, 105, 62],
        }
    ]

    expanded, debug = extend_inpaint_bbox_for_aligned_panel_artifacts(target, detections, 160, 240)

    assert expanded[1] < target[1]
    assert debug["status"] == "extended"


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
