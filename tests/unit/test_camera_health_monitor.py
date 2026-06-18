"""Unit tests for the CameraHealthMonitor.

Uses mock ``FrameCapture`` objects to avoid OpenCV dependencies.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, PropertyMock

import pytest

from src.monitor.camera_health_monitor import (
    CameraHealthMonitor,
    CameraHealthSnapshot,
    HealthStatus,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_mock_capture(
    camera_id: int = 1,
    is_running: bool = True,
    last_frame_age: float = 1.0,
    fps: float = 30.0,
    reconnect_attempts: int = 0,
    uptime_seconds: float = 100.0,
) -> MagicMock:
    """Create a mock ``FrameCapture`` with controllable properties."""
    mock = MagicMock()
    mock.camera_id = camera_id
    type(mock).is_running = PropertyMock(return_value=is_running)
    type(mock).last_frame_age = PropertyMock(return_value=last_frame_age)
    type(mock).fps = PropertyMock(return_value=fps)
    type(mock).reconnect_attempts = PropertyMock(return_value=reconnect_attempts)
    type(mock).uptime_seconds = PropertyMock(return_value=uptime_seconds)
    return mock


# ------------------------------------------------------------------
# Initialisation
# ------------------------------------------------------------------


class TestInit:
    """Tests for initialisation."""

    def test_default_params(self) -> None:
        """Verify default parameter values."""
        monitor = CameraHealthMonitor()
        assert monitor._frame_timeout == 10.0
        assert monitor._max_stale_checks == 3
        assert monitor._check_interval == 5.0
        assert not monitor.is_running

    def test_custom_params(self) -> None:
        """Verify custom parameter values."""
        monitor = CameraHealthMonitor(
            frame_timeout_seconds=30.0,
            max_stale_checks=5,
            check_interval_seconds=2.0,
        )
        assert monitor._frame_timeout == 30.0
        assert monitor._max_stale_checks == 5
        assert monitor._check_interval == 2.0

    def test_invalid_timeout_raises(self) -> None:
        """Verify that zero or negative timeout raises."""
        for invalid in (0, -1, -5.0):
            with pytest.raises(ValueError):
                CameraHealthMonitor(frame_timeout_seconds=invalid)

    def test_invalid_max_stale_raises(self) -> None:
        """Verify that max_stale_checks < 1 raises."""
        with pytest.raises(ValueError):
            CameraHealthMonitor(max_stale_checks=0)

    def test_invalid_interval_raises(self) -> None:
        """Verify that zero or negative interval raises."""
        for invalid in (0, -1.0):
            with pytest.raises(ValueError):
                CameraHealthMonitor(check_interval_seconds=invalid)


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------


class TestRegistration:
    """Tests for camera registration."""

    def test_register_adds_camera(self) -> None:
        """Verify that registering a capture adds it."""
        monitor = CameraHealthMonitor()
        mock = _make_mock_capture(camera_id=1)
        monitor.register(mock)
        assert monitor.monitored_camera_count == 1

    def test_register_multiple_cameras(self) -> None:
        """Verify that multiple cameras can be registered."""
        monitor = CameraHealthMonitor()
        for cid in range(1, 4):
            monitor.register(_make_mock_capture(camera_id=cid))
        assert monitor.monitored_camera_count == 3

    def test_unregister_removes_camera(self) -> None:
        """Verify that unregistering removes the camera."""
        monitor = CameraHealthMonitor()
        mock = _make_mock_capture(camera_id=1)
        monitor.register(mock)
        monitor.unregister(1)
        assert monitor.monitored_camera_count == 0

    def test_get_snapshot_returns_none_for_unknown(self) -> None:
        """Verify that getting a snapshot for an unknown camera returns None."""
        monitor = CameraHealthMonitor()
        assert monitor.get_snapshot(999) is None

    def test_get_snapshot_returns_data(self) -> None:
        """Verify that a snapshot contains the expected fields."""
        monitor = CameraHealthMonitor()
        mock = _make_mock_capture(camera_id=1, last_frame_age=2.0, fps=29.5)
        monitor.register(mock)
        snap = monitor.get_snapshot(1)
        assert snap is not None
        assert snap.camera_id == 1
        assert snap.last_frame_age == 2.0
        assert snap.fps == 29.5
        assert snap.status == HealthStatus.HEALTHY

    def test_all_snapshots_returns_all(self) -> None:
        """Verify that all_snapshots returns all registered cameras."""
        monitor = CameraHealthMonitor()
        for cid in range(1, 4):
            monitor.register(_make_mock_capture(camera_id=cid))
        snaps = monitor.all_snapshots()
        assert len(snaps) == 3


# ------------------------------------------------------------------
# Health status derivation
# ------------------------------------------------------------------


class TestStatusDerivation:
    """Tests for health status derivation."""

    def test_healthy_when_recent_frame(self) -> None:
        """Verify HEALTHY when frame is recent."""
        monitor = CameraHealthMonitor(frame_timeout_seconds=10.0)
        mock = _make_mock_capture(camera_id=1, last_frame_age=1.0)
        monitor.register(mock)
        snap = monitor.get_snapshot(1)
        assert snap is not None
        assert snap.status == HealthStatus.HEALTHY

    def test_warning_when_frame_aging(self) -> None:
        """Verify WARNING when frame age approaches timeout."""
        monitor = CameraHealthMonitor(frame_timeout_seconds=10.0)
        mock = _make_mock_capture(camera_id=1, last_frame_age=6.0)
        monitor.register(mock)
        snap = monitor.get_snapshot(1)
        assert snap is not None
        assert snap.status == HealthStatus.WARNING

    def test_stale_when_frame_exceeds_timeout(self) -> None:
        """Verify STALE when frame age exceeds timeout."""
        monitor = CameraHealthMonitor(frame_timeout_seconds=10.0)
        mock = _make_mock_capture(camera_id=1, last_frame_age=15.0)
        monitor.register(mock)
        snap = monitor.get_snapshot(1)
        assert snap is not None
        assert snap.status == HealthStatus.STALE

    def test_error_when_not_running(self) -> None:
        """Verify ERROR when capture is not running."""
        monitor = CameraHealthMonitor()
        mock = _make_mock_capture(camera_id=1, is_running=False)
        monitor.register(mock)
        snap = monitor.get_snapshot(1)
        assert snap is not None
        assert snap.status == HealthStatus.ERROR


# ------------------------------------------------------------------
# Health check cycle
# ------------------------------------------------------------------


class TestHealthCheck:
    """Tests for the health check cycle."""

    def test_check_one_healthy(self) -> None:
        """Verify that a healthy camera resets the stale counter."""
        monitor = CameraHealthMonitor(frame_timeout_seconds=10.0)
        mock = _make_mock_capture(camera_id=1, last_frame_age=1.0)
        monitor.register(mock)

        monitor._stale_counters[1] = 2  # simulate previous stale
        monitor._check_one(1)
        assert monitor._stale_counters[1] == 0

    def test_check_one_stale_increments_counter(self) -> None:
        """Verify that a stale camera increments the counter."""
        monitor = CameraHealthMonitor(frame_timeout_seconds=10.0)
        mock = _make_mock_capture(camera_id=1, last_frame_age=15.0)
        monitor.register(mock)

        monitor._check_one(1)
        assert monitor._stale_counters[1] == 1

    def test_check_one_auto_reconnect_after_max(self) -> None:
        """Verify that auto-reconnect triggers after max stale checks."""
        monitor = CameraHealthMonitor(
            frame_timeout_seconds=10.0,
            max_stale_checks=2,
        )
        mock = _make_mock_capture(camera_id=1, last_frame_age=15.0)
        monitor.register(mock)

        # First check: stale counter = 1
        monitor._check_one(1)
        assert monitor._stale_counters[1] == 1

        # Second check: stale counter should trigger reconnect and reset
        monitor._check_one(1)
        assert monitor._stale_counters[1] == 0
        mock.restart.assert_called_once()

    def test_stale_callback(self) -> None:
        """Verify that the stale callback is called."""
        callback = MagicMock()
        monitor = CameraHealthMonitor(
            frame_timeout_seconds=10.0,
            on_camera_stale=callback,
        )
        mock = _make_mock_capture(camera_id=1, last_frame_age=15.0)
        monitor.register(mock)

        monitor._check_one(1)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == 1
        assert isinstance(args[1], CameraHealthSnapshot)

    def test_reconnecting_callback(self) -> None:
        """Verify that the reconnecting callback is called."""
        callback = MagicMock()
        monitor = CameraHealthMonitor(
            frame_timeout_seconds=10.0,
            max_stale_checks=2,
            on_camera_reconnecting=callback,
        )
        mock = _make_mock_capture(camera_id=1, last_frame_age=15.0)
        monitor.register(mock)

        # Two checks to trigger reconnect
        monitor._check_one(1)
        monitor._check_one(1)
        callback.assert_called_once()

    def test_recovered_callback(self) -> None:
        """Verify that the recovered callback is called."""
        callback = MagicMock()
        monitor = CameraHealthMonitor(
            frame_timeout_seconds=10.0,
            on_camera_recovered=callback,
        )
        mock = _make_mock_capture(camera_id=1, last_frame_age=15.0)
        monitor.register(mock)

        # First check: stale
        monitor._check_one(1)

        # Change frame age to make it healthy
        type(mock).last_frame_age = PropertyMock(return_value=1.0)

        # Second check: should trigger recovered
        monitor._check_one(1)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == 1
        assert isinstance(args[1], CameraHealthSnapshot)

    def test_check_all_checks_all(self) -> None:
        """Verify that _check_all iterates all cameras."""
        monitor = CameraHealthMonitor(frame_timeout_seconds=10.0)
        for cid in range(1, 4):
            mock = _make_mock_capture(camera_id=cid, last_frame_age=1.0)
            monitor.register(mock)

        monitor._check_all()
        for cid in range(1, 4):
            assert monitor._stale_counters[cid] == 0

    def test_error_during_check_does_not_block(self) -> None:
        """Verify that an exception in one check doesn't block others."""
        monitor = CameraHealthMonitor(frame_timeout_seconds=10.0)

        # Register a problematic camera (PropertyMock that raises)
        bad_mock = _make_mock_capture(camera_id=1, last_frame_age=1.0)
        type(bad_mock).is_running = PropertyMock(side_effect=RuntimeError("boom"))
        monitor.register(bad_mock)

        # Register a good camera
        good_mock = _make_mock_capture(camera_id=2, last_frame_age=1.0)
        monitor.register(good_mock)

        # This should not raise
        monitor._check_all()

    def test_auto_reconnect_threaded(self) -> None:
        """Verify that auto-reconnect runs in a separate thread."""
        monitor = CameraHealthMonitor(max_stale_checks=2)
        mock = _make_mock_capture(camera_id=1, last_frame_age=15.0)

        # Monkey-patch restart to record the calling thread
        import threading

        recorded_thread: list[threading.Thread | None] = [None]

        def _restart() -> None:
            recorded_thread[0] = threading.current_thread()

        mock.restart = _restart
        monitor.register(mock)

        monitor._check_one(1)  # counter = 1
        monitor._check_one(1)  # should trigger reconnect
        assert recorded_thread[0] is not None
        assert recorded_thread[0] is not threading.current_thread()
