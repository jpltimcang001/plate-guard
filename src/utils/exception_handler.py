"""Global exception handler — catches unhandled exceptions across threads and Qt.

Installs a custom ``sys.excepthook`` and a Qt message handler so that
*all* unhandled exceptions (including those raised in Qt slots, timers,
and background threads) are captured, logged, and optionally reported
to the user.

Usage
-----
Call ``install_global_exception_handler()`` early in ``main()``,
ideally right after ``QApplication`` is created::

    from src.utils.exception_handler import install_global_exception_handler

    app = QApplication(sys.argv)
    install_global_exception_handler(app)
"""

from __future__ import annotations

import sys
import threading
import traceback
from typing import TYPE_CHECKING

from loguru import logger

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


def install_global_exception_handler(
    app: QApplication | None = None,
    show_dialog: bool = True,
) -> None:
    """Install global exception handlers for Python and Qt.

    Registers a custom ``sys.excepthook`` and a Qt message handler that
    intercepts unhandled exceptions, logs them via Loguru, and optionally
    displays an error dialog to the user.

    Args:
        app: The ``QApplication`` instance (if ``None``, attempts to
            retrieve it via ``QApplication.instance()``).
        show_dialog: Whether to show a ``QMessageBox`` on unhandled
            exceptions (default ``True``).

    """
    # Store reference for the Qt message handler
    _state = _ExceptionHandlerState(
        app=app,
        show_dialog=show_dialog,
        _original_excepthook=sys.excepthook,
    )

    sys.excepthook = _make_excepthook(_state)

    # Qt message handler (catches exceptions from Qt slots/timers)
    import PySide6.QtCore as QtCore

    _original_message_handler = QtCore.qInstallMessageHandler(None)

    def qt_message_handler(mode: int, context: object, message: str) -> None:  # noqa: ANN401
        """Handle Qt log messages.

        For ``QtFatalMsg`` and ``QtCriticalMsg``, also logs as a Python
        exception to capture the full context.

        Args:
            mode: Qt message type (QtDebugMsg, QtWarningMsg, etc.).
            context: ``QMessageLogContext`` with file, line, function info.
            message: The log message text.

        """
        if mode in (QtCore.QtMsgType.QtFatalMsg, QtCore.QtMsgType.QtCriticalMsg):
            logger.opt(exception=False).error("Qt critical: {}", message)
        elif mode == QtCore.QtMsgType.QtWarningMsg:
            logger.opt(exception=False).warning("Qt warning: {}", message)
        elif mode == QtCore.QtMsgType.QtInfoMsg:
            logger.opt(exception=False).info("Qt info: {}", message)
        # QtDebugMsg is ignored by default

    QtCore.qInstallMessageHandler(qt_message_handler)

    # Hook threading.excepthook for background threads
    _original_thread_excepthook = threading.excepthook

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        """Handle unhandled exceptions in background threads."""
        thread_name = getattr(args.thread, "name", None) if args.thread else None
        thread_id = getattr(args.thread, "ident", None) if args.thread else None
        logger.opt(exception=True).error(
            "Unhandled exception in thread {}({}): {}",
            thread_name or "?",
            thread_id or "?",
            args.exc_value or args.exc_type,
        )
        if show_dialog and _state.app is not None:

            def _show_later() -> None:
                _show_error_dialog(
                    "Thread Error",
                    f"An unhandled error occurred in thread '{thread_name or '?'}'.\n\n"
                    f"{args.exc_type.__name__}: {args.exc_value}",
                )

            QTimer.singleShot(0, _show_later)

    threading.excepthook = _thread_excepthook

    logger.debug("Global exception handler installed")


def _make_excepthook(state: _ExceptionHandlerState) -> callable:
    """Build the custom ``sys.excepthook`` closure.

    Args:
        state: The handler state including original hook reference.

    Returns:
        The replacement ``sys.excepthook`` function.

    """

    def excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: object | None,
    ) -> None:
        """Custom ``sys.excepthook`` that logs before delegating."""
        # Log the full traceback
        logger.opt(exception=True).error(
            "Unhandled exception: {}: {}",
            exc_type.__name__,
            exc_value,
        )

        # Show dialog if configured
        if state.show_dialog and state.app is not None:
            _show_error_dialog(
                "Unhandled Error",
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"Check the application log for full details.",
            )

        # Call the original hook (if it's not us)
        if (
            state._original_excepthook is not None
            and state._original_excepthook is not sys.__excepthook__
        ):
            try:
                state._original_excepthook(exc_type, exc_value, exc_tb)
            except Exception:
                pass

    return excepthook


def _show_error_dialog(title: str, message: str) -> None:
    """Display a modal error dialog to the user.

    Args:
        title: Dialog title.
        message: Dialog message body.

    """
    try:
        dialog = QMessageBox()
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setDetailedText(
            "Please check the application log file for the full "
            "traceback and report this issue to support.",
        )
        dialog.exec()
    except Exception:
        logger.opt(exception=True).warning("Failed to show error dialog")


class _ExceptionHandlerState:
    """Holds state for the exception handler.

    Attributes:
        app: The ``QApplication`` instance or ``None``.
        show_dialog: Whether to show error dialogs.
        _original_excepthook: The prior ``sys.excepthook``.

    """

    def __init__(
        self,
        app: QApplication | None = None,
        show_dialog: bool = True,
        _original_excepthook: object = None,
    ) -> None:
        """Initialise the state.

        Args:
            app: ``QApplication`` reference.
            show_dialog: Whether to show dialogs.
            _original_excepthook: Previous ``sys.excepthook``.

        """
        self.app = app
        self.show_dialog = show_dialog
        self._original_excepthook = _original_excepthook
