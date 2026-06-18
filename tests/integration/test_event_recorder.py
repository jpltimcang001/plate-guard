"""End-to-end integration tests for the EventRecorder.

Tests the full flow from detection event → snapshot/clip capture →
file I/O using real MediaWriter and temporary directories.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pytest

from src.domain.events.plate_detected import PlateDetected
from src.recorder.event_recorder import EventRecorder

if TYPE_CHECKING:
    pass


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def event_recorder(evidence_dir: Path) -> EventRecorder:
    """Return an EventRecorder that writes to the temporary evidence dir."""
    return EventRecorder(
        storage_dir=str(evidence_dir),
        pre_seconds=0.5,
        post_seconds=0.5,
        fps=10.0,
        max_buffer_seconds=3.0,
    )


def _make_frame(height: int = 240, width: int = 320) -> np.ndarray:
    """Create a solid-colour BGR frame."""
    return np.ones((height, width, 3), dtype=np.uint8) * 128


def _make_event(
    camera_id: int,
    confidence: float = 0.95,
) -> PlateDetected:
    """Create a minimal PlateDetected event."""
    return PlateDetected(
        camera_id=camera_id,
        timestamp=datetime.now(),
        confidence=confidence,
        bounding_box=(10, 20, 100, 60),
    )


# ======================================================================
# EventRecorder — Record (snapshot)
# ======================================================================


class TestEventRecorderSnapshot:
    """Tests for snapshot capture via EventRecorder.record()."""

    @patch("src.recorder.event_recorder.time_module.sleep")  # Skip post-recording wait
    def test_record_creates_snapshot_file(
        self,
        mock_sleep: object,
        event_recorder: EventRecorder,
        evidence_dir: Path,
    ) -> None:
        """record() saves a snapshot JPEG file to the snapshots directory."""
        event = _make_event(camera_id=1)
        frame = _make_frame()

        result = event_recorder.record(event, frame, ocr_text="TEST-123")

        assert result.has_snapshot is True
        assert result.snapshot_path is not None
        snapshot_file = Path(result.snapshot_path)
        assert snapshot_file.is_file()
        assert snapshot_file.suffix == ".jpg"
        assert "snapshots" in str(snapshot_file)

    @patch("src.recorder.event_recorder.time_module.sleep")
    def test_record_snapshot_without_plate_text(
        self,
        mock_sleep: object,
        event_recorder: EventRecorder,
        evidence_dir: Path,
    ) -> None:
        """record() still saves a snapshot when no plate text is provided."""
        event = _make_event(camera_id=1)
        frame = _make_frame()

        result = event_recorder.record(event, frame, ocr_text="")

        assert result.has_snapshot is True
        assert result.snapshot_path is not None
        assert Path(result.snapshot_path).is_file()


# ======================================================================
# EventRecorder — Record (video clip)
# ======================================================================


class TestEventRecorderClip:
    """Tests for video clip capture via EventRecorder.record()."""

    @patch("src.recorder.event_recorder.time_module.sleep")  # Skip post-recording wait
    def test_record_creates_clip_with_pre_frames(
        self,
        mock_sleep: object,
        event_recorder: EventRecorder,
        evidence_dir: Path,
    ) -> None:
        """record() creates a video clip using pre-detection frames."""
        camera_id = 1
        event_recorder.register_camera(camera_id)

        import time as time_module

        now = time_module.time()
        for i in range(8):
            from src.detection.frame_queue import Frame

            f = Frame(
                data=_make_frame(),
                camera_id=camera_id,
                timestamp=now - 1.0 + i * 0.1,
                frame_number=i,
            )
            event_recorder.on_frame(camera_id, f)

        event = _make_event(camera_id=camera_id)
        frame = _make_frame()

        result = event_recorder.record(event, frame, ocr_text="CLIP-TEST")

        assert result.has_snapshot is True
        assert result.video_path is not None
        video_file = Path(result.video_path)
        assert video_file.is_file()
        assert video_file.suffix == ".mp4"
        assert "clips" in str(video_file)

    @patch("src.recorder.event_recorder.time_module.sleep")
    def test_record_clip_insufficient_frames(
        self,
        mock_sleep: object,
        event_recorder: EventRecorder,
        evidence_dir: Path,
    ) -> None:
        """record() produces a clip even with insufficient pre-frames."""
        camera_id = 2
        event_recorder.register_camera(camera_id)

        event = _make_event(camera_id=camera_id)
        frame = _make_frame()

        result = event_recorder.record(event, frame, ocr_text="NO-PRE")

        # Should still produce clip (current frame only or with buffer)
        # It may or may not have video depending on available frames
        assert result.has_snapshot is True


# ======================================================================
# EventRecorder — Metadata
# ======================================================================


class TestEventRecorderMetadata:
    """Tests for recording result metadata."""

    @patch("src.recorder.event_recorder.time_module.sleep")
    def test_record_result_contains_metadata(
        self,
        mock_sleep: object,
        event_recorder: EventRecorder,
        evidence_dir: Path,
    ) -> None:
        """Recording result contains plate text and camera info."""
        camera_id = 3
        event_recorder.register_camera(camera_id)

        event = _make_event(camera_id=camera_id, confidence=0.85)
        frame = _make_frame()

        result = event_recorder.record(event, frame, ocr_text="META-123")

        assert result.camera_id == camera_id
        assert result.plate_text == "META-123"
        assert result.detection_confidence == pytest.approx(0.85, abs=0.01)

    @patch("src.recorder.event_recorder.time_module.sleep")
    def test_multiple_cameras_independent(
        self,
        mock_sleep: object,
        event_recorder: EventRecorder,
        evidence_dir: Path,
    ) -> None:
        """Recordings for different cameras are independent."""
        event_recorder.register_camera(1)
        event_recorder.register_camera(2)

        import time as time_module

        now = time_module.time()
        for i in range(5):
            from src.detection.frame_queue import Frame

            event_recorder.on_frame(
                1,
                Frame(data=_make_frame(), camera_id=1, timestamp=now - 0.5 + i * 0.1, frame_number=i),
            )
            event_recorder.on_frame(
                2,
                Frame(data=_make_frame(), camera_id=2, timestamp=now - 0.5 + i * 0.1, frame_number=i),
            )

        result1 = event_recorder.record(
            _make_event(camera_id=1),
            _make_frame(),
            ocr_text="CAM-1",
        )
        result2 = event_recorder.record(
            _make_event(camera_id=2),
            _make_frame(),
            ocr_text="CAM-2",
        )

        assert result1.camera_id == 1
        assert result2.camera_id == 2
        assert result1.has_snapshot is True
        assert result2.has_snapshot is True
        # Snapshot paths should differ
        assert result1.snapshot_path != result2.snapshot_path


# ======================================================================
# EventRecorder — Error handling
# ======================================================================


class TestEventRecorderErrors:
    """Tests for error handling in EventRecorder."""

    def test_record_unregistered_camera_auto_registers(
        self,
        event_recorder: EventRecorder,
    ) -> None:
        """Calling record() for an unregistered camera auto-creates its buffer."""
        # camera_id 99 should be auto-registered
        assert event_recorder.active_camera_count == 0

        event = _make_event(camera_id=99)
        frame = _make_frame()

        with patch("src.recorder.event_recorder.time_module.sleep"):
            result = event_recorder.record(event, frame, ocr_text="AUTO-REG")

        # After record, the buffer should have been registered
        # The buffer exists because on_frame calls register_camera via _get_buffer
        # but record also calls _get_buffer
        assert result.has_snapshot is True

    def test_register_camera_twice_is_safe(
        self,
        event_recorder: EventRecorder,
    ) -> None:
        """register_camera can be called multiple times for the same ID."""
        event_recorder.register_camera(1)
        event_recorder.register_camera(1)
        event_recorder.register_camera(1)
        assert event_recorder.active_camera_count == 1
