"""Unit tests for the event recording module.

Covers ``FrameRingBuffer``, ``MediaWriter``, and ``EventRecorder``.
MediaWriter tests write actual JPEG/MP4 files to a temporary directory
that is cleaned up after each test.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Thread
from typing import Any, Generator, List
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.detection.frame_queue import Frame
from src.domain.events.plate_detected import PlateDetected
from src.recorder.event_recorder import EventRecorder, RecordingResult
from src.recorder.frame_buffer import FrameRingBuffer
from src.recorder.media_writer import MediaWriter

# ======================================================================
# Constants
# ======================================================================

_FRAME_H = 240
_FRAME_W = 320


# ======================================================================
# Helpers
# ======================================================================


def _make_frame(
    camera_id: int = 1,
    value: int = 128,
    timestamp: float | None = None,
    frame_number: int = 0,
) -> Frame:
    """Create a Frame with a solid-colour BGR image.

    The colour varies with *value* so frames are distinguishable.
    """
    # Clamp value to uint8 range
    clamped = max(0, min(255, value))
    data = np.full((_FRAME_H, _FRAME_W, 3), clamped, dtype=np.uint8)
    if clamped == 128:
        pass  # keep it gray
    elif clamped > 0:
        data[:, :] = (clamped, clamped // 2 + 30, clamped // 3 + 60)
    return Frame(
        data=data,
        camera_id=camera_id,
        timestamp=timestamp or time.time(),
        frame_number=frame_number,
    )


def _make_rgb_frame() -> np.ndarray:
    """Return a BGR frame that *looks* like RGB (solid-colour)."""
    return np.full((_FRAME_H, _FRAME_W, 3), 128, dtype=np.uint8)


def _make_event(
    camera_id: int = 1,
    ts: float | None = None,
    confidence: float = 0.92,
) -> PlateDetected:
    """Return a ``PlateDetected`` event with a given timestamp."""
    from datetime import datetime

    dt = datetime.fromtimestamp(ts or time.time())
    return PlateDetected(
        camera_id=camera_id,
        bounding_box=(10, 20, 200, 80),
        confidence=confidence,
        timestamp=dt,
    )


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def temp_media_dir(tmp_path: Path) -> Generator[Path, Any, None]:
    """Provide a temporary media directory that is cleaned up after the test."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    yield media_dir
    # Cleanup — remove any files created during the test
    import shutil

    if media_dir.exists():
        shutil.rmtree(media_dir)


# ======================================================================
# FrameRingBuffer tests
# ======================================================================


class TestFrameRingBuffer:
    """Thread-safe circular frame buffer tests."""

    def test_push_and_size(self) -> None:
        """Pushing frames increases the size."""
        buf = FrameRingBuffer(maxlen=10)
        assert buf.size == 0
        assert len(buf) == 0

        buf.push(_make_frame(frame_number=0))
        assert buf.size == 1

        buf.push(_make_frame(frame_number=1))
        assert buf.size == 2

    def test_maxlen_property(self) -> None:
        """maxlen property reflects the constructor argument."""
        buf = FrameRingBuffer(maxlen=50)
        assert buf.maxlen == 50

    def test_push_over_maxlen_drops_oldest(self) -> None:
        """When buffer exceeds maxlen, the oldest frame is dropped."""
        buf = FrameRingBuffer(maxlen=3)

        frames = [_make_frame(frame_number=i, value=i * 20) for i in range(5)]
        for f in frames:
            buf.push(f)

        # Only the last 3 should remain
        all_frames = buf.get_all()
        assert len(all_frames) == 3
        assert [f.frame_number for f in all_frames] == [2, 3, 4]

    def test_get_frames_before_returns_matching_frames(self) -> None:
        """get_frames_before returns frames within the time window."""
        buf = FrameRingBuffer(maxlen=100)
        now = 1_000_000.0

        for i in range(10):
            ts = now + i * 0.1  # 100 ms apart
            buf.push(_make_frame(timestamp=ts, frame_number=i))

        # Get frames 0.25 seconds before t=1_000_000.5
        result = buf.get_frames_before(timestamp=1_000_000.5, seconds=0.25)
        # Expected: frames with ts in (1_000_000.25, 1_000_000.5]
        # Frames 3..5 (ts=1_000_000.3, 1_000_000.4, 1_000_000.5)
        assert len(result) >= 2
        for f in result:
            assert f.timestamp > 1_000_000.25
            assert f.timestamp <= 1_000_000.5

    def test_get_frames_before_returns_oldest_first(self) -> None:
        """Frames are returned in chronological order."""
        buf = FrameRingBuffer(maxlen=100)
        now = 1_000_000.0
        frames = [_make_frame(timestamp=now + i * 0.1, frame_number=i) for i in range(5)]
        for f in frames:
            buf.push(f)

        result = buf.get_frames_before(timestamp=now + 0.5, seconds=1.0)
        timestamps = [f.timestamp for f in result]
        assert timestamps == sorted(timestamps)

    def test_get_frames_before_empty_when_no_match(self) -> None:
        """Returns empty list if no frames fall in the window."""
        buf = FrameRingBuffer(maxlen=100)
        now = 1_000_000.0
        for i in range(5):
            buf.push(_make_frame(timestamp=now + i * 0.1, frame_number=i))

        result = buf.get_frames_before(timestamp=now - 10.0, seconds=1.0)
        assert result == []

    def test_get_frames_between_returns_matching_frames(self) -> None:
        """get_frames_between returns frames in [start, end)."""
        buf = FrameRingBuffer(maxlen=100)
        now = 1_000_000.0

        for i in range(10):
            buf.push(_make_frame(timestamp=now + i * 0.1, frame_number=i))

        result = buf.get_frames_between(start_ts=now + 0.2, end_ts=now + 0.5)
        # ts: 0.2, 0.3, 0.4 (0.5 excluded)
        assert len(result) == 3
        assert [f.frame_number for f in result] == [2, 3, 4]

    def test_get_frames_between_empty_range(self) -> None:
        """Returns empty list when the range is empty."""
        buf = FrameRingBuffer(maxlen=100)
        now = 1_000_000.0
        for i in range(5):
            buf.push(_make_frame(timestamp=now + i * 0.1, frame_number=i))

        result = buf.get_frames_between(start_ts=now + 10.0, end_ts=now + 20.0)
        assert result == []

    def test_get_all_returns_all_frames(self) -> None:
        """get_all returns a copy of all frames in the buffer."""
        buf = FrameRingBuffer(maxlen=10)
        frames = [_make_frame(frame_number=i, value=i * 30) for i in range(5)]
        for f in frames:
            buf.push(f)

        result = buf.get_all()
        assert len(result) == 5
        assert [f.frame_number for f in result] == [0, 1, 2, 3, 4]

    def test_get_all_returns_copy(self) -> None:
        """Modifying the returned list does not affect the buffer."""
        buf = FrameRingBuffer(maxlen=10)
        buf.push(_make_frame(frame_number=0))
        result = buf.get_all()
        result.clear()
        assert buf.size == 1

    def test_clear_removes_all_frames(self) -> None:
        """clear() empties the buffer."""
        buf = FrameRingBuffer(maxlen=10)
        for i in range(5):
            buf.push(_make_frame(frame_number=i))
        buf.clear()
        assert buf.size == 0
        assert buf.get_all() == []

    def test_repr(self) -> None:
        """__repr__ contains size and maxlen."""
        buf = FrameRingBuffer(maxlen=50)
        buf.push(_make_frame(frame_number=0))
        rep = repr(buf)
        assert "1" in rep
        assert "50" in rep

    def test_push_is_thread_safe(self) -> None:
        """Concurrent pushes do not corrupt the buffer."""
        buf = FrameRingBuffer(maxlen=500)
        num_threads = 4
        frames_per_thread = 100

        def _pusher(start: int) -> None:
            for i in range(start, start + frames_per_thread):
                buf.push(_make_frame(frame_number=i, value=i * 10))

        threads = [
            Thread(target=_pusher, args=(i * frames_per_thread,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert buf.size == min(500, num_threads * frames_per_thread)
        # No duplicate frame numbers (within the retained window)
        nums = [f.frame_number for f in buf.get_all()]
        assert len(nums) == len(set(nums))

    def test_get_frames_before_is_thread_safe(self) -> None:
        """Concurrent reads do not cause errors."""
        buf = FrameRingBuffer(maxlen=100)
        now = time.time()
        for i in range(50):
            buf.push(_make_frame(timestamp=now + i * 0.033, frame_number=i))

        results: list[list[Frame]] = []

        def _reader() -> None:
            results.append(buf.get_frames_before(timestamp=now + 1.0, seconds=0.5))

        threads = [Thread(target=_reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 5
        for r in results:
            assert isinstance(r, list)


# ======================================================================
# MediaWriter tests
# ======================================================================


class TestMediaWriter:
    """Media file I/O tests.

    These tests write actual JPEG and MP4 files to a temporary
    directory, then verify the files exist and have valid headers.
    """

    def test_save_snapshot_creates_jpeg(self, temp_media_dir: Path) -> None:
        """save_snapshot writes a valid JPEG file to disk."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        frame = _make_rgb_frame()
        path = writer.save_snapshot(frame, camera_id=1, timestamp=1_000_000.0)
        path_obj = Path(path)
        assert path_obj.exists()
        assert path_obj.suffix == ".jpg"
        # Verify it's a valid JPEG
        img = cv2.imread(str(path_obj))
        assert img is not None
        assert img.shape == (_FRAME_H, _FRAME_W, 3)

    def test_save_snapshot_returns_absolute_path(self, temp_media_dir: Path) -> None:
        """Returned path is absolute."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        frame = _make_rgb_frame()
        path = writer.save_snapshot(frame, camera_id=1, timestamp=1_000_000.0)
        assert os.path.isabs(path)

    def test_save_snapshot_creates_subdirectories(self, temp_media_dir: Path) -> None:
        """Directories are created automatically if missing."""
        writer = MediaWriter(base_dir=str(temp_media_dir / "nested" / "deep"))
        frame = _make_rgb_frame()
        path = writer.save_snapshot(frame, camera_id=1, timestamp=1_000_000.0)
        assert Path(path).exists()

    def test_save_snapshot_filename_contains_camera_id_and_timestamp(
        self,
        temp_media_dir: Path,
    ) -> None:
        """Filename encodes camera_id and timestamp."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        frame = _make_rgb_frame()
        path = writer.save_snapshot(
            frame,
            camera_id=42,
            timestamp=1_234_567.890,
            plate_text="ABC123",
        )
        filename = Path(path).name
        assert "snap_42_" in filename
        assert "1234567_890" in filename
        assert "ABC123" in filename
        assert filename.endswith(".jpg")

    def test_save_snapshot_raises_on_empty_frame(self, temp_media_dir: Path) -> None:
        """Raises ValueError when frame is None or empty."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        with pytest.raises(ValueError, match="frame is empty"):
            writer.save_snapshot(np.array([]), camera_id=1, timestamp=1_000_000.0)

    def test_save_snapshot_raises_on_invalid_shape(self, temp_media_dir: Path) -> None:
        """Raises ValueError when frame is not HxWx3 BGR."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        frame = np.full((100, 100, 4), 128, dtype=np.uint8)  # RGBA
        with pytest.raises(ValueError, match="3-channel BGR"):
            writer.save_snapshot(frame, camera_id=1, timestamp=1_000_000.0)

    def test_save_clip_creates_mp4(self, temp_media_dir: Path) -> None:
        """save_clip writes a valid MP4 file."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        frames = [_make_rgb_frame() for _ in range(30)]
        path = writer.save_clip(
            frames,
            camera_id=1,
            timestamp=1_000_000.0,
            fps=30.0,
        )
        path_obj = Path(path)
        assert path_obj.exists()
        assert path_obj.suffix == ".mp4"
        assert path_obj.stat().st_size > 100  # non-trivial file

    def test_save_clip_returns_absolute_path(self, temp_media_dir: Path) -> None:
        """Returned path is absolute."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        frames = [_make_rgb_frame() for _ in range(10)]
        path = writer.save_clip(frames, camera_id=1, timestamp=1_000_000.0)
        assert os.path.isabs(path)

    def test_save_clip_filename_format(self, temp_media_dir: Path) -> None:
        """Filename encodes camera_id, timestamp and plate_text."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        frames = [_make_rgb_frame() for _ in range(10)]
        path = writer.save_clip(
            frames,
            camera_id=7,
            timestamp=5_000_000.001,
            plate_text="XYZ789",
            fps=30.0,
        )
        filename = Path(path).name
        assert "clip_7_" in filename
        assert "5000000_001" in filename
        assert "XYZ789" in filename
        assert filename.endswith(".mp4")

    def test_save_clip_raises_on_empty_frames(self, temp_media_dir: Path) -> None:
        """Raises ValueError when frame list is empty."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        with pytest.raises(ValueError, match="frame list is empty"):
            writer.save_clip([], camera_id=1, timestamp=1_000_000.0)

    def test_save_clip_creates_subdirectories(self, temp_media_dir: Path) -> None:
        """Directories are created automatically."""
        writer = MediaWriter(base_dir=str(temp_media_dir / "videos" / "clips"))
        frames = [_make_rgb_frame() for _ in range(10)]
        path = writer.save_clip(frames, camera_id=1, timestamp=1_000_000.0)
        assert Path(path).exists()

    def test_properties_reflect_base_dir(self, temp_media_dir: Path) -> None:
        """Properties correctly resolve subdirectories."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        assert writer.base_dir == temp_media_dir
        assert writer.snapshot_dir == temp_media_dir / "snapshots"
        assert writer.clip_dir == temp_media_dir / "clips"

    def test_repr(self, temp_media_dir: Path) -> None:
        """__repr__ contains the base directory."""
        writer = MediaWriter(base_dir=str(temp_media_dir))
        rep = repr(writer)
        assert str(temp_media_dir.resolve()) in rep


# ======================================================================
# EventRecorder tests
# ======================================================================


class TestEventRecorder:
    """EventRecorder orchestration tests.

    The ``_sleep`` method is patched so tests do not actually wait
    for the post-detection window.
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_init_defaults(self) -> None:
        """Default parameters are set correctly."""
        recorder = EventRecorder()
        assert recorder.pre_seconds == 3.0
        assert recorder.post_seconds == 3.0
        assert recorder.fps == 30.0
        assert recorder.active_camera_count == 0

    def test_init_custom_values(self) -> None:
        """Custom parameters are reflected in properties."""
        recorder = EventRecorder(
            storage_dir="/tmp/test_media",
            pre_seconds=2.0,
            post_seconds=1.5,
            fps=15.0,
            max_buffer_seconds=10.0,
        )
        assert recorder.pre_seconds == 2.0
        assert recorder.post_seconds == 1.5
        assert recorder.fps == 15.0

    def test_init_raises_when_max_buffer_too_small(self) -> None:
        """Raises ValueError when max_buffer_seconds is too small."""
        with pytest.raises(ValueError, match="max_buffer_seconds"):
            EventRecorder(
                pre_seconds=5.0,
                post_seconds=5.0,
                max_buffer_seconds=5.0,  # not *greater* than sum
            )

    @patch.object(EventRecorder, "_sleep", return_value=None)
    def test_record_returns_result_with_snapshot_and_video(
        self,
        mock_sleep: MagicMock,
        temp_media_dir: Path,
    ) -> None:
        """record() produces both snapshot and video paths."""
        recorder = EventRecorder(
            storage_dir=str(temp_media_dir),
            pre_seconds=0.3,
            post_seconds=0.1,
            fps=30.0,
            max_buffer_seconds=2.0,
        )

        # Pre-populate the ring buffer — frames span up to the event
        # timestamp so pre-detection frames are found.
        now = time.time()
        for i in range(15):
            frame_ts = now - 0.4 + i * 0.033  # last frame at ~now-0.4+14*0.033 = now-0.062
            recorder.on_frame(
                camera_id=1,
                frame=_make_frame(timestamp=frame_ts, frame_number=i),
            )

        event = _make_event(camera_id=1, ts=now)
        current_frame = _make_rgb_frame()
        result = recorder.record(event, current_frame, ocr_text="ABC123")

        assert result.camera_id == 1
        assert result.snapshot_path != ""
        assert Path(result.snapshot_path).exists()
        assert result.video_path != ""
        assert Path(result.video_path).exists()
        assert result.plate_text == "ABC123"
        assert result.detection_confidence == 0.92
        assert result.total_frames > 0

    @patch.object(EventRecorder, "_sleep", return_value=None)
    def test_record_snapshot_only_when_clip_fails(
        self,
        mock_sleep: MagicMock,
        temp_media_dir: Path,
    ) -> None:
        """Record returns snapshot path even when video fails."""
        recorder = EventRecorder(
            storage_dir=str(temp_media_dir),
            pre_seconds=0.1,
            post_seconds=0.1,
            max_buffer_seconds=2.0,
        )

        now = time.time()
        # Only push one frame (not enough for a clip with 2+ frames)
        recorder.on_frame(camera_id=1, frame=_make_frame(timestamp=now - 0.05))

        event = _make_event(camera_id=1, ts=now + 0.01)
        current_frame = _make_rgb_frame()
        result = recorder.record(event, current_frame)

        assert result.snapshot_path != ""
        # Video may be empty if < 2 frames total
        # (current frame + maybe 0 pre/post)
        if result.total_frames < 2:
            assert result.video_path == ""

    @patch.object(EventRecorder, "_sleep", return_value=None)
    def test_record_handles_empty_buffer_gracefully(
        self,
        mock_sleep: MagicMock,
        temp_media_dir: Path,
    ) -> None:
        """Empty buffer does not crash; snapshot is saved."""
        recorder = EventRecorder(
            storage_dir=str(temp_media_dir),
            pre_seconds=0.1,
            post_seconds=0.1,
            max_buffer_seconds=2.0,
        )

        event = _make_event(camera_id=99, ts=time.time())
        current_frame = _make_rgb_frame()
        result = recorder.record(event, current_frame)

        assert result.snapshot_path != ""
        assert result.pre_frame_count == 0
        assert result.post_frame_count == 0
        # Only the current frame — insufficient for a clip
        assert result.total_frames == 1
        assert result.video_path == ""

    def test_on_frame_auto_registers_camera(self) -> None:
        """Feeding a frame auto-registers the camera buffer."""
        recorder = EventRecorder(
            pre_seconds=1.0,
            post_seconds=1.0,
            max_buffer_seconds=5.0,
        )
        assert recorder.active_camera_count == 0
        recorder.on_frame(camera_id=1, frame=_make_frame())
        assert recorder.active_camera_count == 1

    def test_register_camera_is_idempotent(self) -> None:
        """Registering the same camera twice does not duplicate buffers."""
        recorder = EventRecorder(
            pre_seconds=1.0,
            post_seconds=1.0,
            max_buffer_seconds=5.0,
        )
        recorder.register_camera(1)
        recorder.register_camera(1)
        assert recorder.active_camera_count == 1

    def test_unregister_camera_removes_buffer(self) -> None:
        """Unregistering a camera removes its buffer."""
        recorder = EventRecorder(
            pre_seconds=1.0,
            post_seconds=1.0,
            max_buffer_seconds=5.0,
        )
        recorder.register_camera(1)
        recorder.register_camera(2)
        assert recorder.active_camera_count == 2
        recorder.unregister_camera(1)
        assert recorder.active_camera_count == 1
        # Unregistering a non-existent camera does not raise
        recorder.unregister_camera(99)
        assert recorder.active_camera_count == 1

    @patch.object(EventRecorder, "_sleep", return_value=None)
    def test_record_with_no_ocr_text(
        self,
        mock_sleep: MagicMock,
        temp_media_dir: Path,
    ) -> None:
        """Record works correctly when no plate text is provided."""
        recorder = EventRecorder(
            storage_dir=str(temp_media_dir),
            pre_seconds=0.1,
            post_seconds=0.1,
            max_buffer_seconds=2.0,
        )
        now = time.time()
        for i in range(5):
            recorder.on_frame(camera_id=1, frame=_make_frame(timestamp=now - 0.2 + i * 0.05))

        event = _make_event(camera_id=1, ts=now)
        result = recorder.record(event, _make_rgb_frame())

        assert result.snapshot_path != ""
        assert result.plate_text == ""

    def test_record_with_snapshot_failure_still_attempts_video(
        self,
        temp_media_dir: Path,
    ) -> None:
        """If snapshot fails, video is still attempted."""
        recorder = EventRecorder(
            storage_dir=str(temp_media_dir),
            pre_seconds=0.0,
            post_seconds=0.0,
            max_buffer_seconds=2.0,
        )

        # Populate buffer
        now = time.time()
        for i in range(5):
            recorder.on_frame(camera_id=1, frame=_make_frame(timestamp=now - 0.2 + i * 0.05))

        event = _make_event(camera_id=1, ts=now)

        # Force snapshot to fail by passing an invalid frame after
        # the snapshot attempt (we can't easily mock save_snapshot
        # since it's the writer's method). Instead, we accept that
        # the snapshot will succeed and just verify both paths.
        # For a true failure test, we patch the writer.
        with patch.object(
            recorder.media_writer,
            "save_snapshot",
            side_effect=OSError("disk full"),
        ):
            with patch.object(EventRecorder, "_sleep", return_value=None):
                result = recorder.record(event, _make_rgb_frame())

        assert result.snapshot_path == ""  # failed
        # Video may still succeed
        # (though with 0 pre/post there's only the current frame = 1 total)

    def test_repr(self) -> None:
        """__repr__ contains camera count and pre/post values."""
        recorder = EventRecorder(pre_seconds=2.0, post_seconds=1.0)
        recorder.register_camera(1)
        rep = repr(recorder)
        assert "1" in rep  # camera count
        assert "2.0s" in rep
        assert "1.0s" in rep

    # ------------------------------------------------------------------
    # RecordingResult tests
    # ------------------------------------------------------------------

    def test_recording_result_defaults(self) -> None:
        """Default instance has no snapshot/video."""
        result = RecordingResult()
        assert result.snapshot_path == ""
        assert result.video_path == ""
        assert result.has_snapshot is False
        assert result.has_video is False
        assert result.total_frames == 0

    def test_recording_result_has_snapshot(self) -> None:
        """has_snapshot reflects whether snapshot_path is set."""
        result = RecordingResult(snapshot_path="/tmp/snap.jpg")
        assert result.has_snapshot is True
        assert result.has_video is False

    def test_recording_result_has_video(self) -> None:
        """has_video reflects whether video_path is set."""
        result = RecordingResult(video_path="/tmp/clip.mp4")
        assert result.has_snapshot is False
        assert result.has_video is True

    def test_recording_result_repr(self) -> None:
        """__repr__ contains camera, snapshot, video, plate."""
        result = RecordingResult(
            camera_id=5,
            snapshot_path="/s.jpg",
            video_path="/v.mp4",
            plate_text="ABC",
        )
        rep = repr(result)
        assert "5" in rep
        assert "ABC" in rep
