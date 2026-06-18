"""Unit tests for the ShutdownManager.

Verifies registration, unregistration, ordered execution, timeout
handling, and error resilience.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from src.services.shutdown_manager import ShutdownManager


class TestRegistration:
    """Tests for handler registration."""

    def test_register_adds_handler(self) -> None:
        """Verify that a registered handler is tracked."""
        mgr = ShutdownManager()
        handler = lambda: None  # noqa: E731
        mgr.register("test", handler)
        assert mgr.handler_count == 1

    def test_register_multiple_handlers(self) -> None:
        """Verify multiple handlers can be registered."""
        mgr = ShutdownManager()
        mgr.register("a", lambda: None, priority=5)
        mgr.register("b", lambda: None, priority=10)
        assert mgr.handler_count == 2

    def test_register_raises_after_shutdown(self) -> None:
        """Verify that registration after shutdown raises."""
        mgr = ShutdownManager()
        mgr.shutdown()
        with pytest.raises(RuntimeError, match="Shutdown already in progress"):
            mgr.register("late", lambda: None)

    def test_unregister_removes_handler(self) -> None:
        """Verify that unregister removes the handler."""
        mgr = ShutdownManager()
        mgr.register("remove-me", lambda: None)
        assert mgr.unregister("remove-me") is True
        assert mgr.handler_count == 0

    def test_unregister_nonexistent_returns_false(self) -> None:
        """Verify that unregistering a non-existent handler returns False."""
        mgr = ShutdownManager()
        assert mgr.unregister("does-not-exist") is False


class TestExecution:
    """Tests for shutdown execution."""

    def test_calls_single_handler(self) -> None:
        """Verify that a single handler is called during shutdown."""
        mgr = ShutdownManager()
        mock = MagicMock()
        mgr.register("mock", mock)
        mgr.shutdown()
        mock.assert_called_once()

    def test_calls_handlers_in_priority_order(self) -> None:
        """Verify that handlers execute in priority order."""
        mgr = ShutdownManager()
        order: list[str] = []

        mgr.register("second", lambda: order.append("second"), priority=10)
        mgr.register("first", lambda: order.append("first"), priority=5)
        mgr.register("third", lambda: order.append("third"), priority=15)

        mgr.shutdown()
        assert order == ["first", "second", "third"]

    def test_continues_on_handler_error(self) -> None:
        """Verify that a failing handler doesn't stop subsequent handlers."""
        mgr = ShutdownManager()
        order: list[str] = []

        def failing() -> None:
            order.append("fail")
            msg = "intentional failure"
            raise RuntimeError(msg)

        mgr.register("fail", failing, priority=5)
        mgr.register("after", lambda: order.append("after"), priority=10)

        mgr.shutdown()
        assert order == ["fail", "after"]

    def test_idempotent_shutdown(self) -> None:
        """Verify that calling shutdown twice is safe."""
        mgr = ShutdownManager()
        mock = MagicMock()
        mgr.register("mock", mock)
        mgr.shutdown()
        mgr.shutdown()  # second call should be a no-op
        mock.assert_called_once()

    def test_timeout_does_not_block(self) -> None:
        """Verify that a handler that exceeds timeout doesn't block."""
        mgr = ShutdownManager()

        def slow() -> None:
            time.sleep(10)  # longer than our timeout

        mgr.register("slow", slow)
        start = time.monotonic()
        mgr.shutdown(timeout=0.1)
        elapsed = time.monotonic() - start
        assert elapsed < 5  # should return quickly


class TestEdgeCases:
    """Tests for edge cases."""

    def test_shutdown_with_no_handlers(self) -> None:
        """Verify that shutdown with no handlers is a no-op."""
        mgr = ShutdownManager()
        mgr.shutdown()  # should not raise
        assert mgr.handler_count == 0

    def test_handler_called_exactly_once(self) -> None:
        """Verify that each handler is called exactly once."""
        mgr = ShutdownManager()
        counter: list[int] = [0]

        def increment() -> None:
            counter[0] += 1

        mgr.register("inc", increment)
        mgr.shutdown()
        mgr.shutdown()  # no-op
        assert counter[0] == 1

    def test_handlers_clear_after_shutdown(self) -> None:
        """Verify that handler list is cleared after shutdown."""
        mgr = ShutdownManager()
        mgr.register("a", lambda: None)
        mgr.shutdown()
        assert mgr.handler_count == 0

    def test_thread_safety(self) -> None:
        """Verify basic thread safety of register and shutdown."""
        mgr = ShutdownManager()
        results: list[str] = []
        lock = threading.Lock()

        def safe_append(val: str) -> None:
            with lock:
                results.append(val)

        mgr.register("a", lambda: safe_append("a"), priority=10)
        mgr.register("b", lambda: safe_append("b"), priority=5)

        t = threading.Thread(target=mgr.shutdown)
        t.start()
        t.join(timeout=5)

        assert results == ["b", "a"]
