"""Abstract base repository providing common CRUD operations.

All concrete repositories inherit from ``BaseRepository`` to ensure
consistent transaction handling and reduce boilerplate.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.orm import Session

from loguru import logger

from src.database.engine import Base
from src.database.session import SessionManager

T = TypeVar("T", bound=Base)
"""Type variable bound to the declarative Base."""


class BaseRepository(Generic[T]):
    """Generic base repository with common CRUD operations.

    Type param ``T`` must be a SQLAlchemy ORM model class.

    Usage::

        class CameraRepository(BaseRepository[CameraModel]):
            def __init__(self, session_manager: SessionManager) -> None:
                super().__init__(session_manager, CameraModel)

    """

    def __init__(self, session_manager: SessionManager, model_cls: type[T]) -> None:
        """Initialize the repository.

        Args:
            session_manager: The application's SessionManager instance.
            model_cls: The ORM model class this repository manages.

        """
        self._session_manager = session_manager
        self._model_cls = model_cls

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def model_cls(self) -> type[T]:
        """Return the ORM model class managed by this repository."""
        return self._model_cls

    # ------------------------------------------------------------------
    # Session access
    # ------------------------------------------------------------------

    def _session(self) -> Session:
        """Return a scoped session for the current thread."""
        return self._session_manager.get_scoped_session()

    # ------------------------------------------------------------------
    # Standard CRUD
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> T | None:
        """Retrieve an entity by its primary key.

        Args:
            entity_id: The primary key value.

        Returns:
            The entity if found, else ``None``.

        """
        session = self._session()
        result = session.get(self._model_cls, entity_id)
        logger.trace("{} get_by_id({}) -> {}", self._model_cls.__name__, entity_id, result)
        return result

    def get_all(self) -> list[T]:
        """Retrieve all entities of this type.

        Returns:
            A list of all entities.

        """
        session = self._session()
        stmt = select(self._model_cls).order_by(self._model_cls.id)
        result = list(session.scalars(stmt).all())
        logger.trace("{} get_all() -> {} rows", self._model_cls.__name__, len(result))
        return result

    def add(self, entity: T) -> T:
        """Add a new entity to the database.

        Args:
            entity: The entity instance to persist.

        Returns:
            The entity with its generated primary key populated.

        """
        session = self._session()
        session.add(entity)
        session.flush()
        session.refresh(entity)
        logger.debug("{} add() -> id={}", self._model_cls.__name__, entity.id)
        return entity

    def update(self, entity: T) -> T:
        """Update an existing entity.

        The entity is merged into the session and flushed.

        Args:
            entity: The entity instance with modified attributes.

        Returns:
            The updated entity.

        """
        session = self._session()
        merged = session.merge(entity)
        session.flush()
        session.refresh(merged)
        logger.debug("{} update() -> id={}", self._model_cls.__name__, merged.id)
        return merged

    def delete(self, entity_id: int) -> bool:
        """Delete an entity by its primary key.

        Args:
            entity_id: The primary key of the entity to delete.

        Returns:
            ``True`` if a row was deleted, ``False`` if not found.

        """
        session = self._session()
        stmt = delete(self._model_cls).where(self._model_cls.id == entity_id)
        result = session.execute(stmt)
        session.flush()
        deleted = result.rowcount > 0
        if deleted:
            logger.debug("{} delete({}) -> deleted", self._model_cls.__name__, entity_id)
        else:
            logger.trace("{} delete({}) -> not found", self._model_cls.__name__, entity_id)
        return deleted

    def count(self) -> int:
        """Return the total number of entities.

        Returns:
            The row count.

        """
        session = self._session()
        stmt = select(func.count()).select_from(self._model_cls)
        result = session.scalar(stmt)
        return result or 0

    def exists(self, entity_id: int) -> bool:
        """Check whether an entity with the given ID exists.

        Args:
            entity_id: The primary key to check.

        Returns:
            ``True`` if a matching row exists.

        """
        session = self._session()
        stmt = select(self._model_cls.id).where(self._model_cls.id == entity_id).limit(1)
        result = session.execute(stmt).first()
        return result is not None

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def bulk_insert(self, entities: list[T]) -> list[T]:
        """Insert multiple entities in a single batch.

        Args:
            entities: A list of entity instances.

        Returns:
            The inserted entities with IDs populated.

        """
        if not entities:
            return []
        session = self._session()
        session.add_all(entities)
        session.flush()
        for entity in entities:
            session.refresh(entity)
        logger.debug(
            "{} bulk_insert() -> {} rows",
            self._model_cls.__name__,
            len(entities),
        )
        return entities

    def bulk_delete(self, entity_ids: list[int]) -> int:
        """Delete multiple entities by their primary keys.

        Args:
            entity_ids: A list of primary key values.

        Returns:
            The number of rows deleted.

        """
        if not entity_ids:
            return 0
        session = self._session()
        stmt = delete(self._model_cls).where(self._model_cls.id.in_(entity_ids))
        result = session.execute(stmt)
        session.flush()
        logger.debug(
            "{} bulk_delete() -> {} rows",
            self._model_cls.__name__,
            result.rowcount,
        )
        return result.rowcount

    # ------------------------------------------------------------------
    # Query builder helpers
    # ------------------------------------------------------------------

    def _select_stmt(self) -> Select[tuple[T]]:
        """Return a base select statement for the model."""
        return select(self._model_cls)

    def _exists_stmt(self) -> Select[tuple[int]]:
        """Return a select statement that yields 0 or 1."""
        return select(1).select_from(self._model_cls).limit(1)

    def _update_stmt(self, values: dict[str, Any]) -> Any:
        """Return an update statement for the model."""
        return update(self._model_cls).values(values)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_integrity_error(self, exc: Exception, context: str = "") -> None:
        """Log and re-raise integrity errors with context.

        Args:
            exc: The caught exception.
            context: Optional context string describing the operation.

        """
        logger.error(
            "Integrity error in {} {}: {}",
            self._model_cls.__name__,
            context,
            exc,
        )
        raise
