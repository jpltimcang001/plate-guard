"""Unit tests for the MemoryMonitor.

Uses mocking to avoid actual psutil dependency in unit tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.monitor.memory_monitor import MemoryMonitor, MemorySnapshot


class TestInit:
    """Tests for MemoryMonitor initialisation."""

    def test_default_params(self) -> None:
        """Verify default parameter values."""
        monitor = MemoryMonitor()
        assert monitor._warning_mb == 500.0
        assert monitor._critical_mb == 1000.0
        assert monitor._check_interval == 30.0
        assert not monitor.is_running

    def test_custom_params(self) -> None:
        """Verify custom parameter values."""
        monitor = MemoryMonitor(
            warning_mb=200.0,
            critical_mb=800.0,
            check_interval_seconds=60.0,
        )
        assert monitor._warning_mb == 200.0
        assert monitor._critical_mb == 800.0
        assert monitor._check_interval == 60.0

    def test_invalid_thresholds_raise(self) -> None:
        """Verify that invalid thresholds raise ValueError."""
        with pytest.raises(ValueError):
            MemoryMonitor(warning_mb=0)
        with pytest.raises(ValueError):
            MemoryMonitor(critical_mb=-1)
        with pytest.raises(ValueError):
            MemoryMonitor(warning_mb=1000, critical_mb=500)
        with pytest.raises(ValueError):
            MemoryMonitor(check_interval_seconds=0)

    def test_thresholds_equal(self) -> None:
        """Verify that equal thresholds are allowed."""
        monitor = MemoryMonitor(warning_mb=500, critical_mb=500)
        assert monitor._warning_mb == 500
        assert monitor._critical_mb == 500


class TestSnapshot:
    """Tests for memory snapshot."""

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_snapshot_requires_psutil(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that snapshot returns None without psutil."""
        mock_ensure.return_value = False
        monitor = MemoryMonitor()
        assert monitor.snapshot() is None

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_snapshot_returns_data(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that snapshot returns a MemorySnapshot."""
        mock_ensure.return_value = True

        mock_mem_info = MagicMock()
        mock_mem_info.rss = 100 * 1024 * 1024  # 100 MB
        mock_mem_info.vms = 200 * 1024 * 1024  # 200 MB

        mock_process = MagicMock()
        mock_process.memory_info.return_value = mock_mem_info
        mock_process.memory_percent.return_value = 5.0

        monitor = MemoryMonitor()
        monitor._process = mock_process

        snap = monitor.snapshot()
        assert snap is not None
        assert snap.rss_mb == 100.0
        assert snap.vms_mb == 200.0
        assert snap.percent == 5.0
        assert snap.timestamp > 0

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_snapshot_error_returns_none(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that snapshot returns None on error."""
        mock_ensure.return_value = True

        mock_process = MagicMock()
        mock_process.memory_info.side_effect = OSError("denied")

        monitor = MemoryMonitor()
        monitor._process = mock_process

        assert monitor.snapshot() is None


class TestCheck:
    """Tests for the memory check cycle."""

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_healthy_does_not_alert(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that healthy memory does not trigger alerts."""
        mock_ensure.return_value = True
        warning_cb = MagicMock()
        critical_cb = MagicMock()

        monitor = MemoryMonitor(
            warning_mb=500,
            critical_mb=1000,
            on_warning=warning_cb,
            on_critical=critical_cb,
        )

        with patch.object(
            monitor,
            "snapshot",
            return_value=MemorySnapshot(
                rss_mb=100.0,
                vms_mb=200.0,
                percent=5.0,
            ),
        ):
            monitor._check()
            warning_cb.assert_not_called()
            critical_cb.assert_not_called()
            assert not monitor._warning_active
            assert not monitor._critical_active

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_warning_triggers_callback(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that warning threshold triggers the callback."""
        mock_ensure.return_value = True
        warning_cb = MagicMock()

        monitor = MemoryMonitor(
            warning_mb=100,
            critical_mb=500,
            on_warning=warning_cb,
        )

        with patch.object(
            monitor,
            "snapshot",
            return_value=MemorySnapshot(
                rss_mb=200.0,
                vms_mb=300.0,
                percent=10.0,
            ),
        ):
            monitor._check()
            warning_cb.assert_called_once()
            assert monitor._warning_active

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_critical_triggers_callback(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that critical threshold triggers the callback."""
        mock_ensure.return_value = True
        critical_cb = MagicMock()

        monitor = MemoryMonitor(
            warning_mb=100,
            critical_mb=200,
            on_critical=critical_cb,
        )

        with patch.object(
            monitor,
            "snapshot",
            return_value=MemorySnapshot(
                rss_mb=300.0,
                vms_mb=400.0,
                percent=15.0,
            ),
        ):
            monitor._check()
            critical_cb.assert_called_once()
            assert monitor._critical_active

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_critical_supersedes_warning(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that critical threshold takes precedence over warning."""
        mock_ensure.return_value = True
        warning_cb = MagicMock()
        critical_cb = MagicMock()

        monitor = MemoryMonitor(
            warning_mb=100,
            critical_mb=200,
            on_warning=warning_cb,
            on_critical=critical_cb,
        )

        with patch.object(
            monitor,
            "snapshot",
            return_value=MemorySnapshot(
                rss_mb=300.0,
                vms_mb=400.0,
                percent=15.0,
            ),
        ):
            monitor._check()
            critical_cb.assert_called_once()
            warning_cb.assert_not_called()

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_alert_only_once(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that alert fires only once while above threshold."""
        mock_ensure.return_value = True
        warning_cb = MagicMock()

        monitor = MemoryMonitor(
            warning_mb=100,
            critical_mb=500,
            on_warning=warning_cb,
        )

        with patch.object(
            monitor,
            "snapshot",
            return_value=MemorySnapshot(
                rss_mb=200.0,
                vms_mb=300.0,
                percent=10.0,
            ),
        ):
            monitor._check()  # first time — fires
            monitor._check()  # second time — should NOT fire again
            warning_cb.assert_called_once()

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_alert_resets_when_below_threshold(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that alert flag resets when memory drops below."""
        mock_ensure.return_value = True
        warning_cb = MagicMock()

        monitor = MemoryMonitor(
            warning_mb=100,
            critical_mb=500,
            on_warning=warning_cb,
        )

        # Step 1: above threshold
        with patch.object(
            monitor,
            "snapshot",
            return_value=MemorySnapshot(
                rss_mb=200.0,
                vms_mb=300.0,
                percent=10.0,
            ),
        ):
            monitor._check()
            warning_cb.assert_called_once()

        # Step 2: below threshold
        with patch.object(
            monitor,
            "snapshot",
            return_value=MemorySnapshot(
                rss_mb=50.0,
                vms_mb=100.0,
                percent=2.0,
            ),
        ):
            monitor._check()
            assert not monitor._warning_active
            assert not monitor._critical_active

    @patch("src.monitor.memory_monitor.MemoryMonitor._ensure_psutil")
    def test_check_skipped_when_no_snapshot(
        self,
        mock_ensure: MagicMock,
    ) -> None:
        """Verify that _check is a no-op when snapshot returns None."""
        mock_ensure.return_value = True
        warning_cb = MagicMock()

        monitor = MemoryMonitor(
            warning_mb=100,
            critical_mb=500,
            on_warning=warning_cb,
        )

        with patch.object(monitor, "snapshot", return_value=None):
            monitor._check()
            warning_cb.assert_not_called()
