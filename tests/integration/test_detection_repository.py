"""Integration tests for DetectionRepository.

Tests CRUD operations, filtered queries, pagination, status updates,
recent-record retrieval, and bulk purging against a real in-memory
SQLite database.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from src.database.models import DetectionModel
from src.repositories.detection_repository import DetectionFilter, DetectionRepository

if TYPE_CHECKING:
    pass


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def many_detections(
    detection_repo: DetectionRepository,
    seeded_camera: DetectionModel,
) -> list[DetectionModel]:
    """Insert 25 detection records over 3 days for pagination/filter tests.

    Days 0‑2 (today, yesterday, two days ago), 8–9 records per day.
    Camera IDs alternate between the seeded camera and a second camera
    (created inline) to exercise multi-camera filtering.
    """
    from src.database.models import CameraModel

    # Create a second camera
    camera2 = CameraModel(
        name="Second Camera",
        type="usb",
        usb_index=1,
        confidence_threshold=0.5,
        enabled=True,
    )
    from src.repositories.camera_repository import CameraRepository

    camera2 = CameraRepository(
        detection_repo._session_manager  # type: ignore[attr-defined]
    ).add(camera2)

    dets: list[DetectionModel] = []
    base = datetime(2026, 6, 18, 8, 0, 0)
    for i in range(25):
        day_offset = i // 8  # 0, 1, 2
        cam_id = seeded_camera.id if i % 2 == 0 else camera2.id
        det = DetectionModel(
            camera_id=cam_id,
            plate_number=f"PLATE-{i:04d}" if i % 3 != 0 else None,
            confidence=0.5 + (i % 5) * 0.1,
            detected_at=base - timedelta(days=day_offset, hours=12 - (i % 24)),
            webhook_status="not_configured",
        )
        dets.append(det)
    return detection_repo.bulk_insert(dets)


# ======================================================================
# DetectionRepository — CRUD
# ======================================================================


class TestDetectionRepositoryCRUD:
    """Tests for basic add / get / update / delete operations."""

    def test_add_and_get_by_id(
        self,
        detection_repo: DetectionRepository,
        seeded_camera: DetectionModel,
    ) -> None:
        """Adding a detection and fetching it by ID returns the same record."""
        det = DetectionModel(
            camera_id=seeded_camera.id,
            plate_number="XYZ-789",
            confidence=0.85,
        )
        saved = detection_repo.add(det)
        assert saved.id is not None and saved.id > 0
        assert saved.plate_number == "XYZ-789"

        fetched = detection_repo.get_by_id(saved.id)
        assert fetched is not None
        assert fetched.plate_number == "XYZ-789"
        assert fetched.camera_id == seeded_camera.id

    def test_get_by_id_not_found(
        self,
        detection_repo: DetectionRepository,
    ) -> None:
        """Fetching a non‑existent ID returns None."""
        assert detection_repo.get_by_id(999_999) is None

    def test_get_all(
        self,
        detection_repo: DetectionRepository,
        seeded_detection: DetectionModel,
    ) -> None:
        """get_all returns all persisted records."""
        all_ = detection_repo.get_all()
        assert len(all_) >= 1
        assert seeded_detection.id in {d.id for d in all_}

    def test_delete(
        self,
        detection_repo: DetectionRepository,
        seeded_detection: DetectionModel,
    ) -> None:
        """Deleting a detection removes it and returns True."""
        assert detection_repo.delete(seeded_detection.id) is True
        assert detection_repo.get_by_id(seeded_detection.id) is None

    def test_delete_not_found(
        self,
        detection_repo: DetectionRepository,
    ) -> None:
        """Deleting a non‑existent ID returns False."""
        assert detection_repo.delete(999_999) is False

    def test_update_webhook_status(
        self,
        detection_repo: DetectionRepository,
        seeded_detection: DetectionModel,
    ) -> None:
        """update_webhook_status changes the stored status."""
        updated = detection_repo.update_webhook_status(
            seeded_detection.id,
            "success",
        )
        assert updated is True
        refreshed = detection_repo.get_by_id(seeded_detection.id)
        assert refreshed is not None
        assert refreshed.webhook_status == "success"

    def test_update_webhook_status_not_found(
        self,
        detection_repo: DetectionRepository,
    ) -> None:
        """update_webhook_status on a non‑existent ID returns False."""
        assert (
            detection_repo.update_webhook_status(999_999, "success") is False
        )

    def test_count_empty(
        self,
        detection_repo: DetectionRepository,
    ) -> None:
        """count returns 0 when no records exist."""
        assert detection_repo.count() == 0

    def test_count_after_insert(
        self,
        detection_repo: DetectionRepository,
        seeded_detection: DetectionModel,
    ) -> None:
        """count reflects the number of persisted records."""
        assert detection_repo.count() >= 1


# ======================================================================
# DetectionRepository — Filtered queries
# ======================================================================


class TestDetectionRepositoryFiltered:
    """Tests for get_filtered, count_filtered with various criteria."""

    def test_filter_no_criteria_returns_all(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """An empty filter returns all records up to the default limit."""
        result = detection_repo.get_filtered(DetectionFilter(limit=100))
        assert len(result) == len(many_detections)

    def test_filter_by_camera_id(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
        seeded_camera: DetectionModel,
    ) -> None:
        """Filtering by camera_id returns only records for that camera."""
        filt = DetectionFilter(
            camera_id=seeded_camera.id,
            limit=100,
        )
        result = detection_repo.get_filtered(filt)
        assert all(d.camera_id == seeded_camera.id for d in result)

    def test_filter_by_plate_number(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """Filtering by plate_number does a case‑insensitive substring match."""
        # At least one record has "PLATE-0000"
        filt = DetectionFilter(plate_number="plate-00", limit=100)
        result = detection_repo.get_filtered(filt)
        assert len(result) >= 1
        assert all("plate-00" in (d.plate_number or "").lower() for d in result)

    def test_filter_by_plate_number_no_match(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """A filter that matches nothing returns an empty list."""
        filt = DetectionFilter(plate_number="NONEXISTENT999")
        assert detection_repo.get_filtered(filt) == []

    def test_filter_by_date_range(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """Filtering by date_from/date_to narrows the result set."""
        # All records are on or after 2026-06-16
        filt = DetectionFilter(
            date_from=datetime(2026, 6, 18, 0, 0, 0),
            limit=100,
        )
        result = detection_repo.get_filtered(filt)
        assert all(d.detected_at >= datetime(2026, 6, 18, 0, 0, 0) for d in result)

    def test_filter_pagination(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """Offset and limit work correctly for pagination."""
        page1 = detection_repo.get_filtered(DetectionFilter(limit=5, offset=0))
        page2 = detection_repo.get_filtered(DetectionFilter(limit=5, offset=5))
        assert len(page1) == 5
        assert len(page2) == 5
        # Pages should not overlap
        ids_page1 = {d.id for d in page1}
        ids_page2 = {d.id for d in page2}
        assert ids_page1.isdisjoint(ids_page2)

    def test_count_filtered(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
        seeded_camera: DetectionModel,
    ) -> None:
        """count_filtered returns the matching record count (ignoring limit)."""
        total = detection_repo.count_filtered(DetectionFilter(limit=100))
        assert total == len(many_detections)

        camera_count = detection_repo.count_filtered(
            DetectionFilter(camera_id=seeded_camera.id, limit=100),
        )
        expected = sum(
            1 for d in many_detections if d.camera_id == seeded_camera.id
        )
        assert camera_count == expected

    def test_filter_order_is_descending(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """Results are ordered by detected_at DESC."""
        result = detection_repo.get_filtered(DetectionFilter(limit=100))
        dates = [d.detected_at for d in result]
        assert dates == sorted(dates, reverse=True)


# ======================================================================
# DetectionRepository — get_recent & delete_older_than
# ======================================================================


class TestDetectionRepositoryMaintenance:
    """Tests for get_recent and bulk-delete (retention)."""

    def test_get_recent_returns_latest(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """get_recent returns the N most recent records in order."""
        recent = detection_repo.get_recent(count=5)
        assert len(recent) == 5
        # Most recent first
        dates = [d.detected_at for d in recent]
        assert dates == sorted(dates, reverse=True)

    def test_get_recent_less_than_requested(
        self,
        detection_repo: DetectionRepository,
    ) -> None:
        """get_recent returns fewer records when not enough exist."""
        # No records inserted yet
        assert detection_repo.get_recent(count=100) == []

    def test_delete_older_than(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """delete_older_than removes records before the cutoff."""
        cutoff = datetime(2026, 6, 17, 0, 0, 0)
        deleted = detection_repo.delete_older_than(cutoff)
        assert deleted > 0

        remaining = detection_repo.get_all()
        assert all(d.detected_at >= cutoff for d in remaining)

    def test_delete_older_than_nothing_to_delete(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """delete_older_than returns 0 when no records are old enough."""
        cutoff = datetime(2026, 6, 1, 0, 0, 0)
        deleted = detection_repo.delete_older_than(cutoff)
        assert deleted == 0

    def test_delete_older_than_respects_count(
        self,
        detection_repo: DetectionRepository,
        many_detections: list[DetectionModel],
    ) -> None:
        """After delete_older_than, .count() reflects the deletion."""
        cutoff = datetime(2026, 6, 17, 12, 0, 0)
        before = detection_repo.count()
        deleted = detection_repo.delete_older_than(cutoff)
        after = detection_repo.count()
        assert after == before - deleted
