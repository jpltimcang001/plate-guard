"""Draggable vertex handle for polygon editing.

Each ``VertexHandle`` is a small circle rendered in the scene that the
user can click and drag to reposition a polygon vertex.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QPen, QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsSceneMouseEvent, QGraphicsView

from loguru import logger

_HANDLE_RADIUS: float = 6.0
_HANDLE_DIAMETER: float = _HANDLE_RADIUS * 2
_FILL_COLOR: QColor = QColor(255, 255, 255)
_STROKE_COLOR: QColor = QColor(0, 120, 215)
_HOVER_COLOR: QColor = QColor(0, 160, 255)
_ACTIVE_COLOR: QColor = QColor(255, 170, 0)


class VertexHandle(QGraphicsEllipseItem):
    """An interactive, draggable polygon vertex.

    Signals
    -------
    ``position_changed(index: int, pos: QPointF)``
        Emitted when the handle is moved by the user.
    ``handle_dragged(index: int, pos: QPointF)``
        Emitted continuously during a drag operation.
    """

    position_changed: Signal = Signal(int, QPointF)
    handle_dragged: Signal = Signal(int, QPointF)

    def __init__(
        self,
        index: int,
        pos: QPointF,
        parent_item: QGraphicsEllipseItem | None = None,
        on_moved: Callable[[int, QPointF], None] | None = None,
        on_dragged: Callable[[int, QPointF], None] | None = None,
    ) -> None:
        """Initialize a vertex handle.

        Args:
            index: The vertex index within its parent polygon.
            pos: Initial scene position.
            parent_item: Optional parent QGraphicsItem.
            on_moved: Optional callback when the handle is released after a drag.
            on_dragged: Optional callback during a drag.

        """
        rect = QRectF(-_HANDLE_RADIUS, -_HANDLE_RADIUS, _HANDLE_DIAMETER, _HANDLE_DIAMETER)
        super().__init__(rect, parent=parent_item)

        self._vertex_index: int = index
        self._on_moved = on_moved
        self._on_dragged = on_dragged
        self._is_dragging: bool = False
        self._drag_start: QPointF = QPointF()

        # Appearance
        self.setPos(pos)
        self.setBrush(QBrush(_FILL_COLOR))
        self.setPen(QPen(_STROKE_COLOR, 2.0))
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(10)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def vertex_index(self) -> int:
        """The index of this vertex in the parent polygon."""
        return self._vertex_index

    @vertex_index.setter
    def vertex_index(self, value: int) -> None:
        """Set the vertex index (used when vertices are reordered)."""
        self._vertex_index = value

    # ------------------------------------------------------------------
    # Hover events
    # ------------------------------------------------------------------

    def hoverEnterEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        """Highlight the handle on hover."""
        self.setBrush(QBrush(_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        """Restore the handle colour on hover leave."""
        self.setBrush(QBrush(_FILL_COLOR))
        super().hoverLeaveEvent(event)

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Begin a drag operation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start = self.pos()
            self.setBrush(QBrush(_ACTIVE_COLOR))
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            logger.trace(
                "VertexHandle[{}] drag started at ({:.0f}, {:.0f})",
                self._vertex_index,
                self.pos().x(),
                self.pos().y(),
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle drag movement."""
        if self._is_dragging:
            super().mouseMoveEvent(event)
            new_pos = self.pos()
            if self._on_dragged is not None:
                self._on_dragged(self._vertex_index, new_pos)
            self.handle_dragged.emit(self._vertex_index, new_pos)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """End the drag and notify listeners."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            new_pos = self.pos()
            self.setBrush(QBrush(_FILL_COLOR))
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

            if self._on_moved is not None:
                self._on_moved(self._vertex_index, new_pos)
            self.position_changed.emit(self._vertex_index, new_pos)

            logger.trace(
                "VertexHandle[{}] moved to ({:.0f}, {:.0f})",
                self._vertex_index,
                new_pos.x(),
                new_pos.y(),
            )

        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Geometry change
    # ------------------------------------------------------------------

    def itemChange(self, change: QGraphicsEllipseItem.GraphicsItemChange, value: object) -> object:  # type: ignore[override]
        """Keep the handle within scene bounds during movement."""
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                # Constrain to scene boundaries
                bounds = self._scene_bounds()
                if bounds is not None:
                    clamped = QPointF(
                        max(bounds.left(), min(bounds.right(), value.x())),
                        max(bounds.top(), min(bounds.bottom(), value.y())),
                    )
                    return clamped
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _scene_bounds(self) -> QRectF | None:
        """Return the scene rectangle, or ``None`` if not in a scene."""
        scene = self.scene()
        if scene is None:
            return None
        return scene.sceneRect()

    def __repr__(self) -> str:
        return (
            f"<VertexHandle index={self._vertex_index} "
            f"pos=({self.pos().x():.0f}, {self.pos().y():.0f})>"
        )
