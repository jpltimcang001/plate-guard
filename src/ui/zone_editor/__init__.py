"""Detection Zone Editor UI components.

Provides interactive polygon drawing and editing on a camera frame
background using PySide6's Graphics View Framework.
"""

from src.ui.zone_editor.vertex_handle import VertexHandle
from src.ui.zone_editor.zone_dialog import ZoneDialog
from src.ui.zone_editor.zone_editor_widget import ZoneEditorWidget
from src.ui.zone_editor.zone_polygon_item import ZonePolygonItem
from src.ui.zone_editor.zone_scene import EditorMode, ZoneGraphicsScene

__all__ = [
    "EditorMode",
    "VertexHandle",
    "ZoneDialog",
    "ZoneEditorWidget",
    "ZoneGraphicsScene",
    "ZonePolygonItem",
]
