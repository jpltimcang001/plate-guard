"""Main application window with tabbed navigation.

The MainWindow provides the top-level frame for the Plate Guard
desktop application, including:
- A tab bar switching between Dashboard, Detection Logs, and Settings
- System tray integration (minimise-to-tray)
- Global keyboard shortcuts
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

import numpy as np
from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.dashboard.dashboard_widget import DashboardWidget
from src.ui.detection_logs_widget import DetectionLogsWidget

if TYPE_CHECKING:
    from src.monitor.camera_health_monitor import CameraHealthMonitor
    from src.monitor.memory_monitor import MemoryMonitor
    from src.recorder.event_recorder import EventRecorder
    from src.services.camera_service import CameraService
    from src.services.dashboard_service import DashboardService
    from src.services.evidence_retention import EvidenceRetentionService
    from src.services.shutdown_manager import ShutdownManager
    from src.repositories.detection_repository import DetectionRepository


class MainWindow(QMainWindow):
    """Top-level window for the Plate Guard application.

    Manages tab navigation, system tray, and global application state.

    Usage::

        window = MainWindow(
            camera_service=camera_service,
            dashboard_service=dashboard_service,
            detection_repository=detection_repo,
        )
        window.show()
    """

    def __init__(
        self,
        camera_service: CameraService,
        dashboard_service: DashboardService,
        detection_repository: DetectionRepository,
        event_recorder: EventRecorder | None = None,
        shutdown_manager: ShutdownManager | None = None,
        camera_health_monitor: CameraHealthMonitor | None = None,
        memory_monitor: MemoryMonitor | None = None,
        evidence_retention: EvidenceRetentionService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the main window.

        Args:
            camera_service: Service for camera management.
            dashboard_service: Service for dashboard data.
            detection_repository: Repository for detection log queries.
            event_recorder: Optional ``EventRecorder`` for manual capture.
            shutdown_manager: Optional ``ShutdownManager`` for graceful
                shutdown orchestration.
            camera_health_monitor: Optional ``CameraHealthMonitor`` for
                automatic camera health checks and reconnection.
            memory_monitor: Optional ``MemoryMonitor`` for periodic
                memory usage checks.
            evidence_retention: Optional ``EvidenceRetentionService``
                for periodic deletion of old media files.
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)

        self._camera_service = camera_service
        self._dashboard_service = dashboard_service
        self._detection_repo = detection_repository
        self._event_recorder = event_recorder
        self._shutdown_mgr = shutdown_manager
        self._camera_health_monitor = camera_health_monitor
        self._memory_monitor = memory_monitor
        self._evidence_retention = evidence_retention

        self._setup_window()
        self._setup_tabs()
        self._setup_system_tray()
        self._setup_menu()
        self._setup_status_bar()

        # Wire manual capture signals
        self._dashboard.capture_snapshot_requested.connect(
            self._on_manual_snapshot,
        )
        self._dashboard.capture_clip_requested.connect(
            self._on_manual_clip,
        )

        # ---- Start background services -----------------------------------
        self._start_background_services()
        self._update_status_bar()

        logger.info("MainWindow initialised")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def dashboard(self) -> DashboardWidget:
        """The dashboard tab widget."""
        return self._dashboard

    @property
    def detection_logs(self) -> DetectionLogsWidget:
        """The detection logs tab widget."""
        return self._logs_widget

    @property
    def status_bar_label(self) -> QLabel:
        """The status bar label widget."""
        return self._status_bar_label

    # ------------------------------------------------------------------
    # Internal — window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        """Configure the main window geometry and appearance."""
        self.setWindowTitle("Plate Guard — License Plate Recognition")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 800)

        # Centre on screen
        screen = QApplication.primaryScreen()
        if screen is not None:
            center = screen.availableGeometry().center()
            frame = self.frameGeometry()
            frame.moveCenter(center)
            self.move(frame.topLeft())

        self._apply_stylesheet()

    def _apply_stylesheet(self) -> None:
        """Apply global application stylesheet."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            QTabWidget::pane {
                background-color: #1a1a1a;
                border: none;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #95a5a6;
                border: none;
                padding: 8px 20px;
                margin-right: 2px;
                font-size: 12px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #3498db;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3a3a3a;
                color: #ecf0f1;
            }
            QMenu {
                background-color: #2b2b2b;
                color: #ecf0f1;
                border: 1px solid #3a3a3a;
            }
            QMenu::item:selected {
                background-color: #3498db;
            }
        """)

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    def _setup_tabs(self) -> None:
        """Create the tab widget with all pages."""
        self._tab_widget = QTabWidget(self)
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(False)

        # Dashboard tab
        self._dashboard = DashboardWidget(
            dashboard_service=self._dashboard_service,
            parent=self,
        )
        self._tab_widget.addTab(self._dashboard, "Dashboard")

        # Detection Logs tab
        self._logs_widget = DetectionLogsWidget(
            camera_service=self._camera_service,
            detection_repository=self._detection_repo,
            parent=self,
        )
        self._tab_widget.addTab(self._logs_widget, "Detection Logs")

        self.setCentralWidget(self._tab_widget)

        # Connect tab changes
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab switching.

        Args:
            index: The new tab index.

        """
        if index == 0:
            # Dashboard tab — start refresh
            self._dashboard.start_refresh()
        elif index == 1:
            # Detection Logs tab — stop dashboard refresh and load logs
            self._dashboard.stop_refresh()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        """Create a persistent status bar at the bottom of the window."""
        from PySide6.QtWidgets import QStatusBar

        status_bar = QStatusBar(self)
        status_bar.setStyleSheet(
            "QStatusBar { background: #2b2b2b; border-top: 1px solid #3a3a3a; }"
            "QStatusBar::item { border: none; }",
        )
        self._status_bar_label = QLabel("Initialising…")
        self._status_bar_label.setToolTip("Application status messages")
        self._status_bar_label.setStyleSheet(
            "color: #95a5a6; font-size: 10px; padding: 2px 8px;",
        )
        status_bar.addWidget(self._status_bar_label, stretch=1)

        # Service status indicators
        self._srv_health = QLabel("● Health: idle")
        self._srv_health.setToolTip("Camera health monitor status — number of cameras monitored")
        self._srv_memory = QLabel("● Memory: N/A")
        self._srv_memory.setToolTip("Memory usage monitor status — current RSS")
        self._srv_retention = QLabel("● Retention: idle")
        self._srv_retention.setToolTip("Evidence retention service status — configured retention period")
        for lbl in (self._srv_health, self._srv_memory, self._srv_retention):
            lbl.setStyleSheet("color: #95a5a6; font-size: 10px; padding: 0 8px;")
            status_bar.addPermanentWidget(lbl)

        self.setStatusBar(status_bar)

    def _update_status_bar(self) -> None:
        """Update the status bar indicators based on service states."""
        if self._camera_health_monitor is not None:
            c = self._camera_health_monitor.monitored_camera_count
            r = "●" if self._camera_health_monitor.is_running else "○"
            colour = "#27ae60" if self._camera_health_monitor.is_running else "#95a5a6"
            self._srv_health.setText(f'{r} <span style="color:{colour}">Health</span>: {c} cams')

        if self._memory_monitor is not None:
            r = "●" if self._memory_monitor.is_running else "○"
            snap = self._memory_monitor.last_snapshot
            mem = f"{snap.rss_mb:.0f}MB" if snap else "N/A"
            colour = "#27ae60" if self._memory_monitor.is_running else "#95a5a6"
            self._srv_memory.setText(f'{r} <span style="color:{colour}">Memory</span>: {mem}')

        if self._evidence_retention is not None:
            r = "●" if self._evidence_retention.is_running else "○"
            colour = "#27ae60" if self._evidence_retention.is_running else "#95a5a6"
            self._srv_retention.setText(
                f'{r} <span style="color:{colour}">Retention</span>: '
                f'{self._evidence_retention.retention_days}d',
            )

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_system_tray(self) -> None:
        """Create the system tray icon and context menu."""
        self._tray_icon: QSystemTrayIcon | None = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("System tray not available on this platform")
            return

        icon = self.windowIcon()
        if icon.isNull():
            # Use a default icon
            from PySide6.QtGui import QPixmap

            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.blue)
            icon = QIcon(pixmap)

        self._tray_icon = QSystemTrayIcon(icon, self)
        self._tray_icon.setToolTip("Plate Guard — License Plate Recognition")

        # Context menu
        tray_menu = QMenu(self)

        show_action = QAction("Show", self)
        show_action.setToolTip("Restore the main window")
        show_action.triggered.connect(self._show_window)
        tray_menu.addAction(show_action)

        self._pause_action = QAction("Pause Detection", self)
        self._pause_action.setToolTip("Pause or resume license plate detection")
        self._pause_action.setCheckable(True)
        self._pause_action.toggled.connect(self._on_pause_toggled)
        tray_menu.addAction(self._pause_action)

        tray_menu.addSeparator()

        settings_action = QAction("Settings", self)
        settings_action.setToolTip("Open application settings")
        settings_action.triggered.connect(self._open_settings)
        tray_menu.addAction(settings_action)

        tray_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setToolTip("Quit the application")
        exit_action.triggered.connect(self._quit_application)
        tray_menu.addAction(exit_action)

        self._tray_icon.setContextMenu(tray_menu)

        # Double-click shows window
        self._tray_icon.activated.connect(self._on_tray_activated)

        self._tray_icon.show()
        logger.info("System tray icon created")

    def _on_tray_activated(
        self,
        reason: QSystemTrayIcon.ActivationReason,
    ) -> None:
        """Handle tray icon activation.

        Args:
            reason: The activation reason.

        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _show_window(self) -> None:
        """Show and raise the main window."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_pause_toggled(self, paused: bool) -> None:
        """Handle pause/resume detection.

        Args:
            paused: Whether detection should be paused.

        """
        if paused:
            logger.info("Detection paused by user")
            self._dashboard.stop_refresh()
        else:
            logger.info("Detection resumed by user")
            self._dashboard.start_refresh()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _setup_menu(self) -> None:
        """Create the application menu bar."""
        menubar = self.menuBar()
        if menubar is None:
            return

        # File menu
        file_menu = menubar.addMenu("&File")

        switch_to_dashboard = QAction("Dashboard", self)
        switch_to_dashboard.setToolTip("Switch to the dashboard view (Ctrl+1)")
        switch_to_dashboard.setShortcut(QKeySequence("Ctrl+1"))
        switch_to_dashboard.triggered.connect(lambda: self._tab_widget.setCurrentIndex(0))
        file_menu.addAction(switch_to_dashboard)

        switch_to_logs = QAction("Detection Logs", self)
        switch_to_logs.setToolTip("Switch to detection logs view (Ctrl+2)")
        switch_to_logs.setShortcut(QKeySequence("Ctrl+2"))
        switch_to_logs.triggered.connect(lambda: self._tab_widget.setCurrentIndex(1))
        file_menu.addAction(switch_to_logs)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setToolTip("Exit Plate Guard")
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self._quit_application)
        file_menu.addAction(quit_action)

    # ------------------------------------------------------------------
    # Background services (Sprint 4)
    # ------------------------------------------------------------------

    def _start_background_services(self) -> None:
        """Start camera health monitor, memory monitor, and evidence
        retention if they were provided."""
        # Camera health monitor
        if self._camera_health_monitor is not None:
            try:
                self._camera_health_monitor.start()
                logger.info("Camera health monitor started")
            except Exception:
                logger.opt(exception=True).warning(
                    "Failed to start camera health monitor",
                )

        # Memory monitor
        if self._memory_monitor is not None:
            try:
                self._memory_monitor.start()
                logger.info("Memory monitor started")
            except Exception:
                logger.opt(exception=True).warning(
                    "Failed to start memory monitor",
                )

        # Evidence retention
        if self._evidence_retention is not None:
            try:
                self._evidence_retention.start()
                logger.info("Evidence retention service started")
            except Exception:
                logger.opt(exception=True).warning(
                    "Failed to start evidence retention",
                )

    # ------------------------------------------------------------------
    # Manual capture
    # ------------------------------------------------------------------

    def _on_manual_snapshot(self, camera_id: int) -> None:
        """Handle manual snapshot capture request.

        Args:
            camera_id: The camera to capture from.

        """
        if self._event_recorder is None:
            logger.warning("EventRecorder not available — cannot capture snapshot")
            self._show_tray_message(
                "Snapshot Failed",
                "Event recorder is not available.",
            )
            return

        frame = self._dashboard.get_current_frame(camera_id)
        if frame is None:
            logger.warning("No frame available for manual snapshot (camera_id={})", camera_id)
            self._show_tray_message(
                "Snapshot Failed",
                f"No frame available from camera #{camera_id}.",
            )
            return

        self._status_bar_label.setText(f"Capturing snapshot from camera #{camera_id}…")
        QApplication.processEvents()

        try:
            from datetime import datetime

            from src.domain.events.plate_detected import PlateDetected

            event = PlateDetected(
                camera_id=camera_id,
                timestamp=datetime.now(),
                confidence=0.0,
                bbox=(0, 0, 0, 0),
            )
            result = self._event_recorder.record(
                event=event,
                current_frame=frame,
                ocr_text="",
            )
            if result.has_snapshot:
                logger.info("Manual snapshot saved: {}", result.snapshot_path)
                self._show_tray_message(
                    "Snapshot Captured",
                    f"Saved to {result.snapshot_path}",
                )
                self._status_bar_label.setText(f"Snapshot saved: {result.snapshot_path}")
            else:
                logger.warning("Manual snapshot failed (camera_id={})", camera_id)
                self._status_bar_label.setText("Snapshot capture failed.")
        except Exception:
            logger.opt(exception=True).error(
                "Error during manual snapshot (camera_id={})", camera_id,
            )
            self._status_bar_label.setText("Snapshot capture error.")

    def _on_manual_clip(self, camera_id: int) -> None:
        """Handle manual video clip capture request.

        Args:
            camera_id: The camera to capture from.

        """
        if self._event_recorder is None:
            logger.warning("EventRecorder not available — cannot capture clip")
            self._show_tray_message(
                "Clip Failed",
                "Event recorder is not available.",
            )
            return

        frame = self._dashboard.get_current_frame(camera_id)
        if frame is None:
            logger.warning("No frame available for manual clip (camera_id={})", camera_id)
            self._show_tray_message(
                "Clip Failed",
                f"No frame available from camera #{camera_id}.",
            )
            return

        self._status_bar_label.setText(f"Recording clip from camera #{camera_id}…")
        QApplication.processEvents()

        try:
            from datetime import datetime

            from src.domain.events.plate_detected import PlateDetected

            event = PlateDetected(
                camera_id=camera_id,
                timestamp=datetime.now(),
                confidence=0.0,
                bbox=(0, 0, 0, 0),
            )
            result = self._event_recorder.record(
                event=event,
                current_frame=frame,
                ocr_text="",
            )
            if result.has_video:
                logger.info(
                    "Manual clip saved: {} ({} frames, {}s)",
                    result.video_path,
                    result.total_frames,
                    result.duration_seconds,
                )
                self._show_tray_message(
                    "Video Clip Captured",
                    f"Saved to {result.video_path}",
                )
                self._status_bar_label.setText(f"Clip saved: {result.video_path}")
            else:
                logger.warning("Manual clip failed (camera_id={})", camera_id)
                self._status_bar_label.setText("Clip capture failed.")
        except Exception:
            logger.opt(exception=True).error(
                "Error during manual clip (camera_id={})", camera_id,
            )
            self._status_bar_label.setText("Clip capture error.")

    def _show_tray_message(self, title: str, message: str) -> None:
        """Show a system tray notification.

        Args:
            title: Notification title.
            message: Notification body.

        """
        if self._tray_icon is not None and self._tray_icon.isVisible():
            self._tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self) -> None:
        """Open the settings page."""
        logger.info("Settings dialog requested")
        QMessageBox.information(
            self,
            "Settings",
            "Settings are not yet implemented.\n\n"
            "The following settings are planned for a future update:\n"
            "• Evidence retention period\n"
            "• Webhook configuration\n"
            "• Camera detection zones\n"
            "• Performance and storage options",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        """Handle window close — minimise to tray instead of quitting.

        Args:
            event: The close event.

        """
        if self._tray_icon is not None and self._tray_icon.isVisible():
            logger.debug("Minimising to system tray")
            self.hide()
            event.ignore()
        else:
            self._do_quit(event)

    def _quit_application(self) -> None:
        """Perform a clean application shutdown with user confirmation."""
        reply = QMessageBox.question(
            self,
            "Quit Plate Guard",
            "Are you sure you want to quit Plate Guard?\n\n"
            "Detection will be stopped and all background services "
            "will be shut down.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        logger.info("User confirmed application quit")
        self._do_shutdown()

    def _do_quit(self, event: QCloseEvent | None = None) -> None:
        """Clean shutdown sequence.

        Args:
            event: Optional close event to accept.

        """
        self._do_shutdown()
        if event is not None:
            event.accept()
        QApplication.quit()

    def _do_shutdown(self) -> None:
        """Execute the full shutdown sequence."""
        self._status_bar_label.setText("Shutting down…")
        self._stop_background_services()
        self._dashboard.cleanup()
        if self._shutdown_mgr is not None:
            self._shutdown_mgr.shutdown()
        logger.info("Shutdown sequence complete")

    def _stop_background_services(self) -> None:
        """Stop all background services before shutdown."""
        if self._camera_health_monitor is not None:
            try:
                self._camera_health_monitor.stop()
            except Exception:
                logger.opt(exception=True).warning(
                    "Error stopping camera health monitor",
                )

        if self._memory_monitor is not None:
            try:
                self._memory_monitor.stop()
            except Exception:
                logger.opt(exception=True).warning(
                    "Error stopping memory monitor",
                )

        if self._evidence_retention is not None:
            try:
                self._evidence_retention.stop()
            except Exception:
                logger.opt(exception=True).warning(
                    "Error stopping evidence retention",
                )

    def __repr__(self) -> str:
        return "<MainWindow>"
