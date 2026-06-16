"""Main dashboard widget — assembles all dashboard panels.

The dashboard provides an at-a-glance view of the entire system:

- **Camera status** cards with health indicators
- **Live preview** from a selected camera
- **Detection summary** with today's counts and recent detections
- Refresh timer that polls the ``DashboardService`` periodically
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np
from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.application.dto.dashboard_dto import DashboardData
from src.ui.dashboard.camera_status_widget import CameraStatusPanel
from src.ui.dashboard.detection_summary_widget import DetectionSummaryWidget
from src.ui.dashboard.live_preview_widget import LivePreviewWidget

if TYPE_CHECKING:
    from src.services.dashboard_service import DashboardService

# ------------------------------------------------------------------
# Style constants
# ------------------------------------------------------------------

_COLOR_BG = QColor("#1a1a1a")
_COLOR_TEXT = QColor("#ecf0f1")
_COLOR_TEXT_MUTED = QColor("#95a5a6")
_COLOR_ACCENT = QColor("#3498db")
_COLOR_ONLINE = QColor("#27ae60")
_COLOR_OFFLINE = QColor("#e74c3c")


class DashboardWidget(QWidget):
    """Main dashboard view for the Plate Guard application.

    Composes the camera status panel, live preview, and detection
    summary into a single page.  A background timer refreshes the
    dashboard data from the ``DashboardService`` every N seconds.

    Usage::

        dashboard = DashboardWidget(dashboard_service, parent=main_window)
        dashboard.set_frame_source(camera_id=1, source=my_source)
        dashboard.start_refresh()
    """

    DEFAULT_REFRESH_INTERVAL_MS = 5_000  # 5 seconds

    def __init__(
        self,
        dashboard_service: DashboardService,
        parent: QWidget | None = None,
        refresh_interval_ms: int = DEFAULT_REFRESH_INTERVAL_MS,
    ) -> None:
        """Initialise the dashboard.

        Args:
            dashboard_service: The ``DashboardService`` instance used
                to fetch aggregated data.
            parent: Optional parent widget.
            refresh_interval_ms: Milliseconds between automatic
                refreshes (default 5000).

        """
        super().__init__(parent=parent)

        self._dashboard_service = dashboard_service
        self._refresh_interval = refresh_interval_ms

        # Frame sources per camera: camera_id → callable
        self._frame_sources: dict[int, Callable[[], Optional[np.ndarray]]] = {}
        self._selected_camera_id: int | None = None

        # Latest dashboard data (cached for UI interactions)
        self._cached_data: DashboardData | None = None

        self._setup_ui()
        self._connect_signals()

        # Refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_refresh(self) -> None:
        """Start the periodic data refresh.

        Also performs an immediate refresh on first call.
        """
        self._on_refresh()
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(self._refresh_interval)
            logger.debug(
                "DashboardWidget refresh started (interval={}ms)",
                self._refresh_interval,
            )

    def stop_refresh(self) -> None:
        """Stop the periodic data refresh."""
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
            logger.debug("DashboardWidget refresh stopped")

    def refresh_now(self) -> None:
        """Trigger an immediate data refresh."""
        self._on_refresh()

    def set_frame_source(
        self,
        camera_id: int,
        source: Callable[[], Optional[np.ndarray]] | None,
        camera_name: str = "",
    ) -> None:
        """Register or remove a frame source for a camera.

        Args:
            camera_id: The camera ID.
            source: A zero-argument callable returning a BGR frame,
                or ``None`` to remove the source.
            camera_name: Optional display name for logging.

        """
        if source is None:
            self._frame_sources.pop(camera_id, None)
        else:
            self._frame_sources[camera_id] = source

        # If this camera is the currently selected one, update the preview
        if self._selected_camera_id == camera_id or self._selected_camera_id is None:
            self._update_preview_source(camera_id)

    def select_camera(self, camera_id: int) -> None:
        """Select a camera for live preview.

        Args:
            camera_id: The camera ID to display.

        """
        self._selected_camera_id = camera_id
        self._update_preview_source(camera_id)

    # ------------------------------------------------------------------
    # Internal — UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the complete dashboard layout."""
        self.setStyleSheet(f"DashboardWidget {{ background-color: {_COLOR_BG.name()}; }}")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self._build_header(main_layout)
        self._build_body(main_layout)
        self._build_status_bar(main_layout)

    def _build_header(self, layout: QVBoxLayout) -> None:
        """Build the dashboard header bar.

        Args:
            layout: The parent layout.

        """
        header = QFrame(self)
        header.setStyleSheet(
            "QFrame { background: transparent; }",
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Dashboard", header)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {_COLOR_TEXT.name()};")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Summary badges row
        self._online_badge = QLabel("● 0 online", header)
        self._online_badge.setStyleSheet(
            f"color: {_COLOR_ONLINE.name()}; font-size: 12px; padding: 4px 12px;",
        )
        header_layout.addWidget(self._online_badge)

        self._offline_badge = QLabel("● 0 offline", header)
        self._offline_badge.setStyleSheet(
            f"color: {_COLOR_OFFLINE.name()}; font-size: 12px; padding: 4px 12px;",
        )
        header_layout.addWidget(self._offline_badge)

        self._refresh_btn = QPushButton("Refresh", header)
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background-color: {_COLOR_ACCENT.name()}; "
            f"color: white; "
            f"border: none; "
            f"padding: 6px 16px; "
            f"border-radius: 4px; "
            f"font-weight: bold; "
            f"}}"
            f"QPushButton:hover {{ background-color: #2980b9; }}",
        )
        self._refresh_btn.clicked.connect(self._on_refresh)
        header_layout.addWidget(self._refresh_btn)

        layout.addWidget(header)

    def _build_body(self, layout: QVBoxLayout) -> None:
        """Build the main body with splitter layout.

        Args:
            layout: The parent layout.

        """
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {_COLOR_TEXT_MUTED.name()}; }}",
        )

        # Left panel: camera status + live preview
        left_panel = QWidget(splitter)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Camera status
        status_title = QLabel("Cameras", left_panel)
        status_title_font = QFont()
        status_title_font.setPointSize(11)
        status_title_font.setBold(True)
        status_title.setFont(status_title_font)
        status_title.setStyleSheet(f"color: {_COLOR_TEXT.name()};")
        left_layout.addWidget(status_title)

        self._camera_panel = CameraStatusPanel(left_panel)
        left_layout.addWidget(self._camera_panel)

        # Live preview
        preview_title = QLabel("Live Preview", left_panel)
        preview_title_font = QFont()
        preview_title_font.setPointSize(11)
        preview_title_font.setBold(True)
        preview_title.setFont(preview_title_font)
        preview_title.setStyleSheet(f"color: {_COLOR_TEXT.name()}; padding-top: 8px;")
        left_layout.addWidget(preview_title)

        self._preview_widget = LivePreviewWidget(left_panel)
        left_layout.addWidget(self._preview_widget, stretch=1)

        # Right panel: detection summary
        right_panel = QWidget(splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._detection_summary = DetectionSummaryWidget(right_panel)
        right_layout.addWidget(self._detection_summary)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 400])

        layout.addWidget(splitter, stretch=1)

    def _build_status_bar(self, layout: QVBoxLayout) -> None:
        """Build the bottom status bar.

        Args:
            layout: The parent layout.

        """
        self._status_label = QLabel("Ready", self)
        self._status_label.setStyleSheet(
            f"color: {_COLOR_TEXT_MUTED.name()}; font-size: 10px; padding: 2px 0;",
        )
        layout.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Internal — signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self._camera_panel.camera_selected.connect(self._on_camera_selected)

    def _on_camera_selected(self, camera_id: int) -> None:
        """Handle camera card click — select for live preview.

        Args:
            camera_id: The selected camera ID.

        """
        self.select_camera(camera_id)

    # ------------------------------------------------------------------
    # Internal — data flow
    # ------------------------------------------------------------------

    def _on_refresh(self) -> None:
        """Fetch fresh data from the dashboard service and update all panels."""
        try:
            data = self._dashboard_service.refresh()
        except Exception:
            logger.opt(exception=True).warning("Dashboard refresh failed")
            self._status_label.setText("Refresh failed — check log")
            return

        self._cached_data = data

        # Update camera status panel
        self._camera_panel.update_cameras(data.cameras)

        # Update detection summary
        self._detection_summary.update_counts(
            total=data.total_detections_today,
            by_camera=data.detection_count_by_camera,
        )
        self._detection_summary.update_recent(data.recent_detections)

        # Update header badges
        self._online_badge.setText(f"● {data.cameras_online} online")
        self._offline_badge.setText(f"● {data.cameras_offline} offline")

        # Update status bar
        ts = data.refreshed_at
        ts_str = ts.strftime("%H:%M:%S") if ts else "?"
        self._status_label.setText(
            f"Refreshed at {ts_str} · "
            f"{data.total_detections_today} detections today · "
            f"{len(data.cameras)} cameras",
        )

    def _update_preview_source(self, camera_id: int) -> None:
        """Connect or disconnect the live preview frame source.

        Args:
            camera_id: The camera ID to preview.

        """
        source = self._frame_sources.get(camera_id)
        if source is not None:
            # Find camera name from cached data
            name = ""
            if self._cached_data:
                for cam in self._cached_data.cameras:
                    if cam.id == camera_id:
                        name = cam.name
                        break
            self._preview_widget.set_frame_source(source, camera_name=name)
            self._preview_widget.start()
        else:
            self._preview_widget.stop()
            self._preview_widget.set_frame_source(None, camera_name="")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Clean up timers and resources.

        Must be called when the dashboard is no longer needed.
        """
        self.stop_refresh()
        self._preview_widget.stop()

    def __repr__(self) -> str:
        return (
            f"<DashboardWidget cameras={len(self._frame_sources)} "
            f"refresh={self._refresh_timer.isActive()}>"
        )
