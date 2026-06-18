"""Integration tests for ZoneService.

Verifies zone CRUD operations with a real in-memory database,
including business rule enforcement (duplicate name detection,
validation of polygon data).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.application.dto.zone_dto import CreateZoneRequest, ZoneDTO
from src.application.exceptions.zone_errors import DuplicateZoneNameError, ZoneNotFoundError
from src.services.zone_service import ZoneService

if TYPE_CHECKING:
    from src.database.models import CameraModel


# ======================================================================
# ZoneService — CRUD
# ======================================================================


class TestZoneServiceCRUD:
    """Tests for create_zone, get_zone, update_zone, delete_zone."""

    def test_create_zone(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Creating a zone returns a ZoneDTO with an ID and the correct data."""
        zone = integration_zone_service.create_zone(
            name="Entrance Zone",
            camera_id=seeded_camera.id,
            points=[(10, 10), (200, 10), (200, 150), (10, 150)],
        )
        assert isinstance(zone, ZoneDTO)
        assert zone.id is not None and zone.id > 0
        assert zone.name == "Entrance Zone"
        assert zone.camera_id == seeded_camera.id
        assert len(zone.points) == 4

    def test_get_zone_by_id(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Fetching a zone by ID returns the correct data."""
        created = integration_zone_service.create_zone(
            name="Get Test Zone",
            camera_id=seeded_camera.id,
            points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        )
        fetched = integration_zone_service.get_zone(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Get Test Zone"

    def test_get_zone_not_found_raises(
        self,
        integration_zone_service: ZoneService,
    ) -> None:
        """Fetching a non-existent zone raises ZoneNotFoundError."""
        from src.application.exceptions.zone_errors import ZoneNotFoundError

        with pytest.raises(ZoneNotFoundError):
            integration_zone_service.get_zone(999_999)

    def test_delete_zone(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Deleting a zone removes it and future fetches raise."""
        from src.application.exceptions.zone_errors import ZoneNotFoundError

        created = integration_zone_service.create_zone(
            name="Delete Me",
            camera_id=seeded_camera.id,
            points=[(0, 0), (50, 0), (50, 50), (0, 50)],
        )
        integration_zone_service.delete_zone(created.id)
        with pytest.raises(ZoneNotFoundError):
            integration_zone_service.get_zone(created.id)

    def test_delete_zone_not_found_raises(
        self,
        integration_zone_service: ZoneService,
    ) -> None:
        """Deleting a non-existent zone raises ZoneNotFoundError."""
        with pytest.raises(ZoneNotFoundError):
            integration_zone_service.delete_zone(999_999)

    def test_update_zone_name(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Updating a zone's name persists the change."""
        created = integration_zone_service.create_zone(
            name="Original Name",
            camera_id=seeded_camera.id,
            points=[(10, 10), (20, 10), (20, 20), (10, 20)],
        )
        updated = integration_zone_service.update_zone(
            zone_id=created.id,
            name="Updated Name",
        )
        assert updated.name == "Updated Name"
        # Verify via fresh fetch
        fetched = integration_zone_service.get_zone(created.id)
        assert fetched is not None
        assert fetched.name == "Updated Name"

    def test_update_zone_points(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Updating a zone's polygon points persists the change."""
        original = [(0, 0), (10, 0), (10, 10), (0, 10)]
        updated_points = [(0, 0), (20, 0), (20, 20), (0, 20)]
        created = integration_zone_service.create_zone(
            name="Points Test",
            camera_id=seeded_camera.id,
            points=original,
        )
        updated = integration_zone_service.update_zone(
            zone_id=created.id,
            points=updated_points,
        )
        assert updated.points == updated_points

    def test_update_zone_not_found_raises(
        self,
        integration_zone_service: ZoneService,
    ) -> None:
        """Updating a non-existent zone raises ZoneNotFoundError."""
        with pytest.raises(ZoneNotFoundError):
            integration_zone_service.update_zone(
                zone_id=999_999,
                name="Nowhere Zone",
            )


# ======================================================================
# ZoneService — Business rules
# ======================================================================


class TestZoneServiceBusinessRules:
    """Tests for name uniqueness, camera scoping, and validation."""

    def test_duplicate_name_same_camera_raises(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Creating a zone with a duplicate name for the same camera raises."""
        integration_zone_service.create_zone(
            name="Unique",
            camera_id=seeded_camera.id,
            points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )
        with pytest.raises(DuplicateZoneNameError):
            integration_zone_service.create_zone(
                name="Unique",
                camera_id=seeded_camera.id,
                points=[(20, 20), (30, 20), (30, 30), (20, 30)],
            )

    def test_duplicate_name_different_camera_allowed(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """The same zone name is allowed on different cameras."""
        from src.database.models import CameraModel

        # Create a second camera
        cam2 = CameraModel(
            name="Second Camera",
            type="usb",
            usb_index=7,
            enabled=True,
        )
        from src.repositories.camera_repository import CameraRepository

        cam2 = CameraRepository(
            integration_zone_service._repo._session_manager  # type: ignore[attr-defined]
        ).add(cam2)

        z1 = integration_zone_service.create_zone(
            name="Shared Name",
            camera_id=seeded_camera.id,
            points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )
        z2 = integration_zone_service.create_zone(
            name="Shared Name",
            camera_id=cam2.id,
            points=[(20, 20), (30, 20), (30, 30), (20, 30)],
        )
        assert z1.id != z2.id
        assert z1.name == z2.name

    def test_get_zones_by_camera(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """get_zones_by_camera returns only zones for that camera."""
        integration_zone_service.create_zone(
            name="Zone A",
            camera_id=seeded_camera.id,
            points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )
        integration_zone_service.create_zone(
            name="Zone B",
            camera_id=seeded_camera.id,
            points=[(20, 20), (30, 20), (30, 30), (20, 30)],
        )
        # Other camera zones
        from src.database.models import CameraModel

        cam2 = CameraModel(name="Empty Cam", type="usb", usb_index=8, enabled=True)
        from src.repositories.camera_repository import CameraRepository

        cam2 = CameraRepository(
            integration_zone_service._repo._session_manager  # type: ignore[attr-defined]
        ).add(cam2)
        integration_zone_service.create_zone(
            name="Zone Other",
            camera_id=cam2.id,
            points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )

        zones = integration_zone_service.get_zones_by_camera(seeded_camera.id)
        assert len(zones) == 2
        assert all(z.camera_id == seeded_camera.id for z in zones)

    def test_get_zones_by_camera_multiple(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """get_zones_by_camera returns zones for a camera after inserts."""
        integration_zone_service.create_zone(
            name="Multi Zone 1",
            camera_id=seeded_camera.id,
            points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )
        integration_zone_service.create_zone(
            name="Multi Zone 2",
            camera_id=seeded_camera.id,
            points=[(20, 20), (30, 20), (30, 30), (20, 30)],
        )
        zones = integration_zone_service.get_zones_by_camera(seeded_camera.id)
        assert len(zones) >= 2

    def test_count_after_create(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Zone count via repository matches after inserts."""
        from src.repositories.zone_repository import ZoneRepository

        # Count through the underlying repo
        repo: ZoneRepository = integration_zone_service._repo  # type: ignore[attr-defined]
        before = repo.count()

        integration_zone_service.create_zone(
            name="Count Test",
            camera_id=seeded_camera.id,
            points=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )
        after = repo.count()
        assert after == before + 1

    def test_create_zone_invalid_points_raises(
        self,
        integration_zone_service: ZoneService,
        seeded_camera: CameraModel,
    ) -> None:
        """Creating a zone with fewer than 3 points raises ValueError."""
        with pytest.raises(ValueError):
            integration_zone_service.create_zone(
                name="Bad Zone",
                camera_id=seeded_camera.id,
                points=[(0, 0), (10, 0)],
            )
