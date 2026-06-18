"""Live camera preview widget.

Displays video frames from a camera in real time.  Frames are
obtained via a callable callback that the capture pipeline
invokes on every frame.
"""

from __future__ import annotations

from typing import Callable, Optional

import cv2
import numpy as np
from loguru import logger
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.detection.fps_monitor import FpsMonitor


class LivePreviewWidget(QWidget):
    """Displays a live camera feed with manual capture controls.

    The widget polls a *frame source* at a configurable interval.
    The frame source is a zero-argument callable that returns
    either a BGR numpy array or ``None``.

    Provides two manual capture buttons — Snapshot and Video Clip —
    that emit signals when clicked so the parent can wire them
    to the ``EventRecorder``.

    If no frame source is set, a placeholder message is shown.

    Signals:
        capture_snapshot_requested: Emitted when the user clicks
            "Capture Snapshot", carrying the current camera ID.
        capture_clip_requested: Emitted when the user clicks
            "Record Clip", carrying the current camera ID.

    Usage::

        preview = LivePreviewWidget(parent=self)
        preview.set_frame_source(my_camera.get_latest_frame, camera_name="Gate 1")
        preview.start()
        preview.capture_snapshot_requested.connect(self._on_manual_snapshot)
        preview.capture_clip_requested.connect(self._on_manual_clip)
    """

    capture_snapshot_requested = Signal(int)
    capture_clip_requested = Signal(int)

    DEFAULT_POLL_MS = 33  # ≈30 FPS
    PLACEHOLDER_TEXT = "No camera selected"
    NO_SOURCE_TEXT = "No frame source configured"

    def __init__(
        self,
        parent: QWidget | None = None,
        poll_interval_ms: int = DEFAULT_POLL_MS,
    ) -> None:
        """Initialise the live preview widget.

        Args:
            parent: Optional parent widget.
            poll_interval_ms: Milliseconds between frame polls
                (default 33 ms ≈ 30 FPS).

        """
        super().__init__(parent=parent)

        self._frame_source: Callable[[], Optional[np.ndarray]] | None = None
        self._poll_interval = poll_interval_ms
        self._camera_name: str = ""
        self._frame_count: int = 0
        self._camera_id: int = 0
        self._capturing: bool = False

        # FPS monitor for display
        self._fps_monitor = FpsMonitor(window_seconds=1.0)

        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_frame)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def camera_name(self) -> str:
        """Name of the camera currently being previewed."""
        return self._camera_name

    @property
    def frame_count(self) -> int:
        """Total number of frames displayed since the source was set."""
        return self._frame_count

    @property
    def is_running(self) -> bool:
        """Whether the polling timer is active."""
        return self._timer.isActive()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_frame_source(
        self,
        source: Callable[[], Optional[np.ndarray]] | None,
        camera_name: str = "",
        camera_id: int = 0,
    ) -> None:
        """Set the callback that provides the latest frame.

        Args:
            source: A zero-argument callable that returns a BGR numpy
                array or ``None``.  Pass ``None`` to disconnect.
            camera_name: Optional display name for the camera.
            camera_id: The camera ID (used for capture signals).

        """
        self._frame_source = source
        self._camera_name = camera_name
        self._camera_id = camera_id
        self._frame_count = 0

        has_source = source is not None
        self._snapshot_btn.setEnabled(has_source)
        self._clip_btn.setEnabled(has_source)

        if source is None:
            self._show_placeholder(self.NO_SOURCE_TEXT)
        else:
            self._show_placeholder(f"Waiting for {camera_name or 'camera'}…")

    def start(self) -> None:
        """Begin polling the frame source."""
        if self._frame_source is None:
            logger.warning("LivePreviewWidget.start() called with no frame source")
            return
        if not self._timer.isActive():
            self._timer.start(self._poll_interval)
            logger.debug(
                "LivePreviewWidget started (poll={}ms, camera={!r})",
                self._poll_interval,
                self._camera_name,
            )

    def stop(self) -> None:
        """Stop polling the frame source."""
        if self._timer.isActive():
            self._timer.stop()
            logger.debug("LivePreviewWidget stopped")

    def set_poll_interval(self, interval_ms: int) -> None:
        """Change the frame polling interval.

        Args:
            interval_ms: New interval in milliseconds (≥ 16).

        """
        interval_ms = max(16, interval_ms)
        self._poll_interval = interval_ms
        if self._timer.isActive():
            self._timer.setInterval(interval_ms)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Style constants
    # ------------------------------------------------------------------

    _ACCENT = "#3498db"
    _DARK_BG = "#1a1a1a"
    _DARK_CARD = "#2b2b2b"
    _DARK_BORDER = "#3a3a3a"
    _TEXT_COLOR = "#ecf0f1"

    def _setup_ui(self) -> None:
        """Build the widget layout with capture buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._image_label.setMinimumSize(320, 240)
        self._image_label.setStyleSheet(
            f"QLabel {{ background-color: {self._DARK_BG}; color: #888; "
            "border: 1px solid #333; font-size: 14px; }",
        )

        # Overlay info bar (FPS, resolution) — created before placeholder
        # so _show_placeholder can clear it.
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(4, 0, 4, 0)
        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            f"color: {self._TEXT_COLOR}; font-size: 10px; padding: 0;",
        )
        self._info_label.setToolTip("Current frame rate and resolution")
        info_layout.addWidget(self._info_label)
        info_layout.addStretch()

        self._show_placeholder(self.PLACEHOLDER_TEXT)

        layout.addWidget(self._image_label, stretch=1)
        layout.addLayout(info_layout)

        # Manual capture buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._snapshot_btn = QPushButton("📷 Capture Snapshot", self)
        self._snapshot_btn.setEnabled(False)
        self._snapshot_btn.setToolTip("Capture a still image from the current camera feed")
        self._snapshot_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self._ACCENT}; color: white; "
            f"border: none; padding: 6px 14px; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #2980b9; }}"
            f"QPushButton:disabled {{ background-color: {self._DARK_BORDER}; "
            f"color: {self._TEXT_COLOR}; }}",
        )
        self._snapshot_btn.clicked.connect(self._on_snapshot_clicked)
        btn_layout.addWidget(self._snapshot_btn)

        self._clip_btn = QPushButton("🎬 Record Clip", self)
        self._clip_btn.setEnabled(False)
        self._clip_btn.setToolTip("Record a short video clip (3s pre-roll + 3s post-roll)")
        self._clip_btn.setStyleSheet(
            f"QPushButton {{ background-color: {self._DARK_CARD}; color: white; "
            f"border: 1px solid {self._ACCENT}; padding: 6px 14px; border-radius: 4px; "
            f"font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #3a3a3a; }}"
            f"QPushButton:disabled {{ background-color: {self._DARK_BORDER}; "
            f"color: {self._TEXT_COLOR}; }}",
        )
        self._clip_btn.clicked.connect(self._on_clip_clicked)
        btn_layout.addWidget(self._clip_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def set_capturing(self, capturing: bool) -> None:
        """Show visual feedback when a capture is in progress.

        Args:
            capturing: Whether a capture operation is in progress.

        """
        self._capturing = capturing
        self._snapshot_btn.setEnabled(not capturing and self._frame_source is not None)
        self._clip_btn.setEnabled(not capturing and self._frame_source is not None)
        self._snapshot_btn.setText(
            "⏳ Capturing…" if capturing else "📷 Capture Snapshot",
        )
        self._clip_btn.setText(
            "⏳ Recording…" if capturing else "🎬 Record Clip",
        )

    def _on_snapshot_clicked(self) -> None:
        """Emit the snapshot capture signal."""
        if self._camera_id > 0 and not self._capturing:
            logger.info("Manual snapshot requested for camera_id={}", self._camera_id)
            self.set_capturing(True)
            self.capture_snapshot_requested.emit(self._camera_id)
            # Reset after a short delay to show feedback
            QTimer.singleShot(1500, lambda: self.set_capturing(False))

    def _on_clip_clicked(self) -> None:
        """Emit the clip capture signal."""
        if self._camera_id > 0 and not self._capturing:
            logger.info("Manual clip requested for camera_id={}", self._camera_id)
            self.set_capturing(True)
            self.capture_clip_requested.emit(self._camera_id)
            # Reset after a short delay to show feedback
            QTimer.singleShot(2000, lambda: self.set_capturing(False))

    def _show_placeholder(self, text: str) -> None:
        """Display centred placeholder text.

        The pixmap is cleared so that only the placeholder text
        is visible.
        """
        self._image_label.clear()
        self._image_label.setText(text)
        self._info_label.setText("")

    def _poll_frame(self) -> None:
        """Called by the timer — fetch and display the latest frame."""
        if self._frame_source is None:
            self.stop()
            self._show_placeholder(self.NO_SOURCE_TEXT)
            return

        try:
            frame = self._frame_source()
        except Exception:
            logger.opt(exception=True).warning(
                "LivePreviewWidget frame source raised an exception",
            )
            return

        if frame is None or frame.size == 0:
            return

        self._display_frame(frame)
        self._frame_count += 1
        self._fps_monitor.tick()

    def _display_frame(self, frame: np.ndarray) -> None:
        """Convert a BGR frame to a QPixmap and display it.

        Args:
            frame: BGR image as a numpy array ``(H, W, 3)``.

        """
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        qimage = QImage(
            rgb_frame.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(qimage)

        # Scale to fit the label while maintaining aspect ratio
        scaled = pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

        # Update overlay info
        fps = self._fps_monitor.fps
        camera_info = f"{self._camera_name} · " if self._camera_name else ""
        self._info_label.setText(
            f"{camera_info}{w}×{h} · {fps:.1f} FPS · {self._frame_count} frames",
        )

    def __repr__(self) -> str:
        return (
            f"<LivePreviewWidget camera={self._camera_name!r} "
            f"running={self.is_running} frames={self._frame_count}>"
        )
