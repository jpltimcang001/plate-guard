"""Graceful shutdown orchestration.

The ``ShutdownManager`` collects *shutdown handlers* from across the
application and invokes them in reverse registration order when
``shutdown()`` is called.  This gives later-registered components
(which may depend on earlier ones) a chance to clean up first.

Usage
-----
Register handlers at application startup::

    from src.services.shutdown_manager import ShutdownManager

    shutdown_mgr = ShutdownManager()
    shutdown_mgr.register("frame-capture", lambda: capture.stop(), priority=10)
    shutdown_mgr.register("db-session", lambda: session.close(), priority=20)

    # Later, on quit:
    shutdown_mgr.shutdown()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from loguru import logger


@dataclass
class _ShutdownEntry:
    """A registered shutdown handler.

    Attributes:
        name: Human-readable identifier for logging.
        handler: The zero-argument callable to invoke.
        priority: Lower numbers run first (default 10).

    """

    name: str
    handler: Callable[[], None]
    priority: int = 10


class ShutdownManager:
    """Manages graceful application shutdown.

    Collects handlers from across the application and calls them in
    priority order when ``shutdown()`` is invoked.

    Usage::

        mgr = ShutdownManager()
        mgr.register("capture-1", capture.stop, priority=5)
        mgr.shutdown()
    """

    def __init__(self) -> None:
        """Initialise the shutdown manager."""
        self._entries: List[_ShutdownEntry] = []
        self._shutdown_started = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        handler: Callable[[], None],
        priority: int = 10,
    ) -> None:
        """Register a shutdown handler.

        Handlers are called in ascending priority order.  If two
        handlers have the same priority they are called in the order
        they were registered.

        Args:
            name: A human-readable label for logging.
            handler: A zero-argument callable.  It should not raise —
                if it does, the error is logged but other handlers
                still run.
            priority: Execution order (lower = earlier).

        Raises:
            RuntimeError: If ``shutdown()`` has already been called.

        """
        if self._shutdown_started:
            raise RuntimeError("Shutdown already in progress")

        self._entries.append(_ShutdownEntry(name=name, handler=handler, priority=priority))
        logger.debug("ShutdownManager: registered handler {!r} (priority={})", name, priority)

    def unregister(self, name: str) -> bool:
        """Remove a previously registered handler by name.

        Args:
            name: The handler name to remove.

        Returns:
            ``True`` if a handler was removed, ``False`` if not found.

        """
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.name != name]
        removed = len(self._entries) < before
        if removed:
            logger.debug("ShutdownManager: unregistered handler {!r}", name)
        return removed

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def shutdown(self, timeout: float = 30.0) -> None:
        """Execute all registered shutdown handlers in priority order.

        Each handler is called sequentially.  If a handler takes longer
        than ``timeout`` seconds the shutdown continues with the next
        handler.

        Args:
            timeout: Maximum seconds to wait for each individual handler
                (default 30).

        """
        if self._shutdown_started:
            logger.warning("Shutdown already in progress, ignoring duplicate call")
            return

        self._shutdown_started = True
        sorted_entries = sorted(self._entries, key=lambda e: e.priority)

        logger.info(
            "ShutdownManager: commencing shutdown with {} handlers",
            len(sorted_entries),
        )

        for entry in sorted_entries:
            try:
                logger.debug("ShutdownManager: running {!r}...", entry.name)
                self._run_with_timeout(entry.handler, timeout)
                logger.debug("ShutdownManager: completed {!r}", entry.name)
            except Exception:
                logger.opt(exception=True).warning(
                    "ShutdownManager: handler {!r} failed", entry.name,
                )

        self._entries.clear()
        logger.info("ShutdownManager: shutdown complete")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_with_timeout(handler: Callable[[], None], timeout: float) -> None:
        """Run a handler, raising if it exceeds *timeout*.

        Uses a daemon-thread join with timeout to detect hangs.
        The thread is *not* killed if it times out — the handler
        continues running in the background.

        Args:
            handler: The callable to run.
            timeout: Maximum seconds to wait.

        """
        import threading

        thread = threading.Thread(target=handler, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning(
                "ShutdownManager: handler did not complete within {}s, "
                "continuing shutdown",
                timeout,
            )

    @property
    def handler_count(self) -> int:
        """Number of registered shutdown handlers."""
        return len(self._entries)

    def __repr__(self) -> str:
        return f"<ShutdownManager handlers={self.handler_count}>"
