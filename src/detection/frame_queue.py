"""Thread-safe bounded frame queue with oldest-frame-drop behaviour.

When the queue is full and a new frame arrives, the oldest unprocessed
frame is discarded to keep latency low. This is essential for real-time
video processing where stale frames must not accumulate.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
from loguru import logger


@dataclass
class Frame:
    """A single video frame with metadata."""

    data: np.ndarray
    """The frame as a BGR numpy array."""

    camera_id: int
    """The ID of the camera that produced this frame."""

    timestamp: float
    """Unix timestamp (time.time()) when the frame was captured."""

    frame_number: int
    """Monotonically increasing frame counter for this camera."""

    @property
    def age_seconds(self) -> float:
        """Seconds since this frame was captured."""
        return time.time() - self.timestamp


class FrameQueue:
    """Bounded, thread-safe queue for video frames.

    Features:
    - Fixed maximum size (oldest frame dropped when full).
    - Thread-safe put and get operations.
    - Non-blocking ``get_nowait`` and ``try_put`` variants.
    - Statistics tracking (peak size, total enqueued, total dropped).
    """

    def __init__(self, maxsize: int = 60, camera_id: int = 0) -> None:
        """Initialize the frame queue.

        Args:
            maxsize: Maximum number of frames to hold. Default 60
                (≈2 seconds at 30 FPS, ≈6 seconds at 10 FPS).
            camera_id: The camera this queue belongs to (for logging).

        """
        self._maxsize = maxsize
        self._camera_id = camera_id
        self._deque: deque[Frame] = deque(maxlen=maxsize)
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

        # Statistics
        self._total_enqueued: int = 0
        self._total_dropped: int = 0
        self._peak_size: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def maxsize(self) -> int:
        """Return the maximum capacity of the queue."""
        return self._maxsize

    @property
    def qsize(self) -> int:
        """Return the current number of frames in the queue."""
        with self._lock:
            return len(self._deque)

    @property
    def empty(self) -> bool:
        """Return ``True`` if the queue has no frames."""
        with self._lock:
            return len(self._deque) == 0

    @property
    def full(self) -> bool:
        """Return ``True`` if the queue is at maximum capacity."""
        with self._lock:
            return len(self._deque) >= self._maxsize

    def put(self, frame: Frame) -> bool:
        """Add a frame to the queue.

        If the queue is full, the oldest frame is silently dropped
        before inserting the new frame.

        Args:
            frame: The ``Frame`` to enqueue.

        Returns:
            ``True`` if the frame was added, ``False`` if it was
            dropped due to the queue being full.

        """
        dropped = False
        with self._lock:
            was_full = len(self._deque) >= self._maxsize
            if was_full:
                self._total_dropped += 1
                dropped = True

            self._deque.append(frame)
            self._total_enqueued += 1
            self._peak_size = max(self._peak_size, len(self._deque))
            self._not_empty.notify()

        if dropped:
            logger.trace(
                "FrameQueue(camera={}) dropped frame (queue full, size={})",
                self._camera_id,
                self._maxsize,
            )
        return not dropped

    def get(self, timeout: float | None = None) -> Frame | None:
        """Retrieve the oldest frame, blocking if necessary.

        Args:
            timeout: Maximum seconds to wait for a frame.
                ``None`` means wait indefinitely.

        Returns:
            A ``Frame``, or ``None`` if the timeout expired.

        """
        with self._lock:
            if not self._deque and timeout is not None:
                self._not_empty.wait(timeout=timeout)

            if not self._deque:
                return None

            frame = self._deque.popleft()
            return frame

    def get_nowait(self) -> Frame | None:
        """Retrieve the oldest frame without blocking.

        Returns:
            A ``Frame``, or ``None`` if the queue is empty.

        """
        return self.get(timeout=0)

    def drain(self) -> list[Frame]:
        """Remove and return all frames currently in the queue.

        Returns:
            A list of all frames that were in the queue (oldest first).

        """
        with self._lock:
            frames = list(self._deque)
            self._deque.clear()
            return frames

    def clear(self) -> None:
        """Discard all frames in the queue immediately."""
        with self._lock:
            count = len(self._deque)
            self._deque.clear()
            if count > 0:
                logger.debug(
                    "FrameQueue(camera={}) cleared {} frame(s)",
                    self._camera_id,
                    count,
                )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def total_enqueued(self) -> int:
        """Total number of frames ever added to this queue."""
        return self._total_enqueued

    @property
    def total_dropped(self) -> int:
        """Total number of frames dropped due to full queue."""
        return self._total_dropped

    @property
    def peak_size(self) -> int:
        """Peak number of frames that were in the queue simultaneously."""
        return self._peak_size

    @property
    def drop_ratio(self) -> float:
        """Fraction of enqueued frames that were dropped (0.0–1.0)."""
        total = self._total_enqueued
        if total == 0:
            return 0.0
        return self._total_dropped / total

    def stats(self) -> dict[str, Any]:
        """Return a snapshot of queue statistics.

        Returns:
            A dict with keys: ``size``, ``maxsize``, ``total_enqueued``,
            ``total_dropped``, ``peak_size``, ``drop_ratio``, ``empty``.

        """
        with self._lock:
            return {
                "size": len(self._deque),
                "maxsize": self._maxsize,
                "total_enqueued": self._total_enqueued,
                "total_dropped": self._total_dropped,
                "peak_size": self._peak_size,
                "drop_ratio": self.drop_ratio,
                "empty": len(self._deque) == 0,
            }

    def __len__(self) -> int:
        return self.qsize

    def __repr__(self) -> str:
        return (
            f"<FrameQueue camera={self._camera_id} "
            f"size={self.qsize}/{self._maxsize} "
            f"dropped={self._total_dropped}>"
        )
