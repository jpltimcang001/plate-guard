"""Repository interface for the Zone aggregate.

Defines the contract that any Zone repository must implement.
The implementation lives in the infrastructure layer.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.zone import Zone


class IZoneRepository(Protocol):
    """Interface for Zone persistence operations."""

    def get_by_id(self, zone_id: int) -> Zone | None:
        """Retrieve a zone by its primary key.

        Args:
            zone_id: The zone ID.

        Returns:
            The Zone if found, else ``None``.

        """
        ...

    def get_by_camera_id(self, camera_id: int) -> list[Zone]:
        """Retrieve all zones for a given camera.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            A list of Zone instances ordered by name.

        """
        ...

    def get_by_name(self, name: str) -> Zone | None:
        """Retrieve a zone by its name.

        Args:
            name: The zone name.

        Returns:
            The Zone if found, else ``None``.

        """
        ...

    def exists_by_name(self, name: str) -> bool:
        """Check whether a zone with the given name exists.

        Args:
            name: The zone name.

        Returns:
            ``True`` if a zone with that name exists.

        """
        ...

    def add(self, zone: Zone) -> Zone:
        """Persist a new zone.

        Args:
            zone: The Zone entity to persist (without an ID).

        Returns:
            The Zone with its generated ID.

        """
        ...

    def update(self, zone: Zone) -> Zone:
        """Update an existing zone.

        Args:
            zone: The Zone entity with modified attributes.

        Returns:
            The updated Zone.

        """
        ...

    def delete(self, zone_id: int) -> bool:
        """Delete a zone by its primary key.

        Args:
            zone_id: The zone ID to delete.

        Returns:
            ``True`` if a zone was deleted, ``False`` if not found.

        """
        ...

    def delete_by_camera_id(self, camera_id: int) -> int:
        """Delete all zones for a given camera.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            The number of zones deleted.

        """
        ...

    def count(self) -> int:
        """Return the total number of zones.

        Returns:
            The zone count.

        """
        ...
