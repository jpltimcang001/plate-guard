"""Unit tests for the DetectionResult domain entity."""

from __future__ import annotations

import numpy as np
import pytest

from src.detection.detection_result import DetectionResult


class TestDetectionResultCreate:
    """Tests for creating DetectionResult instances."""

    def test_create_default(self) -> None:
        """Default DetectionResult has zero-value fields."""
        det = DetectionResult()
        assert det.bounding_box == (0, 0, 0, 0)
        assert det.confidence == 0.0
        assert det.class_id == 0
        assert det.class_name == ""

    def test_create_with_values(self) -> None:
        """DetectionResult stores all constructor arguments."""
        det = DetectionResult(
            bounding_box=(10, 20, 100, 200),
            confidence=0.85,
            class_id=2,
            class_name="plate",
        )
        assert det.bounding_box == (10, 20, 100, 200)
        assert det.confidence == 0.85
        assert det.class_id == 2
        assert det.class_name == "plate"


class TestDetectionResultProperties:
    """Tests for computed properties on DetectionResult."""

    @pytest.fixture
    def det(self) -> DetectionResult:
        return DetectionResult(
            bounding_box=(50, 60, 200, 300),
            confidence=0.92,
            class_id=0,
            class_name="license_plate",
        )

    def test_x1(self, det: DetectionResult) -> None:
        assert det.x1 == 50

    def test_y1(self, det: DetectionResult) -> None:
        assert det.y1 == 60

    def test_x2(self, det: DetectionResult) -> None:
        assert det.x2 == 200

    def test_y2(self, det: DetectionResult) -> None:
        assert det.y2 == 300

    def test_width(self, det: DetectionResult) -> None:
        assert det.width == 150  # 200 - 50

    def test_height(self, det: DetectionResult) -> None:
        assert det.height == 240  # 300 - 60

    def test_area(self, det: DetectionResult) -> None:
        assert det.area == 150 * 240

    def test_center(self, det: DetectionResult) -> None:
        cx, cy = det.center
        assert cx == pytest.approx(125.0)  # (50 + 200) / 2
        assert cy == pytest.approx(180.0)  # (60 + 300) / 2


class TestDetectionResultCrop:
    """Tests for crop_frame utility."""

    @pytest.fixture
    def frame(self) -> np.ndarray:
        """Create a 100x200 test frame with known pixel values."""
        return np.arange(100 * 200 * 3, dtype=np.uint8).reshape((100, 200, 3))

    def test_crop_inside_bounds(self, frame: np.ndarray) -> None:
        """Cropping a region fully inside the frame works."""
        det = DetectionResult(bounding_box=(10, 10, 50, 50))
        cropped = det.crop_frame(frame)
        assert cropped.shape == (40, 40, 3)
        np.testing.assert_array_equal(cropped, frame[10:50, 10:50])

    def test_crop_clamped_to_bounds(self, frame: np.ndarray) -> None:
        """Cropping a region that extends beyond the frame is clamped."""
        det = DetectionResult(bounding_box=(-10, -10, 300, 300))
        cropped = det.crop_frame(frame)
        assert cropped.shape == (100, 200, 3)  # clamped to full frame
        np.testing.assert_array_equal(cropped, frame)

    def test_crop_empty_when_invalid(self, frame: np.ndarray) -> None:
        """Cropping an invalid (zero-area) region returns empty."""
        det = DetectionResult(bounding_box=(50, 50, 30, 30))  # x2 < x1
        cropped = det.crop_frame(frame)
        assert cropped.size == 0


class TestDetectionResultRepr:
    """Tests for string representation."""

    def test_repr_contains_key_fields(self) -> None:
        """__repr__ includes class name, confidence, and bbox."""
        det = DetectionResult(
            bounding_box=(1, 2, 3, 4),
            confidence=0.75,
            class_id=1,
            class_name="plate",
        )
        rep = repr(det)
        assert "plate" in rep
        assert "0.750" in rep
        assert "1,2,3,4" in rep
