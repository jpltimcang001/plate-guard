"""Frame capture via OpenCV for RTSP and USB camera sources.

``FrameCapture`` runs a background thread that continuously reads frames
from an ``cv2.VideoCapture`` and pushes them into a thread-safe
``FrameQueue``.  It supports:

- RTSP and USB sources
- Configurable decode resolution and backend
- FPS monitoring via ``FpsMonitor``
- Graceful start / stop lifecycle
- Frame-skipping when the downstream queue is congested
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from loguru import logger

from src.detection.fps_monitor import FpsMonitor
from src.detection.frame_queue import Frame, FrameQueue
from src.domain.value_objects.camera_status import CameraStatus
from src.domain.value_objects.camera_type import CameraType


class _CaptureState(Enum):
    """Internal states of the capture lifecycle."""

    INIT = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass
class CaptureStats:
    """Snapshot of capture statistics."""

    camera_id: int
    state: str
    status: str
    fps: float
    total_frames: int
    queue_size: int
    queue_maxsize: int
    queue_dropped: int
    dropped_frames: int
    reconnect_attempts: int
    uptime_seconds: float
    last_frame_age: float


class FrameCapture:
    """Captures frames from an RTSP or USB camera in a background thread.

    Usage::

        capture = FrameCapture(
            camera_id=1,
            source="rtsp://192.168.1.100:554/stream1",
            camera_type=CameraType.RTSP,
        )
        capture.start()

        while running:
            frame = capture.queue.get(timeout=1.0)
            if frame is not None:
                process(frame)

        capture.stop()
    """

    def __init__(
        self,
        camera_id: int,
        source: str,
        camera_type: CameraType = CameraType.USB,
        *,
        queue_maxsize: int = 60,
        fps_window: float = 5.0,
        preferred_width: int | None = None,
        preferred_height: int | None = None,
        backend: int | None = None,
        on_frame: Callable[[Frame], None] | None = None,
        on_status_change: Callable[[CameraStatus], None] | None = None,
    ) -> None:
        """Initialize the frame capture.

        Args:
            camera_id: Unique camera identifier (matches DB).
            source: RTSP URL (``rtsp://…``) or USB index as string (``"0"``).
            camera_type: ``CameraType.RTSP`` or ``CameraType.USB``.
            queue_maxsize: Max frames in the internal queue.
            fps_window: Seconds for the rolling FPS window.
            preferred_width: Target decode width (``None`` = source default).
            preferred_height: Target decode height (``None`` = source default).
            backend: OpenCV backend (e.g. ``cv2.CAP_FFMPEG``, ``cv2.CAP_DSHOW``).
                ``None`` auto-selects a sensible default.
            on_frame: Optional callback fired when a frame is captured.
            on_status_change: Optional callback when ``CameraStatus`` changes.

        """
        self._camera_id = camera_id
        self._source = source
        self._camera_type = camera_type
        self._preferred_width = preferred_width
        self._preferred_height = preferred_height
        self._backend = backend or self._default_backend()

        # Components
        self._queue = FrameQueue(maxsize=queue_maxsize, camera_id=camera_id)
        self._fps_monitor = FpsMonitor(window_seconds=fps_window, camera_id=camera_id)

        # Callbacks
        self._on_frame = on_frame
        self._on_status_change = on_status_change

        # State
        self._state = _CaptureState.INIT
        self._status: CameraStatus = CameraStatus.OFFLINE
        self._cap: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._frame_number: int = 0
        self._dropped_frames: int = 0
        self._reconnect_attempts: int = 0
        self._last_frame_time: float = 0.0
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def camera_id(self) -> int:
        return self._camera_id

    @property
    def source(self) -> str:
        return self._source

    @property
    def camera_type(self) -> CameraType:
        return self._camera_type

    @property
    def queue(self) -> FrameQueue:
        return self._queue

    @property
    def fps_monitor(self) -> FpsMonitor:
        return self._fps_monitor

    @property
    def status(self) -> CameraStatus:
        """Current health status of the camera stream."""
        with self._lock:
            return self._status

    @property
    def is_running(self) -> bool:
        """Whether the capture thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def fps(self) -> float:
        """Current rolling average FPS."""
        return self._fps_monitor.fps

    @property
    def total_frames(self) -> int:
        """Total frames captured since start."""
        return self._frame_number

    @property
    def dropped_frames(self) -> int:
        """Frames dropped due to read failures."""
        return self._dropped_frames

    @property
    def reconnect_attempts(self) -> int:
        """Total reconnection attempts."""
        return self._reconnect_attempts

    @property
    def uptime_seconds(self) -> float:
        """Seconds since the capture started."""
        if self._start_time == 0:
            return 0.0
        return time.monotonic() - self._start_time

    @property
    def last_frame_age(self) -> float:
        """Seconds since the last frame was captured."""
        if self._last_frame_time == 0:
            return float("inf")
        return time.monotonic() - self._last_frame_time

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the capture background thread.

        Raises:
            RuntimeError: If the capture is already running.

        """
        with self._lock:
            if self._state is _CaptureState.RUNNING:
                raise RuntimeError(
                    f"FrameCapture(camera={self._camera_id}) is already running"
                )

            self._stop_event.clear()
            self._frame_number = 0
            self._dropped_frames = 0
            self._reconnect_attempts = 0
            self._start_time = time.monotonic()
            self._last_frame_time = 0.0

            self._state = _CaptureState.RUNNING
            self._set_status(CameraStatus.RECONNECTING)

            self._thread = threading.Thread(
                target=self._capture_loop,
                name=f"capture-camera-{self._camera_id}",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "FrameCapture(camera={}) started source={} type={}",
                self._camera_id,
                self._source,
                self._camera_type.value,
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the capture thread to stop and wait for it.

        Args:
            timeout: Seconds to wait for the thread to finish.

        """
        with self._lock:
            was_running = self._state is _CaptureState.RUNNING
            self._state = _CaptureState.STOPPED
            self._set_status(CameraStatus.OFFLINE)
            self._stop_event.set()

        if was_running and self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "FrameCapture(camera={}) capture thread did not stop in {}s",
                    self._camera_id,
                    timeout,
                )

        # Release the underlying capture
        self._close_capture()
        self._queue.clear()

        logger.info(
            "FrameCapture(camera={}) stopped ({} frames, {} dropped)",
            self._camera_id,
            self._frame_number,
            self._dropped_frames,
        )

    def restart(self) -> None:
        """Fully stop and restart the capture."""
        logger.info("FrameCapture(camera={}) restarting...", self._camera_id)
        self.stop(timeout=3.0)
        self.start()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> CaptureStats:
        """Return a snapshot of all capture statistics."""
        with self._lock:
            return CaptureStats(
                camera_id=self._camera_id,
                state=self._state.name.lower(),
                status=self._status.value,
                fps=round(self._fps_monitor.fps, 2),
                total_frames=self._frame_number,
                queue_size=self._queue.qsize,
                queue_maxsize=self._queue.maxsize,
                queue_dropped=self._queue.total_dropped,
                dropped_frames=self._dropped_frames,
                reconnect_attempts=self._reconnect_attempts,
                uptime_seconds=self.uptime_seconds,
                last_frame_age=self.last_frame_age,
            )

    # ------------------------------------------------------------------
    # Internal capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Main worker thread: repeatedly read frames from OpenCV."""
        while not self._stop_event.is_set():
            try:
                self._ensure_capture_open()

                if self._cap is None:
                    # Connection failed; wait before retry
                    self._sleep_or_stop(2.0)
                    continue

                ret, frame_data = self._cap.read()

                if not ret or frame_data is None:
                    self._handle_read_failure()
                    continue

                # Apply target resolution if configured
                if self._preferred_width and self._preferred_height:
                    frame_data = cv2.resize(
                        frame_data,
                        (self._preferred_width, self._preferred_height),
                        interpolation=cv2.INTER_LINEAR,
                    )

                # Create Frame and push to queue
                self._frame_number += 1
                now = time.monotonic()
                self._last_frame_time = now

                frame_obj = Frame(
                    data=frame_data,
                    camera_id=self._camera_id,
                    timestamp=now,
                    frame_number=self._frame_number,
                )

                self._queue.put(frame_obj)
                self._fps_monitor.tick()

                # Update status (transition to ONLINE if we were reconnecting)
                with self._lock:
                    if self._status is not CameraStatus.ONLINE:
                        self._set_status(CameraStatus.ONLINE)

                # Fire callback
                if self._on_frame is not None:
                    try:
                        self._on_frame(frame_obj)
                    except Exception:
                        logger.opt(exception=True).warning(
                            "FrameCapture(camera={}) on_frame callback failed",
                            self._camera_id,
                        )

            except Exception:
                logger.opt(exception=True).error(
                    "FrameCapture(camera={}) unhandled error in capture loop",
                    self._camera_id,
                )
                self._sleep_or_stop(1.0)

        # Thread exiting
        self._close_capture()

    def _ensure_capture_open(self) -> None:
        """Open the VideoCapture if it is not already open.

        Updates status to ``RECONNECTING`` while attempting to connect.
        """
        if self._cap is not None and self._cap.isOpened():
            return

        with self._lock:
            if self._status is not CameraStatus.RECONNECTING:
                self._set_status(CameraStatus.RECONNECTING)
            self._reconnect_attempts += 1

        self._close_capture()

        try:
            if self._camera_type == CameraType.USB:
                source_index = int(self._source)
                cap = cv2.VideoCapture(source_index, self._backend)
            else:
                cap = cv2.VideoCapture(self._source, self._backend)

            if not cap.isOpened():
                cap.release()
                logger.warning(
                    "FrameCapture(camera={}) failed to open source={}",
                    self._camera_id,
                    self._source,
                )
                self._cap = None
                return

            # Set optional properties
            if self._preferred_width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._preferred_width)
            if self._preferred_height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._preferred_height)

            # Reduce FFmpeg buffer for lower latency on RTSP
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self._cap = cap
            logger.info(
                "FrameCapture(camera={}) connected to {} ({}x{})",
                self._camera_id,
                self._source,
                int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )

        except (ValueError, OSError, cv2.error) as exc:
            logger.warning(
                "FrameCapture(camera={}) connection error: {}",
                self._camera_id,
                exc,
            )
            self._cap = None

    def _handle_read_failure(self) -> None:
        """Handle a failed ``cap.read()``."""
        self._dropped_frames += 1

        # If we've had many consecutive failures, force a reconnect
        if self._dropped_frames >= 30:
            logger.warning(
                "FrameCapture(camera={}) {} consecutive read failures, reconnecting",
                self._camera_id,
                self._dropped_frames,
            )
            self._close_capture()
            self._dropped_frames = 0
            with self._lock:
                self._set_status(CameraStatus.RECONNECTING)
        else:
            # Brief sleep to avoid busy-spin on failure
            time.sleep(0.01)

    def _close_capture(self) -> None:
        """Safely release the underlying VideoCapture."""
        cap, self._cap = self._cap, None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                logger.opt(exception=True).debug(
                    "FrameCapture(camera={}) error releasing capture",
                    self._camera_id,
                )

    def _set_status(self, new_status: CameraStatus) -> None:
        """Update the camera status and fire callback if changed."""
        old_status = self._status
        if old_status == new_status:
            return
        self._status = new_status
        logger.debug(
            "FrameCapture(camera={}) status: {} -> {}",
            self._camera_id,
            old_status.value,
            new_status.value,
        )
        if self._on_status_change is not None:
            try:
                self._on_status_change(new_status)
            except Exception:
                logger.opt(exception=True).warning(
                    "FrameCapture(camera={}) on_status_change callback failed",
                    self._camera_id,
                )

    def _sleep_or_stop(self, seconds: float) -> None:
        """Sleep for *seconds* or until stop is requested."""
        self._stop_event.wait(timeout=seconds)

    @staticmethod
    def _default_backend() -> int:
        """Choose a sensible default OpenCV backend per platform."""
        import sys

        if sys.platform == "win32":
            return cv2.CAP_DSHOW
        return cv2.CAP_ANY

    def __repr__(self) -> str:
        return (
            f"<FrameCapture camera={self._camera_id} "
            f"source={self._source} "
            f"status={self._status.value} "
            f"fps={self.fps:.1f}>"
        )
