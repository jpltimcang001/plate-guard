"""Zone management service implementation.

Orchestrates zone CRUD operations, enforces business rules,
and transforms between domain entities, ORM models, and DTOs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from src.application.dto.zone_dto import ZoneDTO
from src.application.exceptions.zone_errors import DuplicateZoneNameError, ZoneNotFoundError
from src.database.models.zone_model import ZoneModel
from src.domain.entities.zone import Zone

if TYPE_CHECKING:
    from src.repositories.zone_repository import ZoneRepository


class ZoneService:
    """Service for managing detection zones.

    This is the primary entry point for all zone-related operations
    from the presentation layer. It enforces business rules and
    transforms data between layers.
    """

    def __init__(self, zone_repository: ZoneRepository) -> None:
        """Initialize the zone service.

        Args:
            zone_repository: Repository for zone persistence.

        """
        self._repo = zone_repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_zone(
        self,
        name: str,
        camera_id: int,
        points: list[tuple[float, float]],
    ) -> ZoneDTO:
        """Create a new detection zone.

        Args:
            name: Zone name (unique per camera).
            camera_id: ID of the parent camera.
            points: Polygon vertices as ``(x, y)`` pixel coordinates.

        Returns:
            A ``ZoneDTO`` representing the newly created zone.

        Raises:
            DuplicateZoneNameError: If the name already exists for the camera.
            ValueError: If validation fails.

        """
        logger.info(
            "Creating zone: name={}, camera_id={}, points={}",
            name,
            camera_id,
            len(points),
        )

        # Validate name uniqueness
        existing = self._repo.get_by_name(name)
        if existing is not None and existing.camera_id == camera_id:
            raise DuplicateZoneNameError(name, camera_id)

        # Build domain entity and validate
        zone = Zone.create(name=name, camera_id=camera_id, points=points)

        # Persist via ORM model
        model = self._to_model(zone)
        saved = self._repo.add(model)
        logger.info("Zone created: id={}, name={}", saved.id, saved.name)
        return self._to_dto(saved)

    def update_zone(
        self,
        zone_id: int,
        name: str | None = None,
        points: list[tuple[float, float]] | None = None,
    ) -> ZoneDTO:
        """Update an existing zone.

        Args:
            zone_id: The zone to update.
            name: New name (optional).
            points: New polygon vertices (optional).

        Returns:
            The updated ``ZoneDTO``.

        Raises:
            ZoneNotFoundError: If the zone does not exist.
            DuplicateZoneNameError: If the new name conflicts.
            ValueError: If validation fails.

        """
        logger.info("Updating zone: id={}", zone_id)

        model = self._repo.get_by_id(zone_id)
        if model is None:
            raise ZoneNotFoundError(zone_id)

        # Update name
        if name is not None and name != model.name:
            existing = self._repo.get_by_name(name)
            if existing is not None and existing.id != zone_id:
                raise DuplicateZoneNameError(name, model.camera_id)
            model.name = name

        # Update points
        if points is not None:
            model.polygon_json = Zone.points_to_json(points)

        # Validate via domain entity
        zone = self._from_model(model)
        zone.validate()

        updated = self._repo.update(model)
        logger.info("Zone updated: id={}", updated.id)
        return self._to_dto(updated)

    def delete_zone(self, zone_id: int) -> None:
        """Delete a zone.

        Args:
            zone_id: The zone to delete.

        Raises:
            ZoneNotFoundError: If the zone does not exist.

        """
        logger.info("Deleting zone: id={}", zone_id)

        if not self._repo.exists(zone_id):
            raise ZoneNotFoundError(zone_id)

        self._repo.delete(zone_id)
        logger.info("Zone deleted: id={}", zone_id)

    def get_zone(self, zone_id: int) -> ZoneDTO:
        """Retrieve a single zone by ID.

        Args:
            zone_id: The zone ID.

        Returns:
            The ``ZoneDTO``.

        Raises:
            ZoneNotFoundError: If the zone does not exist.

        """
        model = self._repo.get_by_id(zone_id)
        if model is None:
            raise ZoneNotFoundError(zone_id)
        return self._to_dto(model)

    def get_zones_by_camera(self, camera_id: int) -> list[ZoneDTO]:
        """Retrieve all zones for a camera.

        Args:
            camera_id: The parent camera ID.

        Returns:
            A list of ``ZoneDTO`` instances.

        """
        models = self._repo.get_by_camera_id(camera_id)
        return [self._to_dto(m) for m in models]

    def delete_zones_by_camera(self, camera_id: int) -> int:
        """Delete all zones for a camera.

        Args:
            camera_id: The parent camera ID.

        Returns:
            The number of zones deleted.

        """
        count = self._repo.delete_by_camera_id(camera_id)
        logger.info("Deleted {} zone(s) for camera id={}", count, camera_id)
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dto(model: ZoneModel) -> ZoneDTO:
        """Convert an ORM ZoneModel to a ZoneDTO.

        Args:
            model: The ORM model instance.

        Returns:
            A ``ZoneDTO``.

        """
        return ZoneDTO(
            id=model.id,
            name=model.name,
            camera_id=model.camera_id,
            points=Zone.points_from_json(model.polygon_json),
            created_at=model.created_at,
        )

    @staticmethod
    def _from_model(model: ZoneModel) -> Zone:
        """Convert an ORM ZoneModel to a domain Zone entity.

        Args:
            model: The ORM model instance.

        Returns:
            A ``Zone`` domain entity.

        """
        return Zone(
            id=model.id,
            camera_id=model.camera_id,
            name=model.name,
            points=Zone.points_from_json(model.polygon_json),
            created_at=model.created_at,
        )

    @staticmethod
    def _to_model(zone: Zone) -> ZoneModel:
        """Convert a domain Zone entity to an ORM ZoneModel.

        Args:
            zone: The domain entity.

        Returns:
            A ``ZoneModel`` ready for persistence.

        """
        return ZoneModel(
            camera_id=zone.camera_id,
            name=zone.name,
            polygon_json=zone.polygon_json,
        )
