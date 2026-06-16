"""OCR infrastructure — PaddleOCR-based license plate recognition.

Components
----------
- ``OcrResult`` — Domain entity for a single OCR recognition result.
- ``PlateOcrService`` — High-level service wrapping PaddleOCR with
  lifecycle management, crop-from-detection, and error handling.
"""

from src.ocr.ocr_result import OcrResult
from src.ocr.ocr_service import OcrError, PlateOcrService

__all__ = [
    "OcrError",
    "OcrResult",
    "PlateOcrService",
]
