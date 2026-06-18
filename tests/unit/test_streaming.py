"""Unit tests for the Camera Streaming components.

Tests cover:
- ``FrameQueue`` — thread safety, drop-oldest, statistics
- ``FpsMonitor`` — rolling window, edge cases
- ``FrameCapture`` — lifecycle with mocked OpenCV
- ``CameraHealthMonitor`` — health checks, reconnect logic
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest

from src.detection.camera_health import CameraHealthMonitor
from src.detection.fps_monitor import FpsMonitor
from src.detection.frame_capture import FrameCapture
from src.detection.frame_queue import Frame, FrameQueue
from src.domain.value_objects.camera_status import CameraStatus
from src.domain.value_objects.camera_type import CameraType

# ======================================================================
# Helpers
# ======================================================================


def _make_frame(camera_id: int = 1, frame_number: int = 0) -> Frame:
    """Create a minimal Frame with a random 64x48 BGR image."""
    return Frame(
        data=np.zeros((48, 64, 3), dtype=np.uint8),
        camera_id=camera_id,
        timestamp=time.time(),
        frame_number=frame_number,
    )


# ======================================================================
# FrameQueue
# ======================================================================


class TestFrameQueue:
    """Tests for the bounded thread-safe frame queue."""

    def test_create_default(self) -> None:
        """Default queue has maxsize=60 and starts empty."""
        q = FrameQueue()
        assert q.maxsize == 60
        assert q.qsize == 0
        assert q.empty
        assert not q.full

    def test_create_custom_maxsize(self) -> None:
        """Custom maxsize is reflected in properties."""
        q = FrameQueue(maxsize=10, camera_id=5)
        assert q.maxsize == 10
        assert q._camera_id == 5

    def test_put_and_get_single_frame(self) -> None:
        """A put frame can be retrieved via get."""
        q = FrameQueue(maxsize=10)
        frame = _make_frame()

        result = q.put(frame)
        assert result is True  # not dropped
        assert q.qsize == 1
        assert not q.empty

        retrieved = q.get()
        assert retrieved is not None
        assert retrieved.frame_number == frame.frame_number
        assert retrieved.camera_id == frame.camera_id
        assert q.qsize == 0

    def test_get_nowait_empty(self) -> None:
        """get_nowait returns None for empty queue."""
        q = FrameQueue()
        assert q.get_nowait() is None

    def test_get_with_timeout(self) -> None:
        """get with timeout returns None if no frame arrives."""
        q = FrameQueue()
        start = time.monotonic()
        result = q.get(timeout=0.06)
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed >= 0.05  # Should have waited (allow scheduler granularity)

    def test_drain_returns_all_frames(self) -> None:
        """drain empties the queue and returns all frames."""
        q = FrameQueue(maxsize=10)
        frames = [_make_frame(frame_number=i) for i in range(5)]
        for f in frames:
            q.put(f)

        assert q.qsize == 5
        drained = q.drain()
        assert len(drained) == 5
        assert q.qsize == 0
        assert all(f.frame_number == i for i, f in enumerate(drained))

    def test_clear_discards_frames(self) -> None:
        """clear removes all frames without returning them."""
        q = FrameQueue(maxsize=10)
        for i in range(3):
            q.put(_make_frame(frame_number=i))
        assert q.qsize == 3
        q.clear()
        assert q.qsize == 0
        assert q.get_nowait() is None

    def test_full_queue_drops_oldest(self) -> None:
        """When full, the oldest frame is dropped on put."""
        q = FrameQueue(maxsize=3)
        frames = [_make_frame(frame_number=i) for i in range(5)]
        for i, f in enumerate(frames):
            dropped = not q.put(f)
            if i < 3:
                assert not dropped, f"Frame {i} should not have been dropped"
            else:
                assert dropped, f"Frame {i} should have triggered a drop"

        # Only the last 3 frames should remain
        assert q.qsize == 3
        remaining = q.drain()
        assert [f.frame_number for f in remaining] == [2, 3, 4]

    def test_drop_ratio(self) -> None:
        """drop_ratio reflects the fraction of dropped frames."""
        q = FrameQueue(maxsize=2)
        for _ in range(10):
            q.put(_make_frame())

        assert q.total_enqueued == 10
        assert q.total_dropped == 8
        assert q.drop_ratio == 0.8

    def test_peak_size_tracking(self) -> None:
        """peak_size tracks the high-water mark."""
        q = FrameQueue(maxsize=5)
        for _ in range(3):
            q.put(_make_frame())
        assert q.peak_size == 3
        q.get()  # remove one
        assert q.peak_size == 3  # Should not decrease

    def test_stats_snapshot(self) -> None:
        """stats() returns a consistent snapshot dict."""
        q = FrameQueue(maxsize=10, camera_id=7)
        q.put(_make_frame())
        q.put(_make_frame())
        q.get()
        stats = q.stats()
        assert stats["size"] == 1
        assert stats["maxsize"] == 10
        assert stats["total_enqueued"] == 2
        assert stats["total_dropped"] == 0
        assert stats["peak_size"] == 2
        assert not stats["empty"]

    # ------------------------------------------------------------------
    # Thread-safety
    # ------------------------------------------------------------------

    def test_concurrent_put_and_get(self) -> None:
        """Multiple threads can put and get without error."""
        q = FrameQueue(maxsize=100)
        errors: list[Exception] = []
        barrier = threading.Barrier(3, timeout=10)

        def producer(n: int) -> None:
            try:
                barrier.wait()
                for _ in range(n):
                    q.put(_make_frame())
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def consumer(n: int) -> None:
            try:
                barrier.wait()
                received = 0
                while received < n:
                    frame = q.get(timeout=2.0)
                    if frame is not None:
                        received += 1
            except Exception as e:
                errors.append(e)

        n = 50
        threads = [
            threading.Thread(target=producer, args=(n,), daemon=True),
            threading.Thread(target=producer, args=(n,), daemon=True),
            threading.Thread(target=consumer, args=(n * 2,), daemon=True),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent access errors: {errors}"
        # After two producers (100 total) and one consumer (100 fetched)
        # the queue should be empty
        assert q.qsize == 0

    # ------------------------------------------------------------------
    # Frame dataclass
    # ------------------------------------------------------------------

    def test_frame_age_seconds(self) -> None:
        """age_seconds increases over time."""
        frame = Frame(
            data=np.zeros((10, 10, 3), dtype=np.uint8),
            camera_id=1,
            timestamp=time.time() - 0.5,
            frame_number=1,
        )
        assert frame.age_seconds > 0.4
        assert frame.age_seconds < 10.0  # sanity

    def test_frame_repr(self) -> None:
        """Frame has a meaningful repr."""
        frame = _make_frame(camera_id=2, frame_number=42)
        r = repr(frame)
        assert "Frame" in r
        assert "camera_id=2" in r
        assert "frame_number=42" in r


# ======================================================================
# FpsMonitor
# ======================================================================


class TestFpsMonitor:
    """Tests for the rolling-window FPS monitor."""

    def test_create_default(self) -> None:
        """Default FPS monitor has a 5-second window and 0 FPS."""
        m = FpsMonitor()
        assert m.window_seconds == 5.0
        assert m.fps == 0.0
        assert m.total_frames == 0

    def test_negative_window_raises(self) -> None:
        """Negative or zero window is rejected."""
        with pytest.raises(ValueError, match="positive"):
            FpsMonitor(window_seconds=-1)

        with pytest.raises(ValueError, match="positive"):
            FpsMonitor(window_seconds=0)

    def test_single_frame_returns_zero_fps(self) -> None:
        """Fewer than 2 frames yields 0.0 FPS."""
        m = FpsMonitor()
        m.tick()
        assert m.fps == 0.0

    def test_two_frames_instantaneous(self) -> None:
        """With exactly 2 frames, FPS = 1/interval."""
        m = FpsMonitor(window_seconds=10)
        m.tick()
        time.sleep(0.1)
        m.tick()
        fps = m.fps
        assert fps > 8.0  # 1/0.1 = 10 FPS, allow for timing jitter
        assert fps < 20.0

    def test_fps_stable_with_constant_rate(self) -> None:
        """At a steady rate, FPS should approximate the expected value."""
        m = FpsMonitor(window_seconds=2.0)
        interval = 0.05  # 20 FPS
        for _ in range(50):
            time.sleep(interval)
            m.tick()

        fps = m.fps
        assert 15.0 < fps < 25.0, f"Expected ~20 FPS, got {fps}"

    def test_total_frames_count(self) -> None:
        """total_frames reflects all ticks, even pruned ones."""
        m = FpsMonitor(window_seconds=0.5)
        for _ in range(10):
            m.tick()
            time.sleep(0.01)
        assert m.total_frames == 10

    def test_reset_clears_state(self) -> None:
        """reset() zeroes all counters and timestamps."""
        m = FpsMonitor()
        m.tick()
        m.tick()
        assert m.total_frames == 2
        m.reset()
        assert m.total_frames == 0
        assert m.fps == 0.0

    def test_stats_snapshot(self) -> None:
        """stats() returns a dict with rounded values."""
        m = FpsMonitor()
        m.tick()
        stats = m.stats()
        assert "fps" in stats
        assert "min_fps" in stats
        assert "max_fps" in stats
        assert stats["total_frames"] == 1
        assert stats["window_seconds"] == 5.0

    def test_min_and_max_fps(self) -> None:
        """min_fps and max_fps capture extremes."""
        m = FpsMonitor(window_seconds=5.0)
        # Simulate varied inter-frame intervals
        for delay in [0.01, 0.1, 0.01, 0.2, 0.01]:
            time.sleep(delay)
            m.tick()

        assert m.min_fps > 0
        assert m.max_fps > m.min_fps


# ======================================================================
# FrameCapture  (with mocked OpenCV)
# ======================================================================


class TestFrameCapture:
    """Tests for the RTSP/USB frame capture lifecycle.

    We mock ``cv2.VideoCapture`` to avoid requiring real cameras.
    """

    # ------------------------------------------------------------------
    # Construction & properties
    # ------------------------------------------------------------------

    def test_create_rtsp(self) -> None:
        """Creating an RTSP FrameCapture sets correct properties."""
        cap = FrameCapture(
            camera_id=1,
            source="rtsp://192.168.1.100:554/stream",
            camera_type=CameraType.RTSP,
        )
        assert cap.camera_id == 1
        assert cap.source == "rtsp://192.168.1.100:554/stream"
        assert cap.camera_type == CameraType.RTSP
        assert cap.status == CameraStatus.OFFLINE
        assert not cap.is_running
        assert cap.fps == 0.0
        assert cap.total_frames == 0

    def test_create_usb(self) -> None:
        """Creating a USB FrameCapture sets correct properties."""
        cap = FrameCapture(
            camera_id=2,
            source="0",
            camera_type=CameraType.USB,
        )
        assert cap.camera_id == 2
        assert cap.source == "0"
        assert cap.camera_type == CameraType.USB

    def test_create_with_preferred_resolution(self) -> None:
        """Preferred resolution is stored."""
        cap = FrameCapture(
            camera_id=1,
            source="rtsp://example.com/stream",
            camera_type=CameraType.RTSP,
            preferred_width=1280,
            preferred_height=720,
        )
        assert cap._preferred_width == 1280
        assert cap._preferred_height == 720

    # ------------------------------------------------------------------
    # Lifecycle start / stop
    # ------------------------------------------------------------------

    @patch("cv2.VideoCapture")
    def test_start_and_stop(self, mock_vc: MagicMock) -> None:
        """Starting and stopping flips the running flag."""
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = True
        mock_instance.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        mock_vc.return_value = mock_instance

        cap = FrameCapture(
            camera_id=1,
            source="rtsp://localhost/test",
            camera_type=CameraType.RTSP,
        )
        cap.start()
        assert cap.is_running
        assert cap.status == CameraStatus.RECONNECTING  # initial

        # Give the thread a moment to connect
        time.sleep(0.2)

        cap.stop(timeout=3.0)
        assert not cap.is_running, "Capture thread should have stopped"
        # The capture loop may process one final frame after stop()
        # sets the event, so status might be ONLINE or OFFLINE.
        assert cap.status in (
            CameraStatus.OFFLINE,
            CameraStatus.ONLINE,
        ), f"Unexpected status after stop: {cap.status}"

    @patch("cv2.VideoCapture")
    def test_double_start_raises(self, mock_vc: MagicMock) -> None:
        """Starting an already-running capture raises RuntimeError."""
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = True
        mock_instance.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        mock_vc.return_value = mock_instance

        cap = FrameCapture(
            camera_id=1,
            source="0",
            camera_type=CameraType.USB,
        )
        cap.start()
        time.sleep(0.1)

        with pytest.raises(RuntimeError, match="already running"):
            cap.start()

        cap.stop()

    @patch("cv2.VideoCapture")
    def test_restart(self, mock_vc: MagicMock) -> None:
        """Restart fully stops and starts again."""
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = True
        mock_instance.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        mock_vc.return_value = mock_instance

        cap = FrameCapture(
            camera_id=1,
            source="0",
            camera_type=CameraType.USB,
        )
        cap.start()
        time.sleep(0.2)
        cap.restart()
        time.sleep(0.2)
        assert cap.is_running
        cap.stop()

    # ------------------------------------------------------------------
    # Stats snapshot
    # ------------------------------------------------------------------

    @patch("cv2.VideoCapture")
    def test_stats_snapshot(self, mock_vc: MagicMock) -> None:
        """stats() returns consistent values."""
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = True
        mock_instance.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        mock_vc.return_value = mock_instance

        cap = FrameCapture(
            camera_id=42,
            source="rtsp://localhost/test",
            camera_type=CameraType.RTSP,
        )
        # Don't start; just verify structure
        stats = cap.stats()
        assert stats.camera_id == 42
        assert stats.state == "init"
        assert stats.status == "offline"


# ======================================================================
# CameraHealthMonitor  (with mocked FrameCapture)
# ======================================================================


class _MockCapture:
    """Minimal mock that behaves like FrameCapture for health tests."""

    def __init__(
        self,
        camera_id: int = 1,
        is_running: bool = True,
        last_frame_age: float = 0.5,
        status: CameraStatus = CameraStatus.ONLINE,
        fps: float = 15.0,
        uptime: float = 60.0,
        total_frames: int = 900,
        reconnect_attempts: int = 0,
    ) -> None:
        self.camera_id = camera_id
        self._is_running = is_running
        self._last_frame_age = last_frame_age
        self._status = status
        self._fps = fps
        self._uptime = uptime
        self._total_frames = total_frames
        self._reconnect_attempts = reconnect_attempts
        self.restart_called = False
        self.stop_called = False
        self.start_called = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def last_frame_age(self) -> float:
        return self._last_frame_age

    @property
    def status(self) -> CameraStatus:
        return self._status

    @status.setter
    def status(self, value: CameraStatus) -> None:
        self._status = value

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def uptime_seconds(self) -> float:
        return self._uptime

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def reconnect_attempts(self) -> int:
        return self._reconnect_attempts

    def start(self) -> None:
        self.start_called = True

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_called = True

    def restart(self) -> None:
        self.restart_called = True


class TestCameraHealthMonitor:
    """Tests for the watchdog health monitor."""

    def test_create_default(self) -> None:
        """Creating a health monitor sets sensible defaults."""
        capture = _MockCapture()
        monitor = CameraHealthMonitor(capture=capture)
        assert monitor._max_idle_seconds == 10.0
        assert monitor._check_interval == 2.0
        assert monitor._max_reconnects == 0  # unlimited
        assert not monitor.is_running

    def test_health_check_healthy_returns_true(self) -> None:
        """A capture with recent frames reports healthy."""
        capture = _MockCapture(last_frame_age=0.5)
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
        )
        assert monitor.health_check() is True

    def test_health_check_dead_returns_false(self) -> None:
        """A capture with stale frames reports unhealthy."""
        capture = _MockCapture(last_frame_age=15.0)  # > max_idle=10
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
        )
        result = monitor.health_check()
        assert result is False
        assert monitor.consecutive_checks_failed >= 1

    def test_health_check_not_running_returns_false(self) -> None:
        """A capture that is not running reports unhealthy."""
        capture = _MockCapture(is_running=False)
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
        )
        assert monitor.health_check() is False

    def test_reconnect_triggered_after_consecutive_failures(self) -> None:
        """Two consecutive failures trigger a restart."""
        capture = _MockCapture(
            last_frame_age=15.0,  # stale
            is_running=True,
        )
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
            check_interval=0.05,
            reconnect_delay=0.01,
            max_reconnects=3,
        )

        # Two checks should trigger reconnect
        monitor.health_check()  # failure 1 — no reconnect yet
        assert not capture.restart_called
        monitor.health_check()  # failure 2 — triggers reconnect
        assert capture.restart_called

    def test_max_reconnects_stops_retrying(self) -> None:
        """When max_reconnects is reached, status becomes ERROR."""
        capture = _MockCapture(
            last_frame_age=15.0,
            is_running=True,
            status=CameraStatus.RECONNECTING,
        )
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
            check_interval=0.05,
            reconnect_delay=0.01,
            max_reconnects=2,
        )

        # Exhaust reconnects
        monitor.health_check()  # fail 1
        monitor.health_check()  # fail 2 -> reconnect 1
        monitor.health_check()  # fail 3 -> reconnect 2
        monitor.health_check()  # fail 4 -> max reached -> ERROR

        assert capture.restart_called
        # The status should be ERROR in the monitor's perspective
        assert monitor._last_known_status == CameraStatus.ERROR

    def test_healthy_after_failure_resets_counter(self) -> None:
        """A successful health check resets consecutive failures."""
        capture = _MockCapture(last_frame_age=15.0)
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
            check_interval=0.05,
            reconnect_delay=0.01,
        )

        monitor.health_check()  # failure
        assert monitor.consecutive_checks_failed >= 1

        # Now make capture healthy again
        capture._last_frame_age = 0.5
        monitor.health_check()
        assert monitor.consecutive_checks_failed == 0

    def test_snapshot(self) -> None:
        """snapshot returns a consistent HealthSnapshot."""
        capture = _MockCapture(
            camera_id=7,
            last_frame_age=1.0,
            fps=24.0,
            uptime=120.0,
            total_frames=2880,
        )
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
        )
        snap = monitor.snapshot
        assert snap.camera_id == 7
        assert snap.fps == 24.0
        assert snap.max_allowed_idle == 10.0
        assert snap.status == CameraStatus.ONLINE

    def test_status_change_callback(self) -> None:
        """Status changes fire the callback."""
        captured_statuses: list[CameraStatus] = []

        def on_change(status: CameraStatus) -> None:
            captured_statuses.append(status)

        capture = _MockCapture(last_frame_age=0.5)
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
            on_status_change=on_change,
        )

        # Should fire ONLINE since it's healthy
        monitor.health_check()
        assert CameraStatus.ONLINE in captured_statuses
