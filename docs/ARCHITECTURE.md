# Architecture

## Layers

Presentation Layer
Application Layer
Domain Layer
Infrastructure Layer

---

# Presentation Layer

PySide6 — Desktop UI components.

### Widgets

- **MainWindow** — Application shell with navigation, system tray integration.
- **CameraManagementWidget** — CRUD for RTSP/USB cameras.
- **ZoneEditorWidget** — Visual polygon editor for detection zones.
- **DashboardWidget** — Live camera grid, recent detections, status overview.
- **LivePreviewWidget** — Per-camera live feed with bounding-box overlay.
- **CameraStatusPanel / CameraCard** — Clickable camera status cards.
- **DetectionSummaryWidget** — Detection count badges + recent detections table.
- **DetectionLogsWidget** — Paginated log table with filters + evidence preview.

---

# Application Layer

Services — Business-logic orchestrators (Service Layer pattern).

- **CameraService** — Camera CRUD, validation, enable/disable.
- **DashboardService** — Aggregates camera status + detection summaries for UI.
- **PlateDetectionService** — YOLOv8 inference wrapper (detect_frame, confidence filtering).
- **PlateOcrService** — PaddleOCR wrapper (ocr_detection, confidence scoring).
- **DetectionPipeline** — Frame → YOLO → Zone → Tracker → Dedup → OCR → Persist → Webhook.
- **ZoneValidator** — Per-camera polygon zone cache, point-in-polygon validation.
- **DetectionTracker** — IOU-based cross-frame plate tracking (greedy matching).
- **DuplicateFilter** — Cooldown-based plate-text deduplication (default 5s).
- **WebhookService** — HTTP dispatch with auth (None/Basic/Bearer/API Key) and retry.
- **MediaWriter** — Snapshot (JPEG) and video clip (MP4) capture.
- **CameraHealthMonitor** — Watchdog with auto-reconnect for stream health.

---

# Domain Layer

Entities — Core business objects.

- **Camera** — RTSP/USB camera configuration.
- **Zone** — Polygon detection zone (contains_point via ray-casting).
- **Detection** — Captured detection event with plate text, confidence, evidence paths.
- **Webhook** — Per-camera webhook configuration (method, URL, auth, attachments).
- **OCRResult** — Plate text + confidence score.
- **DetectionResult** — YOLO bounding box, confidence, center, crop_frame().
- **TrackedObject** — Cross-frame track state (track_id, first/last_seen, misses).
- **CameraStatus** — Enum: ONLINE, OFFLINE, RECONNECTING, ERROR, DISABLED.

### Value Objects

- **CameraType** — Enum: RTSP, USB.
- **OcrResult** — plate_text: str, confidence: float.

### Events

- **PlateDetectedEvent** — Domain event emitted when a plate is recognised.

### Repository Interfaces

- **ICameraRepository** — Camera persistence contract.
- **IZoneRepository** — Zone persistence contract.

---

# Infrastructure Layer

Components — Concrete implementations, frameworks, drivers.

- **SQLite + SQLAlchemy 2.x** — Database engine, ORM models, migrations.
- **OpenCV** — Frame capture (RTSP / USB), image processing, BGR→RGB conversion.
- **YOLOv8 (ultralytics)** — Plate detection (bounding boxes, confidence scores).
- **PaddleOCR** — Optical character recognition for plate text extraction.
- **FFmpeg** — Video clip assembly (pre-roll + post-roll → MP4).
- **httpx** — Synchronous HTTP client for webhook dispatch.
- **Loguru** — Structured logging (file + console, rotation, retention).

---

# Detection Pipeline

The `DetectionPipeline` orchestrates the full detection flow across multiple per-camera stages:

```
                       +-------------------+
                       |   Frame (from      |
                       |  FrameCapture)     |
                       +--------+----------+
                                |
                                v
                       +--------+----------+
                       |  YOLOv8 Inference  |
                       |  (PlateDetection-  |
                       |   Service)          |
                       +--------+----------+
                                |
                        [detections found?]
                              / \
                            no   yes
                             |    |
                          (skip)  v
                       +--------+----------+
                       |  Zone Validation   |
                       |  (ZoneValidator)    |
                       |  is_in_any_zone()   |
                       +--------+----------+
                                |
                        [in any zone?]
                              / \
                            no   yes
                             |    |
                          (skip)  v
                       +--------+----------+
                       |  IOU Tracker       |
                       |  (DetectionTracker) |
                       |  update() → new    |
                       |  tracks only        |
                       +--------+----------+
                                |
                        [new track?]
                              / \
                            no   yes
                             |    |
                          (skip)  v
                       +--------+----------+
                       |  OCR Recognition   |
                       |  (PlateOcrService)  |
                       +--------+----------+
                                |
                                v
                       +--------+----------+
                       |  Duplicate Filter  |
                       |  (DuplicateFilter)  |
                       |  check_and_record() |
                       +--------+----------+
                                |
                        [accepted?]
                              / \
                            no   yes
                             |    |
                          (skip)  v
                       +--------+----------+
                       |  Persist Event     |
                       |  ─ Snapshot (JPEG) |
                       |  ─ DB row          |
                       |  ─ Webhook dispatch|
                       +--------+----------+
```

### Key Design Decisions

1. **All stages individually optional** — ZoneValidator, DetectionTracker, DuplicateFilter, OCR service, MediaWriter, DetectionRepository, and WebhookService can all be `None`. The pipeline degrades gracefully.

2. **Only new tracks reach OCR** — After tracking, only detections flagged as `is_new` proceed to OCR + dedup + persistence. Already-tracked plates are skipped to avoid duplicate work.

3. **Error isolation** — Each stage is wrapped in try/except. Errors are logged via Loguru and do not abort the pipeline. Per-stage counters in `PipelineResult` track successes/failures.

4. **Per-camera state isolation** — Tracker and zone cache maintain separate state per camera_id. No cross-camera interference.

### PipelineResult

| Field | Description |
|-------|-------------|
| `frame_number` | Frame sequence number |
| `camera_id` | Source camera ID |
| `detections_found` | Raw YOLO detection count |
| `new_tracks` | New tracks created by tracker |
| `ocr_processed` | Successful OCR results |
| `duplicates_suppressed` | Duplicate filter hits |
| `detections_persisted` | DB rows inserted |
| `processing_time_ms` | Total wall-clock time |

---

# Detection Flow (Simplified)

Frame → YOLOv8 → Zone Validation → Tracker → Duplicate Filter → OCR → Save Evidence → Send Webhook → Save Log