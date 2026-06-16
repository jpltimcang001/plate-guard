"""Event recording — snapshot and video clip capture for detection events.

Components
----------
- ``FrameRingBuffer`` — Thread-safe circular buffer that keeps the
  last N seconds of video frames for each camera.
- ``MediaWriter`` — Writes JPEG snapshots and MP4 video clips to disk.
- ``EventRecorder`` — Orchestrator that captures snapshots immediately
  on detection, collects pre- and post-detection frames from the ring
  buffer, and assembles video clips.
- ``RecordingResult`` — Outcome of a single recording event (file paths,
  frame counts).
"""

from src.recorder.event_recorder import EventRecorder, RecordingResult
from src.recorder.frame_buffer import FrameRingBuffer
from src.recorder.media_writer import MediaWriter

__all__ = [
    "EventRecorder",
    "FrameRingBuffer",
    "MediaWriter",
    "RecordingResult",
]
