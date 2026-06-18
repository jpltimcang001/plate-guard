"""Integration tests for DashboardService.

Verifies that the service correctly aggregates data from multiple
repositories (CameraRepository + DetectionRepository) when backed
by a real in-memory SQLite database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.database.models import CameraModel, DetectionModel
from src.repositories.camera_repository import CameraRepository
from src.repositories.detection_repository import DetectionRepository
from src.services.dashboard_service import DashboardService

if TYPE_CHECKING:
    pass


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def populated_cameras(camera_repo: CameraRepository) -> list[CameraModel]:
    """Insert four cameras (2 enabled, 2 disabled)."""
    cams = [
        CameraModel(
            name="Front Gate",
            type="rtsp",
            rtsp_url="rtsp://192.168.1.10:554/stream",
            enabled=True,
        ),
        CameraModel(
            name="Back Gate",
            type="rtsp",
            rtsp_url="rtsp://192.168.1.11:554/stream",
            enabled=True,
        ),
        CameraModel(
            name="Parking Lot",
            type="usb",
            usb_index=1,
            enabled=False,
        ),
        CameraModel(
            name="Lobby",
            type="usb",
            usb_index=2,
            enabled=False,
        ),
    ]
    return [camera_repo.add(c) for c in cams]


@pytest.fixture
def populated_detections(
    detection_repo: DetectionRepository,
    populated_cameras: list[CameraModel],
) -> list[DetectionModel]:
    """Insert 15 detection records across the two enabled cameras."""
    import math
    from datetime import datetime

    dets: list[DetectionModel] = []
    for i in range(15):
        cam = populated_cameras[0] if i < 8 else populated_cameras[1]
        dets.append(
            DetectionModel(
                camera_id=cam.id,
                plate_number=f"PLT-{i:04d}",
                confidence=0.7 + (i % 3) * 0.1,
                detected_at=datetime(2026, 6, 18, 8, 0, 0)
                + __import__("datetime").timedelta(minutes=i * 10),
                webhook_status="success" if i % 2 == 0 else "pending",
            )
        )
    return detection_repo.bulk_insert(dets)


# ======================================================================
# DashboardService — refresh
# ======================================================================


class TestDashboardServiceRefresh:
    """Tests for DashboardService.refresh() with real data."""

    def test_refresh_returns_all_cameras(
        self,
        integration_dashboard_service: DashboardService,
        populated_cameras: list[CameraModel],
        populated_detections: list[DetectionModel],
    ) -> None:
        """refresh returns a DashboardData with all cameras."""
        data = integration_dashboard_service.refresh()
        assert len(data.cameras) == len(populated_cameras)

    def test_refresh_camera_status_maps_correctly(
        self,
        integration_dashboard_service: DashboardService,
        populated_cameras: list[CameraModel],
        populated_detections: list[DetectionModel],
    ) -> None:
        """Each camera in the result has the expected status fields."""
        data = integration_dashboard_service.refresh()
        for cam in data.cameras:
            assert cam.id in {c.id for c in populated_cameras}
            assert cam.name in {c.name for c in populated_cameras}
            # Should not be None
            assert cam.status is not None
            assert cam.camera_type is not None

    def test_refresh_total_detections_today(
        self,
        integration_dashboard_service: DashboardService,
        populated_cameras: list[CameraModel],
        populated_detections: list[DetectionModel],
    ) -> None:
        """total_detections_today matches the number of inserted detections."""
        data = integration_dashboard_service.refresh()
        assert data.total_detections_today == len(populated_detections)

    def test_refresh_recent_detections_limit(
        self,
        integration_dashboard_service: DashboardService,
        populated_cameras: list[CameraModel],
        populated_detections: list[DetectionModel],
    ) -> None:
        """recent_detections is limited to RECENT_DETECTIONS_LIMIT (20)."""
        data = integration_dashboard_service.refresh()
        assert len(data.recent_detections) <= DashboardService.RECENT_DETECTIONS_LIMIT

    def test_refresh_recent_detections_ordered(
        self,
        integration_dashboard_service: DashboardService,
        populated_cameras: list[CameraModel],
        populated_detections: list[DetectionModel],
    ) -> None:
        """recent_detections are ordered by detected_at descending."""
        data = integration_dashboard_service.refresh()
        # For older Pythons that don't support chained gt/lt on datetimes
        from datetime import datetime

        for i in range(len(data.recent_detections) - 1):
            assert data.recent_detections[i].detected_at >= data.recent_detections[i + 1].detected_at

    def test_refresh_no_detections(
        self,
        integration_dashboard_service: DashboardService,
        populated_cameras: list[CameraModel],
    ) -> None:
        """With cameras but no detections, counts are zero."""
        data = integration_dashboard_service.refresh()
        assert data.total_detections_today == 0
        assert len(data.recent_detections) == 0

    def test_refresh_no_cameras_no_detections(
        self,
        integration_dashboard_service: DashboardService,
    ) -> None:
        """With no cameras and no detections, the service returns empty data."""
        data = integration_dashboard_service.refresh()
        assert data.cameras == []
        assert data.total_detections_today == 0
        assert data.recent_detections == []

    def test_refresh_detection_summary_has_expected_fields(
        self,
        integration_dashboard_service: DashboardService,
        populated_cameras: list[CameraModel],
        populated_detections: list[DetectionModel],
    ) -> None:
        """Each recent detection in the summary has all expected attributes."""
        data = integration_dashboard_service.refresh()
        for det in data.recent_detections:
            assert det.plate_text is not None
            assert det.confidence >= 0.0
            assert det.camera_name is not None or det.camera_id is not None
            assert det.detected_at is not None
