"""Application entry point for Plate Guard.

Initialises the database, wires up the dependency graph,
creates the main window, and starts the Qt event loop.

Usage:
    python -m src
    PlateGuard.exe             (after PyInstaller build)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger


def _setup_logging() -> None:
    """Configure structured logging to file and stderr."""
    log_dir = _get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    logger.add(
        log_dir / "plate_guard_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
    )


def _get_app_data_dir() -> Path:
    """Return the platform-specific application data directory."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get(
                "XDG_DATA_HOME",
                Path.home() / ".local" / "share",
            )
        )
    return base / "plate-guard"


def _init_database() -> None:
    """Create the SQLite engine and initialise all tables."""
    from sqlalchemy import create_engine

    from src.database.engine import init_db
    from src.database.session import SessionManager

    data_dir = _get_app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "plate_guard.db"

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    init_db(engine)
    logger.info("Database initialised at: {}", db_path)

    # Store the engine and session manager as module-level globals
    # so other modules can access them via src.database.engine / session.
    import src.database.engine as db_engine
    from src.database.engine import create_engine as _create_engine

    db_engine._engine = engine  # type: ignore[attr-defined]

    session_mgr = SessionManager(engine)
    import src.database.session as db_session

    db_session._manager = session_mgr  # type: ignore[attr-defined]
    logger.info("Session manager created.")


def main() -> None:
    """Application entry point.

    Initialises subsystems and launches the Qt main loop.
    """
    _setup_logging()
    logger.info("=== Plate Guard starting ===")

    try:
        _init_database()
    except Exception:
        logger.opt(exception=True).critical("Failed to initialise database")
        sys.exit(1)

    # ---- Build dependency graph -------------------------------------------
    try:
        from src.database.session import SessionManager
        from src.repositories.camera_repository import CameraRepository
        from src.repositories.detection_repository import DetectionRepository
        from src.services.camera_service import CameraService
        from src.services.dashboard_service import DashboardService

        from src.database.engine import _engine as engine  # type: ignore[attr-defined]

        session_mgr = SessionManager(engine)  # type: ignore[arg-type]
        camera_repo = CameraRepository(session_mgr)
        detection_repo = DetectionRepository(session_mgr)

        camera_service = CameraService(camera_repository=camera_repo)
        dashboard_service = DashboardService(
            camera_service=camera_service,
            detection_repository=detection_repo,
        )

    except Exception:
        logger.opt(exception=True).critical("Failed to build dependency graph")
        sys.exit(1)

    # ---- Start Qt application ---------------------------------------------
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from src.ui.main_window import MainWindow  # type: ignore[attr-defined]

        app = QApplication(sys.argv)
        app.setApplicationName("Plate Guard")
        app.setApplicationDisplayName("Plate Guard — License Plate Recognition")
        app.setOrganizationName("PlateGuard")
        app.setQuitOnLastWindowClosed(False)  # system-tray app

        # Set application icon
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        if icon_path.is_file():
            app.setWindowIcon(QIcon(str(icon_path)))

        window = MainWindow(
            camera_service=camera_service,
            dashboard_service=dashboard_service,
        )
        window.show()

        logger.info("Main window displayed. Entering Qt event loop.")
        exit_code = app.exec()

    except ImportError:
        logger.opt(exception=True).critical(
            "PySide6 is not installed. "
            "Install it with: pip install PySide6",
        )
        sys.exit(1)
    except Exception:
        logger.opt(exception=True).critical("Unhandled application error")
        sys.exit(1)

    logger.info("=== Plate Guard exiting (code={}) ===", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
