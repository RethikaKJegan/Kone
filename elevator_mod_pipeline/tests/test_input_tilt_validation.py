from __future__ import annotations

import cv2
import numpy as np

from src import input_validation


def straight_fixture() -> np.ndarray:
    image = np.full((520, 520, 3), 180, dtype=np.uint8)
    for x in (150, 260, 370):
        cv2.line(image, (x, 70), (x, 450), (35, 35, 35), 6)
    cv2.line(image, (100, 120), (420, 120), (35, 35, 35), 5)
    cv2.line(image, (100, 420), (420, 420), (35, 35, 35), 5)
    return image


def rotate(image: np.ndarray, angle: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_LINEAR, borderValue=(180, 180, 180))


def skewed_doorway_fixture() -> np.ndarray:
    image = np.full((520, 520, 3), 180, dtype=np.uint8)
    cv2.line(image, (170, 80), (125, 450), (35, 35, 35), 6)
    cv2.line(image, (330, 80), (380, 450), (35, 35, 35), 6)
    cv2.line(image, (170, 80), (330, 80), (35, 35, 35), 5)
    cv2.line(image, (125, 450), (380, 450), (35, 35, 35), 5)
    return image


def stub_existing_validation(monkeypatch):
    calls = {"perspective": 0}

    def perspective(rgb, cfg):
        calls["perspective"] += 1
        return 1.0, ["existing perspective validation ran"]

    monkeypatch.setattr(input_validation, "perspective_score", perspective)
    monkeypatch.setattr(input_validation, "visibility_score", lambda rgb: (1.0, ["visibility ok"]))
    monkeypatch.setattr(input_validation, "sharpness_score", lambda rgb: (1.0, ["sharpness ok"]))
    monkeypatch.setattr(input_validation, "exposure_score", lambda rgb: (1.0, ["exposure ok"]))
    monkeypatch.setattr(input_validation, "context_score", lambda rgb: (1.0, ["context ok"]))
    monkeypatch.setattr(input_validation, "crop_scale_score", lambda rgb: (1.0, ["crop ok"]))
    monkeypatch.setattr(input_validation, "composition_score", lambda rgb: (1.0, ["composition ok"]))
    monkeypatch.setattr(input_validation, "technical_defects_score", lambda rgb: (1.0, ["technical ok"]))
    monkeypatch.setattr(input_validation, "geometric_defects_score", lambda rgb: (1.0, ["geometry ok"]))
    return calls


def test_straight_image_continues_to_existing_validation(monkeypatch) -> None:
    calls = stub_existing_validation(monkeypatch)

    result = input_validation.validate_input_image(straight_fixture(), {})

    assert result["result"] == "PASS"
    assert calls["perspective"] == 1


def test_left_tilted_image_is_rejected_before_existing_validation(monkeypatch) -> None:
    calls = stub_existing_validation(monkeypatch)

    result = input_validation.validate_input_image(rotate(straight_fixture(), -9), {})

    assert result["result"] == "FAIL"
    assert result["valid"] is False
    assert calls["perspective"] == 0
    assert result["reasons"]["hard_fail"] == ["Image must be straight. Please upload a non-tilted image."]


def test_right_tilted_image_is_rejected_before_existing_validation(monkeypatch) -> None:
    calls = stub_existing_validation(monkeypatch)

    result = input_validation.validate_input_image(rotate(straight_fixture(), 9), {})

    assert result["result"] == "FAIL"
    assert result["valid"] is False
    assert calls["perspective"] == 0
    assert result["reasons"]["hard_fail"] == ["Image must be straight. Please upload a non-tilted image."]


def test_skewed_doorway_image_is_rejected_before_existing_validation(monkeypatch) -> None:
    calls = stub_existing_validation(monkeypatch)

    result = input_validation.validate_input_image(skewed_doorway_fixture(), {})

    assert result["result"] == "FAIL"
    assert result["valid"] is False
    assert calls["perspective"] == 0
    assert result["metrics"]["absolute_tilt_degrees"] > 6.0
    assert result["reasons"]["hard_fail"] == ["Image must be straight. Please upload a non-tilted image."]
