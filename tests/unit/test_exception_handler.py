"""Unit tests for the global exception handler.

These tests verify that ``install_global_exception_handler`` properly
hooks ``sys.excepthook`` and ``threading.excepthook`` to log and/or
display error dialogs for unhandled exceptions.
"""

from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.utils.exception_handler import (
    _ExceptionHandlerState,
    _make_excepthook,
    install_global_exception_handler,
)


class TestInstallGlobalExceptionHandler:
    """Tests for ``install_global_exception_handler``."""

    def test_replaces_sys_excepthook(self) -> None:
        """Verify that ``sys.excepthook`` is replaced."""
        original = sys.excepthook
        try:
            install_global_exception_handler(show_dialog=False)
            assert sys.excepthook is not original
        finally:
            sys.excepthook = original

    def test_replaces_threading_excepthook(self) -> None:
        """Verify that ``threading.excepthook`` is replaced."""
        original = threading.excepthook
        try:
            install_global_exception_handler(show_dialog=False)
            assert threading.excepthook is not original
        finally:
            threading.excepthook = original

    @patch("src.utils.exception_handler.logger")
    def test_logs_on_exception(self, mock_logger: MagicMock) -> None:
        """Verify that the custom hook logs unhandled exceptions."""
        original = sys.excepthook
        try:
            install_global_exception_handler(show_dialog=False)
            try:
                raise ValueError("test error")
            except ValueError:
                sys.excepthook(*sys.exc_info())

            assert mock_logger.opt.called
            error_calls = mock_logger.opt.return_value.error.call_args_list
            assert len(error_calls) >= 1
            args = error_calls[0][0]
            assert "Unhandled exception" in args[0]
            assert "ValueError" in args[1]
        finally:
            sys.excepthook = original

    def test_does_not_dialog_when_disabled(self) -> None:
        """Verify that no dialog is shown when ``show_dialog=False``."""
        original = sys.excepthook
        try:
            with patch(
                "src.utils.exception_handler._show_error_dialog",
            ) as mock_dialog:
                install_global_exception_handler(show_dialog=False)
                try:
                    raise RuntimeError("silent")
                except RuntimeError:
                    sys.excepthook(*sys.exc_info())
                mock_dialog.assert_not_called()
        finally:
            sys.excepthook = original

    def test_calls_original_hook_when_present(self) -> None:
        """Verify that a previously installed hook is still called."""
        original = sys.excepthook
        mock_original = MagicMock()

        try:
            sys.excepthook = mock_original
            install_global_exception_handler(show_dialog=False)

            try:
                raise ValueError("chain")
            except ValueError:
                sys.excepthook(*sys.exc_info())

            mock_original.assert_called_once()
        finally:
            sys.excepthook = original


class TestThreadExcepthook:
    """Tests for the threading exception hook."""

    @patch("src.utils.exception_handler.logger")
    def test_logs_thread_exception(self, mock_logger: MagicMock) -> None:
        """Verify that thread exceptions are logged."""
        original_hook = threading.excepthook
        try:
            install_global_exception_handler(show_dialog=False)

            exc = ValueError("thread error")
            args = threading.ExceptHookArgs((
                ValueError, exc, None, threading.current_thread(),
            ))

            threading.excepthook(args)

            assert mock_logger.opt.called
            error_calls = mock_logger.opt.return_value.error.call_args_list
            assert len(error_calls) >= 1
            error_msg = error_calls[0][0][0]
            assert "Unhandled exception in thread" in error_msg
        finally:
            threading.excepthook = original_hook


class TestMakeExcepthook:
    """Tests for the ``_make_excepthook`` factory."""

    def test_returns_callable(self) -> None:
        """Verify that the factory returns a callable."""
        state = _ExceptionHandlerState(show_dialog=False)
        hook = _make_excepthook(state)
        assert callable(hook)

    def test_calls_original_when_not_sys_excepthook(self) -> None:
        """Verify delegation to prior hook."""
        mock_original = MagicMock()
        state = _ExceptionHandlerState(
            show_dialog=False,
            _original_excepthook=mock_original,
        )
        hook = _make_excepthook(state)

        try:
            raise KeyError("test")
        except KeyError:
            hook(*sys.exc_info())

        mock_original.assert_called_once()

    def test_skips_original_when_sys_excepthook(self) -> None:
        """Verify no delegation when original is ``sys.__excepthook__``."""
        mock_original = MagicMock()
        state = _ExceptionHandlerState(
            show_dialog=False,
            _original_excepthook=sys.__excepthook__,
        )
        hook = _make_excepthook(state)

        try:
            raise KeyError("test")
        except KeyError:
            hook(*sys.exc_info())

        mock_original.assert_not_called()
