"""Unit tests for DashboardService.

Uses mocked ``CameraService`` and ``DetectionRepository`` so no
database or real service layer is involved.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List
from unittest.mock import MagicMock, create_autospec

import pytest

from src.application.dto.camera_dto import CameraDTO
from src.application.dto.dashboard_dto import DashboardData
from src.database.models import DetectionModel
from src.repositories.detection_repository import DetectionFilter
from src.services.camera_service import CameraService
from src.services.dashboard_service import DashboardService

# ======================================================================
# Helpers
# ======================================================================


def _make_camera_dto(
    camera_id: int = 1,
    name: str = "Test Camera",
    enabled: bool = True,
) -> CameraDTO:
    """Create a ``CameraDTO`` for test fixtures."""
    return CameraDTO(
        id=camera_id,
        name=name,
        camera_type="rtsp",
        rtsp_url="rtsp://127.0.0.1:554/stream",
        usb_index=None,
        enabled=enabled,
        confidence_threshold=0.5,
        evidence_mode="none",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _make_detection_model(
    detection_id: int = 1,
    camera_id: int = 1,
    plate: str = "ABC123",
    confidence: float = 0.95,
    detected_at: datetime | None = None,
) -> DetectionModel:
    """Create a ``DetectionModel`` with the minimum required fields.

    The model is not added to any session — it is just a plain
    instance with attributes set.
    """
    model = DetectionModel()
    model.id = detection_id
    model.camera_id = camera_id
    model.plate_number = plate
    model.confidence = confidence
    model.image_path = f"/media/snap_{detection_id}.jpg"
    model.video_path = f"/media/clip_{detection_id}.mp4"
    model.webhook_status = "success"
    model.detected_at = detected_at or datetime.now()
    return model


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def mock_camera_service() -> MagicMock:
    """Create an auto-specced mock for CameraService."""
    mock = create_autospec(CameraService, instance=True)
    # Default: no cameras
    mock.get_all_cameras.return_value = []
    return mock


@pytest.fixture
def mock_detection_repo() -> MagicMock:
    """Create an auto-specced mock for DetectionRepository."""
    mock = MagicMock()
    # Default: no detections
    mock.count_filtered.return_value = 0
    mock.get_filtered.return_value = []
    return mock


@pytest.fixture
def dashboard_service(
    mock_camera_service: MagicMock,
    mock_detection_repo: MagicMock,
) -> DashboardService:
    """Build a DashboardService with mocked dependencies."""
    return DashboardService(
        camera_service=mock_camera_service,
        detection_repository=mock_detection_repo,
    )


# ======================================================================
# Tests
# ======================================================================


class TestRefresh:
    """DashboardService.refresh() behaviour."""

    def test_refresh_with_no_cameras(
        self,
        dashboard_service: DashboardService,
    ) -> None:
        """Empty system returns a DashboardData with zeros."""
        data = dashboard_service.refresh()

        assert isinstance(data, DashboardData)
        assert data.cameras == []
        assert data.total_detections_today == 0
        assert data.detection_count_by_camera == {}
        assert data.recent_detections == []
        assert data.cameras_online == 0
        assert data.cameras_offline == 0
        assert data.cameras_disabled == 0
        assert data.refreshed_at is not None

    def test_refresh_with_one_camera(
        self,
        mock_camera_service: MagicMock,
        mock_detection_repo: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """Single enabled camera is reflected in the dashboard data."""
        mock_camera_service.get_all_cameras.return_value = [
            _make_camera_dto(camera_id=1, name="Gate 1"),
        ]
        mock_detection_repo.count_filtered.return_value = 5

        data = dashboard_service.refresh()

        assert len(data.cameras) == 1
        assert data.cameras[0].name == "Gate 1"
        assert data.cameras[0].status == "online"
        assert data.cameras[0].detection_count_today == 5
        assert data.total_detections_today == 5
        assert data.cameras_online == 1
        assert data.cameras_offline == 0
        assert data.cameras_disabled == 0

    def test_refresh_with_disabled_camera(
        self,
        mock_camera_service: MagicMock,
        mock_detection_repo: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """Disabled camera appears with status 'disabled'."""
        mock_camera_service.get_all_cameras.return_value = [
            _make_camera_dto(camera_id=1, name="Gate 1", enabled=False),
        ]
        mock_detection_repo.count_filtered.return_value = 0

        data = dashboard_service.refresh()

        assert len(data.cameras) == 1
        assert data.cameras[0].enabled is False
        assert data.cameras[0].status == "disabled"
        assert data.cameras_online == 0
        assert data.cameras_offline == 0
        assert data.cameras_disabled == 1

    def test_refresh_with_multiple_cameras(
        self,
        mock_camera_service: MagicMock,
        mock_detection_repo: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """Multiple cameras with mixed status are counted correctly."""
        mock_camera_service.get_all_cameras.return_value = [
            _make_camera_dto(camera_id=1, name="Gate 1", enabled=True),
            _make_camera_dto(camera_id=2, name="Gate 2", enabled=True),
            _make_camera_dto(camera_id=3, name="Lobby", enabled=False),
        ]

        # Per-camera counts returned by repo.
        # The first call (camera_id=None) returns total; subsequent
        # calls are per-camera.
        _call_count: list[int] = []

        def _side_effect(filter_: DetectionFilter) -> int:
            _call_count.append(1)
            if len(_call_count) == 1:
                # First call — total for all cameras
                return 15
            if filter_.camera_id == 1:
                return 10
            if filter_.camera_id == 2:
                return 5
            if filter_.camera_id == 3:
                return 0
            return 0

        mock_detection_repo.count_filtered.side_effect = _side_effect
        mock_detection_repo.get_filtered.return_value = []

        data = dashboard_service.refresh()

        assert len(data.cameras) == 3
        assert data.cameras[0].detection_count_today == 10
        assert data.cameras[1].detection_count_today == 5
        assert data.cameras[2].detection_count_today == 0

        assert data.cameras_online == 2
        assert data.cameras_offline == 0
        assert data.cameras_disabled == 1

        # Total should be sum of all per-camera counts
        assert data.total_detections_today == 15

    def test_refresh_includes_recent_detections(
        self,
        mock_camera_service: MagicMock,
        mock_detection_repo: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """Recent detections are mapped to DetectionSummaryDTO."""
        mock_camera_service.get_all_cameras.return_value = [
            _make_camera_dto(camera_id=1, name="Gate 1"),
        ]

        det_model = _make_detection_model(
            detection_id=42,
            camera_id=1,
            plate="XYZ789",
            confidence=0.88,
        )
        mock_detection_repo.get_filtered.return_value = [det_model]
        mock_detection_repo.count_filtered.return_value = 1

        data = dashboard_service.refresh()

        assert len(data.recent_detections) == 1
        recent = data.recent_detections[0]
        assert recent.id == 42
        assert recent.camera_id == 1
        assert recent.camera_name == "Gate 1"
        assert recent.plate_text == "XYZ789"
        assert recent.confidence == 0.88
        assert recent.webhook_status == "success"

    def test_refresh_handles_empty_recent_detections(
        self,
        dashboard_service: DashboardService,
    ) -> None:
        """When there are no detections, recent list is empty."""
        data = dashboard_service.refresh()
        assert data.recent_detections == []

    def test_refresh_camera_name_fallback(
        self,
        mock_camera_service: MagicMock,
        mock_detection_repo: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """Detection with unknown camera_id gets fallback name."""
        mock_camera_service.get_all_cameras.return_value = [
            _make_camera_dto(camera_id=1, name="Gate 1"),
        ]

        det_model = _make_detection_model(
            detection_id=1,
            camera_id=99,  # not in camera list
            plate="TEST",
            confidence=0.5,
        )
        mock_detection_repo.get_filtered.return_value = [det_model]
        mock_detection_repo.count_filtered.return_value = 1

        data = dashboard_service.refresh()

        assert data.recent_detections[0].camera_name == "Camera #99"

    def test_refresh_sets_refreshed_at(
        self,
        dashboard_service: DashboardService,
    ) -> None:
        """The refreshed_at timestamp is set on each refresh."""
        data = dashboard_service.refresh()
        assert data.refreshed_at is not None
        assert isinstance(data.refreshed_at, datetime)

    def test_refresh_detection_count_by_camera_map(
        self,
        mock_camera_service: MagicMock,
        mock_detection_repo: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """detection_count_by_camera maps camera_id → count."""
        mock_camera_service.get_all_cameras.return_value = [
            _make_camera_dto(camera_id=1, name="Cam 1"),
            _make_camera_dto(camera_id=2, name="Cam 2"),
        ]

        def _side_effect(filter_: DetectionFilter) -> int:
            if filter_.camera_id == 1:
                return 7
            if filter_.camera_id == 2:
                return 3
            return 0

        mock_detection_repo.count_filtered.side_effect = _side_effect
        mock_detection_repo.get_filtered.return_value = []

        data = dashboard_service.refresh()

        assert data.detection_count_by_camera == {1: 7, 2: 3}


class TestGetCameraNames:
    """DashboardService.get_camera_names() behaviour."""

    def test_get_camera_names_empty(
        self,
        mock_camera_service: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """Returns empty dict when no cameras exist."""
        mock_camera_service.get_all_cameras.return_value = []
        assert dashboard_service.get_camera_names() == {}

    def test_get_camera_names(
        self,
        mock_camera_service: MagicMock,
        dashboard_service: DashboardService,
    ) -> None:
        """Returns correct id→name mapping."""
        mock_camera_service.get_all_cameras.return_value = [
            _make_camera_dto(camera_id=1, name="Gate 1"),
            _make_camera_dto(camera_id=2, name="Gate 2"),
        ]
        names = dashboard_service.get_camera_names()
        assert names == {1: "Gate 1", 2: "Gate 2"}


class TestDeriveStatus:
    """DashboardService._derive_status() helper."""

    def test_enabled_returns_online(self) -> None:
        """Enabled camera derives as 'online'."""
        assert DashboardService._derive_status(enabled=True) == "online"

    def test_disabled_returns_disabled(self) -> None:
        """Disabled camera derives as 'disabled'."""
        assert DashboardService._derive_status(enabled=False) == "disabled"


class TestDetectionToSummary:
    """DashboardService._detection_to_summary() conversion."""

    def test_converts_plate_text(self) -> None:
        """Plate number is mapped to plate_text."""
        model = _make_detection_model(plate="TEST123")
        dto = DashboardService._detection_to_summary(model, {1: "Cam 1"})
        assert dto.plate_text == "TEST123"

    def test_converts_none_plate_to_empty(self) -> None:
        """None plate_number becomes empty string."""
        model = _make_detection_model(plate="ABC123")
        model.plate_number = None
        dto = DashboardService._detection_to_summary(model, {1: "Cam 1"})
        assert dto.plate_text == ""

    def test_resolves_camera_name(self) -> None:
        """Camera name is resolved from lookup."""
        model = _make_detection_model(camera_id=2)
        dto = DashboardService._detection_to_summary(model, {2: "Back Gate"})
        assert dto.camera_name == "Back Gate"

    def test_uses_fallback_camera_name(self) -> None:
        """Unknown camera_id gets fallback."""
        model = _make_detection_model(camera_id=999)
        dto = DashboardService._detection_to_summary(model, {})
        assert dto.camera_name == "Camera #999"

    def test_preserves_confidence(self) -> None:
        """Confidence value is preserved."""
        model = _make_detection_model(confidence=0.765)
        dto = DashboardService._detection_to_summary(model, {1: "Cam 1"})
        assert dto.confidence == 0.765

    def test_preserves_webhook_status(self) -> None:
        """Webhook status is preserved."""
        model = _make_detection_model(plate="ABC")
        model.webhook_status = "pending"
        dto = DashboardService._detection_to_summary(model, {1: "Cam 1"})
        assert dto.webhook_status == "pending"

    def test_preserves_image_and_video_paths(self) -> None:
        """Image and video paths are preserved."""
        model = _make_detection_model(plate="ABC")
        model.image_path = "/snaps/test.jpg"
        model.video_path = "/clips/test.mp4"
        dto = DashboardService._detection_to_summary(model, {1: "Cam 1"})
        assert dto.snapshot_path == "/snaps/test.jpg"
        assert dto.video_path == "/clips/test.mp4"

    def test_handles_null_paths(self) -> None:
        """Null paths become empty strings."""
        model = _make_detection_model(plate="ABC")
        model.image_path = None
        model.video_path = None
        dto = DashboardService._detection_to_summary(model, {1: "Cam 1"})
        assert dto.snapshot_path == ""
        assert dto.video_path == ""
