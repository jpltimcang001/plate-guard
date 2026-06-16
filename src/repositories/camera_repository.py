"""Repository implementation for the Camera entity."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from loguru import logger

from src.database.models import CameraModel
from src.database.session import SessionManager
from src.repositories.base import BaseRepository


class CameraRepository(BaseRepository[CameraModel]):
    """Repository for Camera CRUD operations.

    Extends the generic ``BaseRepository`` with camera-specific
    queries such as ``get_by_name`` and ``get_enabled``.
    """

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize the camera repository.

        Args:
            session_manager: The application's SessionManager instance.

        """
        super().__init__(session_manager, CameraModel)

    # ------------------------------------------------------------------
    # Camera-specific queries
    # ------------------------------------------------------------------

    def get_by_name(self, name: str) -> CameraModel | None:
        """Retrieve a camera by its unique name.

        Args:
            name: The camera name (case-sensitive).

        Returns:
            The CameraModel if found, else ``None``.

        """
        session = self._session()
        stmt = select(self._model_cls).where(
            self._model_cls.name == name,  # type: ignore[arg-type]
        )
        result = session.scalar(stmt)
        logger.trace("CameraRepository.get_by_name({!r}) -> {}", name, result)
        return result

    def get_enabled(self) -> list[CameraModel]:
        """Retrieve all cameras that are currently enabled.

        Returns:
            A list of enabled CameraModel instances.

        """
        session = self._session()
        stmt = (
            select(self._model_cls)
            .where(self._model_cls.enabled.is_(True))  # type: ignore[arg-type]
            .order_by(self._model_cls.name)
        )
        result = list(session.scalars(stmt).all())
        logger.trace("CameraRepository.get_enabled() -> {} rows", len(result))
        return result

    def get_by_type(self, camera_type: str) -> list[CameraModel]:
        """Retrieve all cameras of a given type (``rtsp`` or ``usb``).

        Args:
            camera_type: ``"rtsp"`` or ``"usb"``.

        Returns:
            A list of matching CameraModel instances.

        """
        session = self._session()
        stmt = (
            select(self._model_cls)
            .where(self._model_cls.type == camera_type)  # type: ignore[arg-type]
            .order_by(self._model_cls.name)
        )
        result = list(session.scalars(stmt).all())
        logger.trace("CameraRepository.get_by_type({!r}) -> {} rows", camera_type, len(result))
        return result

    def exists_by_name(self, name: str) -> bool:
        """Check whether a camera with the given name already exists.

        Args:
            name: The camera name to check.

        Returns:
            ``True`` if a camera with that name exists.

        """
        session = self._session()
        stmt = (
            select(1)
            .select_from(self._model_cls)
            .where(self._model_cls.name == name)  # type: ignore[arg-type]
            .limit(1)
        )
        result = session.execute(stmt).first()
        return result is not None

    def update_status(self, camera_id: int, enabled: bool) -> bool:
        """Set the enabled/disabled status of a camera.

        Args:
            camera_id: The camera's primary key.
            enabled: The new enabled state.

        Returns:
            ``True`` if the camera was found and updated.

        """
        session = self._session()
        stmt = (
            self._update_stmt({"enabled": enabled})
            .where(self._model_cls.id == camera_id)  # type: ignore[arg-type]
        )
        result = session.execute(stmt)
        session.flush()
        updated = result.rowcount > 0
        if updated:
            logger.debug(
                "CameraRepository.update_status({}, enabled={}) -> updated",
                camera_id,
                enabled,
            )
        return updated

    def update_confidence_threshold(
        self,
        camera_id: int,
        threshold: float,
    ) -> bool:
        """Update the confidence threshold for a camera.

        Args:
            camera_id: The camera's primary key.
            threshold: The new confidence threshold (0.0–1.0).

        Returns:
            ``True`` if the camera was found and updated.

        """
        session = self._session()
        stmt = (
            self._update_stmt({"confidence_threshold": threshold})
            .where(self._model_cls.id == camera_id)  # type: ignore[arg-type]
        )
        result = session.execute(stmt)
        session.flush()
        updated = result.rowcount > 0
        if updated:
            logger.debug(
                "CameraRepository.update_confidence_threshold({}, {}) -> updated",
                camera_id,
                threshold,
            )
        return updated

    def delete_camera_with_dependencies(self, camera_id: int) -> bool:
        """Delete a camera and all its associated zones, webhooks, and detections.

        Relies on ``ON DELETE CASCADE`` foreign keys defined in the database schema.

        Args:
            camera_id: The camera's primary key.

        Returns:
            ``True`` if the camera was found and deleted.

        """
        return self.delete(camera_id)
