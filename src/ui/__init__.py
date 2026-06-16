"""PySide6 user interface components for Plate Guard."""

from src.ui.dashboard import (
    CameraStatusPanel,
    DashboardWidget,
    DetectionSummaryWidget,
    LivePreviewWidget,
)
from src.ui.zone_editor import (
    EditorMode,
    VertexHandle,
    ZoneDialog,
    ZoneEditorWidget,
    ZoneGraphicsScene,
    ZonePolygonItem,
)

__all__ = [
    "CameraStatusPanel",
    "DashboardWidget",
    "DetectionSummaryWidget",
    "EditorMode",
    "LivePreviewWidget",
    "VertexHandle",
    "ZoneDialog",
    "ZoneEditorWidget",
    "ZoneGraphicsScene",
    "ZonePolygonItem",
]
