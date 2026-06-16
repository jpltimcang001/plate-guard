"""Repository interface for the Camera aggregate.

Defines the contract that any Camera repository must implement.
The implementation lives in the infrastructure layer.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.camera import Camera
from src.domain.value_objects.camera_type import CameraType


class ICameraRepository(Protocol):
    """Interface for Camera persistence operations."""

    def get_by_id(self, camera_id: int) -> Camera | None:
        """Retrieve a camera by its primary key.

        Args:
            camera_id: The camera ID.

        Returns:
            The Camera if found, else ``None``.

        """
        ...

    def get_all(self) -> list[Camera]:
        """Retrieve all cameras.

        Returns:
            A list of all Camera instances.

        """
        ...

    def get_by_name(self, name: str) -> Camera | None:
        """Retrieve a camera by its unique name.

        Args:
            name: The camera name.

        Returns:
            The Camera if found, else ``None``.

        """
        ...

    def get_enabled(self) -> list[Camera]:
        """Retrieve all enabled cameras.

        Returns:
            A list of enabled Camera instances.

        """
        ...

    def get_by_type(self, camera_type: CameraType) -> list[Camera]:
        """Retrieve all cameras of the given type.

        Args:
            camera_type: ``CameraType.RTSP`` or ``CameraType.USB``.

        Returns:
            A list of matching Camera instances.

        """
        ...

    def exists_by_name(self, name: str) -> bool:
        """Check whether a camera with the given name exists.

        Args:
            name: The camera name.

        Returns:
            ``True`` if a camera with that name exists.

        """
        ...

    def add(self, camera: Camera) -> Camera:
        """Persist a new camera.

        Args:
            camera: The Camera entity to persist (without an ID).

        Returns:
            The Camera with its generated ID.

        """
        ...

    def update(self, camera: Camera) -> Camera:
        """Update an existing camera.

        Args:
            camera: The Camera entity with modified attributes.

        Returns:
            The updated Camera.

        """
        ...

    def delete(self, camera_id: int) -> bool:
        """Delete a camera by its primary key.

        Args:
            camera_id: The camera ID to delete.

        Returns:
            ``True`` if a camera was deleted, ``False`` if not found.

        """
        ...

    def update_status(self, camera_id: int, enabled: bool) -> bool:
        """Enable or disable a camera.

        Args:
            camera_id: The camera ID.
            enabled: The new enabled state.

        Returns:
            ``True`` if the camera was found and updated.

        """
        ...

    def update_confidence_threshold(self, camera_id: int, threshold: float) -> bool:
        """Update the confidence threshold for a camera.

        Args:
            camera_id: The camera ID.
            threshold: The new threshold (0.0–1.0).

        Returns:
            ``True`` if the camera was found and updated.

        """
        ...

    def count(self) -> int:
        """Return the total number of cameras.

        Returns:
            The camera count.

        """
        ...
