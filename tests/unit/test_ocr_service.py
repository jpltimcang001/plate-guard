"""Unit tests for OcrResult entity and PlateOcrService.

All PaddleOCR interactions are mocked so tests do not require
the paddleocr package or a GPU.
"""

from __future__ import annotations

from typing import Any, List, Tuple
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest

from src.detection.detection_result import DetectionResult
from src.ocr.ocr_result import OcrResult
from src.ocr.ocr_service import OcrError, PlateOcrService

# ======================================================================
# Fake / mock helpers
# ======================================================================

_FRAME_H = 480
_FRAME_W = 640


def _make_frame() -> np.ndarray:
    """Return a solid-gray BGR frame."""
    return np.full((_FRAME_H, _FRAME_W, 3), 128, dtype=np.uint8)


def _make_detection(
    x1: int = 100,
    y1: int = 200,
    x2: int = 300,
    y2: int = 250,
    confidence: float = 0.9,
) -> DetectionResult:
    """Return a DetectionResult with a reasonable plate-sized bbox."""
    return DetectionResult(
        bounding_box=(x1, y1, x2, y2),
        confidence=confidence,
        class_id=0,
        class_name="plate",
    )


def _make_fake_paddle_region(
    text: str = "ABC123",
    confidence: float = 0.95,
    polygon: List[List[float]] | None = None,
) -> List[Any]:
    """Build a single PaddleOCR region in the format ``ocr()`` returns.

    Each region is::

        [polygon_points, (text, confidence)]

    where polygon_points is a list of four ``[x, y]`` pairs.
    """
    if polygon is None:
        polygon = [[100, 200], [300, 200], [300, 250], [100, 250]]
    return [polygon, (text, confidence)]


# ======================================================================
# OcrResult entity
# ======================================================================


class TestOcrResult:
    """Tests for the OcrResult domain entity."""

    def test_create_default(self) -> None:
        """Default OcrResult has empty text and zero confidence."""
        result = OcrResult()
        assert result.text == ""
        assert result.confidence == 0.0
        assert result.bounding_box is None
        assert result.processing_time_ms == 0.0
        assert not result.is_success

    def test_create_with_values(self) -> None:
        """OcrResult stores all constructor arguments."""
        result = OcrResult(
            text="ABC123",
            confidence=0.95,
            bounding_box=(10, 20, 100, 80),
            processing_time_ms=12.5,
            raw_text=" ABC123 ",
        )
        assert result.text == "ABC123"
        assert result.confidence == pytest.approx(0.95)
        assert result.bounding_box == (10, 20, 100, 80)
        assert result.processing_time_ms == pytest.approx(12.5)
        assert result.raw_text == " ABC123 "

    def test_is_success_when_text_and_confidence(self) -> None:
        """is_success is True when text is non-empty and confidence > 0."""
        result = OcrResult(text="XYZ789", confidence=0.8)
        assert result.is_success

    def test_is_success_false_when_empty_text(self) -> None:
        """is_success is False when text is empty."""
        result = OcrResult(text="", confidence=0.8)
        assert not result.is_success

    def test_is_success_false_when_zero_confidence(self) -> None:
        """is_success is False when confidence is zero."""
        result = OcrResult(text="ABC", confidence=0.0)
        assert not result.is_success

    def test_text_length(self) -> None:
        """text_length returns the number of characters."""
        result = OcrResult(text="ABC123")
        assert result.text_length == 6

    def test_text_length_empty(self) -> None:
        """text_length is 0 for empty text."""
        result = OcrResult()
        assert result.text_length == 0

    def test_empty_factory(self) -> None:
        """empty() returns a blank OcrResult."""
        result = OcrResult.empty(reason="crop was empty")
        assert result.text == ""
        assert result.confidence == 0.0
        assert result.bounding_box is None
        assert not result.is_success

    def test_repr_success(self) -> None:
        """__repr__ includes recognised text and confidence."""
        result = OcrResult(text="ABC123", confidence=0.85, processing_time_ms=15.0)
        rep = repr(result)
        assert "ABC123" in rep
        assert "0.850" in rep
        assert "15.0" in rep

    def test_repr_empty(self) -> None:
        """__repr__ for an empty result says 'empty'."""
        result = OcrResult()
        rep = repr(result)
        assert "empty" in rep


# ======================================================================
# PlateOcrService — lifecycle
# ======================================================================


class TestPlateOcrServiceLifecycle:
    """Tests for service start / stop."""

    def test_init_defaults(self) -> None:
        """Service initialises with default values and is not started."""
        service = PlateOcrService()
        assert not service.is_started
        assert service.lang == "en"
        assert service.confidence_threshold == 0.5
        assert service.use_gpu

    def test_init_custom_values(self) -> None:
        """Service stores custom constructor arguments."""
        service = PlateOcrService(
            lang="ch",
            confidence_threshold=0.7,
            use_gpu=False,
            max_text_length=10,
            det_db_thresh=0.3,
        )
        assert service.lang == "ch"
        assert service.confidence_threshold == 0.7
        assert not service.use_gpu
        assert service._max_text_length == 10
        assert service._paddle_kwargs["det_db_thresh"] == 0.3

    def test_start_creates_engine(self) -> None:
        """start() initialises the OCR engine and sets is_started."""
        service = PlateOcrService()
        service._create_engine = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
        service.start()
        assert service.is_started
        assert service._ocr is not None
        service._create_engine.assert_called_once()  # type: ignore[attr-defined]

    def test_start_raises_when_already_started(self) -> None:
        """Calling start() twice raises RuntimeError."""
        service = PlateOcrService()
        service._create_engine = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
        service.start()
        with pytest.raises(RuntimeError, match="already started"):
            service.start()

    def test_stop_releases_engine(self) -> None:
        """stop() clears the engine and is_started."""
        service = PlateOcrService()
        service._create_engine = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
        service.start()
        service.stop()
        assert not service.is_started
        assert service._ocr is None

    def test_stop_idempotent(self) -> None:
        """Calling stop() when not started does not raise."""
        service = PlateOcrService()
        service.stop()  # should not raise

    def test_start_raises_ocr_error_on_import_error(self) -> None:
        """start() raises OcrError when PaddleOCR is not installed."""
        service = PlateOcrService()
        original = service._create_engine

        def _failing_import() -> None:
            raise ImportError("No module named 'paddleocr'")

        service._create_engine = _failing_import  # type: ignore[method-assign]
        with pytest.raises(OcrError, match="PaddleOCR is not installed"):
            service.start()

    def test_start_raises_ocr_error_on_init_failure(self) -> None:
        """start() raises OcrError when the engine constructor fails."""
        service = PlateOcrService()

        def _failing_init() -> None:
            msg = "CUDA out of memory"
            raise RuntimeError(msg)

        service._create_engine = _failing_init  # type: ignore[method-assign]
        with pytest.raises(OcrError, match="Failed to initialise"):
            service.start()


# ======================================================================
# PlateOcrService — core OCR
# ======================================================================


class TestPlateOcrServiceCore:
    """Tests for ocr_crop()."""

    def _make_service(self, **kwargs: Any) -> PlateOcrService:
        """Create a started service with a mock engine."""
        service = PlateOcrService(**kwargs)
        mock_engine = MagicMock()
        service._create_engine = MagicMock(return_value=mock_engine)  # type: ignore[method-assign]
        service.start()
        return service

    def test_ocr_crop_raises_if_not_started(self) -> None:
        """ocr_crop() raises RuntimeError if service not started."""
        service = PlateOcrService()
        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        with pytest.raises(RuntimeError, match="has not been started"):
            service.ocr_crop(crop)

    def test_ocr_crop_returns_empty_for_empty_crop(self) -> None:
        """ocr_crop() returns empty OcrResult when crop is zero-size."""
        service = self._make_service()
        crop = np.array([], dtype=np.uint8)
        result = service.ocr_crop(crop)
        assert result.text == ""
        assert result.confidence == 0.0

    def test_ocr_crop_returns_empty_for_invalid_crop(self) -> None:
        """ocr_crop() returns empty OcrResult when crop has wrong dims."""
        service = self._make_service()
        crop = np.zeros((50, 100), dtype=np.uint8)  # 2D, not 3-channel
        result = service.ocr_crop(crop)
        assert result.text == ""

    def test_ocr_crop_delegates_to_engine(self) -> None:
        """ocr_crop() calls engine.ocr() with the crop."""
        service = self._make_service()
        mock_result = [_make_fake_paddle_region(text="ABC123", confidence=0.95)]
        service._ocr.ocr.return_value = mock_result  # type: ignore[union-attr]

        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        result = service.ocr_crop(crop)
        assert result.text == "ABC123"
        assert result.confidence == pytest.approx(0.95)
        service._ocr.ocr.assert_called_once_with(crop, cls=False)  # type: ignore[union-attr]

    def test_ocr_crop_applies_confidence_threshold(self) -> None:
        """ocr_crop() returns empty text when confidence is below threshold."""
        service = self._make_service(confidence_threshold=0.8)
        mock_result = [_make_fake_paddle_region(text="ABC123", confidence=0.5)]
        service._ocr.ocr.return_value = mock_result  # type: ignore[union-attr]

        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        result = service.ocr_crop(crop)
        assert result.text == ""  # filtered by threshold
        assert result.confidence == pytest.approx(0.5)  # raw confidence preserved

    def test_ocr_crop_applies_max_text_length(self) -> None:
        """ocr_crop() returns empty text when result exceeds max length."""
        service = self._make_service(max_text_length=5)
        mock_result = [_make_fake_paddle_region(text="TOO_LONG_PLATE", confidence=0.95)]
        service._ocr.ocr.return_value = mock_result  # type: ignore[union-attr]

        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        result = service.ocr_crop(crop)
        assert result.text == ""  # filtered by length
        assert result.confidence == pytest.approx(0.95)

    def test_ocr_crop_raises_on_inference_failure(self) -> None:
        """ocr_crop() raises OcrError when engine.ocr() raises."""
        service = self._make_service()
        service._ocr.ocr.side_effect = RuntimeError("CUDA error")  # type: ignore[union-attr]

        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        with pytest.raises(OcrError, match="OCR inference failed"):
            service.ocr_crop(crop)

    def test_ocr_crop_returns_empty_when_engine_returns_none(self) -> None:
        """ocr_crop() returns empty OcrResult when engine returns None."""
        service = self._make_service()
        service._ocr.ocr.return_value = None  # type: ignore[union-attr]

        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        result = service.ocr_crop(crop)
        assert result.text == ""

    def test_ocr_crop_returns_empty_when_engine_returns_none_list(self) -> None:
        """ocr_crop() handles engine returning [None]."""
        service = self._make_service()
        service._ocr.ocr.return_value = [None]  # type: ignore[union-attr]

        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        result = service.ocr_crop(crop)
        assert result.text == ""

    def test_ocr_crop_preserves_raw_text(self) -> None:
        """ocr_crop() preserves raw_text before stripping."""
        service = self._make_service()
        mock_result = [_make_fake_paddle_region(text="  ABC  ")]
        service._ocr.ocr.return_value = mock_result  # type: ignore[union-attr]

        crop = np.zeros((50, 100, 3), dtype=np.uint8)
        result = service.ocr_crop(crop)
        assert result.text == "ABC"  # stripped
        assert result.raw_text == "  ABC  "  # raw preserved


# ======================================================================
# PlateOcrService — detection-level OCR
# ======================================================================


class TestPlateOcrServiceDetection:
    """Tests for ocr_detection() and ocr_detections()."""

    def _make_service(self, **kwargs: Any) -> PlateOcrService:
        service = PlateOcrService(**kwargs)
        mock_engine = MagicMock()
        service._create_engine = MagicMock(return_value=mock_engine)  # type: ignore[method-assign]
        service.start()
        return service

    def test_ocr_detection_crops_and_ocrs(self) -> None:
        """ocr_detection() crops the detection from the frame and OCRs it."""
        service = self._make_service()
        mock_result = [_make_fake_paddle_region(text="PLATE1", confidence=0.92)]
        service._ocr.ocr.return_value = mock_result  # type: ignore[union-attr]

        frame = _make_frame()
        detection = _make_detection(x1=50, y1=60, x2=200, y2=120)
        result = service.ocr_detection(frame, detection)

        assert result.text == "PLATE1"
        assert result.confidence == pytest.approx(0.92)

        # Verify the crop passed to OCR matches the detection bbox
        called_crop = service._ocr.ocr.call_args[0][0]  # type: ignore[union-attr]
        assert called_crop.shape == (60, 150, 3)  # (120-60, 200-50, 3)

    def test_ocr_detection_returns_empty_for_out_of_bounds(self) -> None:
        """ocr_detection() handles out-of-bounds detection gracefully."""
        service = self._make_service()

        frame = _make_frame()
        # Detection entirely outside the frame
        detection = _make_detection(x1=5000, y1=5000, x2=5100, y2=5100)
        result = service.ocr_detection(frame, detection)
        assert result.text == ""
        assert not result.is_success

    def test_ocr_detections_processes_all(self) -> None:
        """ocr_detections() returns one result per detection."""
        service = self._make_service()

        def _side_effect(crop: np.ndarray, **kwargs: Any) -> Any:
            # Return different text depending on crop size
            h, w = crop.shape[:2]
            if w > 100:
                return [_make_fake_paddle_region(text="BIG", confidence=0.9)]
            return [_make_fake_paddle_region(text="SMALL", confidence=0.8)]

        service._ocr.ocr.side_effect = _side_effect  # type: ignore[union-attr]

        frame = _make_frame()
        detections = [
            _make_detection(x1=10, y1=10, x2=200, y2=50),  # wide
            _make_detection(x1=10, y1=60, x2=80, y2=100),  # narrow
        ]
        results = service.ocr_detections(frame, detections)

        assert len(results) == 2
        assert results[0].text == "BIG"
        assert results[1].text == "SMALL"

    def test_ocr_detections_empty_list(self) -> None:
        """ocr_detections() returns empty list when no detections."""
        service = self._make_service()
        frame = _make_frame()
        results = service.ocr_detections(frame, [])
        assert results == []


# ======================================================================
# PlateOcrService — result parsing
# ======================================================================


class TestPlateOcrServiceParse:
    """Tests for the internal result parser."""

    def test_parse_none(self) -> None:
        """_parse_paddle_result returns empty for None input."""
        service = PlateOcrService()
        result = service._parse_paddle_result(None)
        assert result.text == ""
        assert result.confidence == 0.0

    def test_parse_empty_list(self) -> None:
        """_parse_paddle_result returns empty for empty list."""
        service = PlateOcrService()
        result = service._parse_paddle_result([])
        assert result.text == ""

    def test_parse_single_region(self) -> None:
        """_parse_paddle_result extracts text and confidence."""
        service = PlateOcrService()
        raw = [_make_fake_paddle_region(text="XYZ789", confidence=0.88)]
        result = service._parse_paddle_result(raw, processing_time_ms=10.0)
        assert result.text == "XYZ789"
        assert result.confidence == pytest.approx(0.88)
        assert result.processing_time_ms == pytest.approx(10.0)

    def test_parse_multiple_regions_takes_best(self) -> None:
        """_parse_paddle_result picks the highest-confidence region."""
        service = PlateOcrService()
        raw = [
            _make_fake_paddle_region(text="LOW", confidence=0.3),
            _make_fake_paddle_region(text="HIGH", confidence=0.95),
            _make_fake_paddle_region(text="MEDIUM", confidence=0.6),
        ]
        result = service._parse_paddle_result(raw)
        assert result.text == "HIGH"
        assert result.confidence == pytest.approx(0.95)

    def test_parse_returns_empty_below_threshold(self) -> None:
        """_parse_paddle_result returns empty text when below threshold."""
        service = PlateOcrService(confidence_threshold=0.8)
        raw = [_make_fake_paddle_region(text="LOW", confidence=0.3)]
        result = service._parse_paddle_result(raw)
        assert result.text == ""
        assert result.confidence == pytest.approx(0.3)  # raw conf preserved

    def test_parse_polygon_to_bbox(self) -> None:
        """_parse_paddle_result computes bbox from polygon."""
        service = PlateOcrService()
        polygon = [[50, 60], [200, 60], [200, 120], [50, 120]]
        raw = [_make_fake_paddle_region(text="BOX", confidence=0.9, polygon=polygon)]
        result = service._parse_paddle_result(raw)
        assert result.bounding_box == (50, 60, 200, 120)

    def test_parse_skips_malformed_items(self) -> None:
        """_parse_paddle_result skips malformed items without crashing."""
        service = PlateOcrService()
        raw: List[Any] = [
            None,
            "not_a_region",
            [1, 2, 3],  # wrong length
            _make_fake_paddle_region(text="VALID", confidence=0.9),
        ]
        result = service._parse_paddle_result(raw)
        assert result.text == "VALID"


# ======================================================================
# PlateOcrService — confidence threshold setter
# ======================================================================


class TestPlateOcrServiceConfig:
    """Tests for configuration properties and setters."""

    def test_confidence_threshold_setter_valid(self) -> None:
        """Setting a valid threshold updates the value."""
        service = PlateOcrService()
        service.confidence_threshold = 0.75
        assert service.confidence_threshold == 0.75

    def test_confidence_threshold_setter_invalid_low(self) -> None:
        """Setting threshold below 0 raises ValueError."""
        service = PlateOcrService()
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            service.confidence_threshold = -0.1

    def test_confidence_threshold_setter_invalid_high(self) -> None:
        """Setting threshold above 1 raises ValueError."""
        service = PlateOcrService()
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            service.confidence_threshold = 1.5
