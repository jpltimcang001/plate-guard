"""Shared pytest fixtures and configuration for the Plate Guard test suite."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine

from src.database.engine import Base, init_db
from src.database.session import SessionManager
from src.domain.entities.camera import Camera
from src.domain.value_objects.camera_type import CameraType


# ------------------------------------------------------------------
# Database fixtures
# ------------------------------------------------------------------


@pytest.fixture(scope="session")
def in_memory_engine() -> Generator[Engine, Any, None]:
    """Create an in-memory SQLite engine for the test session.

    All tests share the same engine, but each test gets a
    transactionally isolated session (see ``db_session``).
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    # Enable WAL and foreign keys
    import sqlalchemy.event

    @sqlalchemy.event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA journal_mode=MEMORY;")
        cursor.close()

    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_manager(in_memory_engine: Engine) -> Generator[SessionManager, Any, None]:
    """Create a SessionManager bound to the in-memory engine.

    Cleans up the thread-local scoped session after each test
    so that unflushed / uncommitted data does not leak across tests.
    """
    manager = SessionManager(in_memory_engine)
    yield manager
    manager.remove_scoped_session()


@pytest.fixture
def db_session(session_manager: SessionManager) -> Generator[Session, Any, None]:
    """Provide a clean transaction for each test.

    Rolls back after the test to leave no trace.
    """
    session = session_manager.create_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ------------------------------------------------------------------
# Camera domain entity fixtures
# ------------------------------------------------------------------


@pytest.fixture
def sample_rtsp_camera() -> Camera:
    """Return a valid RTSP camera domain entity (not persisted)."""
    return Camera.create_rtsp(
        name="Test RTSP Camera",
        rtsp_url="rtsp://192.168.1.100:554/stream1",
        confidence_threshold=0.6,
    )


@pytest.fixture
def sample_usb_camera() -> Camera:
    """Return a valid USB camera domain entity (not persisted)."""
    return Camera.create_usb(
        name="Test USB Camera",
        usb_index=0,
        confidence_threshold=0.5,
    )


@pytest.fixture
def sample_cameras(session_manager: SessionManager) -> list[Camera]:
    """Persist a few sample cameras for query tests."""
    from src.repositories.camera_repository import CameraRepository

    repo = CameraRepository(session_manager)
    cameras = [
        Camera.create_rtsp("Gate 1", "rtsp://192.168.1.10:554/stream"),
        Camera.create_rtsp("Gate 2", "rtsp://192.168.1.11:554/stream"),
        Camera.create_usb("Lobby USB", usb_index=1),
    ]
    result = []
    for cam in cameras:
        saved = repo.add(cam)
        result.append(saved)
    # Enable the first one
    repo.update_status(result[0].id, True)
    result[0].enabled = True
    return result


# ------------------------------------------------------------------
# Mock repository fixture
# ------------------------------------------------------------------


class MockCameraRepository:
    """In-memory mock of ICameraRepository for unit tests."""

    def __init__(self) -> None:
        self._cameras: dict[int, Camera] = {}
        self._next_id = 1

    def get_by_id(self, camera_id: int) -> Camera | None:
        return self._cameras.get(camera_id)

    def get_all(self) -> list[Camera]:
        return list(self._cameras.values())

    def get_by_name(self, name: str) -> Camera | None:
        for cam in self._cameras.values():
            if cam.name == name:
                return cam
        return None

    def get_enabled(self) -> list[Camera]:
        return [c for c in self._cameras.values() if c.enabled]

    def get_by_type(self, camera_type: CameraType) -> list[Camera]:
        return [c for c in self._cameras.values() if c.type == camera_type]

    def exists_by_name(self, name: str) -> bool:
        return any(c.name == name for c in self._cameras.values())

    def add(self, camera: Camera) -> Camera:
        camera.id = self._next_id
        self._next_id += 1
        self._cameras[camera.id] = camera
        return camera

    def update(self, camera: Camera) -> Camera:
        if camera.id in self._cameras:
            self._cameras[camera.id] = camera
        return camera

    def exists(self, camera_id: int) -> bool:
        return camera_id in self._cameras

    def delete(self, camera_id: int) -> bool:
        return self._cameras.pop(camera_id, None) is not None

    def update_status(self, camera_id: int, enabled: bool) -> bool:
        cam = self._cameras.get(camera_id)
        if cam is None:
            return False
        cam.enabled = enabled
        return True

    def update_confidence_threshold(self, camera_id: int, threshold: float) -> bool:
        cam = self._cameras.get(camera_id)
        if cam is None:
            return False
        cam.confidence_threshold = threshold
        return True

    def count(self) -> int:
        return len(self._cameras)


@pytest.fixture
def mock_camera_repo() -> MockCameraRepository:
    """Return a fresh in-memory mock camera repository."""
    return MockCameraRepository()
