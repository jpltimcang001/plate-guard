"""Unit tests for the ZoneService.

Uses an in-memory mock ZoneRepository to test business logic
without a real database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from src.application.dto.zone_dto import ZoneDTO
from src.application.exceptions.zone_errors import DuplicateZoneNameError, ZoneNotFoundError
from src.services.zone_service import ZoneService


# ------------------------------------------------------------------
# Mock Zone model (imitates ZoneModel ORM object)
# ------------------------------------------------------------------


@dataclass
class _MockZoneModel:
    """Lightweight mock of the ORM ZoneModel for unit testing."""

    id: int | None = None
    camera_id: int = 0
    name: str = ""
    polygon_json: str = "[]"
    created_at: datetime | None = None


# ------------------------------------------------------------------
# Mock ZoneRepository
# ------------------------------------------------------------------


class MockZoneRepository:
    """In-memory mock of ZoneRepository for unit tests.

    Accepts any object with ``id``, ``camera_id``, ``name``,
    ``polygon_json``, and ``created_at`` attributes (duck typing).
    """

    def __init__(self) -> None:
        self._zones: dict[int, Any] = {}
        self._next_id = 1

    def get_by_id(self, zone_id: int) -> Any | None:
        return self._zones.get(zone_id)

    def get_by_camera_id(self, camera_id: int) -> list[Any]:
        return sorted(
            [z for z in self._zones.values() if z.camera_id == camera_id],
            key=lambda z: z.name,
        )

    def get_by_name(self, name: str) -> Any | None:
        for z in self._zones.values():
            if z.name == name:
                return z
        return None

    def exists_by_name(self, name: str) -> bool:
        return any(z.name == name for z in self._zones.values())

    def add(self, model: Any) -> Any:
        model.id = self._next_id
        self._next_id += 1
        model.created_at = datetime(2026, 6, 15, 12, 0, 0)
        self._zones[model.id] = model
        return model

    def update(self, model: Any) -> Any:
        if model.id in self._zones:
            self._zones[model.id] = model
        return model

    def delete(self, zone_id: int) -> bool:
        return self._zones.pop(zone_id, None) is not None

    def delete_by_camera_id(self, camera_id: int) -> int:
        ids = [zid for zid, z in self._zones.items() if z.camera_id == camera_id]
        for zid in ids:
            del self._zones[zid]
        return len(ids)

    def count(self) -> int:
        return len(self._zones)

    def exists(self, zone_id: int) -> bool:
        return zone_id in self._zones


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def mock_zone_repo() -> MockZoneRepository:
    """Return a fresh in-memory mock zone repository."""
    return MockZoneRepository()


@pytest.fixture
def zone_service(mock_zone_repo: MockZoneRepository) -> ZoneService:
    """Return a ZoneService backed by the mock repository."""
    return ZoneService(mock_zone_repo)


@pytest.fixture
def sample_zone_model() -> _MockZoneModel:
    """Return a sample zone model (not persisted)."""
    return _MockZoneModel(
        camera_id=1,
        name="Front Gate",
        polygon_json="[[10,20],[100,20],[100,100],[10,100]]",
    )


# ======================================================================
# Tests
# ======================================================================


class TestCreateZone:
    """Tests for ZoneService.create_zone."""

    def test_create_zone_success(self, zone_service: ZoneService) -> None:
        """A valid zone is created and returned as a DTO."""
        dto = zone_service.create_zone(
            name="Entrance",
            camera_id=1,
            points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        )
        assert dto.id is not None and dto.id > 0
        assert dto.name == "Entrance"
        assert dto.camera_id == 1
        assert dto.points == [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

    def test_create_zone_duplicate_name_raises(
        self, zone_service: ZoneService
    ) -> None:
        """Creating a zone with a duplicate name raises DuplicateZoneNameError."""
        zone_service.create_zone(
            name="Entrance",
            camera_id=1,
            points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        )
        with pytest.raises(DuplicateZoneNameError, match="Entrance"):
            zone_service.create_zone(
                name="Entrance",
                camera_id=1,
                points=[(50, 50), (150, 50), (100, 150)],
            )

    def test_create_zone_empty_name_raises(
        self, zone_service: ZoneService
    ) -> None:
        """Creating a zone with an empty name raises ValueError."""
        with pytest.raises(ValueError, match="Zone name must not be empty"):
            zone_service.create_zone(
                name="",
                camera_id=1,
                points=[(0, 0), (100, 0), (50, 100)],
            )

    def test_create_zone_few_points_raises(
        self, zone_service: ZoneService
    ) -> None:
        """Creating a zone with fewer than 3 points raises ValueError."""
        with pytest.raises(ValueError, match="at least 3 vertices"):
            zone_service.create_zone(
                name="Bad",
                camera_id=1,
                points=[(0, 0), (100, 0)],
            )


class TestUpdateZone:
    """Tests for ZoneService.update_zone."""

    def test_update_zone_name(self, zone_service: ZoneService) -> None:
        """Updating a zone's name works."""
        dto = zone_service.create_zone(
            name="Old Name",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        updated = zone_service.update_zone(dto.id, name="New Name")
        assert updated.name == "New Name"
        assert updated.id == dto.id

    def test_update_zone_points(self, zone_service: ZoneService) -> None:
        """Updating a zone's points works."""
        dto = zone_service.create_zone(
            name="Zone",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        new_points = [(10, 10), (200, 10), (200, 200), (10, 200)]
        updated = zone_service.update_zone(dto.id, points=new_points)
        assert updated.points == [(10.0, 10.0), (200.0, 10.0), (200.0, 200.0), (10.0, 200.0)]

    def test_update_zone_not_found_raises(
        self, zone_service: ZoneService
    ) -> None:
        """Updating a non-existent zone raises ZoneNotFoundError."""
        with pytest.raises(ZoneNotFoundError, match="999"):
            zone_service.update_zone(999, name="Ghost")

    def test_update_zone_duplicate_name_raises(
        self, zone_service: ZoneService
    ) -> None:
        """Updating to a duplicate name raises DuplicateZoneNameError."""
        zone_service.create_zone(
            name="Zone A",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        dto_b = zone_service.create_zone(
            name="Zone B",
            camera_id=1,
            points=[(10, 10), (90, 10), (50, 90)],
        )
        with pytest.raises(DuplicateZoneNameError, match="Zone A"):
            zone_service.update_zone(dto_b.id, name="Zone A")


class TestDeleteZone:
    """Tests for ZoneService.delete_zone."""

    def test_delete_zone_success(self, zone_service: ZoneService) -> None:
        """Deleting an existing zone removes it."""
        dto = zone_service.create_zone(
            name="To Delete",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        zone_service.delete_zone(dto.id)
        with pytest.raises(ZoneNotFoundError):
            zone_service.get_zone(dto.id)

    def test_delete_zone_not_found_raises(
        self, zone_service: ZoneService
    ) -> None:
        """Deleting a non-existent zone raises ZoneNotFoundError."""
        with pytest.raises(ZoneNotFoundError, match="999"):
            zone_service.delete_zone(999)


class TestGetZone:
    """Tests for ZoneService get_zone / get_zones_by_camera."""

    def test_get_zone_by_id(self, zone_service: ZoneService) -> None:
        """Getting a zone by ID returns the correct DTO."""
        dto = zone_service.create_zone(
            name="Find Me",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        found = zone_service.get_zone(dto.id)
        assert found.id == dto.id
        assert found.name == "Find Me"

    def test_get_zone_not_found_raises(
        self, zone_service: ZoneService
    ) -> None:
        """Getting a non-existent zone raises ZoneNotFoundError."""
        with pytest.raises(ZoneNotFoundError, match="999"):
            zone_service.get_zone(999)

    def test_get_zones_by_camera(self, zone_service: ZoneService) -> None:
        """Getting zones by camera returns only that camera's zones."""
        zone_service.create_zone(
            name="Cam1 Zone",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        zone_service.create_zone(
            name="Cam2 Zone",
            camera_id=2,
            points=[(10, 10), (90, 10), (50, 90)],
        )

        cam1_zones = zone_service.get_zones_by_camera(1)
        cam2_zones = zone_service.get_zones_by_camera(2)

        assert len(cam1_zones) == 1
        assert len(cam2_zones) == 1
        assert cam1_zones[0].name == "Cam1 Zone"
        assert cam2_zones[0].name == "Cam2 Zone"

    def test_get_zones_by_camera_empty(
        self, zone_service: ZoneService
    ) -> None:
        """Getting zones for a camera with none returns empty list."""
        zones = zone_service.get_zones_by_camera(999)
        assert zones == []


class TestDeleteZonesByCamera:
    """Tests for ZoneService.delete_zones_by_camera."""

    def test_delete_zones_by_camera(self, zone_service: ZoneService) -> None:
        """Deleting zones by camera removes only that camera's zones."""
        zone_service.create_zone(
            name="Cam1 A",
            camera_id=1,
            points=[(0, 0), (100, 0), (50, 100)],
        )
        zone_service.create_zone(
            name="Cam1 B",
            camera_id=1,
            points=[(10, 10), (90, 10), (50, 90)],
        )
        zone_service.create_zone(
            name="Cam2 A",
            camera_id=2,
            points=[(0, 0), (100, 0), (50, 100)],
        )

        count = zone_service.delete_zones_by_camera(1)
        assert count == 2
        assert len(zone_service.get_zones_by_camera(1)) == 0
        assert len(zone_service.get_zones_by_camera(2)) == 1
