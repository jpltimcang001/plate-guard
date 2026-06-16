"""USB camera device enumeration utility.

Uses OpenCV's ``cv2.VideoCapture`` to probe for available USB camera
indices. On Windows, additional device information can be obtained
via DirectShow (``cv2.CAP_DSHOW``).
"""

from __future__ import annotations

import logging
from typing import Any

import cv2

from src.domain.services.i_camera_service import UsbDeviceInfo

logger = logging.getLogger(__name__)


class UsbEnumerator:
    """Enumerates available USB camera devices by probing indices.

    Probes indices 0–15 (configurable) and returns a list of devices
    that successfully open a video capture.
    """

    def __init__(self, max_index: int = 15, probe_frames: bool = False) -> None:
        """Initialize the enumerator.

        Args:
            max_index: The maximum USB index to probe (default 15).
            probe_frames: If ``True``, try to read a frame to verify
                the camera is fully functional. Slower but more reliable.

        """
        self._max_index = max_index
        self._probe_frames = probe_frames

    def list_devices(self) -> list[UsbDeviceInfo]:
        """Probe all USB indices and return a list of detected devices.

        Returns:
            A list of ``UsbDeviceInfo`` objects for each detected camera.

        """
        devices: list[UsbDeviceInfo] = []
        for index in range(self._max_index + 1):
            info = self._probe_device(index)
            if info is not None:
                devices.append(info)
        logger.debug("USB enumeration complete: %d device(s) found", len(devices))
        return devices

    def device_exists(self, index: int) -> bool:
        """Check whether a specific USB device index is available.

        Args:
            index: The USB device index to check.

        Returns:
            ``True`` if a device is detected at the given index.

        """
        return self._probe_device(index) is not None

    def _probe_device(self, index: int) -> UsbDeviceInfo | None:
        """Probe a single USB index and return device info if available.

        Args:
            index: The USB index to probe.

        Returns:
            ``UsbDeviceInfo`` if a camera is detected, else ``None``.

        """
        try:
            # Use DirectShow backend on Windows for faster enumeration
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                return None

            # Optionally read a test frame to confirm the camera works
            if self._probe_frames:
                ret, _frame = cap.read()
                if not ret:
                    cap.release()
                    return None

            # Try to get the camera name (Windows DirectShow backend)
            name = self._get_camera_name(cap, index)

            cap.release()
            return UsbDeviceInfo(index=index, name=name)

        except Exception:
            logger.debug("Exception probing USB index %d", index, exc_info=True)
            return None

    @staticmethod
    def _get_camera_name(cap: Any, index: int) -> str:
        """Attempt to retrieve a human-readable camera name.

        Args:
            cap: An open ``cv2.VideoCapture`` instance.
            index: The device index (used as fallback name).

        Returns:
            A camera name string.

        """
        # OpenCV 4.x+ supports CAP_PROP_HW_DEVICE_DESCRIPTION on Windows
        try:
            name: str = cap.get(
                getattr(cv2, "CAP_PROP_HW_DEVICE_DESCRIPTION", -1),
            )
            if name:
                return str(name)
        except Exception:
            pass
        return f"USB Camera {index}"
