"""Global mouse button hook with platform-specific backends.

Provides MouseToggleHook for X11 (pynput) and Wayland (pyinputcapture).
Platform detection is automatic — the correct backend is chosen at runtime.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)


def _has_wayland_session() -> bool:
    """Check if running under a Wayland session."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type == "wayland":
        return True
    if os.environ.get("WAYLAND_DISPLAY") and session_type not in ("x11", "xorg"):
        return True
    return False


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _get_hook_class():
    """Return the appropriate MouseToggleHook class for the current platform."""
    if _is_linux() and _has_wayland_session():
        if importlib.util.find_spec("pyinputcapture") is not None:
            try:
                from .input_hook_wayland import MouseToggleHook as WaylandHook
                logger.info("Using Wayland portal mouse hook backend")
                return WaylandHook
            except ImportError:
                logger.info("pyinputcapture import failed, trying evdev backend")
        else:
            logger.info("pyinputcapture not available, trying evdev backend")

        if importlib.util.find_spec("evdev") is not None:
            try:
                from .input_hook_evdev import MouseToggleHook as EvdevHook
                logger.info("Using evdev mouse hook backend")
                return EvdevHook
            except ImportError:
                logger.warning("evdev import failed, falling back to X11/pynput")
        else:
            logger.warning("evdev not available, falling back to X11/pynput")

    # X11 / Windows / macOS / fallback
    from .input_hook_x11 import MouseToggleHook as X11Hook
    logger.info("Using X11/pynput mouse hook backend")
    return X11Hook


class MouseToggleHook:
    """Platform-aware global mouse button hook.

    Delegates to the appropriate backend:
      - Wayland (Linux): pyinputcapture
      - X11 / other: pynput
    """

    def __init__(
        self,
        button_name: str,
        on_trigger: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
        on_press: Callable[[int, int], None] | None = None,
        on_release: Callable[[int, int], None] | None = None,
        on_move: Callable[[int, int], None] | None = None,
    ) -> None:
        self._backend = _get_hook_class()
        self._instance = self._backend(
            button_name=button_name,
            on_trigger=on_trigger,
            on_error=on_error,
            on_press=on_press,
            on_release=on_release,
            on_move=on_move,
        )

    def start(self) -> None:
        self._instance.start()

    def stop(self) -> None:
        self._instance.stop()

    def update_button(self, button_name: str) -> None:
        self._instance.update_button(button_name)
