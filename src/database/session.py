"""SQLAlchemy session management with thread-local scoped sessions."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from loguru import logger


class SessionManager:
    """Manages SQLAlchemy sessions with thread-scoped lifecycle.

    Usage::

        manager = SessionManager(engine)
        with manager.session() as session:
            session.add(some_object)
            session.commit()

    """

    def __init__(self, engine: Engine) -> None:
        """Initialize the session manager.

        Args:
            engine: A SQLAlchemy Engine instance.

        """
        self._engine = engine
        self._session_factory = sessionmaker(
            bind=engine,
            expire_on_commit=False,
        )
        self._scoped_session: scoped_session[Session] = scoped_session(
            self._session_factory,
        )

    @property
    def engine(self) -> Engine:
        """Return the underlying SQLAlchemy Engine."""
        return self._engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(self) -> Session:
        """Create a new, independent session (not scoped).

        Use this for long-running background tasks where you
        want explicit control over the session lifecycle.

        Returns:
            A new SQLAlchemy ``Session``.

        """
        return self._session_factory()

    def get_scoped_session(self) -> Session:
        """Return the thread-local scoped session.

        The same session is returned for all calls within the
        same thread until ``remove_scoped_session`` is called.

        Returns:
            The thread-local scoped Session.

        """
        return self._scoped_session()

    def remove_scoped_session(self) -> None:
        """Remove the current thread's scoped session.

        Should be called at the end of a request / task to
        release the session back to the pool.

        """
        self._scoped_session.remove()

    def close(self) -> None:
        """Close all sessions and dispose of the engine connection pool."""
        self._scoped_session.remove()
        self._engine.dispose()
        logger.debug("SessionManager closed and engine disposed.")

    @contextmanager
    def session(self) -> Generator[Session, Any, None]:
        """Context manager that provides a session with automatic cleanup.

        Commits on success, rolls back on exception, and always
        closes the session.

        Yields:
            A SQLAlchemy ``Session``.

        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            logger.opt(exception=True).warning("Session rolled back due to exception.")
            raise
        finally:
            session.close()

    @contextmanager
    def scoped_session_context(self) -> Generator[Session, Any, None]:
        """Context manager for thread-local scoped sessions.

        Yields:
            The thread-local scoped Session.

        """
        try:
            yield self._scoped_session()
        except BaseException:
            self._scoped_session.rollback()
            raise
        finally:
            self._scoped_session.remove()
