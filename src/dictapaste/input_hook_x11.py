"""X11 mouse hook using pynput.

This is the original X11-compatible implementation, extracted from input_hook.py
and used as the default backend when not running under Wayland.
"""

from __future__ import annotations

from collections.abc import Callable

from pynput.mouse import Button, Listener

from .i18n import tr

BUTTON_MAP = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
    "x1": Button.x1,
    "x2": Button.x2,
}


class MouseToggleHook:
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
        self._listener: Listener | None = None

    def _resolve_button(self) -> Button:
        return BUTTON_MAP.get(self.button_name, Button.x1)

    def start(self) -> None:
        self.stop()
        target_button = self._resolve_button()

        def _on_click(x, y, button, pressed) -> None:
            if button != target_button:
                return
            try:
                if pressed:
                    self._pressed = True
                    if self.on_press is not None:
                        self.on_press(int(x), int(y))
                    else:
                        self.on_trigger()
                    return

                if not self._pressed:
                    return
                self._pressed = False
                if self.on_release is not None:
                    self.on_release(int(x), int(y))
            except Exception as exc:
                if self.on_error:
                    self.on_error(tr("input_hook_callback_error") + str(exc))

        def _on_move(x, y) -> None:
            if not self._pressed or self.on_move is None:
                return
            try:
                self.on_move(int(x), int(y))
            except Exception as exc:
                if self.on_error:
                    self.on_error(tr("input_hook_callback_error") + str(exc))

        self._listener = Listener(on_click=_on_click, on_move=_on_move)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def update_button(self, button_name: str) -> None:
        self.button_name = button_name.lower().strip()
        self.start()
