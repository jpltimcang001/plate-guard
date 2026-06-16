"""Modal dialog wrapping the ZoneEditorWidget for standalone use.

Provides a complete zone editing workflow with Save and Cancel buttons,
suitable for opening from a camera management dialog or settings panel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from loguru import logger

from src.services.zone_service import ZoneService
from src.ui.zone_editor.zone_editor_widget import ZoneEditorWidget

if TYPE_CHECKING:
    from src.repositories.zone_repository import ZoneRepository


class ZoneDialog(QDialog):
    """Modal dialog for editing detection zones.

    Usage::

        dialog = ZoneDialog(
            zone_service=zone_service,
            camera_id=1,
            background_pixmap=frame_pixmap,
            parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            # Zones have been saved
            pass
    """

    def __init__(
        self,
        zone_service: ZoneService | None = None,
        camera_id: int | None = None,
        background_pixmap: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the zone dialog.

        Args:
            zone_service: Optional ``ZoneService`` for persistence.
            camera_id: The camera ID to associate zones with.
            background_pixmap: Optional camera frame background.
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)

        self._editor = ZoneEditorWidget(
            zone_service=zone_service,
            camera_id=camera_id,
            background_pixmap=background_pixmap,
            parent=self,
        )

        self._setup_ui()
        self._connect_signals()

        self.resize(1024, 720)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def editor(self) -> ZoneEditorWidget:
        """The embedded zone editor widget."""
        return self._editor

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Editor widget (takes up most of the space)
        layout.addWidget(self._editor, 1)

        # Button box
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.setCenterButtons(True)
        layout.addWidget(self._button_box)

    def _connect_signals(self) -> None:
        """Connect dialog buttons."""
        self._button_box.accepted.connect(self._on_save)
        self._button_box.rejected.connect(self.reject)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Save zones and accept the dialog."""
        if not self._editor.has_unsaved_changes:
            self.accept()
            return

        # Use the editor's save mechanism
        if self._editor._zone_service is not None:
            self._editor._on_save()

            # Check if there are still unsaved changes (save might have failed)
            if self._editor.has_unsaved_changes:
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "Some zones could not be saved. Exit anyway?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.accept()
                return

        self.accept()

    def closeEvent(self, event) -> None:
        """Prompt the user if there are unsaved changes."""
        if self._editor.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved zone changes. Discard them?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.No:
                self._editor._on_save()
                if self._editor.has_unsaved_changes:
                    event.ignore()  # type: ignore[attr-defined]
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()  # type: ignore[attr-defined]
                return

        super().closeEvent(event)  # type: ignore[misc]
