"""Cooldown-based duplicate plate filter.

Prevents the same license plate text from being logged multiple times
within a configurable time window.  After OCR recognises a plate, the
filter records the timestamp.  Subsequent detections of the same plate
text within the cooldown period are suppressed.

This is essential for real-world deployments where a stopped car would
otherwise generate hundreds of identical detection logs per minute.
"""

from __future__ import annotations

import time
from typing import Dict

from loguru import logger


class DuplicateFilter:
    """Suppresses re-detection of the same plate text within a cooldown.

    Thread-safe if the cooldown map is only accessed from a single
    thread (which is the intended usage — one pipeline instance per
    camera, each in its own thread).

    Usage::

        filt = DuplicateFilter(cooldown_seconds=5.0)

        if not filt.is_duplicate("ABC123"):
            log_detection("ABC123")
            filt.record("ABC123")
    """

    def __init__(self, cooldown_seconds: float = 5.0) -> None:
        """Initialise the duplicate filter.

        Args:
            cooldown_seconds: Minimum seconds between consecutive
                detections of the same plate text.  Set to ``0`` to
                disable filtering.

        """
        if cooldown_seconds < 0:
            raise ValueError(
                f"cooldown_seconds must be >= 0, got {cooldown_seconds}",
            )

        self._cooldown = cooldown_seconds
        # plate_text -> monotonic timestamp of last recorded detection
        self._last_seen: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cooldown_seconds(self) -> float:
        """Current cooldown period in seconds."""
        return self._cooldown

    @cooldown_seconds.setter
    def cooldown_seconds(self, value: float) -> None:
        """Set a new cooldown period.

        Args:
            value: New cooldown in seconds (>= 0).

        """
        if value < 0:
            raise ValueError(
                f"cooldown_seconds must be >= 0, got {value}",
            )
        self._cooldown = value

    @property
    def tracked_plates(self) -> int:
        """Number of unique plate texts currently in the filter."""
        return len(self._last_seen)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_duplicate(self, plate_text: str, now: float | None = None) -> bool:
        """Check whether a plate text is a duplicate (within cooldown).

        Args:
            plate_text: The recognised plate text.
            now: Optional monotonic timestamp.  If ``None``,
                ``time.monotonic()`` is used.

        Returns:
            ``True`` if the plate was seen within the cooldown window,
            ``False`` otherwise.

        """
        if not plate_text:
            return False

        if self._cooldown <= 0:
            return False

        now = now if now is not None else time.monotonic()
        last = self._last_seen.get(plate_text)

        if last is None:
            return False

        return (now - last) < self._cooldown

    def record(self, plate_text: str, now: float | None = None) -> None:
        """Record a detection for the given plate text.

        Updates the last-seen timestamp so that future ``is_duplicate``
        calls within the cooldown window return ``True``.

        Args:
            plate_text: The recognised plate text.
            now: Optional monotonic timestamp.

        """
        if not plate_text:
            return

        if self._cooldown <= 0:
            return

        now = now if now is not None else time.monotonic()
        self._last_seen[plate_text] = now
        logger.debug(
            "DuplicateFilter recorded '{plate}' at {ts:.3f}",
            plate=plate_text,
            ts=now,
        )

    def check_and_record(
        self,
        plate_text: str,
        now: float | None = None,
    ) -> bool:
        """Convenience: check then record in one call.

        Args:
            plate_text: The recognised plate text.
            now: Optional monotonic timestamp.

        Returns:
            ``True`` if the plate was accepted (not a duplicate),
            ``False`` if it was suppressed.

        """
        if self.is_duplicate(plate_text, now=now):
            logger.debug(
                "DuplicateFilter suppressed '{plate}'",
                plate=plate_text,
            )
            return False

        self.record(plate_text, now=now)
        return True

    def clear(self, plate_text: str | None = None) -> None:
        """Clear the filter state.

        Args:
            plate_text: If provided, clear only this plate.
                If ``None``, clear all tracked plates.

        """
        if plate_text is not None:
            self._last_seen.pop(plate_text, None)
        else:
            self._last_seen.clear()

    def stats(self) -> dict:
        """Return filter statistics.

        Returns:
            Dict with keys ``cooldown_seconds``, ``tracked_plates``.

        """
        return {
            "cooldown_seconds": self._cooldown,
            "tracked_plates": len(self._last_seen),
        }

    def __repr__(self) -> str:
        return (
            f"<DuplicateFilter cooldown={self._cooldown}s "
            f"tracked={len(self._last_seen)}>"
        )
