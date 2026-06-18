"""Unit tests for Dashboard UI widgets.

Requires a ``QApplication`` instance (provided by the ``qapp`` fixture).
"""

from __future__ import annotations

from typing import Any, Generator, Optional
from unittest.mock import MagicMock, create_autospec, patch

import numpy as np
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from src.application.dto.dashboard_dto import (
    CameraStatusDTO,
    DashboardData,
    DetectionSummaryDTO,
)
from src.ui.dashboard.camera_status_widget import CameraCard, CameraStatusPanel
from src.ui.dashboard.dashboard_widget import DashboardWidget
from src.ui.dashboard.detection_summary_widget import DetectionSummaryWidget
from src.ui.dashboard.live_preview_widget import LivePreviewWidget

# ======================================================================
# QApplication fixture (session-scoped)
# ======================================================================


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, Any, None]:
    """Provide a single QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ======================================================================
# Helpers
# ======================================================================

_FRAME_H = 240
_FRAME_W = 320


def _make_bgr_frame(value: int = 128) -> np.ndarray:
    """Create a solid-colour BGR test frame."""
    return np.full((_FRAME_H, _FRAME_W, 3), value, dtype=np.uint8)


def _make_camera_status(
    camera_id: int = 1,
    name: str = "Test Cam",
    enabled: bool = True,
    status: str = "online",
    count: int = 0,
) -> CameraStatusDTO:
    """Create a CameraStatusDTO for test fixtures."""
    return CameraStatusDTO(
        id=camera_id,
        name=name,
        camera_type="rtsp",
        enabled=enabled,
        status=status,
        detection_count_today=count,
    )


def _make_detection_summary(
    detection_id: int = 1,
    camera_id: int = 1,
    camera_name: str = "Test Cam",
    plate: str = "ABC123",
) -> DetectionSummaryDTO:
    """Create a DetectionSummaryDTO for test fixtures."""
    from datetime import datetime

    return DetectionSummaryDTO(
        id=detection_id,
        camera_id=camera_id,
        camera_name=camera_name,
        plate_text=plate,
        confidence=0.95,
        snapshot_path=f"/snap_{detection_id}.jpg",
        video_path=f"/clip_{detection_id}.mp4",
        webhook_status="success",
        detected_at=datetime.now(),
    )


# ======================================================================
# LivePreviewWidget tests
# ======================================================================


class TestLivePreviewWidget:
    """LivePreviewWidget behaviour."""

    def test_create_default(self, qapp: QApplication) -> None:
        """Widget can be created with default parameters."""
        widget = LivePreviewWidget()
        assert widget.camera_name == ""
        assert widget.frame_count == 0
        assert widget.is_running is False

    def test_set_frame_source_none_shows_placeholder(self, qapp: QApplication) -> None:
        """Setting source to None shows placeholder text."""
        widget = LivePreviewWidget()
        widget.set_frame_source(None)
        assert "No frame source" in widget._image_label.text()

    def test_set_frame_source_with_callback(self, qapp: QApplication) -> None:
        """Setting a valid callback does not raise."""
        widget = LivePreviewWidget()
        widget.set_frame_source(lambda: _make_bgr_frame(), camera_name="Gate 1")
        assert widget.camera_name == "Gate 1"

    def test_start_and_stop(self, qapp: QApplication) -> None:
        """Start and stop toggle the timer."""
        widget = LivePreviewWidget()
        widget.set_frame_source(lambda: _make_bgr_frame())
        assert widget.is_running is False

        widget.start()
        assert widget.is_running is True

        widget.stop()
        assert widget.is_running is False

    def test_start_without_source_does_not_crash(self, qapp: QApplication) -> None:
        """Starting without a frame source logs a warning but does not crash."""
        widget = LivePreviewWidget()
        widget.start()  # should not raise
        assert widget.is_running is False

    def test_stop_when_not_running_does_not_crash(self, qapp: QApplication) -> None:
        """Stopping when already stopped is a no-op."""
        widget = LivePreviewWidget()
        widget.stop()  # should not raise

    def test_poll_displays_frame(self, qapp: QApplication) -> None:
        """Polling a valid frame source updates the pixmap."""
        widget = LivePreviewWidget(poll_interval_ms=50)
        widget.set_frame_source(lambda: _make_bgr_frame(), camera_name="Cam 1")

        # Manually trigger a poll
        with patch.object(widget, "_display_frame") as mock_display:
            widget._poll_frame()
            mock_display.assert_called_once()

    def test_poll_with_none_frame_does_not_crash(self, qapp: QApplication) -> None:
        """Poll returning None is handled gracefully."""
        widget = LivePreviewWidget()
        widget.set_frame_source(lambda: None)
        widget._poll_frame()  # should not raise

    def test_poll_with_empty_frame_does_not_crash(self, qapp: QApplication) -> None:
        """Poll returning empty array is handled gracefully."""
        widget = LivePreviewWidget()
        widget.set_frame_source(lambda: np.array([]))
        widget._poll_frame()  # should not raise

    def test_poll_increments_frame_count(self, qapp: QApplication) -> None:
        """Each successful poll increments frame_count."""
        widget = LivePreviewWidget()
        widget.set_frame_source(lambda: _make_bgr_frame())
        assert widget.frame_count == 0
        widget._poll_frame()
        assert widget.frame_count == 1
        widget._poll_frame()
        assert widget.frame_count == 2

    def test_set_poll_interval_clamps_minimum(self, qapp: QApplication) -> None:
        """Poll interval cannot be set below 16 ms."""
        widget = LivePreviewWidget(poll_interval_ms=100)
        widget.set_poll_interval(5)
        assert widget._poll_interval == 16

    def test_repr(self, qapp: QApplication) -> None:
        """__repr__ contains key state."""
        widget = LivePreviewWidget()
        rep = repr(widget)
        assert "LivePreviewWidget" in rep


# ======================================================================
# CameraCard tests
# ======================================================================


class TestCameraCard:
    """CameraCard widget behaviour."""

    def test_create(
        self,
        qapp: QApplication,
    ) -> None:
        """Card can be created from CameraStatusDTO."""
        status = _make_camera_status(camera_id=1, name="Gate 1")
        card = CameraCard(status)
        assert card.camera_id == 1
        assert card._name_label.text() == "Gate 1"

    def test_update_status(self, qapp: QApplication) -> None:
        """Updating the status refreshes displayed text."""
        status = _make_camera_status(
            camera_id=1, name="Gate 1", enabled=True, status="online", count=5,
        )
        card = CameraCard(status)
        assert card._count_label.text() == "5"

        new_status = _make_camera_status(
            camera_id=1, name="Gate 1", enabled=False, status="disabled", count=10,
        )
        card.update_status(new_status)
        assert card._count_label.text() == "10"

    def test_clicked_signal(self, qapp: QApplication) -> None:
        """Clicking the card emits clicked with camera_id."""
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent

        status = _make_camera_status(camera_id=42)
        card = CameraCard(status)

        received: list[int] = []
        card.clicked.connect(received.append)

        local = QPointF(10.0, 10.0)
        global_ = QPointF(10.0, 10.0)
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            local,
            global_,
            global_,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mousePressEvent(event)

        assert received == [42]

    def test_repr(self, qapp: QApplication) -> None:
        """__repr__ contains camera ID and name."""
        status = _make_camera_status(camera_id=7, name="Lobby")
        card = CameraCard(status)
        rep = repr(card)
        assert "7" in rep
        assert "Lobby" in rep


# ======================================================================
# CameraStatusPanel tests
# ======================================================================


class TestCameraStatusPanel:
    """CameraStatusPanel widget behaviour."""

    def test_create_empty(self, qapp: QApplication) -> None:
        """Empty panel shows placeholder."""
        panel = CameraStatusPanel()
        assert len(panel._cards) == 0
        # isVisible() requires the widget to be shown; check hidden state instead
        assert not panel._empty_label.isHidden()

    def test_update_cameras_adds_cards(self, qapp: QApplication) -> None:
        """Adding cameras creates CameraCard widgets."""
        panel = CameraStatusPanel()
        cameras = [
            _make_camera_status(camera_id=1, name="Gate 1"),
            _make_camera_status(camera_id=2, name="Gate 2"),
        ]
        panel.update_cameras(cameras)

        assert len(panel._cards) == 2
        assert 1 in panel._cards
        assert 2 in panel._cards
        assert panel._empty_label.isVisible() is False

    def test_update_cameras_removes_stale_cards(self, qapp: QApplication) -> None:
        """Removing a camera from the list removes its card."""
        panel = CameraStatusPanel()
        panel.update_cameras([
            _make_camera_status(camera_id=1, name="A"),
            _make_camera_status(camera_id=2, name="B"),
        ])
        assert len(panel._cards) == 2

        panel.update_cameras([
            _make_camera_status(camera_id=1, name="A"),
        ])
        assert len(panel._cards) == 1
        assert 2 not in panel._cards

    def test_update_cameras_updates_existing_cards(self, qapp: QApplication) -> None:
        """Updating an existing camera refreshes its card in place."""
        panel = CameraStatusPanel()
        panel.update_cameras([
            _make_camera_status(camera_id=1, name="Gate", count=5),
        ])
        assert panel._cards[1]._count_label.text() == "5"

        panel.update_cameras([
            _make_camera_status(camera_id=1, name="Gate", count=10),
        ])
        assert len(panel._cards) == 1  # same card, not duplicated
        assert panel._cards[1]._count_label.text() == "10"

    def test_clear_removes_all_cards(self, qapp: QApplication) -> None:
        """Clearing removes all cards."""
        panel = CameraStatusPanel()
        panel.update_cameras([
            _make_camera_status(camera_id=1),
            _make_camera_status(camera_id=2),
        ])
        panel.clear()
        assert len(panel._cards) == 0
        assert not panel._empty_label.isHidden()

    def test_camera_selected_signal(self, qapp: QApplication) -> None:
        """Clicking a card emits camera_selected via the panel."""
        panel = CameraStatusPanel()
        panel.update_cameras([
            _make_camera_status(camera_id=99, name="Test"),
        ])

        received: list[int] = []
        panel.camera_selected.connect(received.append)

        # Simulate card click with a proper mouse event
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent

        local = QPointF(5.0, 5.0)
        global_ = QPointF(5.0, 5.0)
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            local,
            global_,
            global_,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        panel._cards[99].mousePressEvent(event)

        assert received == [99]


# ======================================================================
# DetectionSummaryWidget tests
# ======================================================================


class TestDetectionSummaryWidget:
    """DetectionSummaryWidget behaviour."""

    def test_create_default(self, qapp: QApplication) -> None:
        """Default widget shows 0 total and no rows."""
        widget = DetectionSummaryWidget()
        assert widget._total_label.text() == "0"

    def test_update_counts(self, qapp: QApplication) -> None:
        """Updating counts changes the total label."""
        widget = DetectionSummaryWidget()
        widget.update_counts(total=42, by_camera={1: 20, 2: 22})
        assert widget._total_label.text() == "42"

    def test_update_counts_without_breakdown(self, qapp: QApplication) -> None:
        """Updating counts without by_camera clears breakdown."""
        widget = DetectionSummaryWidget()
        widget.update_counts(total=10)
        assert widget._total_label.text() == "10"
        assert widget._breakdown_label.text() == ""

    def test_update_recent_populates_table(self, qapp: QApplication) -> None:
        """Adding recent detections populates table rows."""
        widget = DetectionSummaryWidget()
        detections = [
            _make_detection_summary(detection_id=1, plate="ABC123"),
            _make_detection_summary(detection_id=2, plate="XYZ789"),
        ]
        widget.update_recent(detections)

        assert widget._table.rowCount() == 2
        assert widget._table.item(0, 2).text() == "ABC123"
        assert widget._table.item(1, 2).text() == "XYZ789"

    def test_update_recent_empty_shows_placeholder(self, qapp: QApplication) -> None:
        """Empty detections shows 'No detections yet' placeholder."""
        widget = DetectionSummaryWidget()
        widget.update_recent([])

        assert widget._table.rowCount() >= 1
        # The placeholder spans all columns
        placeholder = widget._table.item(0, 0)
        assert placeholder is not None
        assert "No detections yet" in placeholder.text()

    def test_clear_resets_counts_and_table(self, qapp: QApplication) -> None:
        """Clearing resets everything."""
        widget = DetectionSummaryWidget()
        widget.update_counts(total=42)
        widget.update_recent([_make_detection_summary()])

        widget.clear()
        assert widget._total_label.text() == "0"
        assert widget._breakdown_label.text() == ""
        # Table should show placeholder
        assert widget._table.rowCount() >= 1
        placeholder = widget._table.item(0, 0)
        assert placeholder is not None
        assert "No detections yet" in placeholder.text()


# ======================================================================
# DashboardWidget tests
# ======================================================================


class TestDashboardWidget:
    """DashboardWidget integration behaviour."""

    @pytest.fixture
    def mock_dashboard_service(self) -> MagicMock:
        """Create a mock DashboardService."""
        svc = MagicMock()
        svc.refresh.return_value = DashboardData(
            cameras=[],
            total_detections_today=0,
            detection_count_by_camera={},
            recent_detections=[],
            cameras_online=0,
            cameras_offline=0,
            cameras_disabled=0,
            refreshed_at=None,
        )
        return svc

    def test_create_default(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """DashboardWidget can be created and starts with 'Ready'."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        assert widget._status_label.text() == "● Ready"
        assert widget._refresh_timer.isActive() is False

    def test_start_refresh_triggers_immediate_refresh(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """start_refresh calls refresh() immediately and starts timer."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget.start_refresh()

        mock_dashboard_service.refresh.assert_called_once()
        assert widget._refresh_timer.isActive() is True

    def test_stop_refresh_stops_timer(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """stop_refresh stops the periodic timer."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget.start_refresh()
        assert widget._refresh_timer.isActive() is True

        widget.stop_refresh()
        assert widget._refresh_timer.isActive() is False

    def test_refresh_now_triggers_immediate_refresh(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """refresh_now calls refresh() even when timer is not active."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget.refresh_now()

        mock_dashboard_service.refresh.assert_called_once()

    def test_refresh_updates_header_badges(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """Refresh updates online/offline badge counts."""
        mock_dashboard_service.refresh.return_value = DashboardData(
            cameras=[_make_camera_status(camera_id=1, status="online")],
            total_detections_today=5,
            detection_count_by_camera={1: 5},
            recent_detections=[],
            cameras_online=1,
            cameras_offline=0,
            cameras_disabled=0,
            refreshed_at=None,
        )

        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget._on_refresh()

        assert "1 online" in widget._online_badge.text()
        assert "0 offline" in widget._offline_badge.text()

    def test_refresh_updates_status_bar(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """Refresh updates the bottom status bar with stats."""
        mock_dashboard_service.refresh.return_value = DashboardData(
            cameras=[_make_camera_status(camera_id=1)],
            total_detections_today=10,
            detection_count_by_camera={1: 10},
            recent_detections=[],
            cameras_online=1,
            cameras_offline=0,
            cameras_disabled=0,
            refreshed_at=None,
        )

        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget._on_refresh()

        assert "10 detections" in widget._status_label.text()

    def test_set_frame_source_stores_callback(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """set_frame_source stores the callback for later use."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)

        def dummy_source() -> np.ndarray:
            return _make_bgr_frame()

        widget.set_frame_source(camera_id=1, source=dummy_source, camera_name="Cam 1")
        assert 1 in widget._frame_sources
        assert widget._frame_sources[1] is dummy_source

    def test_select_camera_updates_preview(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """Selecting a camera connects the preview to its frame source."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)

        def dummy_source() -> np.ndarray:
            return _make_bgr_frame()

        widget.set_frame_source(camera_id=2, source=dummy_source, camera_name="Cam 2")
        widget.select_camera(2)

        # Preview should have the source connected
        assert widget._preview_widget._frame_source is dummy_source

    def test_select_camera_with_no_source_stops_preview(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """Selecting a camera without a frame source stops preview."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget.select_camera(99)  # no source

        assert widget._preview_widget._frame_source is None

    def test_cleanup_stops_timers(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """cleanup stops all timers."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget.start_refresh()
        widget.cleanup()

        assert widget._refresh_timer.isActive() is False
        assert widget._preview_widget.is_running is False

    def test_refresh_handles_service_error(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """If the service raises an exception, the dashboard shows an error."""
        mock_dashboard_service.refresh.side_effect = RuntimeError("DB down")

        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        widget._on_refresh()  # should not raise

        assert "failed" in widget._status_label.text().lower()

    def test_repr(
        self,
        qapp: QApplication,
        mock_dashboard_service: MagicMock,
    ) -> None:
        """__repr__ contains key state."""
        widget = DashboardWidget(dashboard_service=mock_dashboard_service)
        rep = repr(widget)
        assert "DashboardWidget" in rep
