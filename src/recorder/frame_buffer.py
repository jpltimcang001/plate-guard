"""Thread-safe circular frame buffer that keeps the last N seconds of frames.

Designed for pre‑detection and post‑detection video clip assembly:
the buffer is continuously fed by the capture pipeline, and when a
detection event fires we can extract the frames that precede it.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import List, Optional

import numpy as np
from loguru import logger

from src.detection.frame_queue import Frame


class FrameRingBuffer:
    """Thread-safe circular buffer of video frames.

    The buffer keeps the most recent *maxlen* frames.  When full, the
    oldest frame is silently overwritten.  This is designed for
    retrieving frames that were captured *before* a detection event.

    Usage::

        buffer = FrameRingBuffer(maxlen=300)   # ~10 s at 30 FPS

        # Called from the capture thread for every frame:
        buffer.push(frame)

        # Called when a detection occurs at timestamp T:
        pre_frames = buffer.get_frames_before(T, seconds=3)
    """

    def __init__(self, maxlen: int = 300) -> None:
        """Initialise the ring buffer.

        Args:
            maxlen: Maximum number of frames to retain.  The default
                300 holds ≈10 seconds at 30 FPS or ≈30 seconds at
                10 FPS.

        """
        self._maxlen = maxlen
        self._deque: deque[Frame] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def maxlen(self) -> int:
        """Maximum capacity of the buffer."""
        return self._maxlen

    @property
    def size(self) -> int:
        """Current number of frames in the buffer."""
        with self._lock:
            return len(self._deque)

    def push(self, frame: Frame) -> None:
        """Add a frame to the buffer.

        If the buffer is full the oldest frame is silently discarded.

        Args:
            frame: The ``Frame`` to add.

        """
        with self._lock:
            self._deque.append(frame)

    def get_frames_before(
        self,
        timestamp: float,
        seconds: float = 3.0,
    ) -> List[Frame]:
        """Return frames whose timestamp falls in ``(timestamp - seconds, timestamp]``.

        Frames are returned in oldest-first order suitable for video
        encoding.

        Args:
            timestamp: Unix timestamp (seconds) of the detection.
            seconds: How many seconds of history to retrieve.

        Returns:
            A list of ``Frame`` objects, empty if no frames match.

        """
        cutoff = timestamp - seconds
        with self._lock:
            return [f for f in self._deque if cutoff < f.timestamp <= timestamp]

    def get_frames_between(
        self,
        start_ts: float,
        end_ts: float,
    ) -> List[Frame]:
        """Return frames whose timestamp falls in ``[start_ts, end_ts)``.

        Args:
            start_ts: Start of the window (inclusive).
            end_ts: End of the window (exclusive).

        Returns:
            A list of ``Frame`` objects, oldest first.

        """
        with self._lock:
            return [f for f in self._deque if start_ts <= f.timestamp < end_ts]

    def get_all(self) -> List[Frame]:
        """Return a copy of all frames currently in the buffer (oldest first).

        Returns:
            A list of all frames held by the buffer.

        """
        with self._lock:
            return list(self._deque)

    def clear(self) -> None:
        """Discard all frames."""
        with self._lock:
            count = len(self._deque)
            self._deque.clear()
            if count > 0:
                logger.debug("FrameRingBuffer cleared {} frame(s)", count)

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        return f"<FrameRingBuffer size={self.size}/{self._maxlen}>"
