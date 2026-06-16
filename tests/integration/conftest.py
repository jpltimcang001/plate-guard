"""Integration-test-specific fixtures.

Uses the shared ``in_memory_engine`` and ``session_manager``
fixtures from ``tests/conftest.py``.
"""

from __future__ import annotations

import pytest

from src.repositories.camera_repository import CameraRepository
from src.services.camera_service import CameraService


@pytest.fixture
def camera_repo(session_manager) -> CameraRepository:
    """Return a CameraRepository backed by the in-memory database."""
    return CameraRepository(session_manager)


@pytest.fixture
def integration_camera_service(camera_repo) -> CameraService:
    """Return a CameraService with a real repository and no USB enumerator."""
    # No USB enumerator to avoid OpenCV dependency in integration tests
    return CameraService(camera_repository=camera_repo, usb_enumerator=None)
