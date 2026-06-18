"""Unit tests for the Windows auto-start service.

Uses mocking to avoid actual filesystem/powershell interaction.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.services.auto_start import (
    _get_startup_folder,
    _shortcut_path,
    disable_auto_start,
    enable_auto_start,
    is_auto_start_enabled,
)


class TestGetStartupFolder:
    """Tests for ``_get_startup_folder``."""

    def test_returns_path_on_windows(self) -> None:
        """Verify that a valid path is returned on Windows."""
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        folder = _get_startup_folder()
        assert "Startup" in str(folder)
        assert folder.exists()

    def test_raises_on_non_windows(self) -> None:
        """Verify that an OSError is raised on non-Windows."""
        with patch("src.services.auto_start.sys.platform", "linux"):
            with pytest.raises(OSError, match="only supported on Windows"):
                _get_startup_folder()


class TestShortcutPath:
    """Tests for ``_shortcut_path``."""

    @patch("src.services.auto_start._get_startup_folder")
    def test_returns_lnk_path(self, mock_get_folder: MagicMock) -> None:
        """Verify that the shortcut path ends with .lnk."""
        mock_get_folder.return_value = Path("C:\\Fake\\Startup")
        path = _shortcut_path("PlateGuard")
        assert str(path).endswith(".lnk")
        assert "PlateGuard" in str(path)


class TestIsAutoStartEnabled:
    """Tests for ``is_auto_start_enabled``."""

    @patch("src.services.auto_start._shortcut_path")
    def test_returns_true_when_file_exists(
        self,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that True is returned when the shortcut exists."""
        mock_shortcut.return_value.is_file.return_value = True
        assert is_auto_start_enabled("PlateGuard") is True

    @patch("src.services.auto_start._shortcut_path")
    def test_returns_false_when_not_exists(
        self,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that False is returned when the shortcut doesn't exist."""
        mock_shortcut.return_value.is_file.return_value = False
        assert is_auto_start_enabled("PlateGuard") is False

    @patch("src.services.auto_start._shortcut_path")
    def test_returns_false_on_oserror(
        self,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that False is returned on OSError."""
        mock_shortcut.side_effect = OSError("boom")
        assert is_auto_start_enabled("PlateGuard") is False


class TestEnableAutoStart:
    """Tests for ``enable_auto_start``."""

    def test_returns_false_on_non_windows(self) -> None:
        """Verify that False is returned on non-Windows."""
        with patch("src.services.auto_start.sys.platform", "linux"):
            result = enable_auto_start("Test", "dummy.exe")
            assert result is False

    @patch("src.services.auto_start._shortcut_path")
    @patch("src.services.auto_start._create_shortcut_powershell")
    def test_returns_true_on_success(
        self,
        mock_create: MagicMock,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that True is returned on success."""
        mock_shortcut.return_value.parent = Path("C:\\Fake")
        with patch("src.services.auto_start.sys.platform", "win32"):
            result = enable_auto_start(
                "Test",
                target_path=Path(sys.executable),
            )
            assert result is True

    @patch("src.services.auto_start._shortcut_path")
    @patch("src.services.auto_start._create_shortcut_powershell")
    def test_returns_false_when_target_missing(
        self,
        mock_create: MagicMock,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that False is returned when target doesn't exist."""
        mock_shortcut.return_value.parent = Path("C:\\Fake")
        with patch("src.services.auto_start.sys.platform", "win32"):
            result = enable_auto_start(
                "Test",
                target_path=Path("C:\\nonexistent\\app.exe"),
            )
            assert result is False
            mock_create.assert_not_called()

    @patch("src.services.auto_start._shortcut_path")
    @patch("src.services.auto_start._create_shortcut_powershell")
    def test_returns_false_on_exception(
        self,
        mock_create: MagicMock,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that False is returned on exception during creation."""
        mock_shortcut.return_value.parent = Path("C:\\Fake")
        with patch("src.services.auto_start.sys.platform", "win32"):
            mock_create.side_effect = RuntimeError("PowerShell failed")
            result = enable_auto_start(
                "Test",
                target_path=Path(sys.executable),
            )
            assert result is False


class TestDisableAutoStart:
    """Tests for ``disable_auto_start``."""

    def test_returns_false_on_non_windows(self) -> None:
        """Verify that False is returned on non-Windows."""
        with patch("src.services.auto_start.sys.platform", "linux"):
            result = disable_auto_start("Test")
            assert result is False

    @patch("src.services.auto_start._shortcut_path")
    def test_removes_existing_shortcut(
        self,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that an existing shortcut is removed."""
        with patch("src.services.auto_start.sys.platform", "win32"):
            mock_shortcut.return_value.is_file.return_value = True
            result = disable_auto_start("Test")
            assert result is True
            mock_shortcut.return_value.unlink.assert_called_once()

    @patch("src.services.auto_start._shortcut_path")
    def test_no_error_when_no_shortcut(
        self,
        mock_shortcut: MagicMock,
    ) -> None:
        """Verify that no error when shortcut doesn't exist."""
        with patch("src.services.auto_start.sys.platform", "win32"):
            mock_shortcut.return_value.is_file.return_value = False
            result = disable_auto_start("Test")
            assert result is True
            mock_shortcut.return_value.unlink.assert_not_called()


class TestCreateShortcutPowerShell:
    """Tests for the PowerShell shortcut creation helper."""

    @patch("subprocess.run")
    def test_calls_powershell(self, mock_run: MagicMock) -> None:
        """Verify that PowerShell is invoked with the correct args."""
        from src.services.auto_start import _create_shortcut_powershell

        mock_run.return_value.returncode = 0
        target = Path("C:\\Programs\\app.exe")
        shortcut = Path("C:\\Startup\\App.lnk")

        # Mock the shortcut file existence check
        with patch.object(Path, "is_file", return_value=True):
            _create_shortcut_powershell(target, shortcut, arguments="--flag")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "powershell" in args[0]
        assert "WScript.Shell" in " ".join(args)

    @patch("subprocess.run")
    def test_raises_on_powershell_error(self, mock_run: MagicMock) -> None:
        """Verify that an error in PowerShell raises CalledProcessError."""
        from src.services.auto_start import _create_shortcut_powershell

        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error"

        target = Path("C:\\Programs\\app.exe")
        shortcut = Path("C:\\Startup\\App.lnk")

        with patch.object(Path, "is_file", return_value=False):
            with pytest.raises(subprocess.CalledProcessError):
                _create_shortcut_powershell(target, shortcut)

    @patch("subprocess.run")
    def test_raises_if_shortcut_not_created(
        self,
        mock_run: MagicMock,
    ) -> None:
        """Verify that missing shortcut after success raises."""
        from src.services.auto_start import _create_shortcut_powershell

        mock_run.return_value.returncode = 0

        target = Path("C:\\Programs\\app.exe")
        shortcut = Path("C:\\Startup\\App.lnk")

        with patch.object(Path, "is_file", return_value=False):
            with pytest.raises(OSError, match="does not exist"):
                _create_shortcut_powershell(target, shortcut)
