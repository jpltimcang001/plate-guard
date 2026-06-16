"""Event recording orchestration.

Captures snapshots and video clips when a licence plate is detected.
Pre-detection frames come from a ring buffer; post-detection frames
are collected by waiting the configured duration.
"""

from __future__ import annotations

import time as time_module
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np
from loguru import logger

from src.detection.frame_queue import Frame
from src.domain.events.plate_detected import PlateDetected
from src.recorder.frame_buffer import FrameRingBuffer
from src.recorder.media_writer import MediaWriter


@dataclass
class RecordingResult:
    """Outcome of a single event recording.

    Attributes:
        camera_id: The source camera.
        snapshot_path: Absolute path to the saved JPEG snapshot, or
            empty string if saving failed.
        video_path: Absolute path to the saved MP4 clip, or empty
            string if saving failed or no frames were available.
        pre_frame_count: Number of pre-detection frames used in
            the clip.
        post_frame_count: Number of post-detection frames used in
            the clip.
        total_frames: Total frames in the video clip.
        duration_seconds: Total duration of the video clip in seconds.
        plate_text: Recognised plate text (may be empty).
        detection_confidence: YOLO detection confidence.
    """

    camera_id: int = 0
    snapshot_path: str = ""
    video_path: str = ""
    pre_frame_count: int = 0
    post_frame_count: int = 0
    total_frames: int = 0
    duration_seconds: float = 0.0
    plate_text: str = ""
    detection_confidence: float = 0.0

    @property
    def has_snapshot(self) -> bool:
        """Whether a snapshot was successfully saved."""
        return bool(self.snapshot_path)

    @property
    def has_video(self) -> bool:
        """Whether a video clip was successfully saved."""
        return bool(self.video_path)

    def __repr__(self) -> str:
        return (
            f"<RecordingResult camera={self.camera_id} "
            f"snapshot={self.has_snapshot} "
            f"video={self.has_video} "
            f"plate={self.plate_text!r}>"
        )


class EventRecorder:
    """Records snapshots and video clips when a plate is detected.

    The recorder maintains a ring buffer per camera that is fed by
    the capture pipeline.  When ``record()`` is called:

    1. The current frame is saved as a JPEG snapshot immediately.
    2. Pre-detection frames (up to ``pre_seconds`` seconds before the
       event) are retrieved from the ring buffer.
    3. The method waits ``post_seconds`` seconds to collect
       post-detection frames from the buffer.
    4. All frames are assembled into an MP4 video clip and saved.

    Usage::

        recorder = EventRecorder(storage_dir="./media")

        # Feed every frame from the capture pipeline:
        recorder.on_frame(camera_id, frame)

        # When a plate is detected:
        result = recorder.record(event, current_frame, ocr_text="ABC123")
        print(result.snapshot_path, result.video_path)
    """

    def __init__(
        self,
        storage_dir: str | Path = "media",
        pre_seconds: float = 3.0,
        post_seconds: float = 3.0,
        fps: float = 30.0,
        max_buffer_seconds: float = 10.0,
    ) -> None:
        """Initialise the event recorder.

        Args:
            storage_dir: Root directory for media files.  ``snapshots/``
                and ``clips/`` subdirectories are created inside it.
            pre_seconds: How many seconds of video *before* the
                detection to include in the clip.
            post_seconds: How many seconds of video *after* the
                detection to include in the clip.
            fps: Assumed frame rate for buffer sizing and video
                encoding.
            max_buffer_seconds: How many seconds of frames the ring
                buffer retains (must be greater than
                ``pre_seconds + post_seconds``).

        """
        if max_buffer_seconds <= pre_seconds + post_seconds:
            raise ValueError(
                f"max_buffer_seconds ({max_buffer_seconds}) must be greater than "
                f"pre_seconds + post_seconds ({pre_seconds + post_seconds})",
            )

        self._pre_seconds = pre_seconds
        self._post_seconds = post_seconds
        self._fps = fps
        self._media_writer = MediaWriter(base_dir=storage_dir)

        # Ring buffers indexed by camera_id
        self._buffers: Dict[int, FrameRingBuffer] = {}

        # Cameras currently in the post-detection wait window
        self._recording_cameras: Set[int] = set()

        buffer_size = int(max_buffer_seconds * fps)
        self._buffer_size = buffer_size

        logger.info(
            "EventRecorder initialised (pre={}s, post={}s, fps={}, "
            "buffer={} frames)",
            self._pre_seconds,
            self._post_seconds,
            self._fps,
            buffer_size,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def pre_seconds(self) -> float:
        """Pre-detection window in seconds."""
        return self._pre_seconds

    @property
    def post_seconds(self) -> float:
        """Post-detection window in seconds."""
        return self._post_seconds

    @property
    def fps(self) -> float:
        """Assumed frame rate."""
        return self._fps

    @property
    def media_writer(self) -> MediaWriter:
        """The underlying media writer."""
        return self._media_writer

    @property
    def active_camera_count(self) -> int:
        """Number of cameras with registered buffers."""
        return len(self._buffers)

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def register_camera(self, camera_id: int) -> None:
        """Ensure a ring buffer exists for the given camera.

        Safe to call multiple times for the same camera.

        Args:
            camera_id: The camera ID.

        """
        if camera_id not in self._buffers:
            self._buffers[camera_id] = FrameRingBuffer(maxlen=self._buffer_size)
            logger.debug(
                "EventRecorder registered camera_id={} (buffer={})",
                camera_id,
                self._buffer_size,
            )

    def unregister_camera(self, camera_id: int) -> None:
        """Remove the ring buffer for a camera.

        Args:
            camera_id: The camera ID.

        """
        self._buffers.pop(camera_id, None)
        self._recording_cameras.discard(camera_id)
        logger.debug("EventRecorder unregistered camera_id={}", camera_id)

    # ------------------------------------------------------------------
    # Frame feed
    # ------------------------------------------------------------------

    def on_frame(self, camera_id: int, frame: Frame) -> None:
        """Feed a frame into the recorder.

        Must be called for every frame from the capture pipeline so
        that the ring buffer stays up to date.  This method also
        checks whether the camera is in a post-detection recording
        window.

        Args:
            camera_id: The source camera.
            frame: The captured frame.

        """
        self.register_camera(camera_id)
        self._get_buffer(camera_id).push(frame)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        event: PlateDetected,
        current_frame: np.ndarray,
        ocr_text: str = "",
    ) -> RecordingResult:
        """Record a detection event.

        Saves a snapshot immediately, then collects pre- and
        post-detection frames to assemble a video clip.

        Args:
            event: The ``PlateDetected`` domain event.
            current_frame: The BGR frame at the moment of detection.
            ocr_text: Optional recognised plate text.

        Returns:
            A ``RecordingResult`` with paths to the saved media files.

        """
        camera_id = event.camera_id
        event_ts = event.timestamp.timestamp()
        plate_text = ocr_text or ""

        # --- Snapshot ---
        snapshot_path = ""
        try:
            snapshot_path = self._media_writer.save_snapshot(
                frame=current_frame,
                camera_id=camera_id,
                timestamp=event_ts,
                plate_text=plate_text,
            )
        except (ValueError, OSError) as exc:
            logger.error(
                "Failed to save snapshot for camera_id={}: {}",
                camera_id,
                exc,
            )

        # --- Pre-detection frames ---
        buffer = self._get_buffer(camera_id)
        pre_frames_raw = buffer.get_frames_before(event_ts, seconds=self._pre_seconds)
        pre_frames = [f.data for f in pre_frames_raw]

        logger.debug(
            "Collected {} pre-detection frames for camera_id={}",
            len(pre_frames),
            camera_id,
        )

        # --- Post-detection frames ---
        self._recording_cameras.add(camera_id)

        try:
            self._sleep(self._post_seconds)
        finally:
            self._recording_cameras.discard(camera_id)

        post_frames_raw = buffer.get_frames_between(
            event_ts,
            event_ts + self._post_seconds,
        )
        post_frames = [f.data for f in post_frames_raw]

        logger.debug(
            "Collected {} post-detection frames for camera_id={}",
            len(post_frames),
            camera_id,
        )

        # --- Assemble clip ---
        all_frames: List[np.ndarray] = list(pre_frames)
        all_frames.append(current_frame)
        all_frames.extend(post_frames)

        video_path = ""
        if len(all_frames) >= 2:
            try:
                video_path = self._media_writer.save_clip(
                    frames=all_frames,
                    camera_id=camera_id,
                    timestamp=event_ts,
                    plate_text=plate_text,
                    fps=self._fps,
                )
            except (ValueError, OSError) as exc:
                logger.error(
                    "Failed to save video clip for camera_id={}: {}",
                    camera_id,
                    exc,
                )
        else:
            logger.warning(
                "Not enough frames to create video clip for camera_id={} "
                "(got {} frames)",
                camera_id,
                len(all_frames),
            )

        duration = len(all_frames) / self._fps if all_frames else 0.0

        return RecordingResult(
            camera_id=camera_id,
            snapshot_path=snapshot_path,
            video_path=video_path,
            pre_frame_count=len(pre_frames),
            post_frame_count=len(post_frames),
            total_frames=len(all_frames),
            duration_seconds=round(duration, 2),
            plate_text=plate_text,
            detection_confidence=event.confidence,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_buffer(self, camera_id: int) -> FrameRingBuffer:
        """Return the ring buffer for a camera, creating it if needed.

        Args:
            camera_id: The camera ID.

        Returns:
            The ``FrameRingBuffer`` for this camera.

        """
        if camera_id not in self._buffers:
            self._buffers[camera_id] = FrameRingBuffer(maxlen=self._buffer_size)
        return self._buffers[camera_id]

    @staticmethod
    def _sleep(delay: float) -> None:
        """Blocking sleep (overridable in tests).

        Args:
            delay: Seconds to sleep.

        """
        time_module.sleep(delay)

    def __repr__(self) -> str:
        return (
            f"<EventRecorder cameras={len(self._buffers)} "
            f"pre={self._pre_seconds}s post={self._post_seconds}s>"
        )
