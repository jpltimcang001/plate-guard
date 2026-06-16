"""Dashboard UI — camera status, live preview, and detection summary.

Components
----------
- ``DashboardWidget`` — Main container that assembles all dashboard panels.
- ``CameraStatusPanel`` — List of camera cards with health indicators.
- ``LivePreviewWidget`` — Displays frames from a selected camera.
- ``DetectionSummaryWidget`` — Detection counts and a recent-detections table.
"""

from src.ui.dashboard.camera_status_widget import CameraStatusPanel
from src.ui.dashboard.dashboard_widget import DashboardWidget
from src.ui.dashboard.detection_summary_widget import DetectionSummaryWidget
from src.ui.dashboard.live_preview_widget import LivePreviewWidget

__all__ = [
    "CameraStatusPanel",
    "DashboardWidget",
    "DetectionSummaryWidget",
    "LivePreviewWidget",
]
