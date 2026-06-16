"""Domain entity representing a single PaddleOCR recognition result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


@dataclass
class OcrResult:
    """The result of recognising text in a license plate crop.

    Attributes:
        text: The recognised plate text (empty string if no text found).
        confidence: OCR confidence score in the range ``[0.0, 1.0]``.
            A value of ``0.0`` indicates that no text was recognised or
            the confidence is unavailable.
        bounding_box: Optional tight bounding box around the recognised
            text within the crop, in ``(x1, y1, x2, y2)`` pixel
            coordinates relative to the **original frame**.
            ``None`` when no text is found.
        processing_time_ms: Time spent on OCR inference for this crop
            in milliseconds.
        raw_text: The raw, unfiltered text string returned by the OCR
            engine before any post-processing (e.g. whitespace stripping).
            May be useful for debugging.
    """

    text: str = ""
    confidence: float = 0.0
    bounding_box: Optional[Tuple[int, int, int, int]] = None
    processing_time_ms: float = 0.0
    raw_text: str = ""

    @property
    def is_success(self) -> bool:
        """Whether the OCR produced usable text above the threshold."""
        return len(self.text) > 0 and self.confidence > 0.0

    @property
    def text_length(self) -> int:
        """Number of characters in the recognised text."""
        return len(self.text)

    @staticmethod
    def empty(reason: str = "no text found") -> OcrResult:
        """Return a blank ``OcrResult`` representing a failed recognition.

        Args:
            reason: Logging hint that describes why OCR yielded nothing.

        Returns:
            An ``OcrResult`` with empty text and zero confidence.
        """
        return OcrResult(
            text="",
            confidence=0.0,
            bounding_box=None,
            processing_time_ms=0.0,
            raw_text="",
        )

    def __repr__(self) -> str:
        if self.is_success:
            return (
                f"<OcrResult text={self.text!r} "
                f"conf={self.confidence:.3f} "
                f"ms={self.processing_time_ms:.1f}>"
            )
        return (
            f"<OcrResult empty "
            f"conf={self.confidence:.3f} "
            f"ms={self.processing_time_ms:.1f}>"
        )
