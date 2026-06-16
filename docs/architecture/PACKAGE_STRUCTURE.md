# Package Structure

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Version:** 1.0
> **Date:** 2026-06-15

```
plate_guard/
├── __init__.py
├── main.py                          # Application entry point
├── app.py                           # QApplication setup, DI container bootstrap
├── config.py                        # Configuration loading (env, file, CLI)
├── constants.py                     # App-wide constants
│
├── domain/                          # Domain Layer — enterprise business logic
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── camera.py                # Camera entity
│   │   ├── zone.py                  # Zone entity
│   │   ├── webhook.py               # Webhook entity
│   │   └── detection.py             # Detection entity
│   │
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── camera_type.py           # CameraType enum
│   │   ├── bounding_box.py          # BoundingBox dataclass
│   │   ├── polygon.py               # Polygon, Point dataclasses with contains()
│   │   ├── confidence.py            # Confidence value object
│   │   ├── plate_number.py          # PlateNumber value object
│   │   ├── http_method.py           # HttpMethod enum
│   │   ├── auth_type.py             # AuthType enum
│   │   ├── webhook_status.py        # WebhookStatus enum
│   │   ├── evidence_type.py         # EvidenceType enum
│   │   └── camera_status.py         # CameraStatus enum
│   │
│   ├── events/
│   │   ├── __init__.py
│   │   ├── plate_detected.py        # PlateDetected domain event
│   │   ├── plate_recognized.py      # PlateRecognized domain event
│   │   ├── evidence_captured.py     # EvidenceCaptured domain event
│   │   └── webhook_sent.py          # WebhookSent domain event
│   │
│   ├── repositories/                # Repository interfaces (Protocols)
│   │   ├── __init__.py
│   │   ├── i_camera_repository.py
│   │   ├── i_zone_repository.py
│   │   ├── i_webhook_repository.py
│   │   └── i_detection_repository.py
│   │
│   └── services/                    # Service interfaces (Protocols)
│       ├── __init__.py
│       ├── i_camera_service.py
│       ├── i_detection_service.py
│       ├── i_ocr_service.py
│       ├── i_webhook_service.py
│       ├── i_recording_service.py
│       └── i_logging_service.py
│
├── application/                     # Application Layer — use-case orchestration
│   ├── __init__.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── camera_service.py        # CameraService implementation
│   │   ├── detection_service.py     # DetectionService implementation
│   │   ├── ocr_service.py           # OCRService implementation
│   │   ├── webhook_service.py       # WebhookService implementation
│   │   ├── recording_service.py     # RecordingService implementation
│   │   └── logging_service.py       # LoggingService implementation
│   │
│   ├── dto/                         # Data Transfer Objects
│   │   ├── __init__.py
│   │   ├── camera_dto.py
│   │   ├── detection_dto.py
│   │   └── detection_filter.py      # DetectionFilter dataclass
│   │
│   └── exceptions/                  # Application-level exceptions
│       ├── __init__.py
│       ├── camera_errors.py         # CameraNotFoundError, CameraDisabledError, etc.
│       ├── detection_errors.py      # DetectionAlreadyRunningError, etc.
│       ├── ocr_errors.py            # OCREngineError, InvalidFrameError
│       ├── webhook_errors.py        # WebhookTestError
│       ├── storage_errors.py        # StorageError, BufferUnderrunError
│       └── export_errors.py         # ExportError
│
├── infrastructure/                  # Infrastructure Layer — external integrations
│   ├── __init__.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── engine.py                # SQLAlchemy engine factory
│   │   ├── session.py               # Session management (scoped_session)
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── camera_model.py
│   │   │   ├── zone_model.py
│   │   │   ├── webhook_model.py
│   │   │   └── detection_model.py
│   │   ├── migrations/              # Alembic migration files
│   │   │   ├── alembic.ini
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   └── repositories/            # SQLAlchemy repository implementations
│   │       ├── __init__.py
│   │       ├── camera_repository.py
│   │       ├── zone_repository.py
│   │       ├── webhook_repository.py
│   │       └── detection_repository.py
│   │
│   ├── camera/                      # Camera stream handling
│   │   ├── __init__.py
│   │   ├── frame_capture.py         # OpenCV frame capture (RTSP + USB)
│   │   ├── rtsp_client.py           # RTSP-specific connection/URL parsing
│   │   ├── usb_enumerator.py        # USB camera enumeration (DirectShow)
│   │   └── camera_health.py         # Camera health monitor / watchdog
│   │
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── yolo_engine.py           # YOLOv8 model loading and inference
│   │   ├── zone_validator.py        # Point-in-polygon zone validation
│   │   ├── plate_tracker.py         # Simple IOU-based plate tracker
│   │   └── duplicate_filter.py      # Duplicate detection suppression
│   │
│   ├── ocr/
│   │   ├── __init__.py
│   │   └── paddle_ocr_engine.py     # PaddleOCR integration wrapper
│   │
│   ├── recording/
│   │   ├── __init__.py
│   │   ├── ring_buffer.py           # Circular video frame buffer
│   │   ├── snapshot_writer.py       # JPEG snapshot saving
│   │   └── video_writer.py          # FFmpeg/MP4 video clip assembly
│   │
│   ├── webhook/
│   │   ├── __init__.py
│   │   ├── http_client.py           # httpx-based HTTP client
│   │   ├── payload_builder.py       # Request payload/body/attachment builder
│   │   └── auth_builder.py          # Authentication header builder
│   │
│   └── di/                          # Dependency Injection container
│       ├── __init__.py
│       └── container.py             # DI wiring (services, repos, infra)
│
├── presentation/                    # Presentation Layer — PySide6 GUI
│   ├── __init__.py
│   ├── main_window.py               # Main application window (QMainWindow)
│   │
│   ├── views/                       # Top-level views / pages
│   │   ├── __init__.py
│   │   ├── dashboard_view.py        # Live camera grid + recent detections
│   │   ├── camera_list_view.py      # Camera management (list, add, edit, delete)
│   │   ├── detection_viewer.py      # Single camera live feed with overlays
│   │   ├── logs_view.py             # Detection log table with filters
│   │   └── settings_view.py         # Application settings page
│   │
│   ├── widgets/                     # Reusable UI components
│   │   ├── __init__.py
│   │   ├── camera_card.py           # Camera thumbnail card for dashboard grid
│   │   ├── camera_form.py           # Add/Edit camera form dialog
│   │   ├── zone_editor.py           # Visual polygon editor widget
│   │   ├── webhook_form.py          # Webhook configuration form
│   │   ├── detection_table.py       # Paginated detection table
│   │   ├── evidence_preview.py      # Image modal + video player
│   │   ├── filter_bar.py            # Log filter controls (camera, date, plate)
│   │   ├── export_dialog.py         # Export format/path selector
│   │   ├── status_indicator.py      # Camera online/offline/reconnecting indicator
│   │   └── video_feed.py            # OpenCV video feed display (QLabel painter)
│   │
│   ├── dialogs/                     # Modal dialogs
│   │   ├── __init__.py
│   │   ├── confirm_dialog.py        # Generic confirmation dialog
│   │   └── about_dialog.py          # About / version dialog
│   │
│   ├── tray/                        # System tray integration
│   │   ├── __init__.py
│   │   └── system_tray.py           # QSystemTrayIcon with context menu
│   │
│   ├── viewmodels/                  # Qt Model/View architecture helpers
│   │   ├── __init__.py
│   │   ├── camera_table_model.py    # QAbstractTableModel for camera list
│   │   ├── detection_table_model.py # QAbstractTableModel for detection logs
│   │   └── camera_status_model.py   # Camera status data model
│   │
│   └── resources/                   # Qt resources (icons, styles, QSS)
│       ├── __init__.py
│       ├── icons/                   # PNG/SVG icons
│       └── styles/                  # QSS stylesheets
│
├── di/                              # Top-level DI container (alternative location)
│   ├── __init__.py
│   └── container.py                 # (may be here or in infrastructure/di/)
│
├── common/                          # Shared utilities across layers
│   ├── __init__.py
│   ├── logger.py                    # Loguru logging configuration
│   ├── types.py                     # Shared type aliases
│   └── helpers.py                   # Utility functions
│
├── tests/                           # Test suite
│   ├── __init__.py
│   │
│   ├── unit/                        # Unit tests (fast, no external deps)
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── test_camera.py
│   │   │   ├── test_zone.py
│   │   │   ├── test_polygon.py
│   │   │   ├── test_bounding_box.py
│   │   │   └── test_confidence.py
│   │   ├── application/
│   │   │   ├── test_camera_service.py
│   │   │   ├── test_detection_service.py
│   │   │   ├── test_ocr_service.py
│   │   │   ├── test_webhook_service.py
│   │   │   ├── test_recording_service.py
│   │   │   └── test_logging_service.py
│   │   └── infrastructure/
│   │       ├── test_zone_validator.py
│   │       ├── test_plate_tracker.py
│   │       ├── test_duplicate_filter.py
│   │       ├── test_ring_buffer.py
│   │       ├── test_payload_builder.py
│   │       └── test_auth_builder.py
│   │
│   ├── integration/                 # Integration tests (DB, filesystem)
│   │   ├── __init__.py
│   │   ├── test_camera_repository.py
│   │   ├── test_zone_repository.py
│   │   ├── test_webhook_repository.py
│   │   ├── test_detection_repository.py
│   │   ├── test_detection_pipeline.py
│   │   ├── test_evidence_capture.py
│   │   ├── test_webhook_delivery.py
│   │   └── test_export.py
│   │
│   └── fixtures/                    # Test fixtures and factories
│       ├── __init__.py
│       ├── camera_factory.py
│       ├── zone_factory.py
│       ├── webhook_factory.py
│       ├── detection_factory.py
│       └── frame_factory.py         # Synthetic test frame generation
│
├── scripts/                         # Development and build scripts
│   ├── setup_deps.py                # System dependency checker
│   ├── download_models.py           # Download YOLOv8/PaddleOCR models
│   └── create_shortcut.py           # Create Windows Start menu shortcut
│
├── pyproject.toml                   # Project metadata, dependencies, tool config
├── poetry.lock                      # Poetry lock file
├── alembic.ini                      # Alembic migration configuration
├── Makefile                         # Common dev commands
└── README.md                        # Project documentation
```

---

## Module Responsibilities

### `plate_guard/main.py`
Entry point. Parses CLI arguments (config path, debug mode), initializes logging, creates `QApplication`, instantiates the DI container, and runs the `Application` bootstrap.

### `plate_guard/app.py`
`Application` class responsible for:
- Initializing the DI container (wiring repositories, services, infrastructure)
- Running database migrations on first launch
- Loading camera configurations and starting detection
- Creating and showing the main window
- Setting up the system tray icon
- Handling graceful shutdown (stop detection, flush buffers, close DB)

### `plate_guard/config.py`
Loads configuration from multiple sources (priority order):
1. CLI arguments
2. Environment variables (prefixed `PLATE_GUARD_`)
3. Config file (YAML/JSON at `~/.plate_guard/config.yml` or `--config` path)
4. Default values

Key settings: storage paths, database URL, logging level, performance options.

### `plate_guard/domain/`
Contains pure business logic with zero external dependencies (no PySide6, no SQLAlchemy, no OpenCV). Entities are plain Python dataclasses. Repository interfaces are `Protocol` classes. Domain events are `@dataclass` objects.

### `plate_guard/application/`
Orchestrates use cases by coordinating domain logic with infrastructure. Services depend on repository interfaces (via DI), not concrete implementations. This layer is framework-agnostic (no Qt imports, no OpenCV imports in service logic).

### `plate_guard/infrastructure/`
Implements all interfaces defined in the domain layer. Contains:
- SQLAlchemy repository implementations (concrete classes)
- YOLOv8 inference wrapper (loads model, runs `predict()`, returns bounding boxes)
- PaddleOCR integration (loads OCR engine, processes cropped images)
- Frame capture via OpenCV `cv2.VideoCapture` for both RTSP and USB
- FFmpeg-based video clip assembly
- httpx-based HTTP client for webhook delivery
- Ring buffer for circular video frame storage

### `plate_guard/presentation/`
PySide6 GUI layer. Implements the clean architecture "presenter" role. Views are passive and receive data from services via signals/slots. No business logic lives here — only UI rendering and user input collection.

### `plate_guard/tests/`
Organized mirroring the source structure:
- **Unit tests** mock external dependencies. Pure domain logic is tested without mocking.
- **Integration tests** use a test SQLite database (`:memory:`) and temporary file storage.
- **Fixtures** use `pytest.fixture` and factory pattern for consistent test setup.

---

## Dependency Injection Flow

```
main.py
  └─► app.py (Application)
        └─► container.py (DIContainer)
              ├─► engine.py (SQLAlchemy engine)
              ├─► session.py (session factory)
              ├─► CameraRepository (concrete)
              ├─► ZoneRepository (concrete)
              ├─► WebhookRepository (concrete)
              ├─► DetectionRepository (concrete)
              ├─► YOLOv8Engine
              ├─► PaddleOCREngine
              ├─► FrameCapture
              ├─► RingBuffer
              │
              ├─► CameraService
              ├─► DetectionService
              ├─► OCRService
              ├─► WebhookService
              ├─► RecordingService
              └─► LoggingService
                   │
                   └─► Presentation/Views (receive services via constructor injection)
```

---

## Key Architectural Decisions

1. **Repository interfaces live in `domain/`**, implementations in `infrastructure/database/repositories/`. This keeps domain pure and allows swapping storage backends.

2. **Service interfaces also live in `domain/`**, implementations in `application/services/`. This makes services testable with mock repositories.

3. **The DI container is centralized** in `infrastructure/di/container.py` and bootstrapped in `app.py`. No service locator pattern — explicit constructor injection.

4. **Domain entities are plain dataclasses**, not ORM models. SQLAlchemy models in `infrastructure/database/models/` map between the two. This prevents ORM coupling from leaking into domain logic.

5. **Frame capture runs on per-camera threads**, not the main thread. Results are dispatched to the main thread via Qt signals for UI updates.

6. **Video ring buffer** stores frames in memory (encoded as JPEG to reduce footprint) and is used for pre-roll video clips. Configurable size (default 30 seconds at 10 FPS ≈ 300 frames).

7. **Test file storage** uses `tempfile.TemporaryDirectory` to avoid polluting the real evidence directory.
