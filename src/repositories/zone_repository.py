"""Repository implementation for the Zone entity."""

from __future__ import annotations

from sqlalchemy import select

from loguru import logger

from src.database.models import ZoneModel
from src.database.session import SessionManager
from src.repositories.base import BaseRepository


class ZoneRepository(BaseRepository[ZoneModel]):
    """Repository for Zone CRUD operations.

    Provides zone-specific queries scoped to a camera,
    plus bulk deletion by camera ID.
    """

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize the zone repository.

        Args:
            session_manager: The application's SessionManager instance.

        """
        super().__init__(session_manager, ZoneModel)

    # ------------------------------------------------------------------
    # Zone-specific queries
    # ------------------------------------------------------------------

    def get_by_camera_id(self, camera_id: int) -> list[ZoneModel]:
        """Retrieve all zones belonging to a specific camera.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            A list of ZoneModel instances ordered by name.

        """
        session = self._session()
        stmt = (
            select(self._model_cls)
            .where(self._model_cls.camera_id == camera_id)  # type: ignore[arg-type]
            .order_by(self._model_cls.name)
        )
        result = list(session.scalars(stmt).all())
        logger.trace(
            "ZoneRepository.get_by_camera_id({}) -> {} rows",
            camera_id,
            len(result),
        )
        return result

    def get_by_name(self, name: str) -> ZoneModel | None:
        """Retrieve a zone by its name.

        Args:
            name: The zone name.

        Returns:
            The ZoneModel if found, else ``None``.

        """
        session = self._session()
        stmt = (
            select(self._model_cls)
            .where(self._model_cls.name == name)  # type: ignore[arg-type]
            .limit(1)
        )
        result = session.scalar(stmt)
        logger.trace("ZoneRepository.get_by_name({!r}) -> {}", name, result)
        return result

    def exists_by_name(self, name: str) -> bool:
        """Check whether a zone with the given name exists.

        Args:
            name: The zone name.

        Returns:
            ``True`` if a zone with that name exists.

        """
        session = self._session()
        stmt = (
            select(self._model_cls.id)
            .where(self._model_cls.name == name)  # type: ignore[arg-type]
            .limit(1)
        )
        result = session.execute(stmt).first()
        return result is not None

    def delete_by_camera_id(self, camera_id: int) -> int:
        """Delete all zones for a given camera.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            The number of zones deleted.

        """
        session = self._session()
        stmt = (
            self._model_cls.__table__.delete()
            .where(self._model_cls.camera_id == camera_id)  # type: ignore[arg-type]
        )
        result = session.execute(stmt)
        session.flush()
        logger.debug(
            "ZoneRepository.delete_by_camera_id({}) -> {} rows",
            camera_id,
            result.rowcount,
        )
        return result.rowcount

    def get_zone_count_for_camera(self, camera_id: int) -> int:
        """Return the number of zones assigned to a camera.

        Args:
            camera_id: The parent camera's primary key.

        Returns:
            The zone count.

        """
        session = self._session()
        stmt = (
            select(self._model_cls.id)
            .where(self._model_cls.camera_id == camera_id)  # type: ignore[arg-type]
        )
        result = session.execute(stmt)
        return len(result.fetchall())
