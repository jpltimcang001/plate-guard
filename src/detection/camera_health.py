"""Watchdog monitor for camera stream health with auto-reconnect.

``CameraHealthMonitor`` periodically checks a ``FrameCapture`` instance
for signs of life.  If no frames arrive within a configurable timeout,
it triggers a reconnection cycle.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

from src.detection.frame_capture import FrameCapture
from src.domain.value_objects.camera_status import CameraStatus


@dataclass
class HealthSnapshot:
    """Snapshot of camera health at a point in time."""

    camera_id: int
    status: CameraStatus
    is_alive: bool
    fps: float
    uptime_seconds: float
    last_frame_age: float
    total_frames: int
    reconnect_attempts: int
    consecutive_checks_failed: int
    max_allowed_idle: float


class CameraHealthMonitor:
    """Background watchdog that monitors a ``FrameCapture`` for liveness.

    The monitor runs a daemon thread that checks at a regular interval
    whether the capture is still producing frames.  If the time since
    the last frame exceeds ``max_idle_seconds``, it triggers a reconnect
    via ``FrameCapture.restart()``.

    Usage::

        capture = FrameCapture(...)
        monitor = CameraHealthMonitor(
            capture=capture,
            max_idle_seconds=10.0,
            check_interval=2.0,
        )
        monitor.start()

        # ... later ...
        monitor.stop()
    """

    def __init__(
        self,
        capture: FrameCapture,
        *,
        max_idle_seconds: float = 10.0,
        check_interval: float = 2.0,
        max_reconnects: int = 0,
        reconnect_delay: float = 3.0,
        on_status_change: Callable[[CameraStatus], None] | None = None,
    ) -> None:
        """Initialize the health monitor.

        Args:
            capture: The ``FrameCapture`` instance to monitor.
            max_idle_seconds: If no frame is received for this duration
                the stream is considered dead and a reconnect is triggered.
            check_interval: How often (seconds) to run the health check.
            max_reconnects: Maximum reconnection attempts before giving up.
                ``0`` means unlimited.
            reconnect_delay: Seconds to wait before attempting reconnect
                after detecting a dead stream.
            on_status_change: Optional callback when ``CameraStatus`` changes.

        """
        self._capture = capture
        self._max_idle_seconds = max_idle_seconds
        self._check_interval = check_interval
        self._max_reconnects = max_reconnects
        self._reconnect_delay = reconnect_delay
        self._on_status_change = on_status_change

        # State
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._consecutive_checks_failed: int = 0
        self._reconnect_count: int = 0
        self._last_known_status: CameraStatus = CameraStatus.OFFLINE
        self._running = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def capture(self) -> FrameCapture:
        return self._capture

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def consecutive_checks_failed(self) -> int:
        return self._consecutive_checks_failed

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def snapshot(self) -> HealthSnapshot:
        """Return a health snapshot for the current moment."""
        return HealthSnapshot(
            camera_id=self._capture.camera_id,
            status=self._capture.status,
            is_alive=self._capture.is_running,
            fps=self._capture.fps,
            uptime_seconds=self._capture.uptime_seconds,
            last_frame_age=self._capture.last_frame_age,
            total_frames=self._capture.total_frames,
            reconnect_attempts=self._capture.reconnect_attempts,
            consecutive_checks_failed=self._consecutive_checks_failed,
            max_allowed_idle=self._max_idle_seconds,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the health monitor background thread.

        Also starts the underlying ``FrameCapture`` if it is not already
        running.

        Raises:
            RuntimeError: If the monitor is already running.

        """
        with self._lock:
            if self._running:
                raise RuntimeError(
                    f"CameraHealthMonitor(camera={self._capture.camera_id}) "
                    "is already running"
                )

            self._running = True
            self._stop_event.clear()
            self._consecutive_checks_failed = 0
            self._reconnect_count = 0
            self._last_known_status = self._capture.status

            # Ensure capture is started
            if not self._capture.is_running:
                try:
                    self._capture.start()
                except RuntimeError:
                    # Already running from another caller — that's fine
                    pass

            self._thread = threading.Thread(
                target=self._monitor_loop,
                name=f"health-camera-{self._capture.camera_id}",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "CameraHealthMonitor(camera={}) started "
                "(max_idle={}s, interval={}s)",
                self._capture.camera_id,
                self._max_idle_seconds,
                self._check_interval,
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the health monitor and underlying capture.

        Args:
            timeout: Seconds to wait for the monitor thread to finish.

        """
        with self._lock:
            self._running = False
            self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "CameraHealthMonitor(camera={}) thread did not stop in {}s",
                    self._capture.camera_id,
                    timeout,
                )

        # Stop the underlying capture only if we started it and
        # no other monitor is using it.  For simplicity we always
        # stop — the caller is responsible for lifecycle coordination.
        try:
            self._capture.stop(timeout=timeout)
        except Exception:
            logger.opt(exception=True).debug(
                "CameraHealthMonitor(camera={}) error stopping capture",
                self._capture.camera_id,
            )

        logger.info(
            "CameraHealthMonitor(camera={}) stopped",
            self._capture.camera_id,
        )

    def health_check(self) -> bool:
        """Perform a single health check and return ``True`` if healthy.

        Can be called externally for polling-style health checks
        outside the background thread.
        """
        return self._perform_check()

    # ------------------------------------------------------------------
    # Internal monitor loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Background thread: periodically check health, reconnect if needed."""
        while not self._stop_event.is_set():
            self._perform_check()
            self._stop_event.wait(timeout=self._check_interval)

    def _perform_check(self) -> bool:
        """Execute one health check cycle.

        Returns:
            ``True`` if the camera is healthy, ``False`` otherwise.

        """
        capture = self._capture

        if not capture.is_running:
            logger.warning(
                "CameraHealthMonitor(camera={}) capture is not running, "
                "attempting restart",
                capture.camera_id,
            )
            self._handle_dead_stream()
            return False

        last_frame_age = capture.last_frame_age

        if last_frame_age > self._max_idle_seconds:
            self._consecutive_checks_failed += 1
            logger.warning(
                "CameraHealthMonitor(camera={}) no frame for {:.1f}s "
                "(max_idle={:.1f}s, consecutive_failures={})",
                capture.camera_id,
                last_frame_age,
                self._max_idle_seconds,
                self._consecutive_checks_failed,
            )

            # Only reconnect after at least two consecutive failures
            # to avoid flapping on transient delays.
            if self._consecutive_checks_failed >= 2:
                self._handle_dead_stream()
            else:
                # First failure — just report the current capture status
                # without triggering reconnect logic.
                self._update_status(capture.status)
            return False

        # Healthy
        self._consecutive_checks_failed = 0
        self._update_status(CameraStatus.ONLINE)
        return True

    def _handle_dead_stream(self) -> None:
        """Attempt to reconnect the capture stream."""
        camera_id = self._capture.camera_id

        # Check reconnect limit
        if self._max_reconnects > 0 and self._reconnect_count >= self._max_reconnects:
            logger.error(
                "CameraHealthMonitor(camera={}) max reconnects ({}) reached, "
                "giving up",
                camera_id,
                self._max_reconnects,
            )
            self._update_status(CameraStatus.ERROR)
            return

        self._reconnect_count += 1
        self._update_status(CameraStatus.RECONNECTING)

        logger.info(
            "CameraHealthMonitor(camera={}) reconnecting "
            "(attempt {}/{})",
            camera_id,
            self._reconnect_count,
            self._max_reconnects if self._max_reconnects > 0 else "∞",
        )

        # Brief delay before reconnect to avoid hammering
        if self._reconnect_delay > 0:
            if self._stop_event.wait(timeout=self._reconnect_delay):
                return  # Stop requested during delay

        try:
            self._capture.restart()
        except Exception:
            logger.opt(exception=True).error(
                "CameraHealthMonitor(camera={}) restart failed",
                camera_id,
            )

    def _update_status(self, new_status: CameraStatus) -> None:
        """Fire callback if the camera status changed."""
        if new_status == self._last_known_status:
            return
        self._last_known_status = new_status
        if self._on_status_change is not None:
            try:
                self._on_status_change(new_status)
            except Exception:
                logger.opt(exception=True).warning(
                    "CameraHealthMonitor(camera={}) status callback failed",
                    self._capture.camera_id,
                )

    def __repr__(self) -> str:
        return (
            f"<CameraHealthMonitor camera={self._capture.camera_id} "
            f"status={self._capture.status.value} "
            f"failures={self._consecutive_checks_failed}>"
        )
