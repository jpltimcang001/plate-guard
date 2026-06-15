# General Rules

## Technology

- Python 3.14.2
- PySide6
- SQLAlchemy 2.x
- SQLite
- Pydantic v2
- YOLOv8
- PaddleOCR
- OpenCV
- FFmpeg
- Loguru
- httpx

---

## Architecture Rules

Use:

- Repository Pattern
- Service Layer Pattern
- Dependency Injection
- Domain Driven Structure

Do not:

- Put database queries inside UI
- Put YOLO logic inside UI
- Put OCR logic inside UI
- Put webhook logic inside UI
- Use global variables

---

## Quality Rules

Every feature must include:

- Service
- Repository
- DTO
- Unit Test
- Integration Test

Minimum Coverage:

80%

---

## Coding Rules

Mandatory:

- Type hints
- Dataclasses or Pydantic models
- Structured logging
- Error handling
- Docstrings

Never:

- Use print()
- Hardcode paths
- Hardcode credentials

---

## Security Rules

- Encrypt secrets
- Validate webhook URLs
- Sanitize user input
- Validate uploaded model files

---

## AI Rules

Before generating code:

1. Read PRD
2. Read Architecture
3. Read Existing Services
4. Read Existing Models

Never generate duplicate modules.