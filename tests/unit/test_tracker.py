"""Unit tests for IOU computation and DetectionTracker.

Tests cover:
- ``compute_iou`` with overlapping, non-overlapping, edge-case boxes
- ``DetectionTracker`` initialisation, update, track lifecycle, eviction
- ``TrackedObject`` dataclass
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.detection.detection_result import DetectionResult
from src.detection.geometry import compute_iou
from src.detection.tracker import DetectionTracker, TrackedObject


# ======================================================================
# compute_iou
# ======================================================================


class TestComputeIou:
    """Tests for the Intersection-over-Union computation."""

    def test_identical_boxes(self) -> None:
        iou = compute_iou((0, 0, 10, 10), (0, 0, 10, 10))
        assert iou == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        iou = compute_iou((0, 0, 10, 10), (20, 20, 30, 30))
        assert iou == pytest.approx(0.0)

    def test_half_overlap(self) -> None:
        """Two boxes overlapping by half their area."""
        iou = compute_iou((0, 0, 10, 10), (5, 0, 15, 10))
        # Intersection = (5,0,10,10) = 50
        # Area A = 100, Area B = 100, Union = 150
        assert iou == pytest.approx(50.0 / 150.0)

    def test_one_contained_in_other(self) -> None:
        iou = compute_iou((0, 0, 10, 10), (2, 2, 8, 8))
        # Intersection = 6*6 = 36, Union = 100 + 36 - 36 = 100
        assert iou == pytest.approx(36.0 / 100.0)

    def test_touching_edges(self) -> None:
        """Boxes that touch edge-to-edge have zero IOU (zero-area intersection)."""
        iou = compute_iou((0, 0, 10, 10), (10, 0, 20, 10))
        assert iou == pytest.approx(0.0)

    def test_zero_area_box(self) -> None:
        iou = compute_iou((0, 0, 0, 0), (0, 0, 10, 10))
        assert iou == pytest.approx(0.0)

    def test_negative_coordinates(self) -> None:
        """Boxes can extend beyond frame boundaries (negative coords)."""
        iou = compute_iou((-10, -10, 10, 10), (-5, -5, 5, 5))
        assert iou > 0.0


# ======================================================================
# DetectionTracker
# ======================================================================


class TestDetectionTrackerInit:
    """Tests for tracker initialisation."""

    def test_default_params(self) -> None:
        tracker = DetectionTracker()
        assert tracker.iou_threshold == 0.3
        assert tracker.max_misses == 5

    def test_custom_params(self) -> None:
        tracker = DetectionTracker(iou_threshold=0.5, max_misses=3)
        assert tracker.iou_threshold == 0.5
        assert tracker.max_misses == 3

    def test_invalid_iou_zero(self) -> None:
        with pytest.raises(ValueError, match="iou_threshold"):
            DetectionTracker(iou_threshold=0.0)

    def test_invalid_iou_gt_one(self) -> None:
        with pytest.raises(ValueError, match="iou_threshold"):
            DetectionTracker(iou_threshold=1.5)

    def test_invalid_misses_zero(self) -> None:
        with pytest.raises(ValueError, match="max_misses"):
            DetectionTracker(max_misses=0)


class TestDetectionTrackerUpdate:
    """Tests for the core update() method."""

    def test_empty_detections_returns_empty(self) -> None:
        tracker = DetectionTracker()
        result = tracker.update(camera_id=1, detections=[])
        assert result == []

    def test_first_frame_creates_new_tracks(self) -> None:
        tracker = DetectionTracker()
        dets = [DetectionResult(bounding_box=(0, 0, 10, 10), confidence=0.9)]
        result = tracker.update(camera_id=1, detections=dets)

        assert len(result) == 1
        assert result[0].track_id == 1  # type: ignore[attr-defined]
        assert result[0].is_new is True  # type: ignore[attr-defined]

    def test_second_frame_matches_by_iou(self) -> None:
        tracker = DetectionTracker(iou_threshold=0.3)
        # Frame 1
        dets1 = [DetectionResult(bounding_box=(0, 0, 10, 10), confidence=0.9)]
        tracker.update(camera_id=1, detections=dets1)

        # Frame 2 — slightly moved box, should match
        dets2 = [DetectionResult(bounding_box=(1, 1, 11, 11), confidence=0.91)]
        result = tracker.update(camera_id=1, detections=dets2)

        assert len(result) == 1
        assert result[0].track_id == 1  # type: ignore[attr-defined]
        assert result[0].is_new is False  # type: ignore[attr-defined]

    def test_new_detection_in_second_frame_creates_new_track(self) -> None:
        tracker = DetectionTracker(iou_threshold=0.3)
        dets1 = [DetectionResult(bounding_box=(0, 0, 10, 10), confidence=0.9)]
        tracker.update(camera_id=1, detections=dets1)

        # Far away — new track
        dets2 = [DetectionResult(bounding_box=(100, 100, 110, 110), confidence=0.8)]
        result = tracker.update(camera_id=1, detections=dets2)

        assert len(result) == 1
        assert result[0].track_id == 2  # type: ignore[attr-defined]
        assert result[0].is_new is True  # type: ignore[attr-defined]

    def test_multiple_detections_matched_correctly(self) -> None:
        tracker = DetectionTracker(iou_threshold=0.3)
        # Frame 1: two detections
        dets1 = [
            DetectionResult(bounding_box=(0, 0, 10, 10), confidence=0.9),
            DetectionResult(bounding_box=(100, 100, 110, 110), confidence=0.8),
        ]
        tracker.update(camera_id=1, detections=dets1)

        # Frame 2: same two, slightly moved
        dets2 = [
            DetectionResult(bounding_box=(1, 1, 11, 11), confidence=0.91),
            DetectionResult(bounding_box=(101, 101, 111, 111), confidence=0.81),
        ]
        result = tracker.update(camera_id=1, detections=dets2)

        assert len(result) == 2
        # Both should be matched (not new)
        assert all(getattr(d, "is_new") is False for d in result)
        # Track IDs should be 1 and 2
        tids = sorted([getattr(d, "track_id") for d in result])
        assert tids == [1, 2]

    def test_camera_isolation(self) -> None:
        """Track IDs are independent per camera."""
        tracker = DetectionTracker()
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])
        tracker.update(camera_id=2, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])

        assert tracker.active_track_count(1) == 1
        assert tracker.active_track_count(2) == 1
        assert tracker.total_track_count() == 2

    def test_eviction_after_max_misses(self) -> None:
        """Track is evicted after ``max_misses`` consecutive unmatched frames.

        New tracks do NOT get a "miss" in the frame they are created.
        The first miss is counted in the next frame where the track
        is not matched.
        """
        tracker = DetectionTracker(iou_threshold=0.3, max_misses=2)
        # Frame 1: create track 1 (misses stays 0)
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])
        assert tracker.active_track_count(1) == 1

        # Frame 2: track 1 NOT matched → miss 1, track 2 created
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(100, 100, 110, 110))])

        # Check misses for both tracks
        tracks = {t.track_id: t for t in tracker.get_tracks(1)}
        assert tracks[1].consecutive_misses == 1  # first miss
        assert tracks[2].consecutive_misses == 0  # just created
        assert tracker.active_track_count(1) == 2

        # Frame 3: no detections → track 1 miss 2 (evicted), track 2 miss 1
        tracker.update(camera_id=1, detections=[])
        tracks = {t.track_id: t for t in tracker.get_tracks(1)}
        assert 1 not in tracks  # evicted
        assert tracks[2].consecutive_misses == 1
        assert tracker.active_track_count(1) == 1

    def test_eviction_keeps_matched_tracks(self) -> None:
        """Tracks that still get matched are not evicted."""
        tracker = DetectionTracker(iou_threshold=0.3, max_misses=2)
        # Frame 1: create track 1
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])

        # Frame 2: track 1 matched (misses 0), track 2 created
        tracker.update(camera_id=1, detections=[
            DetectionResult(bounding_box=(0, 0, 10, 10)),
            DetectionResult(bounding_box=(100, 100, 110, 110)),
        ])
        assert tracker.active_track_count(1) == 2

        # Frame 3: track 1 matched, track 2 unmatched → track 2 miss 1
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])
        assert tracker.active_track_count(1) == 2

        # Frame 4: track 1 matched, track 2 unmatched → miss 2 → evicted
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])
        assert tracker.active_track_count(1) == 1  # only track 1 remains

    def test_consecutive_misses_reset_on_match(self) -> None:
        tracker = DetectionTracker(iou_threshold=0.3, max_misses=3)
        # Create track
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])

        # Miss: frame with detections that don't match track 1
        # (new track gets created, track 1 gets a miss)
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(100, 100, 110, 110))])
        # Track 1 has 1 miss, track 2 was just created
        tracks = tracker.get_tracks(1)
        track1 = [t for t in tracks if t.track_id == 1][0]
        assert track1.consecutive_misses == 1

        # Match track 1 again
        tracker.update(camera_id=1, detections=[DetectionResult(bounding_box=(0, 0, 10, 10))])
        track1 = [t for t in tracker.get_tracks(1) if t.track_id == 1][0]
        assert track1.consecutive_misses == 0

    def test_greedy_matching_picks_highest_iou(self) -> None:
        """When two tracks compete for one detection, highest IOU wins."""
        tracker = DetectionTracker(iou_threshold=0.3)
        # Create two tracks: track 1 at (0,0,20,20), track 2 at (30,0,50,20)
        tracker.update(camera_id=1, detections=[
            DetectionResult(bounding_box=(0, 0, 20, 20)),    # track 1
            DetectionResult(bounding_box=(30, 0, 50, 20)),   # track 2
        ])

        # New detection at (5,0,25,20) — IOU with track1 = 300/500 = 0.6,
        # IOU with track2 = 100/700 ≈ 0.14
        # Track 1 wins
        result = tracker.update(camera_id=1, detections=[
            DetectionResult(bounding_box=(5, 0, 25, 20)),
        ])

        assert len(result) == 1
        assert result[0].track_id == 1  # type: ignore[attr-defined]


class TestDetectionTrackerReset:
    """Tests for reset functionality."""

    def test_reset_single_camera(self) -> None:
        tracker = DetectionTracker()
        tracker.update(1, [DetectionResult(bounding_box=(0, 0, 10, 10))])
        tracker.update(2, [DetectionResult(bounding_box=(0, 0, 10, 10))])
        tracker.reset(camera_id=1)
        assert tracker.active_track_count(1) == 0
        assert tracker.active_track_count(2) == 1

    def test_reset_all(self) -> None:
        tracker = DetectionTracker()
        tracker.update(1, [DetectionResult(bounding_box=(0, 0, 10, 10))])
        tracker.update(2, [DetectionResult(bounding_box=(0, 0, 10, 10))])
        tracker.reset()
        assert tracker.total_track_count() == 0


class TestDetectionTrackerStats:
    """Tests for tracker statistics and helpers."""

    def test_get_tracks_empty(self) -> None:
        tracker = DetectionTracker()
        assert tracker.get_tracks(1) == []

    def test_get_tracks_returns_sorted(self) -> None:
        tracker = DetectionTracker()
        tracker.update(1, [DetectionResult(bounding_box=(0, 0, 10, 10))])
        tracker.update(1, [DetectionResult(bounding_box=(100, 100, 110, 110))])
        tracks = tracker.get_tracks(1)
        assert len(tracks) == 2
        assert tracks[0].track_id < tracks[1].track_id

    def test_stats_dict(self) -> None:
        tracker = DetectionTracker(iou_threshold=0.5, max_misses=3)
        tracker.update(1, [DetectionResult(bounding_box=(0, 0, 10, 10))])
        stats = tracker.stats(1)
        assert stats["active_tracks"] == 1
        assert stats["next_id"] == 2
        assert stats["iou_threshold"] == 0.5
        assert stats["max_misses"] == 3

    def test_repr(self) -> None:
        tracker = DetectionTracker()
        rep = repr(tracker)
        assert "DetectionTracker" in rep
        assert "iou=0.3" in rep
