"""Camera management service implementation.

Orchestrates camera CRUD operations, validates business rules,
and coordinates between the domain layer and infrastructure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from src.application.dto.camera_dto import CameraDTO
from src.application.exceptions.camera_errors import (
    CameraConnectionError,
    CameraNotFoundError,
    DuplicateNameError,
)
from src.domain.entities.camera import Camera
from src.domain.services.i_camera_service import UsbDeviceInfo
from src.domain.value_objects.camera_type import CameraType

if TYPE_CHECKING:
    from src.domain.repositories.i_camera_repository import ICameraRepository


class CameraService:
    """Service for managing camera lifecycle.

    This is the primary entry point for all camera-related operations
    from the presentation layer. It enforces business rules and
    transforms domain entities to/from DTOs.
    """

    def __init__(
        self,
        camera_repository: ICameraRepository,
        usb_enumerator: "UsbEnumerator | None" = None,
    ) -> None:
        """Initialize the camera service.

        Args:
            camera_repository: Repository for camera persistence.
            usb_enumerator: Optional USB device enumerator for
                validating USB camera indices. If ``None``, USB
                validation is skipped.

        """
        self._repo = camera_repository
        self._usb_enumerator = usb_enumerator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_camera(
        self,
        name: str,
        camera_type: CameraType,
        rtsp_url: str | None = None,
        usb_index: int | None = None,
        confidence_threshold: float = 0.5,
        evidence_mode: str = "snapshot",
    ) -> CameraDTO:
        """Add a new camera.

        Args:
            name: Unique camera name.
            camera_type: ``CameraType.RTSP`` or ``CameraType.USB``.
            rtsp_url: RTSP URL (required for RTSP).
            usb_index: USB index (required for USB).
            confidence_threshold: Detection threshold (0.0–1.0).
            evidence_mode: Evidence capture mode.

        Returns:
            A ``CameraDTO`` representing the newly created camera.

        Raises:
            DuplicateNameError: If the name already exists.
            CameraConnectionError: If the camera cannot be validated.
            ValueError: If validation fails.

        """
        logger.info(
            "Adding camera: name={}, type={}, rtsp_url={}, usb_index={}, "
            "threshold={}, evidence_mode={}",
            name,
            camera_type,
            rtsp_url,
            usb_index,
            confidence_threshold,
            evidence_mode,
        )

        # --- Validate name uniqueness ---
        if self._repo.exists_by_name(name):
            raise DuplicateNameError(name)

        # --- Build domain entity ---
        if camera_type == CameraType.RTSP:
            camera = Camera.create_rtsp(
                name=name,
                rtsp_url=rtsp_url or "",
                confidence_threshold=confidence_threshold,
            )
        elif camera_type == CameraType.USB:
            if usb_index is None:
                raise ValueError("USB index is required for USB cameras.")
            camera = Camera.create_usb(
                name=name,
                usb_index=usb_index,
                confidence_threshold=confidence_threshold,
            )
        else:
            raise ValueError(f"Unsupported camera type: {camera_type}")

        camera.evidence_mode = evidence_mode

        # --- Validate USB device exists ---
        if camera_type == CameraType.USB and self._usb_enumerator is not None:
            available = self._usb_enumerator.list_devices()
            if not any(d.index == usb_index for d in available):
                raise CameraConnectionError(
                    camera_id=None,
                    detail=f"USB device index {usb_index} not found. "
                    f"Available devices: {[d.index for d in available]}",
                )

        # --- Persist ---
        saved = self._repo.add(camera)
        logger.info("Camera added: id={}, name={}", saved.id, saved.name)
        return self._to_dto(saved)

    def edit_camera(
        self,
        camera_id: int,
        name: str | None = None,
        rtsp_url: str | None = None,
        usb_index: int | None = None,
        confidence_threshold: float | None = None,
        evidence_mode: str | None = None,
    ) -> CameraDTO:
        """Edit an existing camera.

        Args:
            camera_id: The camera to edit.
            name: New name (optional).
            rtsp_url: New RTSP URL (optional).
            usb_index: New USB index (optional).
            confidence_threshold: New threshold (optional).
            evidence_mode: New evidence mode (optional).

        Returns:
            The updated ``CameraDTO``.

        Raises:
            CameraNotFoundError: If the camera does not exist.
            DuplicateNameError: If the new name conflicts.

        """
        logger.info("Editing camera: id={}", camera_id)

        camera = self._repo.get_by_id(camera_id)
        if camera is None:
            raise CameraNotFoundError(camera_id)

        # --- Validate name uniqueness ---
        if name is not None and name != camera.name:
            if self._repo.exists_by_name(name):
                raise DuplicateNameError(name)
            camera.name = name

        # --- Update fields ---
        if rtsp_url is not None:
            camera.rtsp_url = rtsp_url if rtsp_url else None

        if usb_index is not None:
            camera.usb_index = usb_index if usb_index >= 0 else None

        if confidence_threshold is not None:
            camera.confidence_threshold = confidence_threshold

        if evidence_mode is not None:
            camera.evidence_mode = evidence_mode

        # --- Validate ---
        camera.validate()

        # --- Persist ---
        updated = self._repo.update(camera)
        logger.info("Camera edited: id={}", updated.id)
        return self._to_dto(updated)

    def delete_camera(self, camera_id: int) -> None:
        """Delete a camera and all associated data.

        Args:
            camera_id: The camera to delete.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        logger.info("Deleting camera: id={}", camera_id)

        if not self._repo.exists(camera_id):
            raise CameraNotFoundError(camera_id)

        self._repo.delete(camera_id)
        logger.info("Camera deleted: id={}", camera_id)

    def enable_camera(self, camera_id: int) -> CameraDTO:
        """Enable a camera for detection.

        Args:
            camera_id: The camera to enable.

        Returns:
            The updated ``CameraDTO``.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        logger.info("Enabling camera: id={}", camera_id)

        camera = self._repo.get_by_id(camera_id)
        if camera is None:
            raise CameraNotFoundError(camera_id)

        camera.enable()
        updated = self._repo.update(camera)
        return self._to_dto(updated)

    def disable_camera(self, camera_id: int) -> CameraDTO:
        """Disable a camera (stop detection).

        Args:
            camera_id: The camera to disable.

        Returns:
            The updated ``CameraDTO``.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        logger.info("Disabling camera: id={}", camera_id)

        camera = self._repo.get_by_id(camera_id)
        if camera is None:
            raise CameraNotFoundError(camera_id)

        camera.disable()
        updated = self._repo.update(camera)
        return self._to_dto(updated)

    def get_camera(self, camera_id: int) -> CameraDTO:
        """Retrieve a single camera by ID.

        Args:
            camera_id: The camera ID.

        Returns:
            The ``CameraDTO``.

        Raises:
            CameraNotFoundError: If the camera does not exist.

        """
        model = self._repo.get_by_id(camera_id)
        if model is None:
            raise CameraNotFoundError(camera_id)
        return self._to_dto(Camera.from_model(model))

    def get_all_cameras(self) -> list[CameraDTO]:
        """Retrieve all cameras.

        Returns:
            A list of ``CameraDTO`` instances.

        """
        cameras = Camera.from_model_list(self._repo.get_all())
        return [self._to_dto(c) for c in cameras]

    def get_enabled_cameras(self) -> list[CameraDTO]:
        """Retrieve all enabled cameras.

        Returns:
            A list of ``CameraDTO`` instances for enabled cameras.

        """
        cameras = Camera.from_model_list(self._repo.get_enabled())
        return [self._to_dto(c) for c in cameras]

    def enumerate_usb_devices(self) -> list[UsbDeviceInfo]:
        """Detect available USB camera devices.

        Returns:
            A list of detected USB devices.

        """
        if self._usb_enumerator is not None:
            return self._usb_enumerator.list_devices()
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dto(camera: Camera) -> CameraDTO:
        """Convert a domain Camera entity to a CameraDTO.

        Args:
            camera: The domain entity.

        Returns:
            A ``CameraDTO`` suitable for serialization.

        """
        return CameraDTO(
            id=camera.id if camera.id is not None else 0,
            name=camera.name,
            camera_type=camera.type.value,
            rtsp_url=camera.rtsp_url,
            usb_index=camera.usb_index,
            enabled=camera.enabled,
            confidence_threshold=camera.confidence_threshold,
            evidence_mode=camera.evidence_mode,
            created_at=camera.created_at,
            updated_at=camera.updated_at,
        )
