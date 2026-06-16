"""Simple IOU-based detection tracker for cross-frame plate association.

Tracks detected plates across consecutive frames by computing
Intersection-over-Union (IOU) between bounding boxes in frame N
vs. tracked objects from frame N-1.  When IOU exceeds a threshold,
the detection is associated with an existing track and assigned that
track's ID.  Unmatched detections start new tracks.

This prevents re-detecting the same physical plate as a new event
in every frame and enables downstream components (OCR, webhook) to
operate on a per-track basis rather than per-frame.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List

from loguru import logger

from src.detection.detection_result import DetectionResult
from src.detection.geometry import compute_iou


@dataclass
class TrackedObject:
    """A tracked object maintained across frames.

    Attributes:
        track_id: Globally unique (per camera) track identifier.
        detection: The most recent DetectionResult for this track.
        first_seen: Monotonic timestamp when the track was created.
        last_seen: Monotonic timestamp when the track was last updated.
        consecutive_misses: Number of consecutive frames where this
            track had no matching detection.
    """

    track_id: int
    detection: DetectionResult = field(repr=False)
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    consecutive_misses: int = 0


class DetectionTracker:
    """IOU-based tracker that assigns stable IDs across frames.

    Maintains a set of active tracks per camera.  Each frame,
    ``update()`` takes the current frame's detections, matches
    them to existing tracks by IOU, and returns the updated
    detections with ``track_id`` and ``is_new`` metadata.

    Tracks that go unmatched for ``max_misses`` consecutive frames
    are evicted.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_misses: int = 5,
    ) -> None:
        """Initialize the tracker.

        Args:
            iou_threshold: Minimum IOU to consider two detections
                the same object (default 0.3).
            max_misses: Number of consecutive frames a track can go
                unmatched before being evicted (default 5).

        """
        if not 0.0 < iou_threshold <= 1.0:
            raise ValueError(
                f"iou_threshold must be in (0.0, 1.0], got {iou_threshold}",
            )
        if max_misses < 1:
            raise ValueError(
                f"max_misses must be >= 1, got {max_misses}",
            )

        self._iou_threshold = iou_threshold
        self._max_misses = max_misses

        # camera_id -> {track_id: TrackedObject}
        self._tracks: Dict[int, Dict[int, TrackedObject]] = {}
        # camera_id -> next_track_id
        self._next_id: Dict[int, int] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def iou_threshold(self) -> float:
        """IOU threshold for matching."""
        return self._iou_threshold

    @property
    def max_misses(self) -> int:
        """Max consecutive misses before eviction."""
        return self._max_misses

    def active_track_count(self, camera_id: int) -> int:
        """Return the number of active tracks for a camera."""
        return len(self._tracks.get(camera_id, {}))

    def total_track_count(self) -> int:
        """Return total active tracks across all cameras."""
        return sum(len(t) for t in self._tracks.values())

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    def update(
        self,
        camera_id: int,
        detections: list[DetectionResult],
    ) -> list[DetectionResult]:
        """Process detections for a new frame and assign track IDs.

        Args:
            camera_id: The camera that produced the frame.
            detections: Raw detections from this frame.

        Returns:
            The same list of ``DetectionResult`` objects (in-place
            modification), each augmented with a ``track_id`` attribute
            (an ``int``) and an ``is_new`` attribute (a ``bool``).

        """
        if camera_id not in self._tracks:
            self._tracks[camera_id] = {}
            self._next_id[camera_id] = 1

        current_tracks = self._tracks[camera_id]

        # Build IOU matrix between current tracks and new detections
        # (track_index, detection_index) -> iou
        matched_detections: set[int] = set()
        matched_tracks: set[int] = set()

        # Greedy matching: sort by IOU descending
        candidates: list[tuple[float, int, int]] = []
        for tid, tobj in current_tracks.items():
            for didx, det in enumerate(detections):
                iou = compute_iou(tobj.detection.bounding_box, det.bounding_box)
                if iou >= self._iou_threshold:
                    candidates.append((iou, tid, didx))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for _iou, tid, didx in candidates:
            if tid in matched_tracks or didx in matched_detections:
                continue
            matched_tracks.add(tid)
            matched_detections.add(didx)

            # Update existing track
            tobj = current_tracks[tid]
            tobj.detection = detections[didx]
            tobj.last_seen = time.monotonic()
            tobj.consecutive_misses = 0
            detections[didx].track_id = tid  # type: ignore[attr-defined]
            detections[didx].is_new = False  # type: ignore[attr-defined]

        # New tracks for unmatched detections (track newly-created IDs so
        # they don't get a "miss" in the frame they are created).
        newly_created: set[int] = set()
        for didx, det in enumerate(detections):
            if didx in matched_detections:
                continue

            tid = self._next_id[camera_id]
            self._next_id[camera_id] = tid + 1
            newly_created.add(tid)

            current_tracks[tid] = TrackedObject(
                track_id=tid,
                detection=det,
            )
            det.track_id = tid  # type: ignore[attr-defined]
            det.is_new = True  # type: ignore[attr-defined]

        # Increment misses for unmatched tracks and evict stale ones.
        # Newly-created tracks are skipped — they haven't had a chance
        # to miss a frame yet.
        evicted: list[int] = []
        for tid, tobj in list(current_tracks.items()):
            if tid in matched_tracks or tid in newly_created:
                continue
            tobj.consecutive_misses += 1
            if tobj.consecutive_misses >= self._max_misses:
                evicted.append(tid)

        for tid in evicted:
            del current_tracks[tid]

        if evicted:
            logger.debug(
                "DetectionTracker(camera={}) evicted {} stale track(s)",
                camera_id,
                len(evicted),
            )

        return detections

    def reset(self, camera_id: int | None = None) -> None:
        """Clear all tracks for one or all cameras.

        Args:
            camera_id: If provided, reset only this camera.
                If ``None``, reset all cameras.

        """
        if camera_id is not None:
            self._tracks.pop(camera_id, None)
            self._next_id.pop(camera_id, None)
        else:
            self._tracks.clear()
            self._next_id.clear()

    def get_tracks(self, camera_id: int) -> list[TrackedObject]:
        """Return all active tracks for a camera (ordered by track_id)."""
        return sorted(
            self._tracks.get(camera_id, {}).values(),
            key=lambda t: t.track_id,
        )

    def stats(self, camera_id: int) -> dict:
        """Return tracking statistics for a camera.

        Args:
            camera_id: The camera ID.

        Returns:
            Dict with keys ``active_tracks``, ``next_id``, ``max_misses``,
            ``iou_threshold``.

        """
        return {
            "active_tracks": self.active_track_count(camera_id),
            "next_id": self._next_id.get(camera_id, 1),
            "max_misses": self._max_misses,
            "iou_threshold": self._iou_threshold,
        }

    def __repr__(self) -> str:
        return (
            f"<DetectionTracker iou={self._iou_threshold} "
            f"misses={self._max_misses} "
            f"total_tracks={self.total_track_count()}>"
        )
