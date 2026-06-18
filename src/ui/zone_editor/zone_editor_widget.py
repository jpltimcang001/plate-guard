"""Main widget for the interactive Detection Zone Editor.

Provides a toolbar, graphics view, and status bar for drawing and
editing polygon detection zones on a camera frame background.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt, Slot
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QGraphicsView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)

from loguru import logger

from src.application.dto.zone_dto import CreateZoneRequest, ZoneDTO
from src.services.zone_service import ZoneService
from src.ui.zone_editor.zone_scene import EditorMode, ZoneGraphicsScene

if TYPE_CHECKING:
    from src.repositories.zone_repository import ZoneRepository


class ZoneEditorWidget(QWidget):
    """Interactive polygon zone editor widget.

    Provides a complete zone editing workflow:
    - Draw new polygons on a camera frame background
    - Edit existing polygons (drag, insert, delete vertices)
    - Save zones to the database
    - Load and display existing zones
    """

    def __init__(
        self,
        zone_service: ZoneService | None = None,
        camera_id: int | None = None,
        background_pixmap: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the zone editor.

        Args:
            zone_service: Optional ``ZoneService`` for persistence.
                If ``None``, save/load operations are disabled.
            camera_id: The camera ID to associate zones with.
            background_pixmap: Optional camera frame to use as background.
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)

        self._zone_service = zone_service
        self._camera_id = camera_id
        self._original_zones: list[ZoneDTO] = []
        self._current_zones: list[ZoneDTO] = []
        self._has_unsaved_changes: bool = False

        # Build UI
        self._setup_ui()
        self._connect_signals()

        # Set background if provided
        if background_pixmap is not None:
            self._scene.set_background_image(background_pixmap)

        # Load existing zones for this camera
        if self._zone_service is not None and self._camera_id is not None:
            self._load_existing_zones()

        self._update_title()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def camera_id(self) -> int | None:
        """The camera ID currently associated with this editor."""
        return self._camera_id

    @camera_id.setter
    def camera_id(self, value: int | None) -> None:
        """Set the camera ID and reload zones."""
        self._camera_id = value
        if value is not None and self._zone_service is not None:
            self._load_existing_zones()
        else:
            self._scene.clear_all_polygons()
        self._update_title()

    @property
    def zone_service(self) -> ZoneService | None:
        return self._zone_service

    @zone_service.setter
    def zone_service(self, value: ZoneService | None) -> None:
        """Set or replace the zone service."""
        self._zone_service = value

    @property
    def has_unsaved_changes(self) -> bool:
        """Whether there are unsaved polygon modifications."""
        return self._has_unsaved_changes

    def set_background_image(self, pixmap: QPixmap) -> None:
        """Set the background camera frame image.

        Args:
            pixmap: The image to display.

        """
        self._scene.set_background_image(pixmap)

    def get_zone_points(self) -> list[list[QPointF]]:
        """Return all completed polygon point lists.

        Returns:
            A list of point lists, one per polygon.

        """
        return [poly.points for poly in self._scene.polygons]

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the widget layout."""
        self.setWindowTitle("Detection Zone Editor")
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Toolbar ---
        toolbar = QToolBar("Zone Editor Tools")
        toolbar.setMovable(False)
        toolbar.setIconSize(self._default_icon_size())

        self._btn_draw = QAction("✏️ Draw", self)
        self._btn_draw.setToolTip("Draw a new polygon (click to add vertices)")
        self._btn_draw.setCheckable(True)
        self._btn_draw.setChecked(True)
        toolbar.addAction(self._btn_draw)

        self._btn_edit = QAction("✋ Edit", self)
        self._btn_edit.setToolTip("Edit vertices (drag, right-click to delete)")
        self._btn_edit.setCheckable(True)
        toolbar.addAction(self._btn_edit)

        toolbar.addSeparator()

        self._btn_new = QAction("➕ New", self)
        self._btn_new.setToolTip("Start a new polygon")
        toolbar.addAction(self._btn_new)

        self._btn_finish = QAction("✅ Finish", self)
        self._btn_finish.setToolTip("Close the polygon (minimum 3 points)")
        toolbar.addAction(self._btn_finish)

        self._btn_cancel = QAction("❌ Cancel", self)
        self._btn_cancel.setToolTip("Cancel the current polygon")
        toolbar.addAction(self._btn_cancel)

        toolbar.addSeparator()

        self._btn_save = QAction("💾 Save", self)
        self._btn_save.setToolTip("Save all zones to the database")
        toolbar.addAction(self._btn_save)

        self._btn_clear_all = QAction("🗑️ Clear All", self)
        self._btn_clear_all.setToolTip("Remove all polygons from the scene")
        toolbar.addAction(self._btn_clear_all)

        layout.addWidget(toolbar)

        # --- Zone name input ---
        name_layout = QHBoxLayout()
        name_layout.setContentsMargins(8, 8, 8, 4)
        name_label = QLabel("Zone name:")
        name_label.setToolTip("A descriptive name for this detection zone")
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Enter zone name (e.g. Entrance)")
        self._name_input.setToolTip("Give the zone a meaningful name for easy identification")
        self._name_input.setMaximumWidth(300)
        name_layout.addWidget(name_label)
        name_layout.addWidget(self._name_input)
        name_layout.addStretch()
        layout.addLayout(name_layout)

        # --- Graphics view ---
        self._scene = ZoneGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(self._view.RenderHint.Antialiasing)
        self._view.setRenderHint(self._view.RenderHint.SmoothPixmapTransform)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._view, 1)

        # --- Status bar ---
        self._status_bar = QStatusBar()
        self._status_label = QLabel("Ready — click to start drawing")
        self._status_bar.addWidget(self._status_label, 1)
        self._coord_label = QLabel("")
        self._coord_label.setMinimumWidth(200)
        self._coord_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._status_bar.addPermanentWidget(self._coord_label)
        layout.addWidget(self._status_bar)

    def _connect_signals(self) -> None:
        """Connect all UI signals."""
        # Toolbar actions
        self._btn_draw.triggered.connect(self._on_draw_mode)
        self._btn_edit.triggered.connect(self._on_edit_mode)
        self._btn_new.triggered.connect(self._on_new_polygon)
        self._btn_finish.triggered.connect(self._on_finish_polygon)
        self._btn_cancel.triggered.connect(self._on_cancel_polygon)
        self._btn_save.triggered.connect(self._on_save)
        self._btn_clear_all.triggered.connect(self._on_clear_all)

        # Scene signals
        self._scene.status_message.connect(self._status_label.setText)
        self._scene.polygon_completed.connect(self._on_scene_polygon_completed)
        self._scene.polygon_updated.connect(self._on_scene_polygon_updated)
        self._scene.mode_changed.connect(self._on_scene_mode_changed)

        # Track mouse movement for coordinate display
        self._view.viewport().installEventFilter(self)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_draw_mode(self) -> None:
        """Switch to draw mode."""
        self._scene.mode = EditorMode.DRAW
        self._btn_draw.setChecked(True)
        self._btn_edit.setChecked(False)

    @Slot()
    def _on_edit_mode(self) -> None:
        """Switch to edit mode."""
        self._scene.mode = EditorMode.EDIT
        self._btn_draw.setChecked(False)
        self._btn_edit.setChecked(True)

    @Slot()
    def _on_new_polygon(self) -> None:
        """Start drawing a new polygon."""
        self._scene.start_new_polygon()
        self._on_draw_mode()

    @Slot()
    def _on_finish_polygon(self) -> None:
        """Finish/clsoe the current polygon."""
        result = self._scene.finish_polygon()
        if result is not None:
            self._mark_unsaved()
            self._status_label.setText(
                f"Polygon closed with {len(result)} vertices"
            )

    @Slot()
    def _on_cancel_polygon(self) -> None:
        """Cancel the current polygon drawing."""
        self._scene.cancel_polygon()

    @Slot()
    def _on_clear_all(self) -> None:
        """Remove all polygons from the scene."""
        reply = QMessageBox.question(
            self,
            "Clear All Polygons",
            "Remove all polygons from the scene? "
            "Unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._scene.clear_all_polygons()
            self._mark_unsaved()
            self._status_label.setText("All polygons cleared.")

    @Slot()
    def _on_save(self) -> None:
        """Save all polygons to the database."""
        if self._zone_service is None:
            QMessageBox.warning(
                self,
                "No Database",
                "Zone persistence is not available (no ZoneService configured).",
            )
            return

        if self._camera_id is None:
            QMessageBox.warning(
                self,
                "No Camera Selected",
                "Cannot save zones: no camera is selected.",
            )
            return

        # Validate zone name
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                "Name Required",
                "Enter a zone name before saving.",
            )
            return

        # Collect all polygon points
        all_points = self.get_zone_points()
        if not all_points:
            QMessageBox.warning(
                self,
                "No Polygons",
                "Draw at least one polygon before saving.",
            )
            return

        try:
            # Save each polygon as a separate zone
            saved_zones: list[ZoneDTO] = []
            for i, pts in enumerate(all_points):
                zone_name = f"{name} {i + 1}" if len(all_points) > 1 else name
                point_tuples = [(p.x(), p.y()) for p in pts]

                dto = self._zone_service.create_zone(
                    name=zone_name,
                    camera_id=self._camera_id,
                    points=point_tuples,
                )
                saved_zones.append(dto)

            self._original_zones = list(saved_zones)
            self._has_unsaved_changes = False
            self._update_title()
            self._status_label.setText(
                f"Saved {len(saved_zones)} zone(s) successfully."
            )
            logger.info(
                "Saved {} zone(s) for camera_id={}", len(saved_zones), self._camera_id
            )

        except (ValueError, LookupError) as exc:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save zones:\n{exc}",
            )
            logger.opt(exception=True).error("Zone save failed")

    @Slot()
    def _on_scene_polygon_completed(self, points: list[QPointF]) -> None:
        """Handle polygon completion event from the scene."""
        self._mark_unsaved()
        self._status_label.setText(
            f"Polygon completed with {len(points)} vertices"
        )

    @Slot()
    def _on_scene_polygon_updated(self, points: list[QPointF]) -> None:
        """Handle polygon update event from the scene."""
        self._mark_unsaved()

    @Slot()
    def _on_scene_mode_changed(self, mode: EditorMode) -> None:
        """Sync toolbar buttons with scene mode."""
        self._btn_draw.setChecked(mode == EditorMode.DRAW)
        self._btn_edit.setChecked(mode == EditorMode.EDIT)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_existing_zones(self) -> None:
        """Load existing zones from the database into the scene."""
        if self._zone_service is None or self._camera_id is None:
            return

        try:
            dtos = self._zone_service.get_zones_by_camera(self._camera_id)
            self._original_zones = list(dtos)
            self._current_zones = list(dtos)

            polygon_points: list[list[QPointF]] = []
            for dto in dtos:
                pts = [QPointF(x, y) for x, y in dto.points]
                polygon_points.append(pts)

            self._scene.load_polygons(polygon_points)
            self._has_unsaved_changes = False
            self._update_title()

            if dtos:
                self._name_input.setText(dtos[0].name)
                self._status_label.setText(
                    f"Loaded {len(dtos)} existing zone(s)."
                )
            else:
                self._status_label.setText("No existing zones for this camera.")

            logger.debug(
                "Loaded {} zone(s) for camera_id={}",
                len(dtos),
                self._camera_id,
            )

        except Exception as exc:
            logger.opt(exception=True).error(
                "Failed to load zones for camera_id={}", self._camera_id
            )
            self._status_label.setText(f"Error loading zones: {exc}")

    def _mark_unsaved(self) -> None:
        """Mark the editor as having unsaved changes."""
        self._has_unsaved_changes = True
        self._update_title()

    def _update_title(self) -> None:
        """Update the window title to reflect unsaved state."""
        prefix = "* " if self._has_unsaved_changes else ""
        cam = f"Camera {self._camera_id}" if self._camera_id else "No Camera"
        self.setWindowTitle(f"{prefix}Detection Zone Editor — {cam}")

    @staticmethod
    def _default_icon_size():
        """Default icon size for the toolbar."""
        from PySide6.QtCore import QSize

        return QSize(20, 20)

    def eventFilter(self, obj: object, event: object) -> bool:
        """Track mouse movement for coordinate display."""
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent

        if obj == self._view.viewport() and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseMove:
                scene_pos = self._view.mapToScene(event.position().toPoint())
                self._coord_label.setText(
                    f"X: {scene_pos.x():.0f}  Y: {scene_pos.y():.0f}"
                )

        return super().eventFilter(obj, event)
