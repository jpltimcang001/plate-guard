"""Unit tests for the EvidenceRetentionService.

Uses temporary directories to test file deletion logic.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.evidence_retention import EvidenceRetentionService, PurgeResult


class TestInit:
    """Tests for EvidenceRetentionService initialisation."""

    def test_default_params(self) -> None:
        """Verify default parameter values."""
        service = EvidenceRetentionService()
        assert service.retention_days == 30
        assert not service.is_running
        assert service._check_interval_hours == 24

    def test_custom_params(self) -> None:
        """Verify custom parameter values."""
        service = EvidenceRetentionService(
            media_dir=str(Path("custom") / "media"),
            retention_days=7,
            check_interval_hours=12,
        )
        assert service.retention_days == 7
        assert service._check_interval_hours == 12
        assert str(service._media_dir) == str(Path("custom") / "media")

    def test_invalid_params_raise(self) -> None:
        """Verify that invalid parameters raise ValueError."""
        with pytest.raises(ValueError):
            EvidenceRetentionService(retention_days=0)
        with pytest.raises(ValueError):
            EvidenceRetentionService(retention_days=-1)
        with pytest.raises(ValueError):
            EvidenceRetentionService(check_interval_hours=0)


class TestPurge:
    """Tests for the purge operation."""

    def test_purge_empty_directory(self, tmp_path: Path) -> None:
        """Verify that purge on empty directory is a no-op."""
        service = EvidenceRetentionService(media_dir=str(tmp_path), retention_days=1)
        result = service.purge()
        assert isinstance(result, PurgeResult)
        assert result.deleted_files == 0
        assert result.freed_bytes == 0
        assert result.errors == 0

    def test_purge_old_files(self, tmp_path: Path) -> None:
        """Verify that old files are deleted."""
        # Create snapshot and clip dirs with old files
        snap_dir = tmp_path / "snapshots"
        clip_dir = tmp_path / "clips"
        snap_dir.mkdir(parents=True)
        clip_dir.mkdir()

        old_snap = snap_dir / "old_snap.jpg"
        old_snap.write_text("old snapshot content")
        old_clip = clip_dir / "old_clip.mp4"
        old_clip.write_text("old clip content")

        # Set mtime far in the past
        past = time.time() - 86400 * 10  # 10 days ago
        os_utime = None
        try:
            import os
            os.utime(str(old_snap), (past, past))
            os.utime(str(old_clip), (past, past))
            os_utime = True
        except Exception:
            os_utime = False

        service = EvidenceRetentionService(
            media_dir=str(tmp_path),
            retention_days=1,  # 1 day retention
        )
        result = service.purge()

        if os_utime:
            assert result.deleted_files == 2
            assert result.freed_bytes > 0
            assert not old_snap.exists()
            assert not old_clip.exists()
        else:
            # If we can't set mtime, skip assertions
            pytest.skip("Cannot set file timestamps on this platform")

    def test_keep_recent_files(self, tmp_path: Path) -> None:
        """Verify that recent files are not deleted."""
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir(parents=True)

        recent_snap = snap_dir / "recent_snap.jpg"
        recent_snap.write_text("recent content")

        service = EvidenceRetentionService(
            media_dir=str(tmp_path),
            retention_days=30,
        )
        result = service.purge()

        assert result.deleted_files == 0
        assert recent_snap.exists()

    def test_skip_non_media_dirs(self, tmp_path: Path) -> None:
        """Verify that non-media directories are ignored."""
        # Create an unrelated directory
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other_file = other_dir / "data.txt"
        other_file.write_text("data")

        service = EvidenceRetentionService(
            media_dir=str(tmp_path),
            retention_days=1,
        )
        result = service.purge()

        assert result.deleted_files == 0
        assert other_file.exists()

    def test_skip_subdirectories(self, tmp_path: Path) -> None:
        """Verify that subdirectories within media dirs are skipped."""
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir(parents=True)
        sub = snap_dir / "subdir"
        sub.mkdir()
        sub_file = sub / "file.txt"
        sub_file.write_text("nested")

        service = EvidenceRetentionService(
            media_dir=str(tmp_path),
            retention_days=1,
        )
        result = service.purge()

        # The subdirectory itself shouldn't cause errors
        assert result.errors == 0
        # The nested file shouldn't be deleted (it's in a sub-subdir)
        assert sub_file.exists()

    def test_purge_result_has_timestamp(self) -> None:
        """Verify that PurgeResult has a valid timestamp."""
        service = EvidenceRetentionService(retention_days=1)
        result = service.purge()
        assert result.purged_at > 0

    def test_purge_result_duration(self) -> None:
        """Verify that PurgeResult has a non-negative duration."""
        service = EvidenceRetentionService(retention_days=1)
        result = service.purge()
        assert result.duration_seconds >= 0.0


class TestLifecycle:
    """Tests for start/stop lifecycle."""

    @patch("PySide6.QtCore.QTimer")
    def test_start_creates_timer(self, mock_timer: MagicMock) -> None:
        """Verify that start creates a QTimer."""
        service = EvidenceRetentionService()
        service.start()
        assert service.is_running
        mock_timer.assert_called_once()

    @patch("PySide6.QtCore.QTimer")
    def test_stop_stops_timer(self, mock_timer: MagicMock) -> None:
        """Verify that stop stops the timer."""
        service = EvidenceRetentionService()
        service.start()
        service.stop()
        assert not service.is_running
        mock_timer.return_value.stop.assert_called()

    @patch("PySide6.QtCore.QTimer")
    def test_start_is_idempotent(self, mock_timer: MagicMock) -> None:
        """Verify that start is idempotent."""
        service = EvidenceRetentionService()
        service.start()
        service.start()  # second call should be a no-op
        mock_timer.assert_called_once()

    def test_stop_without_start(self) -> None:
        """Verify that stop without start doesn't raise."""
        service = EvidenceRetentionService()
        service.stop()  # should not raise
        assert not service.is_running

    @patch("PySide6.QtCore.QTimer")
    def test_timer_connected_to_purge(self, mock_timer: MagicMock) -> None:
        """Verify that the timer is connected to purge."""
        service = EvidenceRetentionService()
        service.start()
        # Check that timeout signal was connected
        mock_timer.return_value.timeout.connect.assert_called_once_with(
            service.purge,
        )
