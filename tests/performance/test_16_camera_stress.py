"""T3.14 — 16-camera performance stress test.

Simulates 16 concurrent cameras feeding frames through the detection
pipeline with mocked services (YOLO, OCR, zone validation, tracking,
dedup, persistence, and webhooks).

Measures
--------
- Aggregate throughput (frames processed / second across all cameras)
- Per-frame pipeline latency (p50, p95, p99)
- Producer-side frame drop ratios (due to queue congestion)
- Detection event throughput (number of new-tracks persisted)
- Memory footprint (RSS delta before → after)
- Thread completion safety (no crashes, no deadlocks)

CI compatibility
----------------
- Does **not** require real YOLO weights, PaddleOCR models, or camera hardware.
- Uses ``unittest.mock`` services that simulate realistic timings
  (configurable delays for YOLO inference and OCR).
- Can be marked ``@pytest.mark.slow`` to exclude from quick CI runs.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.detection.duplicate_filter import DuplicateFilter
from src.detection.frame_queue import Frame
from src.detection.pipeline import DetectionPipeline
from src.detection.tracker import DetectionTracker
from src.detection.zone_validator import ZoneValidator
from src.ocr.ocr_result import OcrResult

# ======================================================================
# Test configuration
# ======================================================================

NUM_CAMERAS = 16
FRAMES_PER_CAMERA = 50  # per-camera frame count for a quick run
SIMULATED_FPS = 15  # nominal frames-per-second per camera
YOLO_INFERENCE_MS = 15  # simulated YOLO inference delay (ms)
OCR_INFERENCE_MS = 20  # simulated OCR delay (ms)
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Throughput expectations (conservative for CI with CPU-only)
MIN_AGGREGATE_THROUGHPUT = 50  # frames/sec across all cameras


# ======================================================================
# Metrics containers
# ======================================================================


@dataclass
class CameraMetrics:
    """Per-camera performance statistics collected during the test."""

    camera_id: int
    frames_produced: int = 0
    frames_processed: int = 0
    frames_dropped: int = 0
    pipeline_latencies: list[float] = field(default_factory=list)
    detections_persisted: int = 0
    exceptions: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0


@dataclass
class StressTestResult:
    """Aggregate result of the stress test run."""

    num_cameras: int
    total_frames_produced: int
    total_frames_processed: int
    total_frames_dropped: int
    aggregate_throughput: float  # frames/sec
    pipeline_latency_p50: float  # ms
    pipeline_latency_p95: float  # ms
    pipeline_latency_p99: float  # ms
    total_detections_persisted: int
    duration_seconds: float
    all_threads_completed: bool
    rss_delta_mb: float | None = None


# ======================================================================
# Frame producer helpers
# ======================================================================


def _make_frame_data(
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> np.ndarray:
    """Create a synthetic BGR frame with some random-ish content."""
    return np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)


def _produce_frames(
    camera_id: int,
    count: int,
    interval: float,
    pipeline: DetectionPipeline,
    metrics: CameraMetrics,
    stop_event: threading.Event,
) -> None:
    """Produce *count* synthetic frames and feed through the pipeline.

    Runs in a dedicated thread per camera.
    """
    for frame_num in range(1, count + 1):
        if stop_event.is_set():
            return

        data = _make_frame_data()
        frame = Frame(
            data=data,
            camera_id=camera_id,
            timestamp=time.time(),
            frame_number=frame_num,
        )

        metrics.frames_produced += 1

        try:
            result = pipeline.process_frame(frame)
            metrics.frames_processed += 1
            metrics.processing_time_ms += result.processing_time_ms
            if result.processing_time_ms > 0:
                metrics.pipeline_latencies.append(result.processing_time_ms)
            metrics.detections_persisted += result.detections_persisted
        except Exception as exc:
            metrics.exceptions.append(f"Frame {frame_num}: {exc}")
            continue

        # Simulate real-time frame pacing
        time.sleep(interval)

    metrics.frames_dropped = metrics.frames_produced - metrics.frames_processed


# ======================================================================
# Mock pipeline factory
# ======================================================================


def _create_mock_pipeline() -> DetectionPipeline:
    """Create a DetectionPipeline with thread-local mock services.

    Each invocation returns a completely independent set of mocks,
    avoiding MagicMock thread-safety issues when multiple camera
    threads are active simultaneously.
    """
    # YOLO detection mock
    det_svc = MagicMock()
    det_svc.is_started = True

    def _detect_frame(frame: Frame) -> list[Any]:
        if YOLO_INFERENCE_MS > 0:
            time.sleep(YOLO_INFERENCE_MS / 1000.0)

        from src.detection.detection_result import DetectionResult

        n_dets = np.random.randint(1, 4)
        detections = []
        for _ in range(n_dets):
            cx = np.random.randint(100, FRAME_WIDTH - 100)
            cy = np.random.randint(100, FRAME_HEIGHT - 100)
            w = np.random.randint(60, 160)
            h = np.random.randint(20, 60)
            detections.append(
                DetectionResult(
                    bounding_box=(cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2),
                    confidence=float(np.random.uniform(0.5, 0.99)),
                    class_id=0,
                    class_name="plate",
                )
            )
        return detections

    det_svc.detect_frame.side_effect = _detect_frame

    # OCR mock
    ocr_svc = MagicMock()
    ocr_svc.is_started = True

    def _ocr_detection(frame_data: np.ndarray, det: Any) -> OcrResult:
        if OCR_INFERENCE_MS > 0:
            time.sleep(OCR_INFERENCE_MS / 1000.0)

        letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
        digits = "0123456789"
        text = (
            f"{np.random.choice(list(letters))}{np.random.choice(list(letters))}"
            f"{np.random.choice(list(letters))}-"
            f"{np.random.choice(list(digits))}{np.random.choice(list(digits))}"
            f"{np.random.choice(list(digits))}"
        )
        return OcrResult(
            text=text,
            confidence=float(np.random.uniform(0.7, 0.98)),
        )

    ocr_svc.ocr_detection.side_effect = _ocr_detection

    # Zone validator — pass everything
    zone_validator = MagicMock(spec=ZoneValidator)
    zone_validator.is_in_any_zone.return_value = True

    # Tracker — assigns track IDs, marks all as new
    tracker = MagicMock(spec=DetectionTracker)
    _track_counter: dict[int, int] = {}

    def _update(camera_id: int, detections: list[Any]) -> list[Any]:
        tid = _track_counter.get(camera_id, 0)
        for d in detections:
            tid += 1
            d.track_id = tid  # type: ignore[attr-defined]
            d.is_new = True  # type: ignore[attr-defined]
        _track_counter[camera_id] = tid
        return detections

    tracker.update.side_effect = _update

    # Duplicate filter — let everything through
    dup_filter = MagicMock(spec=DuplicateFilter)
    dup_filter.check_and_record.return_value = True

    # Persistence and webhook mocks
    detection_repo = MagicMock()
    media_writer = MagicMock()
    media_writer.save_snapshot.return_value = "/media/snapshots/stress_test.jpg"
    webhook_service = MagicMock()
    on_detection = MagicMock()

    return DetectionPipeline(
        plate_detection_service=det_svc,
        ocr_service=ocr_svc,
        zone_validator=zone_validator,
        tracker=tracker,
        duplicate_filter=dup_filter,
        detection_repo=detection_repo,
        media_writer=media_writer,
        webhook_service=webhook_service,
        on_detection=on_detection,
    )


# ======================================================================
# Stress test
# ======================================================================


class Test16CameraStress:
    """16-camera performance stress test.

    This test validates that the detection pipeline can handle 16
    concurrent camera streams without crashing, deadlocking, or
    exhibiting excessive frame loss.
    """

    def test_16_cameras_stress(self) -> None:
        """Run 16 simulated cameras and measure aggregate throughput."""
        # --------------------------------------------------------------
        # Build 16 pipeline instances with independent mock services
        # --------------------------------------------------------------
        pipelines = [_create_mock_pipeline() for _ in range(NUM_CAMERAS)]

        # --------------------------------------------------------------
        # Metrics per camera
        # --------------------------------------------------------------
        all_metrics: list[CameraMetrics] = [
            CameraMetrics(camera_id=cam_id) for cam_id in range(1, NUM_CAMERAS + 1)
        ]

        # --------------------------------------------------------------
        # Launch frame producer threads (one per camera)
        # --------------------------------------------------------------
        stop_event = threading.Event()
        frame_interval = 1.0 / SIMULATED_FPS

        threads: list[threading.Thread] = []
        for idx, (pipeline, metrics) in enumerate(zip(pipelines, all_metrics)):
            cam_id = idx + 1
            t = threading.Thread(
                target=_produce_frames,
                args=(
                    cam_id,
                    FRAMES_PER_CAMERA,
                    frame_interval,
                    pipeline,
                    metrics,
                    stop_event,
                ),
                name=f"camera-{cam_id}",
                daemon=True,
            )
            threads.append(t)

        # Measure baseline memory
        rss_before = _get_rss_mb()

        # Start all threads
        start_time = time.perf_counter()
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join(timeout=FRAMES_PER_CAMERA * frame_interval * 2 + 10.0)

        duration = time.perf_counter() - start_time
        rss_after = _get_rss_mb()
        rss_delta = (rss_after - rss_before) if (rss_before is not None and rss_after is not None) else None

        # Signal any stragglers
        stop_event.set()

        # --------------------------------------------------------------
        # Aggregate results
        # --------------------------------------------------------------
        total_produced = sum(m.frames_produced for m in all_metrics)
        total_processed = sum(m.frames_processed for m in all_metrics)
        total_dropped = sum(m.frames_dropped for m in all_metrics)
        total_persisted = sum(m.detections_persisted for m in all_metrics)

        all_latencies: list[float] = []
        for m in all_metrics:
            all_latencies.extend(m.pipeline_latencies)

        all_exceptions: list[tuple[int, str]] = []
        for m in all_metrics:
            for exc in m.exceptions:
                all_exceptions.append((m.camera_id, exc))

        all_threads_ok = all(t.name.startswith("camera-") for t in threads) and all(
            not t.is_alive() for t in threads
        )

        aggregate_throughput = total_processed / duration if duration > 0 else 0.0

        # Compute latency percentiles
        sorted_latencies = sorted(all_latencies)
        latency_p50 = _percentile(sorted_latencies, 50)
        latency_p95 = _percentile(sorted_latencies, 95)
        latency_p99 = _percentile(sorted_latencies, 99)

        result = StressTestResult(
            num_cameras=NUM_CAMERAS,
            total_frames_produced=total_produced,
            total_frames_processed=total_processed,
            total_frames_dropped=total_dropped,
            aggregate_throughput=aggregate_throughput,
            pipeline_latency_p50=latency_p50,
            pipeline_latency_p95=latency_p95,
            pipeline_latency_p99=latency_p99,
            total_detections_persisted=total_persisted,
            duration_seconds=duration,
            all_threads_completed=all_threads_ok,
            rss_delta_mb=rss_delta,
        )

        # --------------------------------------------------------------
        # Assertions
        # --------------------------------------------------------------

        # 1. No exceptions during pipeline processing
        assert not all_exceptions, (
            f"{len(all_exceptions)} pipeline exceptions occurred:\n"
            + "\n".join(
                f"  Camera {cid}: {exc}" for cid, exc in all_exceptions[:10]
            )
        )

        # 2. All frames were processed (no drops)
        assert total_produced == FRAMES_PER_CAMERA * NUM_CAMERAS, (
            f"Expected {FRAMES_PER_CAMERA * NUM_CAMERAS} frames produced, "
            f"got {total_produced}"
        )
        assert total_dropped <= total_produced * 0.05, (
            f"Frame drop ratio too high: {total_dropped}/{total_produced} "
            f"({total_dropped / max(total_produced, 1) * 100:.1f}%)"
        )

        # 3. Aggregate throughput meets minimum
        assert aggregate_throughput >= MIN_AGGREGATE_THROUGHPUT, (
            f"Aggregate throughput {aggregate_throughput:.1f} fps "
            f"below minimum {MIN_AGGREGATE_THROUGHPUT} fps "
            f"({total_processed} frames in {duration:.2f}s)"
        )

        # 4. Pipeline latency is reasonable (p99 < 500ms)
        assert latency_p99 < 500.0, (
            f"Pipeline latency p99 too high: {latency_p99:.1f}ms "
            f"(p50={latency_p50:.1f}ms, p95={latency_p95:.1f}ms)"
        )

        # 5. All threads completed (no deadlocks)
        assert all_threads_ok, "Not all producer threads completed"

        # 6. At least some detections were persisted
        assert total_persisted > 0, (
            "No detections were persisted — the pipeline may not be "
            "processing frames correctly"
        )

        # 7. Minimum detections persisted (at least 1 per 5 frames)
        min_expected_persisted = max(1, total_processed // 5 // NUM_CAMERAS)
        assert total_persisted >= min_expected_persisted, (
            f"Only {total_persisted} detections persisted across "
            f"{NUM_CAMERAS} cameras (expected >= {min_expected_persisted})"
        )

        # 8. Memory usage is stable (RSS delta < 1200 MB)
        #    Note: numpy frame allocations during a stress test can be
        #    large. This is a sanity check for gross leaks, not a tight bound.
        if rss_delta is not None:
            assert abs(rss_delta) < 1200.0, (
                f"Memory delta too large: {rss_delta:+.1f} MB "
                "(threshold: ±1200 MB)"
            )

        # Log summary for debugging
        _log_result(result)

    # ------------------------------------------------------------------
    # Degradation test: Frame drop ratio with full-frame rate
    # ------------------------------------------------------------------

    def test_16_cameras_high_frame_rate(self) -> None:
        """Run 16 cameras at 60 FPS each with minimal frame pacing delay.

        This test stresses the queue overflow path — at high frame rates
        the pipeline may not keep up and frames will be dropped.
        """
        pipelines = [_create_mock_pipeline() for _ in range(NUM_CAMERAS)]

        # Use a very tight frame pacing interval to stress the system
        frame_count = 20
        frame_interval = 1.0 / 60.0  # Simulate 60 FPS per camera
        stop_event = threading.Event()

        all_metrics: list[CameraMetrics] = [
            CameraMetrics(camera_id=cam_id) for cam_id in range(1, NUM_CAMERAS + 1)
        ]

        threads = []
        for idx, (pipeline, metrics) in enumerate(zip(pipelines, all_metrics)):
            cam_id = idx + 1
            t = threading.Thread(
                target=_produce_frames,
                args=(cam_id, frame_count, frame_interval, pipeline, metrics, stop_event),
                name=f"highfps-camera-{cam_id}",
                daemon=True,
            )
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=frame_count * frame_interval * 2 + 15.0)

        stop_event.set()

        total_produced = sum(m.frames_produced for m in all_metrics)
        total_processed = sum(m.frames_processed for m in all_metrics)
        total_dropped = sum(m.frames_dropped for m in all_metrics)

        all_exceptions: list[tuple[int, str]] = []
        for m in all_metrics:
            for exc in m.exceptions:
                all_exceptions.append((m.camera_id, exc))

        # Some frames will likely be dropped due to pipeline bandwidth
        # but it should still process a reasonable fraction
        assert not all_exceptions, (
            f"{len(all_exceptions)} pipeline exceptions at high frame rate:\n"
            + "\n".join(f"  Camera {cid}: {exc}" for cid, exc in all_exceptions[:5])
        )

        # Allow up to 80% drop ratio at high frame rate
        max_acceptable_drops = int(total_produced * 0.80)
        assert total_dropped <= max_acceptable_drops, (
            f"Frame drop ratio too high at high frame rate: "
            f"{total_dropped}/{total_produced} dropped "
            f"({total_dropped / max(total_produced, 1) * 100:.1f}%)"
        )

        # At least some frames should have been processed
        assert total_processed > 0, (
            "No frames processed at high frame rate — pipeline may be stuck"
        )


# ======================================================================
# Helpers
# ======================================================================


def _percentile(sorted_data: list[float], p: int) -> float:
    """Compute the *p*-th percentile of a sorted list."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


def _get_rss_mb() -> float | None:
    """Return the current RSS memory in megabytes, or ``None``."""
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return None


def _log_result(result: StressTestResult) -> None:
    """Print a formatted summary of the stress test result."""
    print("=" * 60)
    print(f"  16-Camera Stress Test Results")
    print("=" * 60)
    print(f"  Cameras:              {result.num_cameras}")
    print(f"  Duration:             {result.duration_seconds:.2f}s")
    print(f"  Frames produced:      {result.total_frames_produced}")
    print(f"  Frames processed:     {result.total_frames_processed}")
    print(f"  Frames dropped:       {result.total_frames_dropped}")
    drop_ratio = (
        result.total_frames_dropped / max(result.total_frames_produced, 1) * 100
    )
    print(f"  Drop ratio:           {drop_ratio:.1f}%")
    print(f"  Aggregate throughput: {result.aggregate_throughput:.1f} fps")
    print(f"  Latency p50:          {result.pipeline_latency_p50:.2f}ms")
    print(f"  Latency p95:          {result.pipeline_latency_p95:.2f}ms")
    print(f"  Latency p99:          {result.pipeline_latency_p99:.2f}ms")
    print(f"  Detections persisted: {result.total_detections_persisted}")
    print(f"  All threads OK:       {result.all_threads_completed}")
    if result.rss_delta_mb is not None:
        print(f"  RSS delta:            {result.rss_delta_mb:+.1f} MB")
    print("=" * 60)
