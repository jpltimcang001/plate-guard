"""Windows auto-start management.

Provides functions to enable/disable and check the status of
application auto-start via the Windows Startup folder (shell:startup).

Usage
-----
::

    from src.services.auto_start import (
        is_auto_start_enabled,
        enable_auto_start,
        disable_auto_start,
    )

    # Check
    if not is_auto_start_enabled("PlateGuard"):
        enable_auto_start("PlateGuard", r"C:\\Program Files\\PlateGuard\\PlateGuard.exe")

    # Disable
    disable_auto_start("PlateGuard")
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from loguru import logger


def _get_startup_folder() -> Path:
    """Return the Windows Startup folder path.

    Returns:
        The ``shell:startup`` folder path (e.g.
        ``C:\\Users\\<user>\\AppData\\Roaming\\Microsoft\\Windows\\Start
        Menu\\Programs\\Startup``).

    Raises:
        OSError: If the startup folder cannot be determined (non-Windows
            platform).

    """
    if sys.platform != "win32":
        raise OSError("Auto-start is only supported on Windows")

    startup = Path(os.environ.get(
        "APPDATA",
        Path.home() / "AppData" / "Roaming",
    )) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    if not startup.exists():
        startup.mkdir(parents=True, exist_ok=True)

    return startup


def _shortcut_path(app_name: str) -> Path:
    """Return the expected shortcut path for the given app name.

    Args:
        app_name: The application display name.

    Returns:
        The expected ``.lnk`` file path in the Startup folder.

    """
    startup = _get_startup_folder()
    return startup / f"{app_name}.lnk"


def is_auto_start_enabled(app_name: str) -> bool:
    """Check whether auto-start is enabled for the given application.

    Args:
        app_name: The application display name (used for the shortcut
            file name).

    Returns:
        ``True`` if a shortcut exists in the Windows Startup folder,
        ``False`` otherwise.

    """
    try:
        return _shortcut_path(app_name).is_file()
    except OSError:
        return False


def enable_auto_start(
    app_name: str,
    target_path: str | Path | None = None,
    arguments: str = "",
) -> bool:
    """Enable auto-start by creating a shortcut in the Windows Startup folder.

    Uses ``powershell`` to create a ``.lnk`` shortcut because the
    ``pywin32`` / ``win32com`` packages may not be available.

    Args:
        app_name: The application display name.
        target_path: Path to the executable.  If ``None``, uses
            ``sys.executable`` (the current Python interpreter).
        arguments: Optional command-line arguments for the shortcut.

    Returns:
        ``True`` if the shortcut was created, ``False`` otherwise.

    """
    if sys.platform != "win32":
        logger.warning("Auto-start is only supported on Windows")
        return False

    target = Path(target_path) if target_path else Path(sys.executable)
    if not target.is_file():
        logger.warning(
            "Auto-start target does not exist: {}",
            target,
        )
        return False

    shortcut = _shortcut_path(app_name)
    try:
        _create_shortcut_powershell(target, shortcut, arguments)
        logger.info(
            "Auto-start enabled: {} → {}",
            shortcut,
            target,
        )
        return True
    except (OSError, Exception) as exc:
        logger.opt(exception=True).error(
            "Failed to create auto-start shortcut: {}",
            exc,
        )
        return False


def disable_auto_start(app_name: str) -> bool:
    """Disable auto-start by removing the startup shortcut.

    Args:
        app_name: The application display name.

    Returns:
        ``True`` if the shortcut was removed (or didn't exist),
        ``False`` on error.

    """
    if sys.platform != "win32":
        return False

    shortcut = _shortcut_path(app_name)
    try:
        if shortcut.is_file():
            shortcut.unlink()
            logger.info("Auto-start disabled: removed {}", shortcut)
        return True
    except OSError as exc:
        logger.opt(exception=True).error(
            "Failed to remove auto-start shortcut: {}",
            exc,
        )
        return False


def _create_shortcut_powershell(
    target: Path,
    shortcut: Path,
    arguments: str = "",
) -> None:
    """Create a ``.lnk`` shortcut using PowerShell.

    Args:
        target: Path to the target executable.
        shortcut: Path for the shortcut file.
        arguments: Optional command-line arguments.

    Raises:
        subprocess.CalledProcessError: If PowerShell returns a non-zero
            exit code, or ``OSError`` if PowerShell is not available.

    """
    # PowerShell script to create a shortcut
    ps_script = f"""
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut('{shortcut}')
    $Shortcut.TargetPath = '{target}'
    $Shortcut.Arguments = '{arguments}'
    $Shortcut.WorkingDirectory = '{target.parent}'
    $Shortcut.Save()
    """

    result = subprocess.run(
        ["powershell", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            returncode=result.returncode,
            cmd=["powershell", "-Command", ps_script],
            stderr=result.stderr,
        )

    # Verify the shortcut was created
    if not shortcut.is_file():
        raise OSError(
            f"PowerShell shortcut creation succeeded but {shortcut} "
            f"does not exist",
        )


def __getattr__(name: str) -> None:
    """Re-export for cleaner imports."""
    return None
