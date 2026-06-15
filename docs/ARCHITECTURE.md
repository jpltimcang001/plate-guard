# Architecture

## Layers

Presentation Layer
Application Layer
Domain Layer
Infrastructure Layer

---

# Presentation Layer

PySide6

Responsibilities:

- Dashboard
- Camera Management
- Logs
- Settings
- Detection Viewer

---

# Application Layer

Services:

- CameraService
- DetectionService
- OCRService
- WebhookService
- RecordingService
- LoggingService

---

# Domain Layer

Entities:

- Camera
- Zone
- Detection
- Webhook
- OCRResult

---

# Infrastructure Layer

Components:

- SQLite
- SQLAlchemy
- YOLOv8
- PaddleOCR
- FFmpeg
- OpenCV
- HTTP Client

---

# Detection Flow

Frame
→ YOLOv8
→ Zone Validation
→ Tracker
→ Duplicate Filter
→ OCR
→ Save Evidence
→ Send Webhook
→ Save Log