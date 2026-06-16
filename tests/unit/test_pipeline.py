"""Unit tests for the DetectionPipeline orchestrator.

Tests cover:
- Pipeline initialisation (required + optional services)
- ``process_frame`` with empty frames, no detections
- Full pipeline flow: detection → zone → tracker → OCR → dedup → persist
- Graceful degradation when optional services are ``None``
- Callback invocation
- Error handling (detection/OCR/persistence failures) — logged, not raised
"""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from src.detection.detection_result import DetectionResult
from src.detection.duplicate_filter import DuplicateFilter
from src.detection.frame_queue import Frame
from src.detection.pipeline import DetectionEvent, DetectionPipeline, PipelineResult
from src.detection.tracker import DetectionTracker
from src.detection.zone_validator import ZoneValidator
from src.ocr.ocr_result import OcrResult


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def mock_detection_service() -> MagicMock:
    svc = MagicMock()
    svc.is_started = True
    return svc


@pytest.fixture
def mock_ocr_service() -> MagicMock:
    svc = MagicMock()
    svc.is_started = True
    svc.ocr_detection.return_value = OcrResult(text="ABC-123", confidence=0.95)
    return svc


@pytest.fixture
def mock_zone_validator() -> MagicMock:
    zv = MagicMock(spec=ZoneValidator)
    zv.is_in_any_zone.return_value = True  # pass all zones by default
    return zv


@pytest.fixture
def mock_tracker() -> MagicMock:
    tracker = MagicMock(spec=DetectionTracker)

    def _update(camera_id: int, detections: list[DetectionResult]) -> list[DetectionResult]:
        for i, d in enumerate(detections):
            d.track_id = i + 1  # type: ignore[attr-defined]
            d.is_new = True  # type: ignore[attr-defined]
        return detections

    tracker.update.side_effect = _update
    return tracker


@pytest.fixture
def mock_duplicate_filter() -> MagicMock:
    df = MagicMock(spec=DuplicateFilter)
    # Return False meaning "not a duplicate" (pass through)
    df.check_and_record.return_value = True
    return df


@pytest.fixture
def mock_detection_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_media_writer() -> MagicMock:
    mw = MagicMock()
    mw.save_snapshot.return_value = "/media/snapshots/plate_001.jpg"
    return mw


@pytest.fixture
def mock_webhook_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_on_detection() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sample_frame() -> Frame:
    """A 100x200 BGR frame with some content."""
    data = np.zeros((100, 200, 3), dtype=np.uint8)
    data[30:70, 50:150] = [128, 128, 128]  # grey rectangle
    return Frame(
        data=data,
        camera_id=1,
        timestamp=time.time(),
        frame_number=42,
    )


@pytest.fixture
def sample_detection() -> DetectionResult:
    return DetectionResult(
        bounding_box=(55, 35, 145, 65),
        confidence=0.92,
        class_id=0,
        class_name="plate",
    )


# ======================================================================
# Initialisation
# ======================================================================


class TestPipelineInit:
    """Tests for DetectionPipeline.__init__()."""

    def test_required_only(self, mock_detection_service: MagicMock) -> None:
        pipeline = DetectionPipeline(plate_detection_service=mock_detection_service)
        assert pipeline.detection_service is mock_detection_service
        assert pipeline.ocr_service is None
        assert pipeline.zone_validator is None
        assert pipeline.tracker is None
        assert pipeline.duplicate_filter is None

    def test_all_services(self, mock_detection_service: MagicMock, mock_ocr_service: MagicMock,
                          mock_zone_validator: MagicMock, mock_tracker: MagicMock,
                          mock_duplicate_filter: MagicMock) -> None:
        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            zone_validator=mock_zone_validator,
            tracker=mock_tracker,
            duplicate_filter=mock_duplicate_filter,
        )
        assert pipeline.ocr_service is mock_ocr_service
        assert pipeline.zone_validator is mock_zone_validator
        assert pipeline.tracker is mock_tracker
        assert pipeline.duplicate_filter is mock_duplicate_filter

    def test_repr(self, mock_detection_service: MagicMock) -> None:
        pipeline = DetectionPipeline(plate_detection_service=mock_detection_service)
        rep = repr(pipeline)
        assert "DetectionPipeline" in rep
        assert "ocr=False" in rep
        assert "zones=False" in rep


# ======================================================================
# Empty / no-detection scenarios
# ======================================================================


class TestPipelineNoDetections:
    """Pipeline behaviour when YOLO finds nothing."""

    def test_service_not_started(self, mock_detection_service: MagicMock,
                                  sample_frame: Frame) -> None:
        mock_detection_service.is_started = False
        pipeline = DetectionPipeline(plate_detection_service=mock_detection_service)
        result = pipeline.process_frame(sample_frame)
        assert isinstance(result, PipelineResult)
        assert result.detections_found == 0
        assert result.processing_time_ms >= 0

    def test_no_detections_in_frame(self, mock_detection_service: MagicMock,
                                     sample_frame: Frame) -> None:
        mock_detection_service.detect_frame.return_value = []
        pipeline = DetectionPipeline(plate_detection_service=mock_detection_service)
        result = pipeline.process_frame(sample_frame)
        assert result.detections_found == 0
        assert result.frame_number == 42
        assert result.camera_id == 1

    def test_all_filtered_by_zone(self, mock_detection_service: MagicMock,
                                   mock_zone_validator: MagicMock,
                                   sample_frame: Frame,
                                   sample_detection: DetectionResult) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_zone_validator.is_in_any_zone.return_value = False

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            zone_validator=mock_zone_validator,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.detections_found == 1
        assert result.detections_in_zones == 0

    def test_no_new_tracks_after_tracker(self, mock_detection_service: MagicMock,
                                          mock_tracker: MagicMock,
                                          sample_frame: Frame,
                                          sample_detection: DetectionResult) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]

        # Make tracker return detection but mark is_new=False
        def _update_no_new(camera_id: int, dets: list[DetectionResult]) -> list[DetectionResult]:
            for d in dets:
                d.track_id = 1  # type: ignore[attr-defined]
                d.is_new = False  # type: ignore[attr-defined]
            return dets

        mock_tracker.update.side_effect = _update_no_new

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            tracker=mock_tracker,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.detections_found == 1
        assert result.new_tracks == 0
        # OCR should NOT be called because there are no new tracks
        # (no ocr_service configured anyway here, but just verifying flow stops)


# ======================================================================
# Full pipeline flow
# ======================================================================


class TestPipelineFullFlow:
    """Happy-path tests that exercise all stages."""

    def test_full_pipeline_persists_detection(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_zone_validator: MagicMock,
        mock_tracker: MagicMock,
        mock_duplicate_filter: MagicMock,
        mock_detection_repo: MagicMock,
        mock_media_writer: MagicMock,
        mock_webhook_service: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        """A single detection should flow through all stages and be persisted."""
        mock_detection_service.detect_frame.return_value = [sample_detection]

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            zone_validator=mock_zone_validator,
            tracker=mock_tracker,
            duplicate_filter=mock_duplicate_filter,
            detection_repo=mock_detection_repo,
            media_writer=mock_media_writer,
            webhook_service=mock_webhook_service,
        )
        result = pipeline.process_frame(sample_frame)

        # Verify counts
        assert result.detections_found == 1
        assert result.detections_in_zones == 1
        assert result.new_tracks == 1
        assert result.ocr_processed == 1
        assert result.ocr_successful == 1
        assert result.duplicates_suppressed == 0  # check_and_record returned True → not suppressed
        assert result.detections_persisted == 1
        assert result.processing_time_ms > 0

        # Verify OCR was called
        mock_ocr_service.ocr_detection.assert_called_once_with(
            sample_frame.data, sample_detection,
        )

        # Verify snapshot
        mock_media_writer.save_snapshot.assert_called_once()

        # Verify DB persistence
        mock_detection_repo.add.assert_called_once()
        added_model = mock_detection_repo.add.call_args[0][0]
        assert added_model.camera_id == 1
        assert added_model.plate_number == "ABC-123"
        assert added_model.webhook_status == "pending"

        # Verify webhook
        mock_webhook_service.dispatch.assert_called_once()
        dispatched_event = mock_webhook_service.dispatch.call_args[0][0]
        assert isinstance(dispatched_event, DetectionEvent)
        assert dispatched_event.plate_text == "ABC-123"

    def test_on_detection_callback_invoked(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_on_detection: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            on_detection=mock_on_detection,
        )
        pipeline.process_frame(sample_frame)

        mock_on_detection.assert_called_once()
        event = mock_on_detection.call_args[0][0]
        assert isinstance(event, DetectionEvent)

    def test_multiple_detections(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_detection_repo: MagicMock,
        sample_frame: Frame,
    ) -> None:
        dets = [
            DetectionResult(bounding_box=(10, 10, 50, 50), confidence=0.9),
            DetectionResult(bounding_box=(100, 100, 150, 150), confidence=0.85),
        ]
        mock_detection_service.detect_frame.return_value = dets

        # Return different text per detection to exercise OCR
        mock_ocr_service.ocr_detection.side_effect = [
            OcrResult(text="ABC-123", confidence=0.95),
            OcrResult(text="XYZ-789", confidence=0.88),
        ]

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            duplicate_filter=MagicMock(spec=DuplicateFilter, check_and_record=lambda t: True),
            detection_repo=mock_detection_repo,
        )
        result = pipeline.process_frame(sample_frame)

        assert result.detections_found == 2
        assert result.new_tracks == 2
        assert result.ocr_processed == 2
        assert result.ocr_successful == 2
        assert result.detections_persisted == 2
        assert mock_detection_repo.add.call_count == 2


# ======================================================================
# Optional services
# ======================================================================


class TestPipelineOptionalServices:
    """Graceful degradation when services are None."""

    def test_no_zone_validator(
        self,
        mock_detection_service: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        pipeline = DetectionPipeline(plate_detection_service=mock_detection_service)
        result = pipeline.process_frame(sample_frame)
        # detections_in_zones stays 0 (no zone check performed)
        assert result.detections_found == 1
        assert result.detections_in_zones == 0

    def test_no_tracker(
        self,
        mock_detection_service: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        pipeline = DetectionPipeline(plate_detection_service=mock_detection_service)
        result = pipeline.process_frame(sample_frame)
        # Without tracker, is_new cannot be checked — so new_tracks = 0
        # and the pipeline stops before OCR because no new tracks
        assert result.new_tracks == 0
        assert result.ocr_processed == 0

    def test_no_ocr_service(
        self,
        mock_detection_service: MagicMock,
        mock_tracker: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            tracker=mock_tracker,
            # No OCR service
        )
        result = pipeline.process_frame(sample_frame)
        # Without OCR, the pipeline creates a DetectionEvent with empty plate_text
        assert result.ocr_processed == 1
        assert result.ocr_successful == 0  # empty text

    @patch("src.detection.pipeline.logger")
    def test_no_ocr_service_no_repo_no_webhook(
        self,
        mock_logger: MagicMock,
        mock_detection_service: MagicMock,
        mock_tracker: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        """With just detection + tracker, a minimal event is still created."""
        mock_detection_service.detect_frame.return_value = [sample_detection]
        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            tracker=mock_tracker,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.ocr_processed == 1
        assert result.detections_persisted == 0
        # No errors should have been logged
        error_calls = [c for c in mock_logger.error.call_args_list]
        assert len(error_calls) == 0

    def test_no_duplicate_filter(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_detection_repo: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            detection_repo=mock_detection_repo,
            # No duplicate filter
        )
        result = pipeline.process_frame(sample_frame)
        assert result.duplicates_suppressed == 0
        assert result.detections_persisted == 1


# ======================================================================
# Duplicate suppression
# ======================================================================


class TestPipelineDuplicateFilter:
    """Tests for the duplicate filter integration."""

    def test_duplicate_suppresses_persistence(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_duplicate_filter: MagicMock,
        mock_detection_repo: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]

        # check_and_record returns False → duplicate detected → skip
        mock_duplicate_filter.check_and_record.return_value = False

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            duplicate_filter=mock_duplicate_filter,
            detection_repo=mock_detection_repo,
        )
        result = pipeline.process_frame(sample_frame)

        assert result.ocr_processed == 1
        assert result.ocr_successful == 1
        assert result.duplicates_suppressed == 1
        assert result.detections_persisted == 0
        mock_detection_repo.add.assert_not_called()

    def test_duplicate_filter_called_with_ocr_text(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_duplicate_filter: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_ocr_service.ocr_detection.return_value = OcrResult(text="PLATE-1", confidence=0.95)
        mock_duplicate_filter.check_and_record.return_value = True

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            duplicate_filter=mock_duplicate_filter,
        )
        pipeline.process_frame(sample_frame)

        mock_duplicate_filter.check_and_record.assert_called_once_with("PLATE-1")

    def test_duplicate_filter_not_called_for_empty_ocr(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_duplicate_filter: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_ocr_service.ocr_detection.return_value = OcrResult(text="", confidence=0.0)

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            duplicate_filter=mock_duplicate_filter,
        )
        pipeline.process_frame(sample_frame)

        # Duplicate filter should NOT be called for empty OCR text
        mock_duplicate_filter.check_and_record.assert_not_called()


# ======================================================================
# Error handling
# ======================================================================


class TestPipelineErrorHandling:
    """Errors in any sub-service should be caught and logged, not raised."""

    @patch("src.detection.pipeline.logger")
    def test_ocr_error_logged_not_raised(
        self,
        mock_logger: MagicMock,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_ocr_service.ocr_detection.side_effect = RuntimeError("OCR crashed")

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
        )
        # Should not raise
        result = pipeline.process_frame(sample_frame)

        assert result.ocr_processed == 1
        assert result.ocr_successful == 0
        # Warning should have been logged
        mock_logger.opt.assert_called()

    @patch("src.detection.pipeline.logger")
    def test_snapshot_error_logged_not_raised(
        self,
        mock_logger: MagicMock,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_media_writer: MagicMock,
        mock_detection_repo: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_media_writer.save_snapshot.side_effect = OSError("Disk full")

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            media_writer=mock_media_writer,
            detection_repo=mock_detection_repo,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.detections_persisted == 1  # DB save still happened

    @patch("src.detection.pipeline.logger")
    def test_db_error_logged_not_raised(
        self,
        mock_logger: MagicMock,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_detection_repo: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_detection_repo.add.side_effect = RuntimeError("DB connection lost")

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            detection_repo=mock_detection_repo,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.detections_persisted == 0

    @patch("src.detection.pipeline.logger")
    def test_webhook_error_logged_not_raised(
        self,
        mock_logger: MagicMock,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_detection_repo: MagicMock,
        mock_webhook_service: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_webhook_service.dispatch.side_effect = RuntimeError("HTTP timeout")

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            detection_repo=mock_detection_repo,
            webhook_service=mock_webhook_service,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.detections_persisted == 1  # DB still saved

    @patch("src.detection.pipeline.logger")
    def test_on_detection_callback_error_logged_not_raised(
        self,
        mock_logger: MagicMock,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_on_detection: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        mock_on_detection.side_effect = ValueError("callback failed")

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            on_detection=mock_on_detection,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.ocr_processed == 1
        # Callback error should not crash the pipeline


# ======================================================================
# PipelineResult fields
# ======================================================================


class TestPipelineResult:
    """Verify PipelineResult is populated correctly."""

    def test_frame_number_and_camera_id(
        self,
        mock_detection_service: MagicMock,
        sample_frame: Frame,
    ) -> None:
        mock_detection_service.detect_frame.return_value = []
        pipeline = DetectionPipeline(plate_detection_service=mock_detection_service)
        result = pipeline.process_frame(sample_frame)
        assert result.frame_number == 42
        assert result.camera_id == 1

    def test_processing_time_positive(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]
        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
        )
        result = pipeline.process_frame(sample_frame)
        assert result.processing_time_ms > 0


class TestPipelineEmptyFrame:
    """Edge case: empty frame data."""

    def test_empty_frame_data(
        self,
        mock_detection_service: MagicMock,
        mock_tracker: MagicMock,
    ) -> None:
        frame = Frame(
            data=np.array([], dtype=np.uint8),
            camera_id=1,
            timestamp=time.time(),
            frame_number=0,
        )
        mock_detection_service.detect_frame.return_value = []
        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            tracker=mock_tracker,
        )
        result = pipeline.process_frame(frame)
        assert result.detections_found == 0

    def test_frame_with_size_zero_after_detection(
        self,
        mock_detection_service: MagicMock,
        mock_tracker: MagicMock,
    ) -> None:
        """Detection found but frame data is empty — should handle gracefully."""
        frame = Frame(
            data=np.array([], dtype=np.uint8),
            camera_id=1,
            timestamp=time.time(),
            frame_number=5,
        )
        det = DetectionResult(bounding_box=(10, 10, 50, 50), confidence=0.9)
        mock_detection_service.detect_frame.return_value = [det]

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            tracker=mock_tracker,
        )
        result = pipeline.process_frame(frame)
        assert result.new_tracks == 1
        assert result.ocr_processed == 1


# ======================================================================
# Webhook status mapping
# ======================================================================


class TestPipelineWebhookStatus:
    """Verify the webhook_status field in DB records."""

    def test_webhook_status_pending_when_webhook_service_present(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_detection_repo: MagicMock,
        mock_webhook_service: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            detection_repo=mock_detection_repo,
            webhook_service=mock_webhook_service,
        )
        pipeline.process_frame(sample_frame)

        added = mock_detection_repo.add.call_args[0][0]
        assert added.webhook_status == "pending"

    def test_webhook_status_not_configured_when_no_webhook(
        self,
        mock_detection_service: MagicMock,
        mock_ocr_service: MagicMock,
        mock_tracker: MagicMock,
        mock_detection_repo: MagicMock,
        sample_frame: Frame,
        sample_detection: DetectionResult,
    ) -> None:
        mock_detection_service.detect_frame.return_value = [sample_detection]

        pipeline = DetectionPipeline(
            plate_detection_service=mock_detection_service,
            ocr_service=mock_ocr_service,
            tracker=mock_tracker,
            detection_repo=mock_detection_repo,
            # No webhook service
        )
        pipeline.process_frame(sample_frame)

        added = mock_detection_repo.add.call_args[0][0]
        assert added.webhook_status == "not_configured"


# ======================================================================
# DetectionEvent dataclass
# ======================================================================


class TestDetectionEvent:
    """Smoke tests for the DetectionEvent dataclass."""

    def test_default_detected_at(self) -> None:
        event = DetectionEvent(
            camera_id=1,
            track_id=1,
            plate_text="ABC",
            confidence=0.95,
            bounding_box=(0, 0, 10, 10),
            frame=np.zeros((10, 10, 3), dtype=np.uint8),
            cropped_plate=np.zeros((5, 5, 3), dtype=np.uint8),
        )
        assert event.detected_at is not None
        assert event.snapshot_path is None
        assert event.video_path is None

    def test_custom_timestamp(self) -> None:
        dt = datetime(2026, 6, 15, 12, 0, 0)
        event = DetectionEvent(
            camera_id=1,
            track_id=5,
            plate_text="XYZ",
            confidence=0.8,
            bounding_box=(10, 10, 50, 50),
            frame=np.zeros((100, 100, 3), dtype=np.uint8),
            cropped_plate=np.zeros((20, 20, 3), dtype=np.uint8),
            detected_at=dt,
        )
        assert event.detected_at == dt
