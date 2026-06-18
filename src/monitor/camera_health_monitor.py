"""Camera health monitor with watchdog and auto-reconnect.

Periodically checks all registered ``FrameCapture`` instances for:

- **Frame timeout**: no frame received within ``frame_timeout_seconds``.
- **Reconnect threshold**: repeated timeouts trigger a full restart of
  the capture.

When a camera is detected as stale, the monitor:

1. Logs a warning.
2. Calls the ``on_camera_stale`` callback (if configured).
3. After ``max_stale_checks`` consecutive stale checks, triggers an
   automatic ``capture.restart()`` and calls ``on_camera_reconnecting``.

Usage
-----
Create and start the monitor, then register captures::

    from src.monitor.camera_health_monitor import CameraHealthMonitor

    monitor = CameraHealthMonitor(check_interval_seconds=5.0)
    monitor.register(capture_instance)
    monitor.start()

    # Later:
    monitor.stop()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional

from loguru import logger


class HealthStatus(Enum):
    """Health status of a monitored camera."""

    HEALTHY = auto()
    WARNING = auto()  # missed a few frames but not yet critical
    STALE = auto()  # no frames within timeout
    RECONNECTING = auto()
    ERROR = auto()


@dataclass
class CameraHealthSnapshot:
    """Snapshot of a camera's health at a point in time.

    Attributes:
        camera_id: The camera ID.
        status: Current health status.
        last_frame_age: Seconds since the last frame was captured.
        fps: Current frames per second.
        reconnect_attempts: Total reconnection attempts.
        consecutive_stale_checks: How many consecutive checks found
            the camera stale.
        uptime_seconds: Seconds since the capture started.
        checked_at: Timestamp of this health check.

    """

    camera_id: int
    status: HealthStatus
    last_frame_age: float
    fps: float
    reconnect_attempts: int
    consecutive_stale_checks: int
    uptime_seconds: float
    checked_at: float = field(default_factory=time.monotonic)


class CameraHealthMonitor:
    """Periodically checks camera health and triggers auto-reconnect.

    Usage::

        monitor = CameraHealthMonitor(
            frame_timeout_seconds=10.0,
            max_stale_checks=3,
            check_interval_seconds=5.0,
        )
        monitor.register(capture)
        monitor.start()

        # Query status:
        snapshot = monitor.get_snapshot(camera_id=1)

        monitor.stop()
    """

    def __init__(
        self,
        frame_timeout_seconds: float = 10.0,
        max_stale_checks: int = 3,
        check_interval_seconds: float = 5.0,
        on_camera_stale: Callable[[int, CameraHealthSnapshot], None] | None = None,
        on_camera_reconnecting: Callable[[int, CameraHealthSnapshot], None] | None = None,
        on_camera_recovered: Callable[[int, CameraHealthSnapshot], None] | None = None,
    ) -> None:
        """Initialise the camera health monitor.

        Args:
            frame_timeout_seconds: If no frame received within this
                many seconds, the camera is considered stale.
            max_stale_checks: Consecutive stale checks before
                triggering auto-reconnect.
            check_interval_seconds: Seconds between health checks.
            on_camera_stale: Called when a camera first becomes stale.
            on_camera_reconnecting: Called when auto-reconnect is
                triggered.
            on_camera_recovered: Called when a camera returns to
                healthy after a stale/reconnecting period.

        """
        if frame_timeout_seconds <= 0:
            raise ValueError("frame_timeout_seconds must be positive")
        if max_stale_checks < 1:
            raise ValueError("max_stale_checks must be at least 1")
        if check_interval_seconds <= 0:
            raise ValueError("check_interval_seconds must be positive")

        self._frame_timeout = frame_timeout_seconds
        self._max_stale_checks = max_stale_checks
        self._check_interval = check_interval_seconds
        self._on_camera_stale = on_camera_stale
        self._on_camera_reconnecting = on_camera_reconnecting
        self._on_camera_recovered = on_camera_recovered

        # Captures indexed by camera_id
        self._captures: Dict[int, "FrameCapture"] = {}  # noqa: F821
        self._stale_counters: Dict[int, int] = {}
        self._healthy_since_stale: Dict[int, bool] = {}  # was stale, now healthy?

        self._timer: "QTimer | None" = None  # noqa: F821 — will be a QTimer
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, capture: "FrameCapture") -> None:  # noqa: F821
        """Register a ``FrameCapture`` for health monitoring.

        Args:
            capture: The ``FrameCapture`` instance to monitor.

        """
        cid = capture.camera_id
        self._captures[cid] = capture
        self._stale_counters.setdefault(cid, 0)
        self._healthy_since_stale.setdefault(cid, True)
        logger.debug(
            "CameraHealthMonitor: registered camera_id={} (timeout={}s)",
            cid,
            self._frame_timeout,
        )

    def unregister(self, camera_id: int) -> None:
        """Remove a camera from health monitoring.

        Args:
            camera_id: The camera ID to remove.

        """
        self._captures.pop(camera_id, None)
        self._stale_counters.pop(camera_id, None)
        self._healthy_since_stale.pop(camera_id, None)
        logger.debug("CameraHealthMonitor: unregistered camera_id={}", camera_id)

    def get_snapshot(self, camera_id: int) -> CameraHealthSnapshot | None:
        """Return the latest health snapshot for a camera.

        Args:
            camera_id: The camera ID.

        Returns:
            A ``CameraHealthSnapshot`` or ``None`` if the camera is not
            registered.

        """
        capture = self._captures.get(camera_id)
        if capture is None:
            return None

        age = capture.last_frame_age
        fps = capture.fps
        attempts = capture.reconnect_attempts
        uptime = capture.uptime_seconds
        stale_count = self._stale_counters.get(camera_id, 0)

        status = self._derive_status(camera_id, age)
        return CameraHealthSnapshot(
            camera_id=camera_id,
            status=status,
            last_frame_age=age,
            fps=fps,
            reconnect_attempts=attempts,
            consecutive_stale_checks=stale_count,
            uptime_seconds=uptime,
        )

    def all_snapshots(self) -> list[CameraHealthSnapshot]:
        """Return health snapshots for all registered cameras.

        Returns:
            A list of ``CameraHealthSnapshot`` instances.

        """
        return [
            snap
            for cid in list(self._captures.keys())
            if (snap := self.get_snapshot(cid)) is not None
        ]

    def start(self) -> None:
        """Start periodic health checks.

        Uses a ``QTimer`` to run checks on the main thread.

        """
        if self._running:
            logger.warning("CameraHealthMonitor already running")
            return

        from PySide6.QtCore import QTimer

        self._timer = QTimer()
        self._timer.timeout.connect(self._check_all)
        self._timer.start(int(self._check_interval * 1000))
        self._running = True

        logger.info(
            "CameraHealthMonitor started (interval={}s, timeout={}s, "
            "max_stale={})",
            self._check_interval,
            self._frame_timeout,
            self._max_stale_checks,
        )

    def stop(self) -> None:
        """Stop periodic health checks."""
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        logger.info("CameraHealthMonitor stopped")

    @property
    def is_running(self) -> bool:
        """Whether the monitor is running."""
        return self._running

    @property
    def monitored_camera_count(self) -> int:
        """Number of registered cameras."""
        return len(self._captures)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_all(self) -> None:
        """Run a health check cycle for all registered cameras."""
        for camera_id in list(self._captures.keys()):
            try:
                self._check_one(camera_id)
            except Exception:
                logger.opt(exception=True).warning(
                    "CameraHealthMonitor: check failed for camera_id={}",
                    camera_id,
                )

    def _check_one(self, camera_id: int) -> None:
        """Run a single health check for one camera.

        Args:
            camera_id: The camera ID to check.

        """
        capture = self._captures.get(camera_id)
        if capture is None:
            return

        age = capture.last_frame_age
        is_stale = age > self._frame_timeout and capture.is_running

        if is_stale:
            count = self._stale_counters.get(camera_id, 0) + 1
            self._stale_counters[camera_id] = count

            if count == 1:
                self._healthy_since_stale[camera_id] = False
                logger.warning(
                    "CameraHealthMonitor: camera_id={} is stale "
                    "(last frame {}s ago)",
                    camera_id,
                    round(age, 1),
                )
                if self._on_camera_stale is not None:
                    snap = self.get_snapshot(camera_id)
                    if snap is not None:
                        self._on_camera_stale(camera_id, snap)

            if count >= self._max_stale_checks:
                logger.warning(
                    "CameraHealthMonitor: camera_id={} auto-reconnecting "
                    "(stale for {} checks)",
                    camera_id,
                    count,
                )
                if self._on_camera_reconnecting is not None:
                    snap = self.get_snapshot(camera_id)
                    if snap is not None:
                        self._on_camera_reconnecting(camera_id, snap)
                self._auto_reconnect(capture)
                self._stale_counters[camera_id] = 0
        else:
            was_healthy = self._healthy_since_stale.get(camera_id, True)

            self._stale_counters[camera_id] = 0

            if not was_healthy:
                # Camera was stale/reconnecting and is now healthy
                logger.info(
                    "CameraHealthMonitor: camera_id={} recovered "
                    "(last frame {}s ago, fps={:.1f})",
                    camera_id,
                    round(age, 1),
                    capture.fps,
                )
                if self._on_camera_recovered is not None:
                    snap = self.get_snapshot(camera_id)
                    if snap is not None:
                        self._on_camera_recovered(camera_id, snap)

            self._healthy_since_stale[camera_id] = True

    def _derive_status(self, camera_id: int, age: float) -> HealthStatus:
        """Derive the health status for a camera.

        Args:
            camera_id: The camera ID.
            age: Seconds since last frame.

        Returns:
            The ``HealthStatus`` enum value.

        """
        capture = self._captures.get(camera_id)
        if capture is None:
            return HealthStatus.ERROR

        if not capture.is_running:
            return HealthStatus.ERROR

        stale_count = self._stale_counters.get(camera_id, 0)
        if stale_count >= self._max_stale_checks:
            return HealthStatus.RECONNECTING
        if age > self._frame_timeout:
            return HealthStatus.STALE
        if age > self._frame_timeout * 0.5:
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY

    @staticmethod
    def _auto_reconnect(capture: "FrameCapture") -> None:  # noqa: F821
        """Restart the capture in a background thread.

        Args:
            capture: The ``FrameCapture`` to restart.

        """
        import threading

        def _restart() -> None:
            try:
                capture.restart()
            except Exception:
                logger.opt(exception=True).error(
                    "CameraHealthMonitor: auto-reconnect failed for "
                    "camera_id={}",
                    capture.camera_id,
                )

        thread = threading.Thread(target=_restart, daemon=True)
        thread.start()

    def __repr__(self) -> str:
        return (
            f"<CameraHealthMonitor cameras={self.monitored_camera_count} "
            f"running={self._running}>"
        )
