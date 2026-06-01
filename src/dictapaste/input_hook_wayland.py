"""Wayland-compatible mouse hook using pyinputcapture (XDG InputCapture portal).

This module provides a Wayland-native alternative to pynput's mouse listener.
It captures global mouse events via the XDG InputCapture portal, which is
supported by GNOME, KDE Plasma, Sway, and other compositors that implement
the portal spec.

Falls back gracefully if pyinputcapture is unavailable or the compositor
does not support InputCapture.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from .i18n import tr

logger = logging.getLogger(__name__)


class WaylandMouseHookError(RuntimeError):
    """Raised when Wayland input capture cannot be initialized."""


class MouseToggleHook:
    """Wayland-compatible global mouse button hook.

    Uses pyinputcapture to listen for pointer button events across all monitors.

    Args:
        button_name: Mouse button name ("left", "right", "middle", "x1", "x2").
        on_trigger: Called when the target button is pressed.
        on_error: Optional error callback.
        on_press: Optional callback on button press (x, y).
        on_release: Optional callback on button release (x, y).
        on_move: Optional callback on mouse move (x, y).
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
        self.button_name = button_name.lower().strip()
        self.on_trigger = on_trigger
        self.on_error = on_error
        self.on_press = on_press
        self.on_release = on_release
        self.on_move = on_move
        self._pressed = False
        self._capture = None
        self._running = False

    def _resolve_button(self) -> int:
        """Resolve button name to pyinputcapture button code.

        pyinputcapture uses standard button codes:
            1 = left, 2 = middle, 3 = right, 4 = x1 (scroll left), 5 = x2 (scroll right)
        """
        button_map = {
            "left": 1,
            "right": 3,
            "middle": 2,
            "x1": 4,
            "x2": 5,
        }
        return button_map.get(self.button_name, 4)  # default x2

    def start(self) -> None:
        """Start listening for mouse events."""
        self.stop()

        try:
            import pyinputcapture
        except ImportError:
            error_msg = tr("input_hook_wayland_missing")
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            return

        target_button = self._resolve_button()
        self._running = True

        def _on_button(button: int, pressed: bool, x: int, y: int) -> None:
            if not self._running:
                return
            if button != target_button:
                return
            try:
                if pressed:
                    self._pressed = True
                    if self.on_press is not None:
                        self.on_press(x, y)
                    else:
                        self.on_trigger()
                    return

                if not self._pressed:
                    return
                self._pressed = False
                if self.on_release is not None:
                    self.on_release(x, y)
            except Exception as exc:
                if self.on_error:
                    self.on_error(tr("input_hook_callback_error") + str(exc))

        def _on_motion(x: int, y: int) -> None:
            if not self._running or self.on_move is None:
                return
            try:
                self.on_move(x, y)
            except Exception as exc:
                if self.on_error:
                    self.on_error(tr("input_hook_callback_error") + str(exc))

        try:
            self._capture = pyinputcapture.InputCapture()
            self._capture.on_button = _on_button
            self._capture.on_motion = _on_motion
            self._capture.start()
            logger.info("Wayland mouse hook started (button=%s)", self.button_name)
        except Exception as exc:
            error_msg = tr("input_hook_wayland_error").format(error=str(exc))
            logger.error(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            self._capture = None

    def stop(self) -> None:
        """Stop listening for mouse events."""
        self._running = False
        if self._capture is not None:
            try:
                self._capture.stop()
            except Exception:
                pass
            self._capture = None

    def update_button(self, button_name: str) -> None:
        """Update the monitored mouse button."""
        self.button_name = button_name.lower().strip()
        self.start()
