# Domain Design

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Version:** 1.0
> **Date:** 2026-06-15

---

## Domain Entities

### Camera

```
+-----------------------------+
|           Camera            |
+-----------------------------+
| - id: int                   |
| - name: str                 |
| - type: CameraType          |
| - rtsp_url: str | None      |
| - usb_index: int | None     |
| - enabled: bool             |
| - confidence_threshold: float|
| - created_at: datetime      |
| - updated_at: datetime      |
+-----------------------------+
| + zones: List[Zone]         |
| + webhooks: List[Webhook]   |
+-----------------------------+
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Primary key, auto-generated |
| `name` | `str` | User-friendly camera name (unique) |
| `type` | `CameraType` | Enum: `RTSP` or `USB` |
| `rtsp_url` | `Optional[str]` | RTSP stream URL (required if type=RTSP) |
| `usb_index` | `Optional[int]` | USB device index (required if type=USB) |
| `enabled` | `bool` | Whether detection is active |
| `confidence_threshold` | `float` | Minimum YOLOv8 confidence (0.0–1.0) |
| `created_at` | `datetime` | Record creation timestamp |
| `updated_at` | `datetime` | Record last-update timestamp |

**Relationships:**
- `Camera` → `Zone`: 1-to-many (a camera has many zones)
- `Camera` → `Webhook`: 1-to-many (a camera has many webhooks)
- `Camera` → `Detection`: 1-to-many (a camera generates many detections)
- `Camera` is the **aggregate root** for the Camera aggregate (which includes Zones and Webhooks)

---

### Zone

```
+-----------------------------+
|            Zone             |
+-----------------------------+
| - id: int                   |
| - camera_id: int            |
| - name: str                 |
| - polygon_json: str         |
| - created_at: datetime      |
+-----------------------------+
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Primary key |
| `camera_id` | `int` | FK to Camera |
| `name` | `str` | User-friendly zone name |
| `polygon_json` | `str` | JSON array of `[x, y]` vertex coordinates |
| `created_at` | `datetime` | Record creation timestamp |

**Business rules:**
- Polygon must have ≥ 3 vertices
- Polygon must not be self-intersecting
- Zone belongs exclusively to one Camera

---

### Webhook

```
+-----------------------------+
|          Webhook            |
+-----------------------------+
| - id: int                   |
| - camera_id: int            |
| - method: HttpMethod        |
| - url: str                  |
| - headers_json: str | None  |
| - auth_type: AuthType       |
| - auth_value: str | None    |
| - body_template: str | None |
| - send_image: bool          |
| - send_video: bool          |
| - created_at: datetime      |
+-----------------------------+
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Primary key |
| `camera_id` | `int` | FK to Camera |
| `method` | `HttpMethod` | Enum: `GET`, `POST`, `PUT`, `PATCH` |
| `url` | `str` | Webhook endpoint URL |
| `headers_json` | `Optional[str]` | Custom headers as JSON key-value pairs |
| `auth_type` | `AuthType` | Enum: `NONE`, `BASIC`, `BEARER`, `API_KEY` |
| `auth_value` | `Optional[str]` | Auth credential (token, key, or user:pass) |
| `body_template` | `Optional[str]` | JSON template for request body |
| `send_image` | `bool` | Whether to attach snapshot image |
| `send_video` | `bool` | Whether to attach video clip |

---

### Detection

```
+-----------------------------+
|         Detection           |
+-----------------------------+
| - id: int                   |
| - camera_id: int            |
| - plate_number: str | None  |
| - confidence: float         |
| - image_path: str | None    |
| - video_path: str | None    |
| - webhook_status: WebhookStatus |
| - detected_at: datetime     |
+-----------------------------+
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `int` | Primary key |
| `camera_id` | `int` | FK to Camera |
| `plate_number` | `Optional[str]` | Recognized plate text (None if OCR failed) |
| `confidence` | `float` | OCR confidence score (0.0–1.0) |
| `image_path` | `Optional[str]` | Filesystem path to snapshot (None if not captured) |
| `video_path` | `Optional[str]` | Filesystem path to video clip (None if not captured) |
| `webhook_status` | `WebhookStatus` | Enum: `NOT_CONFIGURED`, `PENDING`, `SUCCESS`, `FAILED` |
| `detected_at` | `datetime` | Timestamp of detection event |

---

### OCRResult (Value Object)

```
+-----------------------------+
|         OCRResult           |
+-----------------------------+
| - plate_text: str           |
| - confidence: float         |
| - bounding_box: BoundingBox |
| - raw_data: dict            |
+-----------------------------+
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `plate_text` | `str` | Recognized license plate text |
| `confidence` | `float` | OCR confidence score (0.0–1.0) |
| `bounding_box` | `BoundingBox` | The bounding box of the recognized text region |
| `raw_data` | `dict` | Raw PaddleOCR output |

---

## Value Objects

### CameraType (Enum)
```python
class CameraType(enum.Enum):
    RTSP = "rtsp"
    USB = "usb"
```

### HttpMethod (Enum)
```python
class HttpMethod(enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
```

### AuthType (Enum)
```python
class AuthType(enum.Enum):
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    API_KEY = "api_key"
```

### WebhookStatus (Enum)
```python
class WebhookStatus(enum.Enum):
    NOT_CONFIGURED = "not_configured"
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
```

### BoundingBox (Value Object)
```python
@dataclass(frozen=True)
class BoundingBox:
    x1: int    # top-left x
    y1: int    # top-left y
    x2: int    # bottom-right x
    y2: int    # bottom-right y
    confidence: float  # YOLOv8 detection confidence (0.0–1.0)
```

### Polygon (Value Object)
```python
@dataclass(frozen=True)
class Point:
    x: float
    y: float

@dataclass
class Polygon:
    vertices: list[Point]  # ≥ 3 points

    def contains(self, point: Point) -> bool: ...
    def is_valid(self) -> bool: ...       # no self-intersection
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, json_str: str) -> Polygon: ...
```

### Confidence (Value Object)
```python
@dataclass(frozen=True)
class Confidence:
    value: float  # 0.0–1.0

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")
```

### PlateNumber (Value Object)
```python
@dataclass(frozen=True)
class PlateNumber:
    text: str

    def normalized(self) -> str:  # uppercase, strip whitespace
        return self.text.strip().upper()
```

### EvidenceType (Enum)
```python
class EvidenceType(enum.Enum):
    NONE = "none"
    SNAPSHOT = "snapshot"
    VIDEO = "video"
    BOTH = "both"
```

---

## Domain Events

```python
@dataclass
class PlateDetected:
    """Emitted when YOLOv8 detects a potential plate above the confidence threshold."""
    camera_id: int
    bounding_box: BoundingBox
    frame: np.ndarray
    timestamp: datetime

@dataclass
class PlateRecognized:
    """Emitted after OCR successfully extracts text from a detected plate."""
    camera_id: int
    bounding_box: BoundingBox
    ocr_result: OCRResult
    timestamp: datetime

@dataclass
class EvidenceCaptured:
    """Emitted after evidence (snapshot and/or video) is saved to disk."""
    camera_id: int
    detection_id: int
    image_path: Optional[str]
    video_path: Optional[str]
    timestamp: datetime

@dataclass
class WebhookSent:
    """Emitted after a webhook delivery attempt (success or failure)."""
    detection_id: int
    camera_id: int
    status: WebhookStatus
    http_status_code: Optional[int]
    error_message: Optional[str]
    attempt: int
    timestamp: datetime
```

---

## Aggregates

### Camera Aggregate

```
Camera (Aggregate Root)
├── id: int
├── name: str
├── type: CameraType
├── enabled: bool
├── confidence_threshold: float
│
├── Zones: List[Zone]          (1-to-many, owned by Camera)
│   ├── Zone (id, name, polygon_json)
│   └── Zone ...
│
└── Webhooks: List[Webhook]    (1-to-many, owned by Camera)
    ├── Webhook (method, url, auth, etc.)
    └── Webhook ...
```

**Invariants:**
- Camera name must be unique
- If type is `RTSP`, `rtsp_url` must be non-empty
- If type is `USB`, `usb_index` must be ≥ 0
- Deleting a Camera cascades to all its Zones, Webhooks, and Detections

### Detection Aggregate

```
Detection (Aggregate Root)
├── id: int
├── camera_id: int
├── plate_number: Optional[str]
├── confidence: float
├── image_path: Optional[str]
├── video_path: Optional[str]
├── webhook_status: WebhookStatus
└── detected_at: datetime
```

---

## Repository Interfaces

```python
class ICameraRepository(Protocol):
    def get_by_id(self, camera_id: int) -> Camera: ...
    def get_all(self) -> list[Camera]: ...
    def get_enabled(self) -> list[Camera]: ...
    def add(self, camera: Camera) -> Camera: ...
    def update(self, camera: Camera) -> Camera: ...
    def delete(self, camera_id: int) -> None: ...
    def exists_by_name(self, name: str) -> bool: ...

class IZoneRepository(Protocol):
    def get_by_id(self, zone_id: int) -> Zone: ...
    def get_by_camera_id(self, camera_id: int) -> list[Zone]: ...
    def add(self, zone: Zone) -> Zone: ...
    def update(self, zone: Zone) -> Zone: ...
    def delete(self, zone_id: int) -> None: ...
    def delete_by_camera_id(self, camera_id: int) -> None: ...

class IWebhookRepository(Protocol):
    def get_by_id(self, webhook_id: int) -> Webhook: ...
    def get_by_camera_id(self, camera_id: int) -> list[Webhook]: ...
    def add(self, webhook: Webhook) -> Webhook: ...
    def update(self, webhook: Webhook) -> Webhook: ...
    def delete(self, webhook_id: int) -> None: ...
    def delete_by_camera_id(self, camera_id: int) -> None: ...

class IDetectionRepository(Protocol):
    def get_by_id(self, detection_id: int) -> Detection: ...
    def get_filtered(
        self,
        camera_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        plate_number: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Detection]: ...
    def count_filtered(
        self,
        camera_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        plate_number: Optional[str] = None,
    ) -> int: ...
    def add(self, detection: Detection) -> Detection: ...
    def update_webhook_status(
        self, detection_id: int, status: WebhookStatus, error_message: Optional[str] = None
    ) -> None: ...
    def delete_older_than(self, cutoff: datetime) -> int: ...  # returns count deleted
```

---

## Service Interfaces

```python
class ICameraService(Protocol):
    def add_camera(self, name: str, type: CameraType, ...) -> Camera: ...
    def edit_camera(self, camera_id: int, ...) -> Camera: ...
    def delete_camera(self, camera_id: int) -> None: ...
    def enable_camera(self, camera_id: int) -> None: ...
    def disable_camera(self, camera_id: int) -> None: ...
    def get_all_cameras(self) -> list[Camera]: ...
    def enumerate_usb_devices(self) -> list[dict]: ...

class IDetectionService(Protocol):
    def start_camera(self, camera_id: int) -> None: ...
    def stop_camera(self, camera_id: int) -> None: ...
    def start_all(self) -> None: ...
    def stop_all(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def is_running(self, camera_id: int) -> bool: ...

class IOCRService(Protocol):
    def recognize(self, image: np.ndarray, bounding_box: BoundingBox) -> OCRResult: ...

class IWebhookService(Protocol):
    def send(self, detection: Detection, camera: Camera) -> WebhookStatus: ...
    def test_webhook(self, webhook: Webhook) -> bool: ...

class IRecordingService(Protocol):
    def save_snapshot(self, camera_id: int, frame: np.ndarray) -> str: ...  # returns path
    def save_video_clip(self, camera_id: int) -> str: ...  # returns path
    def start_preview_buffer(self, camera_id: int) -> None: ...
    def stop_preview_buffer(self, camera_id: int) -> None: ...
    def manual_snapshot(self, camera_id: int, frame: np.ndarray) -> str: ...
    def manual_clip(self, camera_id: int) -> str: ...

class ILoggingService(Protocol):
    def log_detection(self, detection: Detection) -> Detection: ...
    def query_detections(self, filters: DetectionFilter) -> PaginatedResult[Detection]: ...
    def export_csv(self, filters: DetectionFilter, output_path: str) -> None: ...
    def export_json(self, filters: DetectionFilter, output_path: str) -> None: ...
    def purge_old_records(self, retention_days: int) -> PurgeResult: ...
```

---

## Entity Relationship Summary

```
Camera 1 ──── * Zone
Camera 1 ──── * Webhook
Camera 1 ──── * Detection

Detection * ──── 1 Camera  (via camera_id)

Zone ── belongs to ── Camera
Webhook ── belongs to ── Camera
Detection ── belongs to ── Camera

Camera (Aggregate Root)
├── owns Zones (composition — zones deleted with camera)
├── owns Webhooks (composition — webhooks deleted with camera)
└── references Detections (aggregation — detections survive camera deletion? No, cascading delete)
```

**Ownership semantics:**
- Camera owns Zone and Webhook (composition: if Camera is deleted, all associated Zones and Webhooks are also deleted)
- Camera is associated with Detection, but Detection is its own aggregate root
- When a Camera is deleted, its Detections are also deleted (cascade)
