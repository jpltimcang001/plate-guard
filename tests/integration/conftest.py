"""Integration-test-specific fixtures.

Uses the shared ``in_memory_engine`` and ``session_manager``
fixtures from ``tests/conftest.py``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src.database.models import CameraModel, DetectionModel, WebhookModel
from src.repositories.camera_repository import CameraRepository
from src.repositories.detection_repository import DetectionRepository
from src.repositories.webhook_repository import WebhookRepository
from src.repositories.zone_repository import ZoneRepository
from src.services.camera_service import CameraService
from src.services.dashboard_service import DashboardService
from src.services.zone_service import ZoneService

if TYPE_CHECKING:
    from src.database.session import SessionManager


# ------------------------------------------------------------------
# Repositories
# ------------------------------------------------------------------


@pytest.fixture
def camera_repo(session_manager: SessionManager) -> CameraRepository:
    """Return a CameraRepository backed by the in-memory database."""
    return CameraRepository(session_manager)


@pytest.fixture
def detection_repo(session_manager: SessionManager) -> DetectionRepository:
    """Return a DetectionRepository backed by the in-memory database."""
    return DetectionRepository(session_manager)


@pytest.fixture
def webhook_repo(session_manager: SessionManager) -> WebhookRepository:
    """Return a WebhookRepository backed by the in-memory database."""
    return WebhookRepository(session_manager)


@pytest.fixture
def zone_repo(session_manager: SessionManager) -> ZoneRepository:
    """Return a ZoneRepository backed by the in-memory database."""
    return ZoneRepository(session_manager)


# ------------------------------------------------------------------
# Services
# ------------------------------------------------------------------


@pytest.fixture
def integration_camera_service(camera_repo: CameraRepository) -> CameraService:
    """Return a CameraService with a real repository and no USB enumerator."""
    # No USB enumerator to avoid OpenCV dependency in integration tests
    return CameraService(camera_repository=camera_repo, usb_enumerator=None)


@pytest.fixture
def integration_dashboard_service(
    integration_camera_service: CameraService,
    detection_repo: DetectionRepository,
) -> DashboardService:
    """Return a DashboardService wired to real repos."""
    return DashboardService(
        camera_service=integration_camera_service,
        detection_repository=detection_repo,
    )


@pytest.fixture
def integration_zone_service(zone_repo: ZoneRepository) -> ZoneService:
    """Return a ZoneService wired to a real ZoneRepository."""
    return ZoneService(zone_repository=zone_repo)


# ------------------------------------------------------------------
# Seeded data fixtures
# ------------------------------------------------------------------


@pytest.fixture
def seeded_camera(camera_repo: CameraRepository) -> CameraModel:
    """Persist a single RTSP camera and return its ORM model."""
    cam = CameraModel(
        name="Integration Test Camera",
        type="rtsp",
        rtsp_url="rtsp://192.168.1.99:554/live",
        confidence_threshold=0.6,
        enabled=True,
    )
    return camera_repo.add(cam)


@pytest.fixture
def seeded_detection(
    detection_repo: DetectionRepository,
    seeded_camera: CameraModel,
) -> DetectionModel:
    """Persist a single detection record linked to the seeded camera."""
    det = DetectionModel(
        camera_id=seeded_camera.id,
        plate_number="ABC-1234",
        confidence=0.92,
        image_path="/tmp/snapshots/test_snapshot.jpg",
        video_path="/tmp/clips/test_clip.mp4",
        webhook_status="not_configured",
        detected_at=datetime(2026, 6, 18, 10, 30, 0),
    )
    return detection_repo.add(det)


@pytest.fixture
def seeded_webhook(
    webhook_repo: WebhookRepository,
    seeded_camera: CameraModel,
) -> WebhookModel:
    """Persist a single webhook config linked to the seeded camera."""
    wh = WebhookModel(
        camera_id=seeded_camera.id,
        method="POST",
        url="https://hooks.example.com/plate-guard",
        auth_type="none",
        send_image=True,
        send_video=False,
    )
    return webhook_repo.add(wh)


# ------------------------------------------------------------------
# Temporary directory for evidence file I/O
# ------------------------------------------------------------------


@pytest.fixture
def evidence_dir(tmp_path: Path) -> Path:
    """Return a temporary directory that acts as the media base path."""
    (tmp_path / "snapshots").mkdir(parents=True, exist_ok=True)
    (tmp_path / "clips").mkdir(parents=True, exist_ok=True)
    return tmp_path
