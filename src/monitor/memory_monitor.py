"""Memory usage monitor.

Periodically checks the application's memory usage using ``psutil``
and logs warnings when it exceeds configurable thresholds.

Usage
-----
::

    from src.monitor.memory_monitor import MemoryMonitor

    monitor = MemoryMonitor(
        warning_mb=500,
        critical_mb=1000,
        check_interval_seconds=30.0,
        on_warning=lambda mb: logger.warning("Memory: {} MB", mb),
        on_critical=lambda mb: logger.error("Memory: {} MB", mb),
    )
    monitor.start()

    # Later:
    monitor.stop()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from loguru import logger


@dataclass
class MemorySnapshot:
    """Memory usage snapshot at a point in time.

    Attributes:
        rss_mb: Resident Set Size in megabytes.
        vms_mb: Virtual Memory Size in megabytes.
        percent: Percentage of total physical memory used.
        timestamp: Monotonic timestamp of the snapshot.

    """

    rss_mb: float
    vms_mb: float
    percent: float
    timestamp: float = field(default_factory=lambda: _monotonic())  # noqa: E731


def _monotonic() -> float:
    """Return monotonic time (wrapped for testability)."""
    import time
    return time.monotonic()


class MemoryMonitor:
    """Periodically checks process memory and alerts on thresholds.

    The monitor runs on a ``QTimer`` on the main thread.

    Usage::

        monitor = MemoryMonitor(warning_mb=500, critical_mb=1000)
        monitor.start()

        # Get current usage:
        snapshot = monitor.snapshot()

        monitor.stop()
    """

    def __init__(
        self,
        warning_mb: float = 500.0,
        critical_mb: float = 1000.0,
        check_interval_seconds: float = 30.0,
        on_warning: Callable[[MemorySnapshot], None] | None = None,
        on_critical: Callable[[MemorySnapshot], None] | None = None,
    ) -> None:
        """Initialise the memory monitor.

        Args:
            warning_mb: Memory threshold in MB that triggers the warning
                callback (default 500).
            critical_mb: Memory threshold in MB that triggers the
                critical callback (default 1000).
            check_interval_seconds: Seconds between memory checks
                (default 30).
            on_warning: Called when memory exceeds ``warning_mb``.
            on_critical: Called when memory exceeds ``critical_mb``.

        Raises:
            ValueError: If ``warning_mb > critical_mb`` or either
                threshold is non-positive.

        """
        if warning_mb <= 0 or critical_mb <= 0:
            raise ValueError("Thresholds must be positive")
        if warning_mb > critical_mb:
            raise ValueError(
                f"warning_mb ({warning_mb}) must not exceed "
                f"critical_mb ({critical_mb})",
            )
        if check_interval_seconds <= 0:
            raise ValueError("check_interval_seconds must be positive")

        self._warning_mb = warning_mb
        self._critical_mb = critical_mb
        self._check_interval = check_interval_seconds
        self._on_warning = on_warning
        self._on_critical = on_critical

        self._timer: "QTimer | None" = None  # noqa: F821
        self._running = False
        self._last_snapshot: MemorySnapshot | None = None
        self._warning_active = False
        self._critical_active = False

        # Process handle for memory reading
        self._process: "psutil.Process | None" = None  # noqa: F821

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start periodic memory monitoring.

        Requires ``psutil`` to be installed.  If ``psutil`` is not
        available, a warning is logged and monitoring is disabled.

        """
        if self._running:
            return

        if not self._ensure_psutil():
            logger.warning(
                "MemoryMonitor: psutil not available — memory monitoring "
                "disabled. Install it with: pip install psutil",
            )
            return

        from PySide6.QtCore import QTimer

        self._process = self._get_process()

        self._timer = QTimer()
        self._timer.timeout.connect(self._check)
        self._timer.start(int(self._check_interval * 1000))
        self._running = True

        # Take an initial reading
        self._check()

        logger.info(
            "MemoryMonitor started (warning={}MB, critical={}MB, "
            "interval={}s)",
            self._warning_mb,
            self._critical_mb,
            self._check_interval,
        )

    def stop(self) -> None:
        """Stop periodic memory monitoring."""
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._process = None
        logger.debug("MemoryMonitor stopped")

    def snapshot(self) -> MemorySnapshot | None:
        """Take a memory usage snapshot now.

        Returns:
            A ``MemorySnapshot`` or ``None`` if monitoring is not
            active or psutil is not available.

        """
        if self._process is None and not self._ensure_psutil():
            return None

        if self._process is None:
            self._process = self._get_process()

        try:
            mem = self._process.memory_info()
            rss_mb = mem.rss / (1024 * 1024)
            vms_mb = mem.vms / (1024 * 1024)

            try:
                percent = self._process.memory_percent()
            except Exception:
                percent = 0.0

            self._last_snapshot = MemorySnapshot(
                rss_mb=round(rss_mb, 1),
                vms_mb=round(vms_mb, 1),
                percent=round(percent, 1),
            )
            return self._last_snapshot
        except (OSError, AttributeError) as exc:
            logger.opt(exception=True).warning(
                "MemoryMonitor: failed to read memory: {}",
                exc,
            )
            return None

    @property
    def is_running(self) -> bool:
        """Whether the monitor is running."""
        return self._running

    @property
    def last_snapshot(self) -> MemorySnapshot | None:
        """The most recent memory snapshot."""
        return self._last_snapshot

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check(self) -> None:
        """Run a single memory check cycle."""
        snap = self.snapshot()
        if snap is None:
            return

        rss = snap.rss_mb

        if rss >= self._critical_mb:
            if not self._critical_active:
                logger.warning(
                    "MemoryMonitor: CRITICAL memory usage: {}MB "
                    "(threshold: {}MB)",
                    rss,
                    self._critical_mb,
                )
                self._critical_active = True
                if self._on_critical is not None:
                    self._on_critical(snap)
        elif rss >= self._warning_mb:
            if not self._warning_active:
                logger.warning(
                    "MemoryMonitor: WARNING memory usage: {}MB "
                    "(threshold: {}MB)",
                    rss,
                    self._warning_mb,
                )
                self._warning_active = True
                if self._on_warning is not None:
                    self._on_warning(snap)
        else:
            # Reset alert flags when memory drops below thresholds
            if self._warning_active or self._critical_active:
                logger.info(
                    "MemoryMonitor: memory returned to normal ({}MB)",
                    rss,
                )
            self._warning_active = False
            self._critical_active = False

    def _ensure_psutil(self) -> bool:
        """Check if ``psutil`` is available.

        Returns:
            ``True`` if psutil can be imported.

        """
        try:
            import psutil  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _get_process() -> "psutil.Process":  # noqa: F821
        """Return a ``psutil.Process`` for the current process."""
        import psutil
        return psutil.Process(os.getpid())

    def __repr__(self) -> str:
        return (
            f"<MemoryMonitor running={self._running} "
            f"last={self._last_snapshot}>"
        )
