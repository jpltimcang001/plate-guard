# Sprint Breakdown

> **Project:** Plate Guard — AI License Plate Recognition Desktop Application
> **Document Version:** 1.0
> **Date:** 2026-06-15
> **Sprint Duration:** 2 weeks each

---

## Sprint 1: Foundation

**Goal:** Establish project scaffolding, database schema, repository layer, and camera management CRUD.

**Duration:** 2 weeks (Sprint 1–2)

### User Stories

| ID | Story | Points |
|----|-------|--------|
| US-001 | Add RTSP Camera | 5 |
| US-002 | Add USB Camera | 3 |
| US-003 | Edit Camera Configuration | 3 |
| US-004 | Delete Camera | 2 |
| US-005 | Enable / Disable Camera | 2 |
| US-006 | View All Cameras | 3 |
| US-033 | Fast Startup (<5s) | 5 |
| US-038 | Application Settings | 5 |

**Total Story Points:** 28

### Technical Tasks

| # | Task | Points | Dependencies | Owner |
|---|------|--------|-------------|-------|
| T1.1 | Initialize Python project with Poetry, pyproject.toml, linters, and pre-commit hooks | 2 | — | Backend |
| T1.2 | Set up SQLAlchemy models (Camera, Zone, Webhook, Detection) matching ERD | 5 | T1.1 | Backend |
| T1.3 | Implement Alembic migrations for initial schema | 3 | T1.2 | Backend |
| T1.4 | Implement CameraRepository with full CRUD operations | 5 | T1.3 | Backend |
| T1.5 | Implement CameraService with validation and business logic | 5 | T1.4 | Backend |
| T1.6 | Build PySide6 Camera Management UI (list, add, edit, delete, toggle) | 8 | T1.5 | Frontend |
| T1.7 | Implement USB device enumeration utility | 3 | T1.1 | Backend |
| T1.8 | Build global Settings UI (storage paths, retention, performance) | 5 | T1.3 | Frontend |
| T1.9 | Implement dependency injection container | 3 | T1.1 | Backend |
| T1.10 | Set up logging with Loguru (file + console) | 2 | T1.1 | Backend |
| T1.11 | Unit tests for CameraRepository | 5 | T1.4 | QA |
| T1.12 | Unit tests for CameraService | 5 | T1.5 | QA |
| T1.13 | Integration tests for camera CRUD flow | 3 | T1.6 | QA |

### Dependencies

- T1.4 → T1.1, T1.3
- T1.5 → T1.4
- T1.6 → T1.5
- T1.9 → T1.1
- Tests → respective implementation tasks

### Definition of Done

- All story acceptance criteria pass
- Code passes `mypy --strict` with no errors
- Test coverage ≥ 85% for repository and service layers
- All tests pass (unit + integration)
- UI renders correctly on 1080p and 4K displays
- Camera CRUD operations work end-to-end with SQLite
- Fast startup verified (app launches in <5s with 0–4 cameras)

---

## Sprint 2: Core Detection

**Goal:** Integrate YOLOv8 for plate detection, build detection zones with visual editor, integrate PaddleOCR for text recognition, and implement the core detection pipeline.

**Duration:** 2 weeks (Sprint 3–4)

### User Stories

| ID | Story | Points |
|----|-------|--------|
| US-007 | Real-Time YOLOv8 Detection | 13 |
| US-008 | Configure Confidence Threshold per Camera | 2 |
| US-009 | Display Bounding Box and Confidence | 5 |
| US-010 | Create Polygon Detection Zone | 8 |
| US-011 | Edit Detection Zone | 5 |
| US-012 | Delete Detection Zone | 2 |
| US-013 | Multiple Zones per Camera | 5 |
| US-014 | Automatic OCR on Detected Plates | 8 |
| US-015 | OCR Confidence Score | 2 |
| US-037 | Zone Visual Editor | 8 |

**Total Story Points:** 58

### Technical Tasks

| # | Task | Points | Dependencies | Owner |
|---|------|--------|-------------|-------|
| T2.1 | Integrate YOLOv8 model loading and inference wrapper | 8 | T1.1 | CV |
| T2.2 | Implement frame capture pipeline from RTSP and USB sources via OpenCV | 8 | T1.1 | CV |
| T2.3 | Build detection pipeline: frame → YOLOv8 → zone filter → tracker → duplicate filter | 13 | T2.1, T2.2 | CV |
| T2.4 | Implement confidence threshold filtering in pipeline | 2 | T2.3 | CV |
| T2.5 | Implement ZoneRepository (CRUD for polygon zones) | 3 | T1.3 | Backend |
| T2.6 | Implement point-in-polygon test for detection zone validation | 5 | T2.5 | CV |
| T2.7 | Build visual polygon editor widget (click-to-place, drag vertices, remove) | 8 | T1.6 | Frontend |
| T2.8 | Integrate PaddleOCR for plate text extraction from cropped regions | 8 | T2.3 | CV |
| T2.9 | Implement OCR confidence scoring and filtering | 3 | T2.8 | CV |
| T2.10 | Build Detection Viewer showing live feed with bounding boxes and zones | 8 | T2.3, T2.7 | Frontend |
| T2.11 | Implement simple tracker to avoid re-detecting same plate in consecutive frames | 5 | T2.3 | CV |
| T2.12 | Unit tests for YOLOv8 wrapper | 5 | T2.1 | QA |
| T2.13 | Unit tests for zone filtering logic | 3 | T2.6 | QA |
| T2.14 | Unit tests for OCR service | 5 | T2.8 | QA |
| T2.15 | Integration tests: end-to-end detection pipeline | 8 | T2.3, T2.8 | QA |

### Dependencies

- T2.2 → USB/RTSP enumeration from Sprint 1
- T2.3 → T2.1, T2.2
- T2.7 → Camera management UI from Sprint 1
- T2.10 → T2.3, T2.7
- All zones tasks → ZoneRepository (T2.5)
- Tests → respective implementation tasks

### Definition of Done

- YOLOv8 runs at ≥10 FPS on a single camera with a modern GPU
- PaddleOCR returns text within 500ms per cropped plate
- Polygon zones correctly filter detections (inside/outside tested with at least 20 cases)
- Visual editor allows creating, editing, and deleting zones
- Bounding boxes overlay correctly on live feed
- All acceptance criteria pass
- Test coverage ≥ 80% for detection pipeline

---

## Sprint 3: Evidence & Webhooks

**Goal:** Implement snapshot and video clip evidence capture, webhook engine with retry logic, and detection logging with filtering.

**Duration:** 2 weeks (Sprint 5–6)

### User Stories

| ID | Story | Points |
|----|-------|--------|
| US-016 | Snapshot Capture on Detection | 5 |
| US-017 | Video Clip Capture on Detection | 8 |
| US-018 | Configure Evidence Mode per Camera | 3 |
| US-019 | Manual Evidence Capture | 5 |
| US-020 | Configure Webhook per Camera | 5 |
| US-021 | Webhook Authentication | 3 |
| US-022 | Attach Image and Video to Webhook | 5 |
| US-023 | Retry Failed Webhooks | 5 |
| US-024 | Webhook Delivery Status Logging | 3 |
| US-025 | View Detection Logs | 5 |
| US-026 | Filter Detection Logs | 5 |
| US-027 | View Evidence from Logs | 3 |
| US-028 | Export Detection Logs | 5 |
| US-034 | Support 16 Cameras Simultaneously | 8 |

**Total Story Points:** 68

### Technical Tasks

| # | Task | Points | Dependencies | Owner |
|---|------|--------|-------------|-------|
| T3.1 | Implement video ring buffer for pre-roll (3s) using FFmpeg or OpenCV | 8 | T2.2 | CV |
| T3.2 | Implement snapshot capture service (save frame as JPEG) | 3 | T2.3 | CV |
| T3.3 | Implement video clip assembly (pre-roll + post-roll → MP4) | 8 | T3.1 | CV |
| T3.4 | Implement manual capture triggers (snapshot + clip from UI) | 5 | T3.2, T3.3 | Frontend |
| T3.5 | Build WebhookRepository (CRUD) | 3 | T1.3 | Backend |
| T3.6 | Implement webhook HTTP client with httpx (supports GET/POST/PUT/PATCH) | 5 | T1.1 | Backend |
| T3.7 | Implement webhook authentication (None, Basic, Bearer, API Key) | 5 | T3.6 | Backend |
| T3.8 | Implement webhook attachment logic (multipart for image/video) | 5 | T3.6, T3.2, T3.3 | Backend |
| T3.9 | Implement webhook retry with exponential backoff (3 attempts) | 5 | T3.6 | Backend |
| T3.10 | Implement webhook invocation from detection pipeline (async, non-blocking) | 5 | T2.3, T3.6 | Backend |
| T3.11 | Build Detection Logs UI (paginated table with filters) | 8 | T1.6 | Frontend |
| T3.12 | Implement log export to CSV/JSON | 5 | T3.11 | Frontend |
| T3.13 | Build evidence preview components (image modal, video player) | 5 | T3.11 | Frontend |
| T3.14 | Performance test: 16 concurrent cameras with evidence capture | 8 | T3.1–T3.3 | QA |
| T3.15 | Unit tests for webhook service | 5 | T3.6, T3.9 | QA |
| T3.16 | Integration tests for evidence capture pipeline | 8 | T3.2, T3.3 | QA |

### Dependencies

- T3.1, T3.2 → Detection pipeline from Sprint 2
- T3.6 → httpx setup (infrastructure)
- T3.10 → T2.3 (pipeline) + T3.6 (webhook client)
- T3.11 → Camera entities from Sprint 1
- T3.13 → T3.2, T3.3
- Tests → respective implementation tasks

### Definition of Done

- Snapshots saved within 1s of detection event
- Video clips correctly contain 3s pre + 3s post (±500ms)
- Webhooks successfully deliver to test server with all auth types
- Webhook retries work correctly with 3 attempts
- Logs UI filters work with camera, date range, and plate number
- Evidence preview (image + video) works from log entries
- Export produces valid CSV and JSON files
- 16-camera stress test passes (all streams active, no crashes)
- All acceptance criteria pass
- Test coverage ≥ 80%

---

## Sprint 4: Polish & Background

**Goal:** Implement system tray, background mode, auto-start, auto-reconnect, reliability hardening, and final polish.

**Duration:** 2 weeks (Sprint 7–8)

### User Stories

| ID | Story | Points |
|----|-------|--------|
| US-029 | Minimize to System Tray | 5 |
| US-030 | Auto-Start with Windows | 3 |
| US-031 | Auto-Reconnect on Camera Disconnect | 8 |
| US-032 | 24/7 Continuous Operation | 13 |
| US-035 | Performance Stability | 8 |
| US-036 | User-Friendly Dashboard | 8 |

**Total Story Points:** 45

### Technical Tasks

| # | Task | Points | Dependencies | Owner |
|---|------|--------|-------------|-------|
| T4.1 | Implement system tray icon with context menu (Show, Pause, Settings, Exit) | 5 | T1.6 | Frontend |
| T4.2 | Implement minimize-to-tray behavior (hide window on close/minimize) | 3 | T4.1 | Frontend |
| T4.3 | Implement auto-start via Windows registry/Startup folder | 3 | T1.1 | Backend |
| T4.4 | Implement camera health monitor and auto-reconnect logic | 8 | T2.2 | CV |
| T4.5 | Add watchdog timer for camera frame timeout detection | 5 | T4.4 | CV |
| T4.6 | Implement graceful shutdown (flush buffers, close streams, save state) | 5 | T1.1 | Backend |
| T4.7 | Add global exception handler for unhandled exceptions in threads | 5 | T1.10 | Backend |
| T4.8 | Implement memory usage monitoring and alerting | 5 | T1.1 | Backend |
| T4.9 | Build Dashboard UI (live camera grid, recent detections panel, status bar) | 8 | T2.10, T3.11 | Frontend |
| T4.10 | Implement evidence retention/purge scheduler (daily cleanup) | 5 | T3.2, T3.3 | Backend |
| T4.11 | 24/7 soak test (7 days continuous operation) | 13 | All above | QA |
| T4.12 | Memory leak detection and profiling | 8 | T4.8 | QA |
| T4.13 | UI/UX polish pass (loading states, error messages, tooltips, accessibility) | 5 | T4.9 | Frontend |
| T4.14 | Final integration tests and regression suite | 8 | All above | QA |

### Dependencies

- T4.1 → PySide6 application from Sprint 1
- T4.4 → Frame capture (T2.2) and detection pipeline (T2.3)
- T4.9 → Detection Viewer (T2.10) and Logs UI (T3.11)
- T4.10 → Evidence services from Sprint 3
- T4.11 → All prior tasks completed

### Definition of Done

- System tray icon appears on minimize; context menu works
- Auto-start works on Windows (verified with reboot test)
- Camera auto-reconnect works: disconnect → 5 retries → offline; manual enable reconnects
- Application runs 7 days continuously without crash or degradation
- Memory usage stable (±20% of baseline over 7 days)
- Dashboard shows live feeds, recent detections, and system status
- Evidence retention correctly purges files older than configured days
- All acceptance criteria for Sprint 4 stories pass
- Full regression suite passes
- Application packaging (PyInstaller or similar) produces a single executable

---

## Summary

| Sprint | Theme | Stories | Points | Key Deliverables |
|--------|-------|---------|--------|------------------|
| Sprint 1 | Foundation | 8 | 28 | Project setup, DB schema, Camera CRUD, Settings |
| Sprint 2 | Core Detection | 10 | 58 | YOLOv8 pipeline, OCR, zones, visual editor |
| Sprint 3 | Evidence & Webhooks | 14 | 68 | Snapshots, video clips, webhooks, logs, 16-cam support |
| Sprint 4 | Polish & Background | 6 | 45 | System tray, auto-start, auto-reconnect, 24/7 ops, dashboard |
| **Total** | | **38** | **199** | |

### Velocity Assumption
- Team of 4 (2 backend, 1 frontend, 1 CV/ML engineer)
- Expected velocity: 25–35 story points per sprint
- Total 199 points ÷ 30 avg velocity ≈ 6.6 sprints → 4 sprints with some overtime/scope adjustment
- Buffer: ~1 sprint for bug fixes and packaging at the end (included in Sprint 4)
