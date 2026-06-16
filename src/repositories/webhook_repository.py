"""Repository implementation for the Webhook entity."""

from __future__ import annotations

from sqlalchemy import select

from loguru import logger

from src.database.models import WebhookModel
from src.database.session import SessionManager
from src.repositories.base import BaseRepository


class WebhookRepository(BaseRepository[WebhookModel]):
    """Repository for Webhook CRUD operations.

    Provides webhook-specific queries scoped to a camera,
    plus bulk deletion by camera ID.
    """

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize the webhook repository.

        Args:
            session_manager: The application's SessionManager instance.

        """
        super().__init__(session_manager, WebhookModel)

    # ------------------------------------------------------------------
    # Webhook-specific queries
    # ------------------------------------------------------------------

    def get_by_camera_id(self, camera_id: int) -> list[WebhookModel]:
        """Retrieve all webhook configs for a specific camera.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            A list of WebhookModel instances.

        """
        session = self._session()
        stmt = (
            select(self._model_cls)
            .where(self._model_cls.camera_id == camera_id)  # type: ignore[arg-type]
            .order_by(self._model_cls.id)
        )
        result = list(session.scalars(stmt).all())
        logger.trace(
            "WebhookRepository.get_by_camera_id({}) -> {} rows",
            camera_id,
            len(result),
        )
        return result

    def delete_by_camera_id(self, camera_id: int) -> int:
        """Delete all webhooks for a given camera.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            The number of webhooks deleted.

        """
        session = self._session()
        stmt = (
            self._model_cls.__table__.delete()
            .where(self._model_cls.camera_id == camera_id)  # type: ignore[arg-type]
        )
        result = session.execute(stmt)
        session.flush()
        logger.debug(
            "WebhookRepository.delete_by_camera_id({}) -> {} rows",
            camera_id,
            result.rowcount,
        )
        return result.rowcount

    def has_webhooks(self, camera_id: int) -> bool:
        """Check if a camera has any webhook configurations.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            ``True`` if at least one webhook exists for the camera.

        """
        session = self._session()
        stmt = (
            select(1)
            .select_from(self._model_cls)
            .where(self._model_cls.camera_id == camera_id)  # type: ignore[arg-type]
            .limit(1)
        )
        return session.execute(stmt).first() is not None
