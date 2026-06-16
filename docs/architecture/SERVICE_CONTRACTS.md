# Service Contracts

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Version:** 1.0
> **Date:** 2026-06-15

---

## 1. CameraService

**File:** `plate_guard/application/services/camera_service.py`
**Thread-safety:** All public methods are thread-safe (internal lock). UI calls must be dispatched via Qt signals.

### Methods

#### `add_camera`

```python
def add_camera(
    self,
    name: str,
    camera_type: CameraType,
    rtsp_url: str | None = None,
    usb_index: int | None = None,
    confidence_threshold: float = 0.5,
) -> Camera:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | `name` must be non-empty and unique. If `camera_type == RTSP`, `rtsp_url` must be a valid URL. If `camera_type == USB`, `usb_index` must be ≥ 0. `confidence_threshold` must be 0.0–1.0. |
| **Postconditions** | Camera is persisted in the database. Camera is disabled by default (must be enabled separately). |
| **Exceptions** | `ValueError` — invalid input parameters. `DuplicateNameError` — name already exists. `CameraConnectionError` — unable to validate RTSP URL or USB index. |
| **Example** | `camera = camera_service.add_camera("Gate 1", CameraType.RTSP, rtsp_url="rtsp://192.168.1.100:554/stream1")` |

#### `edit_camera`

```python
def edit_camera(
    self,
    camera_id: int,
    name: str | None = None,
    rtsp_url: str | None = None,
    usb_index: int | None = None,
    confidence_threshold: float | None = None,
    enabled: bool | None = None,
) -> Camera:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera with `camera_id` must exist. At least one field must be provided for update. |
| **Postconditions** | Only provided fields are updated. Camera is reconnected if stream URL changed. |
| **Exceptions** | `CameraNotFoundError` — invalid `camera_id`. `ValueError` — invalid field values. `DuplicateNameError` — new name conflicts. |
| **Example** | `camera = camera_service.edit_camera(1, name="Main Gate", confidence_threshold=0.7)` |

#### `delete_camera`

```python
def delete_camera(self, camera_id: int) -> None:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera must exist. |
| **Postconditions** | Camera, its zones, webhooks, and all detections are permanently deleted. Stream is stopped and resources released. |
| **Exceptions** | `CameraNotFoundError` — invalid `camera_id`. |
| **Example** | `camera_service.delete_camera(1)` |

#### `enable_camera`

```python
def enable_camera(self, camera_id: int) -> None:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera must exist and be disabled. |
| **Postconditions** | Camera is enabled and detection stream is started. |
| **Exceptions** | `CameraNotFoundError` — invalid `camera_id`. `CameraConnectionError` — unable to establish stream. |

#### `disable_camera`

```python
def disable_camera(self, camera_id: int) -> None:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera must exist and be enabled. |
| **Postconditions** | Camera is disabled and detection stream is stopped. Any in-progress detection event is completed first. |
| **Exceptions** | `CameraNotFoundError` — invalid `camera_id`. |

#### `get_all_cameras`

```python
def get_all_cameras(self) -> list[Camera]:
```

Returns all cameras ordered by name. Never raises.

#### `get_camera_by_id`

```python
def get_camera_by_id(self, camera_id: int) -> Camera:
```

| Aspect | Detail |
|--------|--------|
| **Exceptions** | `CameraNotFoundError` — invalid `camera_id`. |

#### `enumerate_usb_devices`

```python
def enumerate_usb_devices(self) -> list[UsbDeviceInfo]:
```

Returns a list of detected USB camera devices with index, name, and hardware ID. Never raises.

---

## 2. DetectionService

**File:** `plate_guard/application/services/detection_service.py`
**Thread-safety:** Runs detection on dedicated worker threads per camera. All state transitions are protected by a lock. UI callbacks are dispatched via Qt signals.

### Methods

#### `start_camera`

```python
def start_camera(self, camera_id: int) -> None:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera must exist and be enabled. Camera must not already be running. |
| **Postconditions** | A dedicated worker thread is spawned. Frame capture loop begins. YOLOv8 inference runs on each frame. |
| **Exceptions** | `CameraNotFoundError`. `CameraDisabledError`. `DetectionAlreadyRunningError`. `CameraConnectionError`. |

#### `stop_camera`

```python
def stop_camera(self, camera_id: int) -> None:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera must be running. |
| **Postconditions** | Worker thread is joined. Frame capture and inference stop. Video ring buffer is flushed. |
| **Exceptions** | `CameraNotFoundError`. `DetectionNotRunningError`. |

#### `start_all`

```python
def start_all(self) -> None:
```

Starts detection on all enabled cameras. Skips cameras that are already running. Logs errors per-camera without failing the entire batch.

#### `stop_all`

```python
def stop_all(self) -> None:
```

Stops detection on all running cameras. Called during application shutdown.

#### `pause` / `resume`

```python
def pause(self) -> None:
def resume(self) -> None:
```

Pauses/resumes detection on all running cameras. Paused cameras continue frame capture but skip inference. Useful for temporarily reducing CPU load.

#### `is_running`

```python
def is_running(self, camera_id: int) -> bool:
```

Returns `True` if the camera's detection loop is active.

#### `get_status`

```python
def get_status(self, camera_id: int) -> CameraStatus:
```

Returns the current camera status enum: `ONLINE`, `OFFLINE`, `RECONNECTING`, `DISABLED`, `ERROR`.

### Internal Pipeline Callbacks (registered by the infrastructure layer)

```python
def _on_frame(self, camera_id: int, frame: np.ndarray, timestamp: datetime) -> None:
    """Called by the frame capture thread for each new frame."""

def _on_detection(self, camera_id: int, bounding_box: BoundingBox) -> None:
    """Called when YOLOv8 detects a plate above threshold."""

def _on_recognized(self, camera_id: int, ocr_result: OCRResult) -> None:
    """Called when OCR extracts text from a detected plate."""

def _on_disconnect(self, camera_id: int) -> None:
    """Called when the camera stream is lost."""
```

---

## 3. OCRService

**File:** `plate_guard/application/services/ocr_service.py`
**Thread-safety:** PaddleOCR is not fully thread-safe. A single OCR engine instance is shared with a thread lock. Consider a dedicated OCR worker thread for high throughput.

### Methods

#### `recognize`

```python
def recognize(
    self,
    frame: np.ndarray,
    bounding_box: BoundingBox,
) -> OCRResult:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | `frame` is a valid BGR numpy array. `bounding_box` coordinates are within the frame dimensions. |
| **Postconditions** | Returns an `OCRResult` with the extracted text and confidence score. If no text is found, returns empty string with 0.0 confidence. |
| **Exceptions** | `OCREngineError` — PaddleOCR fails to initialize or returns an error. `InvalidFrameError` — frame is corrupted or empty. |
| **Performance** | Expected to complete within 500ms for a typical plate crop (~200×100 px). |
| **Example** | `result = ocr_service.recognize(frame, BoundingBox(100, 200, 300, 250, 0.95))` |

#### `recognize_batch`

```python
def recognize_batch(
    self,
    crops: list[tuple[np.ndarray, BoundingBox]],
) -> list[OCRResult]:
```

Processes multiple plate crops in a single call. Useful when multiple plates appear in the same frame. Results are returned in the same order as input.

---

## 4. WebhookService

**File:** `plate_guard/application/services/webhook_service.py`
**Thread-safety:** HTTP calls are made via `httpx.AsyncClient`. The service uses an internal thread pool for synchronous wrappers around async calls. Fire-and-forget semantics for detection-triggered webhooks.

### Methods

#### `send`

```python
def send(
    self,
    detection: Detection,
    camera: Camera,
) -> WebhookStatus:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera must have at least one configured webhook. Detection must be persisted. |
| **Postconditions** | Webhook is dispatched to the configured URL. Status is updated in the detection record. Image/video files are attached if configured. |
| **Exceptions** | No exceptions raised to the caller (failures are logged and reflected in `WebhookStatus`). |
| **Retry** | Up to 3 attempts with exponential backoff (1s, 4s, 9s). Only HTTP 2xx responses are considered success. Network errors and non-2xx status codes trigger a retry. |
| **Example** | `status = webhook_service.send(detection, camera)` |

#### `send_async`

```python
def send_async(
    self,
    detection: Detection,
    camera: Camera,
) -> Future[WebhookStatus]:
```

Non-blocking variant. Returns a `Future` that resolves when delivery completes (including retries). Used by the detection pipeline to avoid blocking frame processing.

#### `test_webhook`

```python
def test_webhook(self, webhook: Webhook) -> TestResult:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Webhook must have a valid URL. |
| **Postconditions** | Sends a test payload to the webhook endpoint. Returns success/failure with HTTP status code and response body preview. No retries. |
| **Exceptions** | `WebhookTestError` — connection refused, DNS failure, timeout. |

#### `get_pending_count`

```python
def get_pending_count(self) -> int:
```

Returns the number of webhooks currently queued for delivery. Used for health monitoring.

---

## 5. RecordingService

**File:** `plate_guard/application/services/recording_service.py`
**Thread-safety:** Video ring buffers are per-camera with thread-safe circular buffers. File I/O runs on a dedicated writer thread to avoid blocking frame capture.

### Methods

#### `save_snapshot`

```python
def save_snapshot(
    self,
    camera_id: int,
    frame: np.ndarray,
    timestamp: datetime | None = None,
) -> str:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Camera must exist. `frame` must be a valid BGR image. |
| **Postconditions** | JPEG image is saved to `{storage_path}/{camera_name}/{timestamp}_snapshot.jpg`. Returns the absolute file path. |
| **Exceptions** | `StorageError` — disk full, permission denied, or I/O error. |
| **Performance** | Must complete within 1 second. I/O is on a writer thread; the caller receives a future. |

#### `save_video_clip`

```python
def save_video_clip(
    self,
    camera_id: int,
    detection_timestamp: datetime,
    pre_seconds: int = 3,
    post_seconds: int = 3,
) -> str:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Ring buffer must be active for the camera. Buffer must contain at least `pre_seconds` of frames. |
| **Postconditions** | MP4 (H.264) video is saved to `{storage_path}/{camera_name}/{timestamp}_clip.mp4`. Clip contains pre_seconds before + post_seconds after the detection timestamp. Returns the absolute file path. |
| **Exceptions** | `StorageError`. `BufferUnderrunError` — insufficient pre-roll data (e.g., camera just started). |
| **Performance** | Video encoding runs on a dedicated thread. Method returns immediately with a future. |

#### `start_preview_buffer` / `stop_preview_buffer`

```python
def start_preview_buffer(self, camera_id: int) -> None:
def stop_preview_buffer(self, camera_id: int) -> None:
```

Manages the circular video buffer that holds the last N seconds of frames in memory. Automatically started when detection begins and stopped when it ends.

#### `manual_snapshot` / `manual_clip`

```python
def manual_snapshot(self, camera_id: int, frame: np.ndarray) -> str:
def manual_clip(self, camera_id: int) -> str:
```

Same behavior as the automatic variants but tagged as "manual" in the filename and logged as a manual event.

#### `purge_old_evidence`

```python
def purge_old_evidence(self, retention_days: int) -> PurgeResult:
```

| Aspect | Detail |
|--------|--------|
| **Postconditions** | Scans evidence directory and deletes files older than `retention_days`. Files without matching DB records are also cleaned up. |
| **Returns** | `PurgeResult(deleted_files=int, freed_bytes=int, errors=list[str])` |

---

## 6. LoggingService

**File:** `plate_guard/application/services/logging_service.py`
**Thread-safety:** Database operations use SQLAlchemy session-per-call pattern (thread-safe). UI queries run on the main thread with a short timeout.

### Methods

#### `log_detection`

```python
def log_detection(self, detection: Detection) -> Detection:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Detection must have `camera_id` and `detected_at` set. |
| **Postconditions** | Detection is persisted to the database. Returns the saved entity with generated `id`. |
| **Exceptions** | `DatabaseError` — persistence failure. |

#### `query_detections`

```python
@dataclass
class DetectionFilter:
    camera_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    plate_number: str | None = None  # substring match, case-insensitive
    limit: int = 100
    offset: int = 0
    order_by: Literal["detected_at", "-detected_at"] = "-detected_at"

@dataclass
class PaginatedResult[T]:
    items: list[T]
    total: int
    limit: int
    offset: int

def query_detections(self, filter: DetectionFilter) -> PaginatedResult[Detection]:
```

| Aspect | Detail |
|--------|--------|
| **Preconditions** | Filter parameters are valid (date_to ≥ date_from, limit ≤ 1000, offset ≥ 0). |
| **Postconditions** | Returns paginated results matching all filter criteria (AND logic). Results ordered by `detected_at` descending by default. |
| **Exceptions** | `InvalidFilterError` — invalid filter parameters. |

#### `export_csv` / `export_json`

```python
def export_csv(self, filter: DetectionFilter, output_path: str) -> str:
    """Returns the output path."""

def export_json(self, filter: DetectionFilter, output_path: str) -> str:
    """Returns the output path."""
```

| Aspect | Detail |
|--------|--------|
| **Postconditions** | File is written at `output_path`. Character encoding is UTF-8. CSV includes a header row. JSON is an array of objects. |
| **Exceptions** | `ExportError` — I/O failure. |

#### `purge_old_records`

```python
@dataclass
class PurgeResult:
    deleted_detections: int
    deleted_files: int
    freed_bytes: int
    errors: list[str]

def purge_old_records(self, retention_days: int) -> PurgeResult:
```

| Aspect | Detail |
|--------|--------|
| **Postconditions** | Deletes detection records older than `retention_days`. Also deletes associated evidence files from disk. Runs within a single transaction. |
| **Exceptions** | `DatabaseError` — transaction failure. |

#### `get_detection_count`

```python
def get_detection_count(self) -> int:
```

Returns total number of detection records. Never raises.

#### `get_recent_detections`

```python
def get_recent_detections(self, count: int = 10) -> list[Detection]:
```

Returns the most recent `count` detections. Used by the dashboard "Recent Detections" panel.

---

## Common Exceptions

```python
class CameraNotFoundError(ValueError):
    """Raised when camera_id does not match any existing camera."""

class DuplicateNameError(ValueError):
    """Raised when a camera name already exists."""

class CameraConnectionError(RuntimeError):
    """Raised when unable to connect to camera stream."""

class CameraDisabledError(RuntimeError):
    """Raised when attempting to start detection on a disabled camera."""

class DetectionAlreadyRunningError(RuntimeError):
    """Raised when start_camera is called on an already-running camera."""

class DetectionNotRunningError(RuntimeError):
    """Raised when stop_camera is called on a stopped camera."""

class OCREngineError(RuntimeError):
    """Raised when PaddleOCR fails to initialize or process."""

class InvalidFrameError(ValueError):
    """Raised when a frame is None, empty, or corrupted."""

class StorageError(RuntimeError):
    """Raised when file I/O fails (disk full, permission denied, etc.)."""

class BufferUnderrunError(RuntimeError):
    """Raised when video buffer does not have enough pre-roll frames."""

class ExportError(RuntimeError):
    """Raised when log export fails (I/O, encoding, etc.)."""

class DatabaseError(RuntimeError):
    """Raised when a database operation fails unexpectedly."""

class InvalidFilterError(ValueError):
    """Raised when query filter parameters are invalid."""

class WebhookTestError(RuntimeError):
    """Raised when a test webhook fails to reach the endpoint."""
```
