"""Detection Logs — paginated, filterable table of detection events.

Features
--------
- Paginated table of detection events (timestamp, camera, plate, confidence)
- Filters: camera dropdown, date range, plate number search
- Click-to-preview evidence (snapshot image viewer + video player)
- Export to CSV and JSON
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.database.models.detection_model import DetectionModel
from src.repositories.detection_repository import DetectionFilter

if TYPE_CHECKING:
    from src.services.camera_service import CameraService
    from src.repositories.detection_repository import DetectionRepository

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_PAGE_SIZE = 50
_DATE_FORMAT = "yyyy-MM-dd"
_COLUMNS = [
    ("ID", 50),
    ("Timestamp", 160),
    ("Camera", 140),
    ("Plate Number", 140),
    ("Confidence", 90),
    ("Webhook", 110),
    ("Snapshot", 80),
    ("Video", 80),
]
_COL_KEYS = ["id", "timestamp", "camera", "plate", "confidence", "webhook", "snapshot", "video"]

_DARK_BG = QColor("#1a1a1a")
_DARK_CARD = QColor("#2b2b2b")
_DARK_BORDER = QColor("#3a3a3a")
_TEXT_COLOR = QColor("#ecf0f1")
_TEXT_MUTED = QColor("#95a5a6")
_ACCENT = QColor("#3498db")
_ONLINE = QColor("#27ae60")
_OFFLINE = QColor("#e74c3c")

# ------------------------------------------------------------------
# Widgets
# ------------------------------------------------------------------


class EvidencePreviewDialog(QDialog):
    """Modal dialog for viewing snapshot images and playing video clips.

    Usage::

        dialog = EvidencePreviewDialog(image_path="/path/to/snapshot.jpg", parent=self)
        dialog.exec()
    """

    def __init__(
        self,
        image_path: str | None = None,
        video_path: str | None = None,
        plate_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the preview dialog.

        Args:
            image_path: Absolute path to a snapshot JPEG (or ``None``).
            video_path: Absolute path to a video clip MP4 (or ``None``).
            plate_text: The plate text for the title.
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)

        title = f"Evidence — {plate_text}" if plate_text else "Evidence Preview"
        self.setWindowTitle(title)
        self.setMinimumSize(640, 480)
        self.resize(800, 600)

        self._image_path = image_path
        self._video_path = video_path

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        tabs = QWidget(self)
        tabs_layout = QVBoxLayout(tabs)
        tabs_layout.setContentsMargins(0, 0, 0, 0)

        has_image = self._image_path is not None and Path(self._image_path).is_file()
        has_video = self._video_path is not None and Path(self._video_path).is_file()

        if not has_image and not has_video:
            no_evidence = QLabel("No evidence available for this detection.")
            no_evidence.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_evidence.setStyleSheet(f"color: {_TEXT_MUTED.name()}; font-size: 14px;")
            tabs_layout.addWidget(no_evidence)
        else:
            if has_image and self._image_path:
                image_label = QLabel(self)
                pixmap = QPixmap(self._image_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        720,
                        540,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    image_label.setPixmap(scaled)
                else:
                    image_label.setText("Failed to load image")
                    image_label.setStyleSheet(f"color: {_OFFLINE.name()};")
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tabs_layout.addWidget(image_label)

            if has_video:
                video_label = QLabel(
                    f"Video clip available at:\n{self._video_path}",
                    self,
                )
                video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                video_label.setStyleSheet(f"color: {_TEXT_COLOR.name()}; font-size: 12px;")
                video_label.setWordWrap(True)
                tabs_layout.addWidget(video_label)

        close_btn = QPushButton("Close", self)
        close_btn.setToolTip("Close the evidence preview")
        close_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background-color: {_ACCENT.name()}; color: white; border: none; "
            f"padding: 8px 24px; border-radius: 4px; font-weight: bold; "
            f"}}"
            f"QPushButton:hover {{ background-color: #2980b9; }}",
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(tabs)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)


class DetectionLogsWidget(QWidget):
    """Filterable, paginated table of detection events.

    Signals:
        detection_count_changed: Emitted when the total count of
            matching detections changes.
    """

    detection_count_changed = Signal(int)

    def __init__(
        self,
        camera_service: CameraService,
        detection_repository: DetectionRepository,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the detection logs widget.

        Args:
            camera_service: For resolving camera names and filtering
                by camera.
            detection_repository: For querying detection records.
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)

        self._camera_service = camera_service
        self._detection_repo = detection_repository

        self._current_page: int = 0
        self._total_count: int = 0
        self._total_pages: int = 0

        self._setup_ui()
        self._load_cameras()
        self._refresh()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def total_detections(self) -> int:
        """Total number of detections matching current filters."""
        return self._total_count

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the complete logs page layout."""
        self.setStyleSheet(f"DetectionLogsWidget {{ background-color: {_DARK_BG.name()}; }}")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self._build_header(main_layout)
        self._build_filters(main_layout)
        self._build_table(main_layout)
        self._build_pagination(main_layout)

    def _build_header(self, layout: QVBoxLayout) -> None:
        """Build the page header.

        Args:
            layout: The parent layout.

        """
        header = QFrame(self)
        header.setStyleSheet("QFrame { background: transparent; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Detection Logs", header)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self._count_label = QLabel("0 detections", header)
        self._count_label.setStyleSheet(
            f"color: {_TEXT_MUTED.name()}; font-size: 12px; padding: 4px 12px;",
        )
        header_layout.addWidget(self._count_label)

        layout.addWidget(header)

    def _build_filters(self, layout: QVBoxLayout) -> None:
        """Build the filter bar.

        Args:
            layout: The parent layout.

        """
        filter_frame = QFrame(self)
        filter_frame.setStyleSheet(
            f"QFrame {{ background-color: {_DARK_CARD.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; "
            f"border-radius: 6px; padding: 8px; }}",
        )
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(12)

        # Camera filter
        camera_label = QLabel("Camera:", filter_frame)
        camera_label.setStyleSheet(f"color: {_TEXT_COLOR.name()}; font-weight: bold;")
        camera_label.setToolTip("Filter by camera")
        filter_layout.addWidget(camera_label)

        self._camera_filter = QComboBox(filter_frame)
        self._camera_filter.setToolTip("Select a camera to filter detections")
        self._camera_filter.setMinimumWidth(160)
        self._camera_filter.addItem("All Cameras", None)
        self._camera_filter.setStyleSheet(
            f"QComboBox {{ background-color: {_DARK_BG.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; padding: 4px 8px; border-radius: 4px; }}"
            f"QComboBox:hover {{ border-color: {_ACCENT.name()}; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background-color: {_DARK_CARD.name()}; "
            f"color: {_TEXT_COLOR.name()}; selection-background-color: {_ACCENT.name()}; }}"
        )
        self._camera_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._camera_filter)

        # Date range
        date_from_label = QLabel("From:", filter_frame)
        date_from_label.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        date_from_label.setToolTip("Filter detections from this date")
        filter_layout.addWidget(date_from_label)

        self._date_from = QDateEdit(filter_frame)
        self._date_from.setToolTip("Earliest detection date to include")
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat(_DATE_FORMAT)
        self._date_from.setDate(date.today() - timedelta(days=7))
        self._date_from.setStyleSheet(
            f"QDateEdit {{ background-color: {_DARK_BG.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; padding: 4px 8px; border-radius: 4px; }}"
            f"QDateEdit:hover {{ border-color: {_ACCENT.name()}; }}"
        )
        self._date_from.dateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._date_from)

        date_to_label = QLabel("To:", filter_frame)
        date_to_label.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        date_to_label.setToolTip("Filter detections until this date")
        filter_layout.addWidget(date_to_label)

        self._date_to = QDateEdit(filter_frame)
        self._date_to.setToolTip("Latest detection date to include")
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat(_DATE_FORMAT)
        self._date_to.setDate(date.today())
        self._date_to.setStyleSheet(
            f"QDateEdit {{ background-color: {_DARK_BG.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; padding: 4px 8px; border-radius: 4px; }}"
            f"QDateEdit:hover {{ border-color: {_ACCENT.name()}; }}"
        )
        self._date_to.dateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._date_to)

        # Plate search
        plate_label = QLabel("Plate:", filter_frame)
        plate_label.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        plate_label.setToolTip("Filter by license plate number (partial match)")
        filter_layout.addWidget(plate_label)

        self._plate_search = QLineEdit(filter_frame)
        self._plate_search.setPlaceholderText("Search plate number…")
        self._plate_search.setToolTip("Enter a full or partial plate number to search")
        self._plate_search.setStyleSheet(
            f"QLineEdit {{ background-color: {_DARK_BG.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; padding: 4px 8px; border-radius: 4px; }}"
            f"QLineEdit:hover {{ border-color: {_ACCENT.name()}; }}"
            f"QLineEdit:focus {{ border-color: {_ACCENT.name()}; }}"
        )
        self._plate_search.returnPressed.connect(self._on_filter_changed)
        filter_layout.addWidget(self._plate_search, stretch=1)

        # Export buttons
        export_csv_btn = QPushButton("Export CSV", filter_frame)
        export_csv_btn.setToolTip("Export the current filtered results as a CSV file")
        export_csv_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_ACCENT.name()}; color: white; "
            f"border: none; padding: 6px 14px; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #2980b9; }}"
        )
        export_csv_btn.clicked.connect(lambda: self._export("csv"))
        filter_layout.addWidget(export_csv_btn)

        export_json_btn = QPushButton("Export JSON", filter_frame)
        export_json_btn.setToolTip("Export the current filtered results as a JSON file")
        export_json_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_DARK_CARD.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_ACCENT.name()}; padding: 6px 14px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: #3a3a3a; }}"
        )
        export_json_btn.clicked.connect(lambda: self._export("json"))
        filter_layout.addWidget(export_json_btn)

        # Loading indicator (hidden by default)
        self._loading_label = QLabel("", filter_frame)
        self._loading_label.setStyleSheet(f"color: {_ACCENT.name()}; font-weight: bold;")
        filter_layout.addWidget(self._loading_label)

        layout.addWidget(filter_frame)

    def _build_table(self, layout: QVBoxLayout) -> None:
        """Build the detection events table.

        Args:
            layout: The parent layout.

        """
        self._table = QTableWidget(self)
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels([c[0] for c in _COLUMNS])

        # Set column widths
        header = self._table.horizontalHeader()
        if header is not None:
            for i, (_, width) in enumerate(_COLUMNS):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                self._table.setColumnWidth(i, width)

        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.cellClicked.connect(self._on_cell_clicked)

        self._table.setStyleSheet(
            f"QTableWidget {{ background-color: {_DARK_CARD.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; border-radius: 6px; "
            f"gridline-color: transparent; }}"
            f"QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {_DARK_BORDER.name()}; }}"
            f"QTableWidget::item:selected {{ background-color: {_ACCENT.name()}; }}"
            f"QHeaderView::section {{ background-color: {_DARK_BG.name()}; "
            f"color: {_TEXT_MUTED.name()}; padding: 8px; border: none; "
            f"font-weight: bold; }}"
            f"QTableWidget::item:alternate {{ background-color: #242424; }}"
        )

        layout.addWidget(self._table, stretch=1)

    def _build_pagination(self, layout: QVBoxLayout) -> None:
        """Build the pagination bar.

        Args:
            layout: The parent layout.

        """
        pagination = QFrame(self)
        pagination.setStyleSheet("QFrame { background: transparent; }")
        page_layout = QHBoxLayout(pagination)
        page_layout.setContentsMargins(0, 4, 0, 0)

        self._prev_btn = QPushButton("◀ Previous", pagination)
        self._prev_btn.setToolTip("Go to the previous page of results")
        self._prev_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_DARK_CARD.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; padding: 6px 14px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: #3a3a3a; }}"
            f"QPushButton:disabled {{ color: {_TEXT_MUTED.name()}; }}"
        )
        self._prev_btn.clicked.connect(self._prev_page)
        page_layout.addWidget(self._prev_btn)

        page_layout.addStretch()

        self._page_label = QLabel("Page 0 of 0", pagination)
        self._page_label.setStyleSheet(f"color: {_TEXT_COLOR.name()}; font-size: 12px;")
        page_layout.addWidget(self._page_label)

        page_layout.addStretch()

        self._next_btn = QPushButton("Next ▶", pagination)
        self._next_btn.setToolTip("Go to the next page of results")
        self._next_btn.setStyleSheet(
            f"QPushButton {{ background-color: {_DARK_CARD.name()}; color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; padding: 6px 14px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: #3a3a3a; }}"
            f"QPushButton:disabled {{ color: {_TEXT_MUTED.name()}; }}"
        )
        self._next_btn.clicked.connect(self._next_page)
        page_layout.addWidget(self._next_btn)

        layout.addWidget(pagination)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_cameras(self) -> None:
        """Populate the camera filter dropdown."""
        try:
            cameras = self._camera_service.get_all_cameras()
        except Exception:
            logger.opt(exception=True).warning("Failed to load cameras for filter")
            return

        for cam in cameras:
            self._camera_filter.addItem(
                f"{cam.name} ({cam.camera_type.upper()})",
                cam.id,
            )

    def _build_filter(self) -> DetectionFilter:
        """Build a ``DetectionFilter`` from the current UI state.

        Returns:
            A ``DetectionFilter`` instance.

        """
        camera_id = self._camera_filter.currentData()
        date_from = self._date_from.date().toPython()
        date_to = self._date_to.date().toPython()
        plate_text = self._plate_search.text().strip()

        return DetectionFilter(
            camera_id=camera_id,
            date_from=datetime.combine(date_from, datetime.min.time()),
            date_to=datetime.combine(date_to, datetime.max.time()),
            plate_number=plate_text if plate_text else None,
            limit=_PAGE_SIZE,
            offset=self._current_page * _PAGE_SIZE,
        )

    def _refresh(self) -> None:
        """Reload data from the repository and update the table."""
        self._loading_label.setText("⟳ Loading…")
        QApplication.processEvents()

        try:
            filter_ = self._build_filter()
            detections = self._detection_repo.get_filtered(filter_)
            self._total_count = self._detection_repo.count_filtered(filter_)
        except Exception:
            logger.opt(exception=True).warning("Failed to load detection logs")
            self._table.setRowCount(0)
            self._update_pagination()
            self._loading_label.setText("⚠ Load failed")
            return

        self._total_pages = max(1, math.ceil(self._total_count / _PAGE_SIZE))
        self._current_page = min(self._current_page, self._total_pages - 1)

        self._populate_table(detections)
        self._update_pagination()
        self._loading_label.setText("")
        self.detection_count_changed.emit(self._total_count)

    def _populate_table(self, detections: list[DetectionModel]) -> None:
        """Fill the table with detection records.

        Args:
            detections: The list of detection models to display.

        """
        self._table.setRowCount(len(detections))

        for row, det in enumerate(detections):
            # Resolve camera name
            camera_name = self._resolve_camera_name(det.camera_id)

            # Timestamp
            ts_str = det.detected_at.strftime("%Y-%m-%d %H:%M:%S") if det.detected_at else "?"

            # Confidence
            conf_str = f"{det.confidence:.2%}" if det.confidence else "N/A"

            # Webhook status
            wh_status = det.webhook_status or "not_configured"
            wh_colour = self._webhook_status_colour(wh_status)

            self._set_item(row, 0, str(det.id))
            self._set_item(row, 1, ts_str)
            self._set_item(row, 2, camera_name)
            self._set_item(row, 3, det.plate_number or "(no OCR)")
            self._set_item(row, 4, conf_str)
            self._set_item(row, 5, wh_status.capitalize(), wh_colour)

            # Snapshot / Video — clickable indicators
            has_image = bool(det.image_path)
            has_video = bool(det.video_path)

            snap_text = "📷 View" if has_image else "—"
            snap_item = QTableWidgetItem(snap_text)
            snap_item.setData(Qt.ItemDataRole.UserRole, det.image_path or "")
            if not has_image:
                snap_item.setForeground(_TEXT_MUTED)
            self._table.setItem(row, 6, snap_item)

            vid_text = "🎬 Play" if has_video else "—"
            vid_item = QTableWidgetItem(vid_text)
            vid_item.setData(Qt.ItemDataRole.UserRole, det.video_path or "")
            if not has_video:
                vid_item.setForeground(_TEXT_MUTED)
            self._table.setItem(row, 7, vid_item)

    def _set_item(
        self,
        row: int,
        col: int,
        text: str,
        colour: QColor | None = None,
    ) -> None:
        """Set a table cell item with optional colour.

        Args:
            row: Row index.
            col: Column index.
            text: Display text.
            colour: Optional foreground colour.

        """
        item = QTableWidgetItem(text)
        if colour is not None:
            item.setForeground(colour)
        else:
            item.setForeground(_TEXT_COLOR)
        self._table.setItem(row, col, item)

    @staticmethod
    def _webhook_status_colour(status: str) -> QColor:
        """Map webhook status to a display colour.

        Args:
            status: The webhook status string.

        Returns:
            A ``QColor`` for the status.

        """
        mapping = {
            "success": _ONLINE,
            "failed": _OFFLINE,
            "pending": QColor("#f39c12"),
        }
        return mapping.get(status, _TEXT_MUTED)

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _update_pagination(self) -> None:
        """Refresh the pagination controls."""
        page_display = self._current_page + 1
        total_display = max(self._total_pages, 1)
        self._page_label.setText(f"Page {page_display} of {total_display}")
        self._count_label.setText(f"{self._total_count} detections")
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(self._current_page < self._total_pages - 1)

    def _prev_page(self) -> None:
        """Go to the previous page."""
        if self._current_page > 0:
            self._current_page -= 1
            self._refresh()

    def _next_page(self) -> None:
        """Go to the next page."""
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._refresh()

    # ------------------------------------------------------------------
    # Filter handling
    # ------------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        """Reset to page 0 and refresh when any filter changes."""
        self._current_page = 0
        self._refresh()

    # ------------------------------------------------------------------
    # Cell clicks
    # ------------------------------------------------------------------

    def _on_cell_clicked(self, row: int, col: int) -> None:
        """Handle clicks on evidence cells.

        Args:
            row: The clicked row.
            col: The clicked column (6=snapshot, 7=video).

        """
        if col not in (6, 7):
            return

        path = self._table.item(row, col).data(Qt.ItemDataRole.UserRole) if self._table.item(row, col) else ""
        if not path:
            return

        plate_text = self._table.item(row, 3).text() if self._table.item(row, 3) else ""
        image_path = path if col == 6 else None
        video_path = path if col == 7 else None

        dialog = EvidencePreviewDialog(
            image_path=image_path,
            video_path=video_path,
            plate_text=plate_text,
            parent=self,
        )
        dialog.exec()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export(self, fmt: str) -> None:
        """Export the current filtered results.

        Args:
            fmt: ``"csv"`` or ``"json"``.

        """
        try:
            # Fetch all matching records (no pagination)
            filter_ = self._build_filter()
            filter_.limit = self._total_count if self._total_count > 0 else 1
            filter_.offset = 0
            detections = self._detection_repo.get_filtered(filter_)
        except Exception:
            logger.opt(exception=True).warning("Failed to load detections for export")
            QMessageBox.warning(self, "Export Failed", "Could not load detection data.")
            return

        if not detections:
            QMessageBox.information(self, "Export", "No data to export.")
            return

        # Choose save path
        ext = fmt.upper()
        file_filter = f"{ext} Files (*.{fmt})"
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Detection Logs as {ext}",
            f"plate_guard_detections_{date.today().isoformat()}.{fmt}",
            file_filter,
        )
        if not path:
            return

        try:
            records = []
            for det in detections:
                records.append({
                    "id": det.id,
                    "camera_id": det.camera_id,
                    "camera_name": self._resolve_camera_name(det.camera_id),
                    "plate_number": det.plate_number,
                    "confidence": det.confidence,
                    "detected_at": det.detected_at.isoformat() if det.detected_at else None,
                    "webhook_status": det.webhook_status,
                    "image_path": det.image_path,
                    "video_path": det.video_path,
                })

            if fmt == "csv":
                self._export_csv(path, records)
            else:
                self._export_json(path, records)

            QMessageBox.information(
                self,
                "Export Successful",
                f"Exported {len(records)} records to:\n{path}",
            )

        except (OSError, PermissionError) as exc:
            logger.error("Export failed: {}", exc)
            QMessageBox.critical(self, "Export Failed", str(exc))

    @staticmethod
    def _export_csv(path: str, records: list[dict[str, Any]]) -> None:
        """Write records to a CSV file.

        Args:
            path: Output file path.
            records: List of record dicts.

        """
        if not records:
            return
        with io.open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)
        logger.info("Exported {} records to CSV: {}", len(records), path)

    @staticmethod
    def _export_json(path: str, records: list[dict[str, Any]]) -> None:
        """Write records to a JSON file.

        Args:
            path: Output file path.
            records: List of record dicts.

        """
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, default=str)
        logger.info("Exported {} records to JSON: {}", len(records), path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_camera_name(self, camera_id: int) -> str:
        """Resolve a camera ID to a display name.

        Args:
            camera_id: The camera ID.

        Returns:
            The camera name, or a fallback string.

        """
        try:
            cam = self._camera_service.get_camera(camera_id)
            return cam.name
        except Exception:
            return f"Camera #{camera_id}"

    def __repr__(self) -> str:
        return (
            f"<DetectionLogsWidget page={self._current_page + 1}/"
            f"{self._total_pages} count={self._total_count}>"
        )
