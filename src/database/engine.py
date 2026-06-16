"""SQLAlchemy engine factory and lifecycle management."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase

from loguru import logger


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""

    __abstract__ = True


def _get_default_db_path() -> str:
    """Return the default SQLite database path.

    Uses the XDG data home convention on Linux/macOS and
    %APPDATA% on Windows. Falls back to ~/.plate_guard/.
    """
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get(
                "XDG_DATA_HOME",
                Path.home() / ".local" / "share",
            )
        )
    data_dir = base / "plate-guard"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "plate_guard.db")


def create_engine(
    database_url: str | None = None,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
    **kwargs: Any,
) -> Engine:
    """Create and configure a SQLAlchemy engine.

    Args:
        database_url: SQLAlchemy database URL. Defaults to SQLite at
            the platform-specific data directory.
        echo: Enable SQL echo for debugging.
        pool_size: Number of connections to maintain in the pool.
        max_overflow: Maximum overflow connections beyond pool_size.
        **kwargs: Additional arguments passed to ``create_engine``.

    Returns:
        A configured SQLAlchemy Engine instance.

    """
    url = database_url or f"sqlite:///{_get_default_db_path()}"

    engine = create_engine(
        url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        **kwargs,
    )

    _configure_sqlite_pragmas(engine)

    logger.debug("SQLAlchemy engine created: url={}, echo={}", url, echo)
    return engine


def _configure_sqlite_pragmas(engine: Engine) -> None:
    """Set optimal SQLite pragmas for WAL mode and performance."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA cache_size=-8000;")  # 8 MB cache
        cursor.execute("PRAGMA temp_store=MEMORY;")
        cursor.close()


def init_db(engine: Engine) -> None:
    """Create all tables defined by the ORM models.

    Uses ``Base.metadata.create_all`` which is safe to call
    multiple times (idempotent).

    Args:
        engine: A SQLAlchemy Engine instance.

    """
    from src.database.models import (  # noqa: F401  ensure models are registered
        CameraModel,
        DetectionModel,
        WebhookModel,
        ZoneModel,
    )

    Base.metadata.create_all(engine)
    logger.info("Database tables created / verified.")


def drop_db(engine: Engine) -> None:
    """Drop all tables. Intended for test teardown only.

    Args:
        engine: A SQLAlchemy Engine instance.

    """
    Base.metadata.drop_all(engine)
    logger.warning("All database tables dropped.")
