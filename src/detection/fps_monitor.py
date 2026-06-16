"""Frames-per-second monitor using a sliding window.

Tracks frame timestamps to compute a stable rolling average FPS
without the jitter of instantaneous measurements.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any


class FpsMonitor:
    """Monitors frame rate using a sliding window of timestamps.

    Usage::

        monitor = FpsMonitor(window_seconds=5.0)
        while capturing:
            frame = capture()
            monitor.tick()
            current_fps = monitor.fps  # stable rolling average

    """

    def __init__(self, window_seconds: float = 5.0, camera_id: int = 0) -> None:
        """Initialize the FPS monitor.

        Args:
            window_seconds: Duration of the sliding window in seconds.
                Longer windows produce smoother readings but react slower
                to changes.
            camera_id: The camera ID (for logging context).

        """
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self._window_seconds = window_seconds
        self._camera_id = camera_id
        self._timestamps: deque[float] = deque()
        self._total_frames: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def window_seconds(self) -> float:
        """Return the sliding window duration."""
        return self._window_seconds

    def tick(self) -> None:
        """Record one frame at the current time.

        Call this once per frame, immediately after capture.
        """
        now = time.monotonic()
        self._timestamps.append(now)
        self._total_frames += 1
        self._prune(now)

    @property
    def fps(self) -> float:
        """Return the rolling average FPS.

        Returns 0.0 if fewer than 2 frames have been recorded.
        """
        if len(self._timestamps) < 2:
            return 0.0

        # Prune first so the window is up to date
        self._prune(time.monotonic())

        if len(self._timestamps) < 2:
            return 0.0

        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed <= 0:
            return 0.0

        # Only count unique timestamps within the window
        return (len(self._timestamps) - 1) / elapsed

    @property
    def min_fps(self) -> float:
        """Return the minimum FPS observed during the window."""
        return self._compute_extreme(min)

    @property
    def max_fps(self) -> float:
        """Return the maximum FPS observed during the window."""
        return self._compute_extreme(max)

    @property
    def total_frames(self) -> int:
        """Return the total number of frames recorded since creation."""
        return self._total_frames

    @property
    def current_fps(self) -> float:
        """Alias for ``.fps``."""
        return self.fps

    def reset(self) -> None:
        """Clear all recorded timestamps and reset counters."""
        self._timestamps.clear()
        self._total_frames = 0

    def stats(self) -> dict[str, Any]:
        """Return a snapshot of FPS statistics.

        Returns:
            Dict with keys: ``fps``, ``min_fps``, ``max_fps``,
            ``total_frames``, ``window_seconds``.

        """
        return {
            "fps": round(self.fps, 2),
            "min_fps": round(self.min_fps, 2),
            "max_fps": round(self.max_fps, 2),
            "total_frames": self._total_frames,
            "window_seconds": self._window_seconds,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self, now: float) -> None:
        """Remove timestamps older than the sliding window."""
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def _compute_extreme(self, aggr_func: callable) -> float:
        """Compute the min or max instantaneous FPS from the window.

        Args:
            aggr_func: ``min`` or ``max`` builtin.

        Returns:
            The extreme FPS value, or 0.0 if insufficient data.

        """
        if len(self._timestamps) < 3:
            return 0.0

        # Prune stale timestamps first
        self._prune(time.monotonic())

        if len(self._timestamps) < 3:
            return 0.0

        diffs = [
            self._timestamps[i + 1] - self._timestamps[i]
            for i in range(len(self._timestamps) - 1)
        ]
        # 1 / diff gives instantaneous FPS for each inter-frame gap
        inst_values = [1.0 / d for d in diffs if d > 0]
        if not inst_values:
            return 0.0
        return aggr_func(inst_values)

    def __repr__(self) -> str:
        return (
            f"<FpsMonitor camera={self._camera_id} "
            f"fps={self.fps:.1f} total={self._total_frames}>"
        )
