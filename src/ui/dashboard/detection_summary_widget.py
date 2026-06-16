"""Detection summary widget — count badges and recent-detections table.

Displays total detection count for today alongside per-camera
breakdown, followed by a scrollable table of the most recent
detection events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from loguru import logger

from src.application.dto.dashboard_dto import DetectionSummaryDTO

# ------------------------------------------------------------------
# Style constants
# ------------------------------------------------------------------

_COLOR_BG = QColor("#2b2b2b")
_COLOR_BORDER = QColor("#3a3a3a")
_COLOR_TEXT = QColor("#ecf0f1")
_COLOR_TEXT_MUTED = QColor("#95a5a6")
_COLOR_HEADER_BG = QColor("#222222")
_COLOR_TABLE_ALT = QColor("#333333")
_COLOR_SUCCESS = QColor("#27ae60")
_COLOR_FAILURE = QColor("#e74c3c")
_COLOR_PENDING = QColor("#f39c12")


def _webhook_display(status: str) -> tuple[str, str]:
    """Return (display_text, colour_hex) for a webhook status.

    Args:
        status: Raw webhook status from the database.

    Returns:
        A tuple of ``(display_text, colour_hex)``.

    """
    mapping: dict[str, tuple[str, str]] = {
        "success": ("Delivered", _COLOR_SUCCESS.name()),
        "failed": ("Failed", _COLOR_FAILURE.name()),
        "pending": ("Pending", _COLOR_PENDING.name()),
        "not_configured": ("N/A", _COLOR_TEXT_MUTED.name()),
    }
    return mapping.get(status, (status, _COLOR_TEXT_MUTED.name()))


class DetectionSummaryWidget(QWidget):
    """Displays detection counts and a recent-detections table.

    Usage::

        summary = DetectionSummaryWidget(parent=self)
        summary.update_counts(total=42, by_camera={1: 20, 2: 22})
        summary.update_recent(recent_detections_list)
    """

    COLUMNS = ["ID", "Camera", "Plate", "Confidence", "Webhook", "Time"]
    COL_WIDTHS = [40, 120, 120, 80, 100, 160]

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the detection summary widget.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)
        self._recent: list[DetectionSummaryDTO] = []
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_counts(
        self,
        total: int,
        by_camera: dict[int, int] | None = None,
    ) -> None:
        """Update the detection count display.

        Args:
            total: Total detections today.
            by_camera: Optional map of ``camera_id → count``.

        """
        self._total_label.setText(str(total))

        if by_camera:
            parts = [str(total)]
            for cid, cnt in sorted(by_camera.items()):
                parts.append(f"Cam {cid}: {cnt}")
            self._breakdown_label.setText(" | ".join(parts))
        else:
            self._breakdown_label.setText("")

    def update_recent(self, detections: list[DetectionSummaryDTO]) -> None:
        """Replace the recent-detections table content.

        Args:
            detections: The latest list of ``DetectionSummaryDTO``
                instances, newest first.

        """
        self._recent = detections
        self._populate_table()

    def clear(self) -> None:
        """Clear all counts and the table."""
        self._total_label.setText("0")
        self._breakdown_label.setText("")
        self._recent = []
        self._populate_table()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the widget layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._build_count_section(layout)
        self._build_table_section(layout)

    def _build_count_section(self, layout: QVBoxLayout) -> None:
        """Build the top section with detection count badges.

        Args:
            layout: The parent layout.

        """
        count_frame = QFrame(self)
        count_frame.setStyleSheet(
            f"QFrame {{ background-color: {_COLOR_BG.name()}; "
            f"border: 1px solid {_COLOR_BORDER.name()}; "
            f"border-radius: 6px; padding: 12px; }}",
        )

        count_layout = QGridLayout(count_frame)
        count_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("Detections Today", count_frame)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {_COLOR_TEXT.name()};")
        count_layout.addWidget(title, 0, 0, 1, 2)

        self._total_label = QLabel("0", count_frame)
        total_font = QFont()
        total_font.setPointSize(36)
        total_font.setBold(True)
        self._total_label.setFont(total_font)
        self._total_label.setStyleSheet(f"color: {_COLOR_TEXT.name()};")
        self._total_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        count_layout.addWidget(self._total_label, 1, 0)

        self._breakdown_label = QLabel("", count_frame)
        self._breakdown_label.setStyleSheet(
            f"color: {_COLOR_TEXT_MUTED.name()}; font-size: 10px;",
        )
        count_layout.addWidget(self._breakdown_label, 1, 1)

        layout.addWidget(count_frame)

    def _build_table_section(self, layout: QVBoxLayout) -> None:
        """Build the recent-detections table.

        Args:
            layout: The parent layout.

        """
        table_label = QLabel("Recent Detections", self)
        table_label_font = QFont()
        table_label_font.setPointSize(11)
        table_label_font.setBold(True)
        table_label.setFont(table_label_font)
        table_label.setStyleSheet(f"color: {_COLOR_TEXT.name()}; padding: 4px 0;")
        layout.addWidget(table_label)

        self._table = QTableWidget(self)
        self._table.setColumnCount(len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(self.COLUMNS)

        # Header style
        header = self._table.horizontalHeader()
        header.setStyleSheet(
            f"QHeaderView::section {{ "
            f"background-color: {_COLOR_HEADER_BG.name()}; "
            f"color: {_COLOR_TEXT.name()}; "
            f"padding: 6px; "
            f"border: none; "
            f"font-weight: bold; "
            f"}}",
        )
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        for i, w in enumerate(self.COL_WIDTHS):
            self._table.setColumnWidth(i, w)

        # Table appearance
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ "
            f"background-color: {_COLOR_BG.name()}; "
            f"alternate-background-color: {_COLOR_TABLE_ALT.name()}; "
            f"color: {_COLOR_TEXT.name()}; "
            f"border: 1px solid {_COLOR_BORDER.name()}; "
            f"border-radius: 4px; "
            f"gridline-color: {_COLOR_BORDER.name()}; "
            f"font-size: 11px; "
            f"}}"
            f"QTableWidget::item {{ padding: 4px; }}",
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self._table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection,
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setMinimumHeight(200)

        layout.addWidget(self._table, stretch=1)

    def _populate_table(self) -> None:
        """Fill the table with recent detection records."""
        self._table.setRowCount(len(self._recent))

        for row, dto in enumerate(self._recent):
            self._set_item(row, 0, str(dto.id))
            self._set_item(row, 1, dto.camera_name)
            self._set_item(row, 2, dto.plate_text)
            self._set_item(
                row,
                3,
                f"{dto.confidence:.1%}" if dto.confidence > 0 else "-",
            )

            # Webhook status with colour
            wh_text, wh_colour = _webhook_display(dto.webhook_status)
            wh_item = QTableWidgetItem(wh_text)
            wh_item.setForeground(QColor(wh_colour))
            self._table.setItem(row, 4, wh_item)

            # Timestamp
            ts_str = dto.detected_at.strftime("%H:%M:%S") if dto.detected_at else "-"
            self._set_item(row, 5, ts_str)

        if not self._recent:
            self._table.setRowCount(1)
            empty = QTableWidgetItem("No detections yet")
            empty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(0, 0, empty)
            self._table.setSpan(0, 0, 1, len(self.COLUMNS))

    def _set_item(self, row: int, col: int, text: str) -> None:
        """Set a table cell value with standard styling.

        Args:
            row: Row index.
            col: Column index.
            text: Display text.

        """
        item = QTableWidgetItem(text)
        item.setForeground(QColor(_COLOR_TEXT))
        self._table.setItem(row, col, item)

    def __repr__(self) -> str:
        return (
            f"<DetectionSummaryWidget total={self._total_label.text()}>"
        )
