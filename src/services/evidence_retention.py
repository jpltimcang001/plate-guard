"""Evidence retention/purge scheduler.

Periodically deletes snapshot and video clip files that are older
than the configured retention period.

Usage
-----
::

    from src.services.evidence_retention import EvidenceRetentionService

    retention = EvidenceRetentionService(
        media_dir="./media",
        retention_days=30,
    )
    retention.start()  # runs on a QTimer

    # Trigger a cleanup immediately:
    result = retention.purge()
    print(f"Deleted {result.deleted_files} files, freed {result.freed_bytes} bytes")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger


@dataclass
class PurgeResult:
    """Result of a single purge operation.

    Attributes:
        deleted_files: Number of files deleted.
        freed_bytes: Total bytes freed.
        errors: Number of errors encountered during deletion.
        duration_seconds: How long the purge took.
        purged_at: Monotonic timestamp of the operation.

    """

    deleted_files: int = 0
    freed_bytes: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    purged_at: float = field(default_factory=time.monotonic)


class EvidenceRetentionService:
    """Deletes evidence files older than the configured retention period.

    Uses a ``QTimer`` to run periodic purges.  Snapshots and video clips
    are scanned separately.

    Usage::

        service = EvidenceRetentionService(
            media_dir="./media",
            retention_days=30,
            check_interval_hours=24,
        )
        service.start()
        service.stop()
    """

    def __init__(
        self,
        media_dir: str | Path = "media",
        retention_days: int = 30,
        check_interval_hours: int = 24,
    ) -> None:
        """Initialise the evidence retention service.

        Args:
            media_dir: Root directory containing ``snapshots/`` and
                ``clips/`` subdirectories.
            retention_days: Files older than this many days will be
                deleted (default 30).
            check_interval_hours: How often to run the purge check
                (default 24 hours).

        Raises:
            ValueError: If ``retention_days`` or
                ``check_interval_hours`` is non-positive.

        """
        if retention_days < 1:
            raise ValueError("retention_days must be at least 1")
        if check_interval_hours < 1:
            raise ValueError("check_interval_hours must be at least 1")

        self._media_dir = Path(media_dir)
        self._retention_days = retention_days
        self._check_interval_hours = check_interval_hours
        self._cutoff_seconds = retention_days * 86400

        self._timer: "QTimer | None" = None  # noqa: F821
        self._running = False

        logger.debug(
            "EvidenceRetentionService initialised (retention={}d, "
            "interval={}h, dir={})",
            retention_days,
            check_interval_hours,
            media_dir,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic purge timer."""
        if self._running:
            return

        from PySide6.QtCore import QTimer

        self._timer = QTimer()
        interval_ms = int(self._check_interval_hours * 3600 * 1000)
        self._timer.timeout.connect(self.purge)
        self._timer.start(interval_ms)
        self._running = True

        logger.info(
            "EvidenceRetentionService started (retention={}d, interval={}h)",
            self._retention_days,
            self._check_interval_hours,
        )

    def stop(self) -> None:
        """Stop the periodic purge timer."""
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        logger.debug("EvidenceRetentionService stopped")

    def purge(self) -> PurgeResult:
        """Run a single purge cycle — delete files older than retention.

        Returns:
            A ``PurgeResult`` summarising the operation.

        """
        start = time.monotonic()
        result = PurgeResult()

        # Scan snapshots and clips directories
        for subdir in ("snapshots", "clips"):
            target_dir = self._media_dir / subdir
            if not target_dir.is_dir():
                continue

            for entry in target_dir.iterdir():
                if not entry.is_file():
                    continue

                age = time.time() - entry.stat().st_mtime
                if age > self._cutoff_seconds:
                    try:
                        size = entry.stat().st_size
                        entry.unlink()
                        result.deleted_files += 1
                        result.freed_bytes += size
                        logger.debug(
                            "Purged old evidence: {} ({} bytes, age={:.1f}s)",
                            entry,
                            size,
                            age,
                        )
                    except OSError as exc:
                        logger.warning(
                            "Failed to delete {}: {}",
                            entry,
                            exc,
                        )
                        result.errors += 1

        result.duration_seconds = time.monotonic() - start

        if result.deleted_files > 0 or result.errors > 0:
            logger.info(
                "Evidence purge complete: {} files deleted, "
                "{} bytes freed, {} errors in {:.2f}s",
                result.deleted_files,
                result.freed_bytes,
                result.errors,
                result.duration_seconds,
            )

        return result

    @property
    def is_running(self) -> bool:
        """Whether the service is running."""
        return self._running

    @property
    def retention_days(self) -> int:
        """The configured retention period in days."""
        return self._retention_days

    def __repr__(self) -> str:
        return (
            f"<EvidenceRetentionService retention={self._retention_days}d "
            f"running={self._running}>"
        )
