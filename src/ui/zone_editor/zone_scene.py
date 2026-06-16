"""Graphics scene for interactive zone editing.

``ZoneGraphicsScene`` provides the interaction model for drawing and
editing polygon detection zones:

- **Draw mode**: Left-click adds vertices, right-click removes the nearest
  vertex (if more than 3).  Pressing Enter or double-clicking the first
  vertex closes the polygon.
- **Edit mode**: Vertices can be dragged to reposition.  Right-click on a
  vertex deletes it.  Double-click on an edge inserts a new vertex.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QGraphicsView,
    QMenu,
)

from loguru import logger

from src.ui.zone_editor.vertex_handle import VertexHandle
from src.ui.zone_editor.zone_polygon_item import ZonePolygonItem


class EditorMode(Enum):
    """Interaction mode for the zone editor scene."""

    DRAW = auto()
    """Click to add polygon vertices.  Finished when closed."""

    EDIT = auto()
    """Drag vertices, right-click to delete, edge-double-click to insert."""

    VIEW = auto()
    """No editing allowed — pan/zoom only."""


_INSTRUCTION_FONT: QFont = QFont("Segoe UI", 11)
_INSTRUCTION_COLOR: QColor = QColor(255, 255, 255, 200)
_INSTRUCTION_BG: QBrush = QBrush(QColor(0, 0, 0, 120))
_GRID_COLOR: QColor = QColor(200, 200, 200, 30)
_GRID_SPACING: float = 50.0


class ZoneGraphicsScene(QGraphicsScene):
    """Interactive scene for drawing and editing polygon zones.

    Signals
    -------
    ``polygon_updated(points: list[QPointF])``
        Emitted whenever the active polygon's vertices change.
    ``polygon_completed(points: list[QPointF])``
        Emitted when a polygon is closed (3+ vertices).
    ``status_message(message: str)``
        Emitted to request a status bar update.
    mode_changed(mode: EditorMode)
        Emitted when the editor mode changes.
    """

    polygon_updated: Signal = Signal(list)  # list[QPointF]
    polygon_completed: Signal = Signal(list)  # list[QPointF]
    status_message: Signal = Signal(str)
    mode_changed: Signal = Signal(object)  # EditorMode

    def __init__(
        self,
        parent: QGraphicsView | None = None,
    ) -> None:
        """Initialize the zone editor scene.

        Args:
            parent: Optional parent QGraphicsView.

        """
        super().__init__(parent=parent)

        self._mode: EditorMode = EditorMode.DRAW
        self._active_polygon: ZonePolygonItem | None = None
        self._background_item: QGraphicsPixmapItem | None = None
        self._instruction_item: QGraphicsTextItem | None = None
        self._polygons: list[ZonePolygonItem] = []

        # Scene defaults
        self.setBackgroundBrush(QBrush(QColor(45, 45, 45)))
        self.setSceneRect(0, 0, 800, 600)

        self._update_instructions()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> EditorMode:
        """Current editor mode."""
        return self._mode

    @mode.setter
    def mode(self, value: EditorMode) -> None:
        """Change the editor mode."""
        if value != self._mode:
            self._mode = value
            self._update_cursor()
            self._update_instructions()
            self.mode_changed.emit(value)
            logger.debug("ZoneScene mode -> {}", value.name)

    @property
    def active_polygon(self) -> ZonePolygonItem | None:
        """The polygon currently being drawn / edited, or ``None``."""
        return self._active_polygon

    @property
    def polygons(self) -> list[ZonePolygonItem]:
        """All completed polygons in the scene."""
        return list(self._polygons)

    # ------------------------------------------------------------------
    # Background image
    # ------------------------------------------------------------------

    def set_background_image(self, pixmap: QPixmap) -> None:
        """Set or replace the background camera frame image.

        Args:
            pixmap: The image to display as the background.

        """
        if self._background_item is not None:
            self.removeItem(self._background_item)

        self._background_item = QGraphicsPixmapItem(pixmap)
        self._background_item.setZValue(-100)
        self.addItem(self._background_item)
        self.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        logger.debug(
            "ZoneScene background set: {}x{}", pixmap.width(), pixmap.height()
        )

    def clear_background(self) -> None:
        """Remove the background image."""
        if self._background_item is not None:
            self.removeItem(self._background_item)
            self._background_item = None

    # ------------------------------------------------------------------
    # Polygon management
    # ------------------------------------------------------------------

    def start_new_polygon(self) -> None:
        """Begin a new polygon drawing session."""
        if self._active_polygon is not None:
            self._cancel_active_polygon()

        self.mode = EditorMode.DRAW
        self._active_polygon = ZonePolygonItem(
            completed=False,
            on_changed=self._on_polygon_changed,
        )
        self.addItem(self._active_polygon)
        logger.debug("ZoneScene: started new polygon")

    def finish_polygon(self) -> list[QPointF] | None:
        """Close the active polygon and add it to the completed list.

        Returns:
            The list of points if the polygon was completed, or ``None``
            if there is no active polygon or fewer than 3 points.

        """
        if self._active_polygon is None:
            return None

        points = self._active_polygon.points
        if len(points) < 3:
            self.status_message.emit(
                f"Polygon requires at least 3 points (has {len(points)})."
            )
            return None

        self._active_polygon.completed = True
        self._polygons.append(self._active_polygon)
        self._active_polygon = None
        self.polygon_completed.emit(points)
        logger.info("ZoneScene: polygon completed with {} points", len(points))
        self._update_instructions()
        return points

    def cancel_polygon(self) -> None:
        """Cancel drawing and remove the in-progress polygon."""
        self._cancel_active_polygon()
        self.status_message.emit("Polygon drawing cancelled.")
        self._update_instructions()

    def clear_all_polygons(self) -> None:
        """Remove all completed polygons from the scene."""
        for poly in self._polygons:
            self.removeItem(poly)
        self._polygons.clear()
        self._cancel_active_polygon()
        logger.debug("ZoneScene: all polygons cleared")

    def load_polygons(self, polygon_points: list[list[QPointF]]) -> None:
        """Load existing polygons into the scene.

        Args:
            polygon_points: A list of point lists, one per polygon.

        """
        self.clear_all_polygons()
        for pts in polygon_points:
            poly = ZonePolygonItem(
                points=pts,
                completed=True,
                on_changed=self._on_polygon_changed,
            )
            self.addItem(poly)
            self._polygons.append(poly)
        logger.debug("ZoneScene: loaded {} polygon(s)", len(polygon_points))

    # ------------------------------------------------------------------
    # Mouse handling
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press based on current mode."""
        scene_pos = event.scenePos()

        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode == EditorMode.DRAW:
                self._handle_draw_click(scene_pos)
                return
            elif self._mode == EditorMode.EDIT:
                # Check if we clicked near an existing vertex
                item = self._item_at(scene_pos)
                if isinstance(item, VertexHandle):
                    # Let the handle handle it
                    super().mousePressEvent(event)
                    return
                # Check if we clicked on an edge to insert a point
                if self._active_polygon is not None:
                    result = self._active_polygon.nearest_edge_point(scene_pos)
                    if result is not None:
                        idx, proj = result
                        self._active_polygon.insert_point_at(idx, proj)
                        self.status_message.emit(
                            f"Vertex inserted at edge (total: {self._active_polygon.vertex_count})"
                        )
                        return
                super().mousePressEvent(event)
                return

        elif event.button() == Qt.MouseButton.RightButton:
            self._handle_right_click(scene_pos)
            return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double-click to close polygon or insert vertex."""
        scene_pos = event.scenePos()

        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode == EditorMode.DRAW and self._active_polygon is not None:
                points = self._active_polygon.points
                if len(points) >= 3:
                    # Check if double-click is near the first vertex
                    first = points[0]
                    dx = scene_pos.x() - first.x()
                    dy = scene_pos.y() - first.y()
                    if dx * dx + dy * dy < 400:  # 20px tolerance
                        self.finish_polygon()
                        return

                # Otherwise, add a vertex
                self._handle_draw_click(scene_pos)
                return

            if self._mode == EditorMode.EDIT and self._active_polygon is not None:
                # Insert a vertex at the double-click position
                result = self._active_polygon.nearest_edge_point(scene_pos)
                if result is not None:
                    idx, proj = result
                    self._active_polygon.insert_point_at(idx, proj)
                    self.status_message.emit(
                        f"Vertex inserted (total: {self._active_polygon.vertex_count})"
                    )
                    return

        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_draw_click(self, scene_pos: QPointF) -> None:
        """Left-click in draw mode — add a vertex."""
        if self._active_polygon is None:
            self.start_new_polygon()

        if self._active_polygon is not None:
            self._active_polygon.add_point(scene_pos)
            count = self._active_polygon.vertex_count
            msg = f"Vertex {count} added at ({scene_pos.x():.0f}, {scene_pos.y():.0f})"
            if count >= 3:
                msg += " — double-click first vertex or press Finish to close."
            self.status_message.emit(msg)

    def _handle_right_click(self, scene_pos: QPointF) -> None:
        """Right-click — remove the nearest vertex."""
        polygon = self._active_polygon
        if polygon is None or polygon.vertex_count < 3:
            return

        idx = polygon.contains_point(scene_pos)
        if idx is not None:
            try:
                polygon.remove_point(idx)
                self.status_message.emit(
                    f"Vertex {idx} removed (remaining: {polygon.vertex_count})"
                )
            except ValueError as exc:
                self.status_message.emit(str(exc))

    def _cancel_active_polygon(self) -> None:
        """Remove the in-progress polygon from the scene."""
        if self._active_polygon is not None:
            self.removeItem(self._active_polygon)
            self._active_polygon = None

    def _on_polygon_changed(self, points: list[QPointF]) -> None:
        """Callback when the active polygon's vertices change."""
        self.polygon_updated.emit(points)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _item_at(self, scene_pos: QPointF) -> QGraphicsItem | None:
        """Return the topmost interactive item at *scene_pos*."""
        items = self.items(scene_pos, Qt.ItemSelectionMode.ContainsItemShape)
        for item in items:
            if item.isEnabled() and item.isVisible():
                return item
        return None

    def _update_cursor(self) -> None:
        """Set the cursor based on current mode."""
        views = self.views()
        if not views:
            return
        view = views[0]
        if self._mode == EditorMode.DRAW:
            view.setCursor(Qt.CursorShape.CrossCursor)
        elif self._mode == EditorMode.EDIT:
            view.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            view.setCursor(Qt.CursorShape.OpenHandCursor)

    def _update_instructions(self) -> None:
        """Show context-sensitive instructions."""
        if self._instruction_item is not None:
            self.removeItem(self._instruction_item)
            self._instruction_item = None

        if self._mode == EditorMode.DRAW:
            text = (
                "Click to add vertices  |  Right-click vertex to remove  |  "
                "Double-click first vertex or press Finish to close"
            )
        elif self._mode == EditorMode.EDIT:
            text = (
                "Drag vertices  |  Right-click to remove  |  "
                "Double-click edge to insert vertex"
            )
        else:
            text = ""

        if text:
            self._instruction_item = self.addText(text, _INSTRUCTION_FONT)
            self._instruction_item.setDefaultTextColor(_INSTRUCTION_COLOR)
            self._instruction_item.setZValue(50)
            # Position at the top-center
            br = self._instruction_item.boundingRect()
            self._instruction_item.setPos(
                (self.sceneRect().width() - br.width()) / 2,
                8,
            )

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw a grid in the background for orientation."""
        super().drawBackground(painter, rect)

        painter.setPen(QPen(_GRID_COLOR, 1.0))
        left = int(rect.left() // _GRID_SPACING) * _GRID_SPACING
        top = int(rect.top() // _GRID_SPACING) * _GRID_SPACING

        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += _GRID_SPACING

        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += _GRID_SPACING
