"""Integration tests for EvidenceRetentionService.

Tests the file purge scheduler with real file I/O in a temporary
directory, verifying that files older than the retention period
are deleted while newer files are kept.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src.services.evidence_retention import EvidenceRetentionService

if TYPE_CHECKING:
    pass


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def retention_service(evidence_dir: Path) -> EvidenceRetentionService:
    """Return an EvidenceRetentionService configured with a 1-day retention."""
    return EvidenceRetentionService(
        media_dir=str(evidence_dir),
        retention_days=1,
        check_interval_hours=24,  # Not used in manual purge
    )


def _touch_file(path: Path, days_old: float) -> None:
    """Create an empty file at *path* with an mtime in the past."""
    """Create an empty file at *path* with an mtime in the past."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test content")
    age_seconds = days_old * 86400
    new_mtime = time.time() - age_seconds
    os.utime(path, (new_mtime, new_mtime))


# ======================================================================
# EvidenceRetentionService — purge
# ======================================================================


class TestEvidenceRetentionPurge:
    """Tests for purge() logic."""

    def test_purge_removes_old_snapshots(
        self,
        retention_service: EvidenceRetentionService,
        evidence_dir: Path,
    ) -> None:
        """Snapshots older than retention_days are deleted."""
        old_file = evidence_dir / "snapshots" / "old_snapshot.jpg"
        _touch_file(old_file, days_old=5.0)  # 5 days old
        assert old_file.is_file()

        result = retention_service.purge()
        assert result.deleted_files >= 1
        assert not old_file.is_file()

    def test_purge_keeps_recent_snapshots(
        self,
        retention_service: EvidenceRetentionService,
        evidence_dir: Path,
    ) -> None:
        """Snapshots newer than retention_days are kept."""
        new_file = evidence_dir / "snapshots" / "new_snapshot.jpg"
        _touch_file(new_file, days_old=0.1)  # ~2.4 hours old
        assert new_file.is_file()

        result = retention_service.purge()
        # The file should still exist (not deleted)
        assert new_file.is_file()

    def test_purge_removes_old_clips(
        self,
        retention_service: EvidenceRetentionService,
        evidence_dir: Path,
    ) -> None:
        """Video clips older than retention_days are deleted."""
        old_clip = evidence_dir / "clips" / "old_clip.mp4"
        _touch_file(old_clip, days_old=3.0)
        assert old_clip.is_file()

        result = retention_service.purge()
        assert result.deleted_files >= 1
        assert not old_clip.is_file()

    def test_purge_keeps_recent_clips(
        self,
        retention_service: EvidenceRetentionService,
        evidence_dir: Path,
    ) -> None:
        """Video clips newer than retention_days are kept."""
        new_clip = evidence_dir / "clips" / "new_clip.mp4"
        _touch_file(new_clip, days_old=0.5)
        assert new_clip.is_file()

        result = retention_service.purge()
        assert new_clip.is_file()

    def test_purge_mixed_ages(
        self,
        retention_service: EvidenceRetentionService,
        evidence_dir: Path,
    ) -> None:
        """Only files older than retention_days are deleted; newer ones survive."""
        files = [
            ("snapshots", "old_snap.jpg", 5.0, True),
            ("snapshots", "recent_snap.jpg", 0.5, False),
            ("clips", "old_clip.mp4", 3.0, True),
            ("clips", "recent_clip.mp4", 0.2, False),
        ]
        expected_paths = {}
        old_count = 0
        for subdir, name, age, should_delete in files:
            p = evidence_dir / subdir / name
            _touch_file(p, age)
            expected_paths[p] = not should_delete  # True = should survive
            if should_delete:
                old_count += 1

        result = retention_service.purge()
        assert result.deleted_files >= old_count

        for path, should_survive in expected_paths.items():
            if should_survive:
                assert path.is_file(), f"{path} should still exist"
            else:
                assert not path.is_file(), f"{path} should have been deleted"

    def test_purge_empty_directory(
        self,
        retention_service: EvidenceRetentionService,
        evidence_dir: Path,
    ) -> None:
        """Purge on an empty directory returns zero files deleted."""
        result = retention_service.purge()
        assert result.deleted_files == 0
        assert result.errors == 0

    def test_purge_with_nonexistent_dir(
        self,
        evidence_dir: Path,
    ) -> None:
        """Purge with a non-existent media base dir handles gracefully."""
        service = EvidenceRetentionService(
            media_dir=str(evidence_dir / "nonexistent"),
            retention_days=1,
        )
        result = service.purge()
        assert result.deleted_files == 0
        assert result.errors == 0

    def test_purge_result_attributes(
        self,
        retention_service: EvidenceRetentionService,
        evidence_dir: Path,
    ) -> None:
        """PurgeResult contains expected attributes after a purge."""
        _touch_file(evidence_dir / "snapshots" / "gone.jpg", days_old=10.0)
        result = retention_service.purge()
        assert result.deleted_files >= 1
        assert result.freed_bytes > 0
        assert result.errors == 0
        assert result.duration_seconds > 0.0

    def test_purge_respects_retention_days(
        self,
        evidence_dir: Path,
    ) -> None:
        """Files older than retention_days are deleted; newer files are kept."""
        service = EvidenceRetentionService(
            media_dir=str(evidence_dir),
            retention_days=1,
        )
        old_file = evidence_dir / "snapshots" / "old.jpg"
        _touch_file(old_file, days_old=2.0)  # 2 days → older than 1 day
        new_file = evidence_dir / "snapshots" / "new.jpg"
        _touch_file(new_file, days_old=0.5)  # 12 hours → newer than 1 day
        assert old_file.is_file()
        assert new_file.is_file()

        result = service.purge()
        assert not old_file.is_file(), "Old file should have been deleted"
        assert new_file.is_file(), "New file should still exist"
        assert result.deleted_files >= 1
