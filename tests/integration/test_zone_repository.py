"""Integration tests for the ZoneRepository using a real SQLite database.

These tests verify that the ZoneRepository correctly persists and
retrieves zone data using the actual ORM model and database engine.
"""

from __future__ import annotations

import json

import pytest

from src.database.models import CameraModel, ZoneModel
from src.database.session import SessionManager
from src.repositories.camera_repository import CameraRepository
from src.repositories.zone_repository import ZoneRepository


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def zone_repo(session_manager: SessionManager) -> ZoneRepository:
    """Return a ZoneRepository bound to the test database."""
    return ZoneRepository(session_manager)


@pytest.fixture
def camera_repo(session_manager: SessionManager) -> CameraRepository:
    """Return a CameraRepository bound to the test database."""
    return CameraRepository(session_manager)


@pytest.fixture
def sample_camera_id(camera_repo: CameraRepository) -> int:
    """Create a sample camera and return its ID."""
    cam = CameraModel(
        name="Test Camera",
        type="rtsp",
        rtsp_url="rtsp://192.168.1.100:554/stream",
        enabled=True,
        confidence_threshold=0.5,
    )
    saved = camera_repo.add(cam)
    return saved.id


def _create_zone(
    zone_repo: ZoneRepository, camera_id: int, **overrides: dict
) -> ZoneModel:
    """Helper to create a zone model with sensible defaults."""
    data = {
        "camera_id": camera_id,
        "name": "Default Zone",
        "polygon_json": "[[0,0],[100,0],[50,100]]",
    }
    data.update(overrides)
    model = ZoneModel(**data)
    return zone_repo.add(model)


# ======================================================================
# Tests
# ======================================================================


class TestZoneRepositoryAdd:
    """Tests for adding zones."""

    def test_add_zone(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Adding a zone returns it with an assigned ID."""
        model = ZoneModel(
            camera_id=sample_camera_id,
            name="Front Gate",
            polygon_json="[[0,0],[200,0],[200,150],[0,150]]",
        )
        saved = zone_repo.add(model)
        assert saved.id is not None and saved.id > 0
        assert saved.name == "Front Gate"
        assert saved.camera_id == sample_camera_id

    def test_add_multiple_zones(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Adding multiple zones assigns sequential IDs."""
        z1 = _create_zone(zone_repo, camera_id=sample_camera_id, name="Zone A")
        z2 = _create_zone(zone_repo, camera_id=sample_camera_id, name="Zone B")
        assert z1.id is not None and z2.id is not None
        assert z2.id > z1.id


class TestZoneRepositoryGet:
    """Tests for retrieving zones."""

    def test_get_by_id_found(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Getting a zone by ID returns the correct model."""
        saved = _create_zone(zone_repo, camera_id=sample_camera_id, name="Target Zone")
        found = zone_repo.get_by_id(saved.id)
        assert found is not None
        assert found.id == saved.id
        assert found.name == "Target Zone"

    def test_get_by_id_not_found(self, zone_repo: ZoneRepository) -> None:
        """Getting a non-existent zone ID returns None."""
        found = zone_repo.get_by_id(9999)
        assert found is None

    def test_get_by_name_found(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Getting a zone by name returns the correct model."""
        _create_zone(zone_repo, camera_id=sample_camera_id, name="Unique Zone")
        found = zone_repo.get_by_name("Unique Zone")
        assert found is not None
        assert found.name == "Unique Zone"

    def test_get_by_name_not_found(self, zone_repo: ZoneRepository) -> None:
        """Getting a non-existent zone name returns None."""
        found = zone_repo.get_by_name("NonExistent")
        assert found is None

    def test_get_by_camera_id(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Getting zones by camera returns only zones for that camera."""
        _create_zone(zone_repo, camera_id=sample_camera_id, name="Cam1 A")
        _create_zone(zone_repo, camera_id=sample_camera_id, name="Cam1 B")
        # Create second camera for cross-camera test
        cam2 = CameraModel(
            name="Camera 2", type="usb", usb_index=1, enabled=False,
            confidence_threshold=0.5,
        )
        cam2_saved = CameraRepository(
            zone_repo._session_manager
        ).add(cam2)
        _create_zone(zone_repo, camera_id=cam2_saved.id, name="Cam2 A")

        cam1_zones = zone_repo.get_by_camera_id(sample_camera_id)
        cam2_zones = zone_repo.get_by_camera_id(cam2_saved.id)

        assert len(cam1_zones) == 2
        assert len(cam2_zones) == 1
        assert cam1_zones[0].name == "Cam1 A"
        assert cam1_zones[1].name == "Cam1 B"

    def test_get_by_camera_id_empty(self, zone_repo: ZoneRepository) -> None:
        """Getting zones for a camera with no zones returns empty list."""
        zones = zone_repo.get_by_camera_id(9999)
        assert zones == []

    def test_exists_by_name_true(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """exists_by_name returns True for existing names."""
        _create_zone(zone_repo, camera_id=sample_camera_id, name="Existing Zone")
        assert zone_repo.exists_by_name("Existing Zone") is True

    def test_exists_by_name_false(self, zone_repo: ZoneRepository) -> None:
        """exists_by_name returns False for non-existent names."""
        assert zone_repo.exists_by_name("Ghost Zone") is False


class TestZoneRepositoryUpdate:
    """Tests for updating zones."""

    def test_update_name(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Updating a zone's name persists the change."""
        saved = _create_zone(zone_repo, camera_id=sample_camera_id, name="Old Name")
        saved.name = "New Name"
        updated = zone_repo.update(saved)
        assert updated.name == "New Name"

        # Verify persistence
        refetched = zone_repo.get_by_id(saved.id)
        assert refetched is not None
        assert refetched.name == "New Name"

    def test_update_polygon(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Updating a zone's polygon persists the change."""
        saved = _create_zone(
            zone_repo, camera_id=sample_camera_id, name="Poly",
            polygon_json="[[0,0],[100,0],[50,100]]",
        )
        new_polygon = "[[10,10],[90,10],[90,90],[10,90]]"
        saved.polygon_json = new_polygon
        updated = zone_repo.update(saved)
        assert json.loads(updated.polygon_json) == json.loads(new_polygon)


class TestZoneRepositoryDelete:
    """Tests for deleting zones."""

    def test_delete_zone(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Deleting a zone removes it from the database."""
        saved = _create_zone(zone_repo, camera_id=sample_camera_id, name="To Delete")
        zone_id = saved.id
        deleted = zone_repo.delete(zone_id)
        assert deleted is True
        assert zone_repo.get_by_id(zone_id) is None

    def test_delete_not_found(self, zone_repo: ZoneRepository) -> None:
        """Deleting a non-existent zone returns False."""
        deleted = zone_repo.delete(9999)
        assert deleted is False

    def test_delete_by_camera_id(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Deleting zones by camera removes only those zones."""
        _create_zone(zone_repo, camera_id=sample_camera_id, name="Cam1 A")
        _create_zone(zone_repo, camera_id=sample_camera_id, name="Cam1 B")
        cam2 = CameraModel(
            name="Other Cam", type="usb", usb_index=2, enabled=False,
            confidence_threshold=0.5,
        )
        cam2_saved = CameraRepository(
            zone_repo._session_manager
        ).add(cam2)
        _create_zone(zone_repo, camera_id=cam2_saved.id, name="Cam2 A")

        count = zone_repo.delete_by_camera_id(sample_camera_id)
        assert count == 2
        assert len(zone_repo.get_by_camera_id(sample_camera_id)) == 0
        assert len(zone_repo.get_by_camera_id(cam2_saved.id)) == 1


class TestZoneRepositoryCount:
    """Tests for zone counting."""

    def test_count_empty(self, zone_repo: ZoneRepository) -> None:
        """Count returns 0 for an empty table."""
        assert zone_repo.count() == 0

    def test_count_after_inserts(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Count reflects inserted zones."""
        _create_zone(zone_repo, camera_id=sample_camera_id, name="A")
        assert zone_repo.count() == 1
        _create_zone(zone_repo, camera_id=sample_camera_id, name="B")
        assert zone_repo.count() == 2


class TestZoneRepositoryBulk:
    """Tests for bulk operations."""

    def test_bulk_insert(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Bulk inserting multiple zones assigns IDs to all."""
        models = [
            ZoneModel(
                camera_id=sample_camera_id, name=f"Bulk Zone {i}",
                polygon_json="[[0,0],[10,0],[5,10]]",
            )
            for i in range(3)
        ]
        inserted = zone_repo.bulk_insert(models)
        assert len(inserted) == 3
        assert all(m.id is not None and m.id > 0 for m in inserted)

    def test_bulk_delete(
        self, zone_repo: ZoneRepository, sample_camera_id: int
    ) -> None:
        """Bulk deleting zones removes them all."""
        models = [
            ZoneModel(
                camera_id=sample_camera_id, name=f"Del Zone {i}",
                polygon_json="[[0,0],[10,0],[5,10]]",
            )
            for i in range(3)
        ]
        inserted = zone_repo.bulk_insert(models)
        ids = [m.id for m in inserted]

        count = zone_repo.bulk_delete(ids)
        assert count == 3
        assert zone_repo.count() == 0
