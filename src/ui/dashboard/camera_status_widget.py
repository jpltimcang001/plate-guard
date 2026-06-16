"""Camera status panel — list of camera cards with health indicators.

Each camera is displayed as a card showing its name, type, status
(online / offline / disabled), and today's detection count.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from loguru import logger

from src.application.dto.dashboard_dto import CameraStatusDTO

# ------------------------------------------------------------------
# Colour constants
# ------------------------------------------------------------------

_COLOR_ONLINE = QColor("#27ae60")
_COLOR_OFFLINE = QColor("#e74c3c")
_COLOR_RECONNECTING = QColor("#f39c12")
_COLOR_ERROR = QColor("#c0392b")
_COLOR_DISABLED = QColor("#7f8c8d")
_COLOR_CARD_BG = QColor("#2b2b2b")
_COLOR_CARD_BORDER = QColor("#3a3a3a")
_COLOR_TEXT = QColor("#ecf0f1")
_COLOR_TEXT_MUTED = QColor("#95a5a6")


def _status_color(status: str) -> QColor:
    """Map a status string to a display colour.

    Args:
        status: ``"online"``, ``"offline"``, ``"reconnecting"``,
            ``"error"``, or ``"disabled"``.

    Returns:
        The corresponding ``QColor``.

    """
    mapping = {
        "online": _COLOR_ONLINE,
        "offline": _COLOR_OFFLINE,
        "reconnecting": _COLOR_RECONNECTING,
        "error": _COLOR_ERROR,
        "disabled": _COLOR_DISABLED,
    }
    return mapping.get(status, _COLOR_DISABLED)


class CameraCard(QFrame):
    """A single camera status card.

    Signals:
        clicked: Emitted when the card is clicked (carries the
            camera ID).

    """

    clicked = Signal(int)

    def __init__(
        self,
        status: CameraStatusDTO,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the card.

        Args:
            status: The camera status data to display.
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)
        self._camera_id = status.id
        self._setup_ui(status)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def camera_id(self) -> int:
        """The camera ID for this card."""
        return self._camera_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_status(self, status: CameraStatusDTO) -> None:
        """Refresh the card with new status data.

        Args:
            status: The updated ``CameraStatusDTO``.

        """
        self._camera_id = status.id
        self._name_label.setText(status.name)
        self._type_label.setText(status.camera_type.upper())
        self._count_label.setText(str(status.detection_count_today))

        colour = _status_color(status.status)
        self._status_dot.setStyleSheet(
            f"background-color: {colour.name()}; "
            f"border-radius: 5px; "
            f"min-width: 10px; min-height: 10px; "
            f"max-width: 10px; max-height: 10px;",
        )
        self._status_label.setText(status.status.capitalize())
        self._status_label.setStyleSheet(f"color: {colour.name()}; font-weight: bold;")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_ui(self, status: CameraStatusDTO) -> None:
        """Build the card layout."""
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(
            f"CameraCard {{ background-color: {_COLOR_CARD_BG.name()}; "
            f"border: 1px solid {_COLOR_CARD_BORDER.name()}; "
            f"border-radius: 6px; padding: 8px; }}"
            f"CameraCard:hover {{ border-color: #555; }}",
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumHeight(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Status dot
        colour = _status_color(status.status)
        self._status_dot = QLabel(self)
        self._status_dot.setFixedSize(10, 10)
        self._status_dot.setStyleSheet(
            f"background-color: {colour.name()}; "
            f"border-radius: 5px;",
        )
        layout.addWidget(self._status_dot)

        # Name + type column
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._name_label = QLabel(status.name, self)
        name_font = QFont()
        name_font.setPointSize(11)
        name_font.setBold(True)
        self._name_label.setFont(name_font)
        self._name_label.setStyleSheet(f"color: {_COLOR_TEXT.name()};")
        text_col.addWidget(self._name_label)

        self._type_label = QLabel(status.camera_type.upper(), self)
        type_font = QFont()
        type_font.setPointSize(8)
        self._type_label.setFont(type_font)
        self._type_label.setStyleSheet(f"color: {_COLOR_TEXT_MUTED.name()};")
        text_col.addWidget(self._type_label)

        layout.addLayout(text_col, stretch=1)

        # Status text
        status_col = QVBoxLayout()
        status_col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._status_label = QLabel(status.status.capitalize(), self)
        self._status_label.setStyleSheet(
            f"color: {colour.name()}; font-weight: bold; font-size: 11px;",
        )
        status_col.addWidget(self._status_label)

        layout.addLayout(status_col)

        # Detection count
        count_col = QVBoxLayout()
        count_col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._count_label = QLabel(str(status.detection_count_today), self)
        count_font = QFont()
        count_font.setPointSize(16)
        count_font.setBold(True)
        self._count_label.setFont(count_font)
        self._count_label.setStyleSheet(f"color: {_COLOR_TEXT.name()};")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_col.addWidget(self._count_label)

        count_title = QLabel("today", self)
        count_title.setStyleSheet(
            f"color: {_COLOR_TEXT_MUTED.name()}; font-size: 9px;",
        )
        count_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_col.addWidget(count_title)

        layout.addLayout(count_col)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """Handle mouse click — emit ``clicked`` signal."""
        super().mousePressEvent(event)
        self.clicked.emit(self._camera_id)

    def __repr__(self) -> str:
        return f"<CameraCard id={self._camera_id} name={self._name_label.text()}>"


class CameraStatusPanel(QWidget):
    """Scrollable panel showing all camera status cards.

    Signals:
        camera_selected: Emitted when a camera card is clicked,
            carrying the camera ID.

    """

    camera_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the panel.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)
        self._cards: dict[int, CameraCard] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_cameras(self, cameras: list[CameraStatusDTO]) -> None:
        """Replace the displayed camera cards.

        Cards for new cameras are created; cards for removed cameras
        are destroyed; existing cards are updated in place.

        Args:
            cameras: The latest list of ``CameraStatusDTO`` instances.

        """
        # Remove cards for cameras that no longer exist
        new_ids = {c.id for c in cameras}
        for cid in list(self._cards.keys()):
            if cid not in new_ids:
                card = self._cards.pop(cid)
                self._card_layout.removeWidget(card)
                card.deleteLater()

        # Add / update cards
        for cs in cameras:
            if cs.id in self._cards:
                self._cards[cs.id].update_status(cs)
            else:
                card = CameraCard(cs, parent=self)
                card.clicked.connect(self._on_card_clicked)
                self._cards[cs.id] = card
                self._card_layout.addWidget(card)

        # Show/hide empty state
        self._empty_label.setVisible(len(cameras) == 0)

    def clear(self) -> None:
        """Remove all camera cards."""
        self.update_cameras([])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the scrollable panel layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical { width: 8px; }",
        )

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._card_layout = QVBoxLayout(self._scroll_content)
        self._card_layout.setContentsMargins(4, 4, 4, 4)
        self._card_layout.setSpacing(6)
        self._card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Empty state
        self._empty_label = QLabel("No cameras configured", self._scroll_content)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {_COLOR_TEXT_MUTED.name()}; font-size: 13px; padding: 20px;",
        )
        self._card_layout.addWidget(self._empty_label)

        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll)

    def _on_card_clicked(self, camera_id: int) -> None:
        """Forward the ``camera_selected`` signal.

        Args:
            camera_id: The clicked camera's ID.

        """
        self.camera_selected.emit(camera_id)

    def __repr__(self) -> str:
        return f"<CameraStatusPanel cards={len(self._cards)}>"
