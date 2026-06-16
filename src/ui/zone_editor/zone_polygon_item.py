"""Polygon overlay item with editable vertices.

``ZonePolygonItem`` manages a closed polygon shape and its associated
``VertexHandle`` instances. When vertices are added, removed, or moved,
the polygon path is automatically rebuilt.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QMenu,
)

from loguru import logger

from src.ui.zone_editor.vertex_handle import VertexHandle

_STROKE_COLOR: QColor = QColor(0, 120, 215)
_STROKE_WIDTH: float = 2.5
_FILL_COLOR: QColor = QColor(0, 120, 215, 40)
_COMPLETION_COLOR: QColor = QColor(76, 175, 80, 60)
_MIN_VERTICES: int = 3


class ZonePolygonItem(QGraphicsPathItem):
    """Interactive polygon with draggable vertex handles.

    The polygon is drawn as a closed shape with a semi-transparent
    fill.  Vertex handles are managed as child items and are updated
    whenever the underlying point list changes.
    """

    def __init__(
        self,
        points: list[QPointF] | None = None,
        *,
        completed: bool = False,
        on_changed: Callable[[list[QPointF]], None] | None = None,
        parent: QGraphicsPathItem | None = None,
    ) -> None:
        """Initialize the polygon item.

        Args:
            points: Initial vertex positions.  Empty list means no points.
            completed: ``True`` if the polygon is closed and should
                render with a filled background.
            on_changed: Optional callback when vertices change.
            parent: Optional parent QGraphicsItem.

        """
        super().__init__(parent=parent)

        self._points: list[QPointF] = list(points) if points else []
        self._completed: bool = completed
        self._on_changed = on_changed
        self._handles: list[VertexHandle] = []
        self._suppress_rebuild: bool = False

        # Appearance — outline always visible; fill only when closed
        self.setPen(QPen(_STROKE_COLOR, _STROKE_WIDTH, Qt.PenStyle.SolidLine))
        self._update_fill()
        self.setZValue(5)

        # Build initial handles
        self._rebuild_handles()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def points(self) -> list[QPointF]:
        """Return a copy of the current vertex positions."""
        return list(self._points)

    @points.setter
    def points(self, value: list[QPointF]) -> None:
        """Replace all vertices and rebuild handles."""
        self._points = list(value)
        self._rebuild_handles()
        self._update_path()
        self._notify_changed()

    @property
    def completed(self) -> bool:
        """Whether the polygon is closed (3+ vertices)."""
        return self._completed

    @completed.setter
    def completed(self, value: bool) -> None:
        """Set or clear the completed state."""
        if value != self._completed:
            self._completed = value
            self._update_fill()
            self._update_path()

    @property
    def vertex_count(self) -> int:
        """Number of vertices in the polygon."""
        return len(self._points)

    # ------------------------------------------------------------------
    # Point manipulation
    # ------------------------------------------------------------------

    def add_point(self, scene_pos: QPointF) -> None:
        """Add a vertex at the given scene position.

        Args:
            scene_pos: Position in scene coordinates.

        """
        self._points.append(scene_pos)
        self._add_handle(len(self._points) - 1, scene_pos)
        self._update_path()
        self._notify_changed()
        logger.debug("ZonePolygonItem add_point at ({:.0f}, {:.0f})", scene_pos.x(), scene_pos.y())

    def insert_point_at(self, index: int, scene_pos: QPointF) -> None:
        """Insert a vertex at a specific index.

        Args:
            index: 0-based insertion position.
            scene_pos: Position in scene coordinates.

        Raises:
            IndexError: If *index* is out of range.

        """
        self._points.insert(index, scene_pos)
        self._rebuild_handles()
        self._update_path()
        self._notify_changed()

    def remove_point(self, index: int) -> None:
        """Remove the vertex at *index*.

        Args:
            index: 0-based index of the vertex to remove.

        Raises:
            ValueError: If removing would leave fewer than ``MIN_VERTICES``.

        """
        if len(self._points) <= _MIN_VERTICES:
            raise ValueError(
                f"Cannot remove vertex: polygon requires at least {_MIN_VERTICES} vertices."
            )
        self._points.pop(index)
        self._rebuild_handles()
        self._update_path()
        self._notify_changed()
        logger.debug("ZonePolygonItem remove_point index={}", index)

    def move_point(self, index: int, scene_pos: QPointF) -> None:
        """Move the vertex at *index* to a new scene position.

        Args:
            index: 0-based vertex index.
            scene_pos: New position.

        """
        if 0 <= index < len(self._points):
            self._points[index] = scene_pos
            self._update_path()
            self._notify_changed()

    def clear_points(self) -> None:
        """Remove all vertices and handles."""
        self._points.clear()
        self._remove_all_handles()
        self._update_path()
        self._notify_changed()

    # ------------------------------------------------------------------
    # Geometry query
    # ------------------------------------------------------------------

    def contains_point(self, scene_pos: QPointF, tolerance: float = 8.0) -> int | None:
        """Find the nearest vertex index within *tolerance* of *scene_pos*.

        Args:
            scene_pos: Query position in scene coordinates.
            tolerance: Maximum distance in pixels.

        Returns:
            The index of the nearest vertex, or ``None``.

        """
        best_idx: int | None = None
        best_dist: float = tolerance * tolerance  # squared
        for i, pt in enumerate(self._points):
            dx = pt.x() - scene_pos.x()
            dy = pt.y() - scene_pos.y()
            dist_sq = dx * dx + dy * dy
            if dist_sq < best_dist:
                best_dist = dist_sq
                best_idx = i
        return best_idx

    def nearest_edge_point(self, scene_pos: QPointF) -> tuple[int, QPointF] | None:
        """Find the nearest point on any polygon edge to *scene_pos*.

        Args:
            scene_pos: Query position in scene coordinates.

        Returns:
            A tuple ``(insertion_index, projected_point)`` for the
            nearest edge, or ``None`` if there are fewer than 2 vertices.

        """
        if len(self._points) < 2:
            return None

        best_idx: int = -1
        best_proj: QPointF = QPointF()
        best_dist: float = float("inf")

        # Check each edge (including closing edge if completed)
        n = len(self._points)
        edges = list(range(n - 1))
        if self._completed:
            edges.append(n - 1)  # last -> first

        for i in edges:
            p1 = self._points[i]
            p2 = self._points[(i + 1) % n]

            proj = self._project_point_on_segment(scene_pos, p1, p2)
            dist = (proj.x() - scene_pos.x()) ** 2 + (proj.y() - scene_pos.y()) ** 2
            if dist < best_dist:
                best_dist = dist
                best_idx = i + 1  # Insert AFTER the first vertex of the edge
                best_proj = proj

        if best_dist > 400:  # tolerance of 20px squared
            return None

        return best_idx, best_proj

    # ------------------------------------------------------------------
    # Internal: handle management
    # ------------------------------------------------------------------

    def _rebuild_handles(self) -> None:
        """Recreate all vertex handles from ``self._points``."""
        self._remove_all_handles()
        for i, pt in enumerate(self._points):
            self._add_handle(i, pt)

    def _add_handle(self, index: int, pos: QPointF) -> VertexHandle:
        """Create a single handle and wire its callbacks."""
        handle = VertexHandle(
            index=index,
            pos=pos,
            parent_item=self,
            on_moved=self._on_handle_moved,
            on_dragged=self._on_handle_dragged,
        )
        self._handles.insert(index, handle)
        return handle

    def _remove_all_handles(self) -> None:
        """Delete all vertex handle items."""
        for handle in self._handles:
            scene = self.scene()
            if scene is not None:
                scene.removeItem(handle)
        self._handles.clear()

    def _on_handle_moved(self, index: int, pos: QPointF) -> None:
        """Callback when a handle is released after dragging."""
        self._points[index] = pos
        self._update_path()
        self._notify_changed()

    def _on_handle_dragged(self, index: int, pos: QPointF) -> None:
        """Callback continuously during a drag."""
        self._points[index] = pos
        self._update_path()

    def _notify_changed(self) -> None:
        """Fire the change callback if set."""
        if self._on_changed is not None and not self._suppress_rebuild:
            self._on_changed(self.points)

    # ------------------------------------------------------------------
    # Internal: path & paint
    # ------------------------------------------------------------------

    def _update_path(self) -> None:
        """Rebuild the QPainterPath from current points."""
        path = QPainterPath()
        if not self._points:
            self.setPath(path)
            return

        path.moveTo(self._points[0])
        for pt in self._points[1:]:
            path.lineTo(pt)

        if self._completed and len(self._points) >= 3:
            path.lineTo(self._points[0])  # Close the polygon
            path.closeSubpath()

        self.setPath(path)

    def _update_fill(self) -> None:
        """Update the fill brush based on completion state."""
        if self._completed and len(self._points) >= 3:
            self.setBrush(QBrush(_COMPLETION_COLOR))
        else:
            self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _project_point_on_segment(p: QPointF, a: QPointF, b: QPointF) -> QPointF:
        """Project point *p* onto line segment *ab*.

        Returns the closest point on the segment to *p*.
        """
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        dot = (p.x() - a.x()) * abx + (p.y() - a.y()) * aby
        len_sq = abx * abx + aby * aby

        if len_sq == 0:
            return a

        t = max(0.0, min(1.0, dot / len_sq))
        return QPointF(a.x() + t * abx, a.y() + t * aby)

    def __repr__(self) -> str:
        return (
            f"<ZonePolygonItem vertices={len(self._points)} "
            f"completed={self._completed}>"
        )
