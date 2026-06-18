"""Webhook configuration dialog — add/edit webhook targets for a camera.

Supports configuring:
- HTTP method (GET, POST, PUT, PATCH)
- Target URL
- Custom headers (key-value pairs)
- Authentication (None, Basic, Bearer, API Key)
- Body template (optional JSON template)
- Snapshot/video attachment toggles
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.database.models.webhook_model import WebhookModel

# ------------------------------------------------------------------
# Style constants
# ------------------------------------------------------------------

_DARK_BG = QColor("#1a1a1a")
_DARK_CARD = QColor("#2b2b2b")
_DARK_BORDER = QColor("#3a3a3a")
_TEXT_COLOR = QColor("#ecf0f1")
_TEXT_MUTED = QColor("#95a5a6")
_ACCENT = QColor("#3498db")
_ERROR = QColor("#e74c3c")


class WebhookDialog(QDialog):
    """Modal dialog for creating or editing a webhook configuration.

    Usage::

        # Create a new webhook
        dialog = WebhookDialog(camera_id=1, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()

        # Edit an existing webhook
        dialog = WebhookDialog(camera_id=1, webhook_model=existing, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = dialog.get_config()
    """

    def __init__(
        self,
        camera_id: int,
        webhook_model: WebhookModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the webhook dialog.

        Args:
            camera_id: The parent camera ID.
            webhook_model: An existing ``WebhookModel`` to edit, or
                ``None`` to create a new webhook.
            parent: Optional parent widget.

        """
        super().__init__(parent=parent)

        self._camera_id = camera_id
        self._model = webhook_model
        self._config: dict[str, Any] | None = None

        title = "Edit Webhook" if webhook_model else "Add Webhook"
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setModal(True)

        self._setup_ui()
        self._load_model()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def camera_id(self) -> int:
        """The parent camera ID."""
        return self._camera_id

    def get_config(self) -> dict[str, Any]:
        """Return the webhook configuration as a dictionary.

        Returns:
            A dict suitable for creating/updating a ``WebhookModel``.

        """
        return dict(self._config) if self._config else {}

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        self.setStyleSheet(
            f"WebhookDialog {{ background-color: {_DARK_BG.name()}; }}",
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Form
        form = QFrame(self)
        form.setStyleSheet(
            f"QFrame {{ background-color: {_DARK_CARD.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; "
            f"border-radius: 6px; padding: 16px; }}",
        )
        form_layout = QFormLayout(form)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Method
        self._method_combo = QComboBox(form)
        self._method_combo.addItems(["POST", "GET", "PUT", "PATCH"])
        self._method_combo.setCurrentText("POST")
        self._method_combo.setStyleSheet(self._combo_style())
        form_layout.addRow("Method:", self._method_combo)

        # URL
        self._url_input = QLineEdit(form)
        self._url_input.setPlaceholderText("https://example.com/webhook")
        self._url_input.setStyleSheet(self._input_style())
        form_layout.addRow("URL:", self._url_input)

        # Auth type
        self._auth_combo = QComboBox(form)
        self._auth_combo.addItems(["None", "Basic", "Bearer", "API Key"])
        self._auth_combo.setStyleSheet(self._combo_style())
        self._auth_combo.currentTextChanged.connect(self._on_auth_changed)
        form_layout.addRow("Auth Type:", self._auth_combo)

        # Auth value
        self._auth_value_input = QLineEdit(form)
        self._auth_value_input.setPlaceholderText("user:pass  or  token")
        self._auth_value_input.setStyleSheet(self._input_style())
        self._auth_value_input.setEnabled(False)
        form_layout.addRow("Auth Credentials:", self._auth_value_input)

        # Custom headers
        headers_label = QLabel("Custom Headers (JSON):", form)
        headers_label.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        form_layout.addRow(headers_label)

        self._headers_input = QPlainTextEdit(form)
        self._headers_input.setPlaceholderText('{"X-Custom": "value"}')
        self._headers_input.setMaximumHeight(80)
        self._headers_input.setStyleSheet(self._textarea_style())
        form_layout.addRow("", self._headers_input)

        # Body template
        body_label = QLabel("Body Template (JSON):", form)
        body_label.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        form_layout.addRow(body_label)

        self._body_input = QPlainTextEdit(form)
        self._body_input.setPlaceholderText(
            '{"plate": "${plate_text}", "camera": ${camera_id}}',
        )
        self._body_input.setMaximumHeight(80)
        self._body_input.setStyleSheet(self._textarea_style())
        form_layout.addRow("", self._body_input)

        # Attachment toggles
        self._send_image_check = QCheckBox("Attach snapshot image", form)
        self._send_image_check.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        form_layout.addRow("", self._send_image_check)

        self._send_video_check = QCheckBox("Attach video clip", form)
        self._send_video_check.setStyleSheet(f"color: {_TEXT_COLOR.name()};")
        form_layout.addRow("", self._send_video_check)

        main_layout.addWidget(form)

        # Buttons
        buttons = QDialogButtonBox(self)
        buttons.setStyleSheet(
            f"QPushButton {{ background-color: {_ACCENT.name()}; color: white; "
            f"border: none; padding: 8px 20px; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #2980b9; }}"
            f"QPushButton[text='Cancel'] {{ background-color: {_DARK_CARD.name()}; "
            f"color: {_TEXT_COLOR.name()}; border: 1px solid {_DARK_BORDER.name()}; }}"
        )
        save_btn = buttons.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        save_btn.clicked.connect(self._validate_and_accept)
        cancel_btn.clicked.connect(self.reject)

        main_layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _input_style() -> str:
        """Return stylesheet for text inputs."""
        return (
            f"QLineEdit {{ background-color: {_DARK_BG.name()}; "
            f"color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; "
            f"padding: 6px 8px; border-radius: 4px; }}"
            f"QLineEdit:hover {{ border-color: {_ACCENT.name()}; }}"
            f"QLineEdit:focus {{ border-color: {_ACCENT.name()}; }}"
        )

    @staticmethod
    def _combo_style() -> str:
        """Return stylesheet for combo boxes."""
        return (
            f"QComboBox {{ background-color: {_DARK_BG.name()}; "
            f"color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; "
            f"padding: 6px 8px; border-radius: 4px; }}"
            f"QComboBox:hover {{ border-color: {_ACCENT.name()}; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background-color: {_DARK_CARD.name()}; "
            f"color: {_TEXT_COLOR.name()}; selection-background-color: {_ACCENT.name()}; }}"
        )

    @staticmethod
    def _textarea_style() -> str:
        """Return stylesheet for text areas."""
        return (
            f"QPlainTextEdit {{ background-color: {_DARK_BG.name()}; "
            f"color: {_TEXT_COLOR.name()}; "
            f"border: 1px solid {_DARK_BORDER.name()}; "
            f"padding: 6px 8px; border-radius: 4px; }}"
            f"QPlainTextEdit:hover {{ border-color: {_ACCENT.name()}; }}"
            f"QPlainTextEdit:focus {{ border-color: {_ACCENT.name()}; }}"
        )

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Populate form fields from an existing webhook model."""
        if self._model is None:
            return

        self._method_combo.setCurrentText(self._model.method.upper())
        self._url_input.setText(self._model.url)
        self._headers_input.setPlainText(self._model.headers_json or "")
        self._body_input.setPlainText(self._model.body_template or "")
        self._send_image_check.setChecked(bool(self._model.send_image))
        self._send_video_check.setChecked(bool(self._model.send_video))

        # Auth
        auth_map = {
            "none": "None",
            "basic": "Basic",
            "bearer": "Bearer",
            "api_key": "API Key",
        }
        self._auth_combo.setCurrentText(
            auth_map.get((self._model.auth_type or "none").lower(), "None"),
        )
        self._auth_value_input.setText(self._model.auth_value or "")
        self._on_auth_changed(self._auth_combo.currentText())

    def _on_auth_changed(self, auth_type: str) -> None:
        """Enable/disable the auth credentials field based on auth type.

        Args:
            auth_type: The selected auth type.

        """
        enabled = auth_type.lower() not in ("none", "")
        self._auth_value_input.setEnabled(enabled)
        if auth_type.lower() == "basic":
            self._auth_value_input.setPlaceholderText("username:password")
        elif auth_type.lower() == "bearer":
            self._auth_value_input.setPlaceholderText("Bearer token")
        elif auth_type.lower() == "api key":
            self._auth_value_input.setPlaceholderText("API key value")
        else:
            self._auth_value_input.setPlaceholderText("")

    # ------------------------------------------------------------------
    # Validation & acceptance
    # ------------------------------------------------------------------

    def _validate_and_accept(self) -> None:
        """Validate form data and accept if valid."""
        url = self._url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Validation Error", "URL is required.")
            self._url_input.setFocus()
            return

        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(
                self,
                "Validation Error",
                "URL must start with http:// or https://",
            )
            self._url_input.setFocus()
            return

        # Validate headers JSON
        headers_raw = self._headers_input.toPlainText().strip()
        if headers_raw:
            try:
                parsed = json.loads(headers_raw)
                if not isinstance(parsed, dict):
                    raise ValueError("Headers must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Invalid headers JSON: {exc}",
                )
                self._headers_input.setFocus()
                return

        # Validate body template JSON
        body_raw = self._body_input.toPlainText().strip()
        if body_raw:
            try:
                json.loads(body_raw)
            except json.JSONDecodeError as exc:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Invalid body template JSON: {exc}",
                )
                self._body_input.setFocus()
                return

        # Map auth type
        auth_map = {
            "none": "none",
            "basic": "basic",
            "bearer": "bearer",
            "api key": "api_key",
        }
        auth_type = auth_map.get(self._auth_combo.currentText().lower(), "none")

        self._config = {
            "camera_id": self._camera_id,
            "method": self._method_combo.currentText().upper(),
            "url": url,
            "headers_json": headers_raw if headers_raw else None,
            "auth_type": auth_type,
            "auth_value": self._auth_value_input.text().strip() or None,
            "body_template": body_raw if body_raw else None,
            "send_image": self._send_image_check.isChecked(),
            "send_video": self._send_video_check.isChecked(),
        }

        logger.info(
            "Webhook config validated: method={}, url={!r}, auth={}",
            self._config["method"],
            self._config["url"],
            auth_type,
        )
        self.accept()

    def __repr__(self) -> str:
        return (
            f"<WebhookDialog camera={self._camera_id} "
            f"model={'edit' if self._model else 'new'}>"
        )
