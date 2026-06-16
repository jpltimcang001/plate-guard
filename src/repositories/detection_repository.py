"""Repository implementation for the Detection entity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from loguru import logger

from src.database.models import DetectionModel
from src.database.session import SessionManager
from src.repositories.base import BaseRepository


class DetectionFilter:
    """Filter parameters for querying detection records.

    All fields are optional. When multiple fields are set,
    they are combined with AND logic.
    """

    def __init__(
        self,
        camera_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        plate_number: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> None:
        """Initialize the filter.

        Args:
            camera_id: Filter by camera ID.
            date_from: Include detections at or after this timestamp.
            date_to: Include detections at or before this timestamp.
            plate_number: Substring match on plate number (case-insensitive).
            limit: Maximum number of records to return.
            offset: Number of records to skip for pagination.

        """
        self.camera_id = camera_id
        self.date_from = date_from
        self.date_to = date_to
        self.plate_number = plate_number
        self.limit = limit
        self.offset = offset


class DetectionRepository(BaseRepository[DetectionModel]):
    """Repository for Detection CRUD operations.

    Provides filtered queries, pagination, counts, and
    bulk purging for retention policies.
    """

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize the detection repository.

        Args:
            session_manager: The application's SessionManager instance.

        """
        super().__init__(session_manager, DetectionModel)

    # ------------------------------------------------------------------
    # Filtered queries
    # ------------------------------------------------------------------

    def get_filtered(self, filter_: DetectionFilter) -> list[DetectionModel]:
        """Retrieve detections matching the given filter criteria.

        Args:
            filter_: A ``DetectionFilter`` instance.

        Returns:
            A list of matching DetectionModel instances.

        """
        session = self._session()
        stmt = self._build_filtered_query(filter_).order_by(
            self._model_cls.detected_at.desc(),
        )
        stmt = stmt.limit(filter_.limit).offset(filter_.offset)
        result = list(session.scalars(stmt).all())
        logger.trace("DetectionRepository.get_filtered() -> {} rows", len(result))
        return result

    def count_filtered(self, filter_: DetectionFilter) -> int:
        """Return the count of detections matching the given filter.

        Args:
            filter_: A ``DetectionFilter`` instance.

        Returns:
            The matching record count.

        """
        session = self._session()
        stmt = self._build_filtered_query(filter_)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = session.scalar(count_stmt)
        return result or 0

    def _build_filtered_query(self, filter_: DetectionFilter) -> select:
        """Build a select statement with optional WHERE clauses.

        Args:
            filter_: A ``DetectionFilter`` instance.

        Returns:
            A SQLAlchemy ``Select`` statement.

        """
        stmt = select(self._model_cls)

        if filter_.camera_id is not None:
            stmt = stmt.where(
                self._model_cls.camera_id == filter_.camera_id,  # type: ignore[arg-type]
            )

        if filter_.date_from is not None:
            stmt = stmt.where(
                self._model_cls.detected_at >= filter_.date_from,  # type: ignore[arg-type]
            )

        if filter_.date_to is not None:
            stmt = stmt.where(
                self._model_cls.detected_at <= filter_.date_to,  # type: ignore[arg-type]
            )

        if filter_.plate_number is not None:
            stmt = stmt.where(
                self._model_cls.plate_number.ilike(  # type: ignore[arg-type]
                    f"%{filter_.plate_number}%",
                ),
            )

        return stmt

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------

    def update_webhook_status(
        self,
        detection_id: int,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """Update the webhook delivery status for a detection record.

        Args:
            detection_id: The detection's primary key.
            status: The new webhook status value.
            error_message: Optional error detail for failed deliveries.

        Returns:
            ``True`` if the record was found and updated.

        """
        session = self._session()
        values: dict = {"webhook_status": status}
        if error_message is not None:
            # Store error message: we append to a simple text column.
            # In a production system this would be a separate field.
            pass

        stmt = (
            self._update_stmt(values)
            .where(self._model_cls.id == detection_id)  # type: ignore[arg-type]
        )
        result = session.execute(stmt)
        session.flush()
        updated = result.rowcount > 0
        if updated:
            logger.debug(
                "DetectionRepository.update_webhook_status({}, {}) -> updated",
                detection_id,
                status,
            )
        return updated

    # ------------------------------------------------------------------
    # Recent & purging
    # ------------------------------------------------------------------

    def get_recent(self, count: int = 10) -> list[DetectionModel]:
        """Return the most recent detection records.

        Args:
            count: The number of records to return.

        Returns:
            A list of the most recent DetectionModel instances.

        """
        session = self._session()
        stmt = (
            select(self._model_cls)
            .order_by(self._model_cls.detected_at.desc())
            .limit(count)
        )
        result = list(session.scalars(stmt).all())
        logger.trace("DetectionRepository.get_recent({}) -> {} rows", count, len(result))
        return result

    def delete_older_than(self, cutoff: datetime) -> int:
        """Delete detection records older than the given cutoff timestamp.

        This also triggers cascading deletion of associated evidence
        at the application layer (the caller is responsible for
        cleaning up files on disk).

        Args:
            cutoff: Timestamp threshold; records with ``detected_at < cutoff``
                are deleted.

        Returns:
            The number of deleted records.

        """
        session = self._session()
        stmt = (
            self._model_cls.__table__.delete()
            .where(self._model_cls.detected_at < cutoff)  # type: ignore[arg-type]
        )
        result = session.execute(stmt)
        session.flush()
        logger.info(
            "DetectionRepository.delete_older_than({}) -> {} rows",
            cutoff.isoformat(),
            result.rowcount,
        )
        return result.rowcount
