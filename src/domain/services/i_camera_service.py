"""Service interface for Camera management operations.

Defines the contract that the Camera service implementation must satisfy.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.camera import Camera
from src.domain.value_objects.camera_type import CameraType


class UsbDeviceInfo:
    """Information about a detected USB camera device."""

    def __init__(self, index: int, name: str, hardware_id: str | None = None) -> None:
        self.index = index
        self.name = name
        self.hardware_id = hardware_id

    def __repr__(self) -> str:
        return (
            f"<UsbDeviceInfo index={self.index} name={self.name!r}>"
        )


class ICameraService(Protocol):
    """Interface for the Camera management service."""

    def add_camera(
        self,
        name: str,
        camera_type: CameraType,
        rtsp_url: str | None = None,
        usb_index: int | None = None,
        confidence_threshold: float = 0.5,
    ) -> Camera:
        """Add a new camera.

        Args:
            name: Unique camera name.
            camera_type: ``CameraType.RTSP`` or ``CameraType.USB``.
            rtsp_url: RTSP stream URL (required for RTSP).
            usb_index: USB device index (required for USB).
            confidence_threshold: Detection confidence threshold (0.0–1.0).

        Returns:
            The newly created Camera with its generated ID.

        Raises:
            DuplicateNameError: If a camera with the same name exists.
            CameraConnectionError: If the camera stream cannot be validated.
            ValueError: If input validation fails.

        """
        ...

    def edit_camera(
        self,
        camera_id: int,
        name: str | None = None,
        rtsp_url: str | None = None,
        usb_index: int | None = None,
        confidence_threshold: float | None = None,
    ) -> Camera:
        """Edit an existing camera's configuration.

        Only provided fields are updated.

        Args:
            camera_id: The camera to edit.
            name: New camera name.
            rtsp_url: New RTSP URL.
            usb_index: New USB index.
            confidence_threshold: New confidence threshold.

        Returns:
            The updated Camera.

        Raises:
            CameraNotFoundError: If the camera does not exist.
            DuplicateNameError: If the new name conflicts with another camera.
            ValueError: If input validation fails.

        """
        ...

    def delete_camera(self, camera_id: int) -> None:
        """Delete a camera and all associated data.

        Args:
            camera_id: The camera to delete.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        ...

    def enable_camera(self, camera_id: int) -> Camera:
        """Enable a camera for detection.

        Args:
            camera_id: The camera to enable.

        Returns:
            The updated Camera.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        ...

    def disable_camera(self, camera_id: int) -> Camera:
        """Disable a camera (stop detection).

        Args:
            camera_id: The camera to disable.

        Returns:
            The updated Camera.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        ...

    def get_camera(self, camera_id: int) -> Camera:
        """Retrieve a single camera by ID.

        Args:
            camera_id: The camera ID.

        Returns:
            The Camera.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        ...

    def get_all_cameras(self) -> list[Camera]:
        """Retrieve all cameras.

        Returns:
            A list of all Camera instances.

        """
        ...

    def get_enabled_cameras(self) -> list[Camera]:
        """Retrieve all enabled cameras.

        Returns:
            A list of enabled Camera instances.

        """
        ...

    def enumerate_usb_devices(self) -> list[UsbDeviceInfo]:
        """Detect available USB camera devices.

        Returns:
            A list of detected USB devices with index and name.

        """
        ...
