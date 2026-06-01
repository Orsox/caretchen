"""Wayland-compatible mouse hook using Linux evdev.

This backend reads raw mouse button events from /dev/input/event* and therefore
works under Wayland, X11, and console sessions. It requires permission to read
input devices, usually via the `input` group or a udev rule.
"""

from __future__ import annotations

import logging
import select
import threading
from collections.abc import Callable

from .i18n import tr

logger = logging.getLogger(__name__)


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
        self._running = False
        self._thread: threading.Thread | None = None
        self._devices = []
        self._x = 0
        self._y = 0

    def _resolve_button_code(self) -> int:
        from evdev import ecodes

        button_map = {
            "left": ecodes.BTN_LEFT,
            "right": ecodes.BTN_RIGHT,
            "middle": ecodes.BTN_MIDDLE,
            "x1": ecodes.BTN_SIDE,
            "x2": ecodes.BTN_EXTRA,
        }
        return button_map.get(self.button_name, ecodes.BTN_SIDE)

    def _open_mouse_devices(self):
        from evdev import InputDevice, ecodes, list_devices

        devices = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
                caps = dev.capabilities(verbose=False)
                keys = caps.get(ecodes.EV_KEY, [])
                rels = caps.get(ecodes.EV_REL, [])
                has_mouse_buttons = any(
                    code in keys
                    for code in (
                        ecodes.BTN_LEFT,
                        ecodes.BTN_RIGHT,
                        ecodes.BTN_MIDDLE,
                        ecodes.BTN_SIDE,
                        ecodes.BTN_EXTRA,
                    )
                )
                has_motion = ecodes.REL_X in rels or ecodes.REL_Y in rels
                if has_mouse_buttons and has_motion:
                    devices.append(dev)
                    logger.info("evdev mouse device: %s (%s)", dev.name, dev.path)
                else:
                    dev.close()
            except PermissionError:
                # Keep scanning; if all fail, report below.
                logger.debug("No permission for input device %s", path)
            except OSError:
                logger.debug("Could not open input device %s", path)

        return devices

    def start(self) -> None:
        self.stop()

        try:
            import evdev  # noqa: F401
        except ImportError:
            msg = tr("input_hook_evdev_missing")
            logger.error(msg)
            if self.on_error:
                self.on_error(msg)
            return

        self._devices = self._open_mouse_devices()
        if not self._devices:
            msg = tr("input_hook_evdev_permission")
            logger.error(msg)
            if self.on_error:
                self.on_error(msg)
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("evdev mouse hook started (button=%s)", self.button_name)

    def _run(self) -> None:
        from evdev import ecodes

        target_code = self._resolve_button_code()
        device_by_fd = {dev.fd: dev for dev in self._devices}

        while self._running:
            try:
                readable, _, _ = select.select(device_by_fd, [], [], 0.25)
            except (OSError, ValueError):
                break

            for fd in readable:
                dev = device_by_fd.get(fd)
                if dev is None:
                    continue
                try:
                    for event in dev.read():
                        if event.type == ecodes.EV_REL:
                            if event.code == ecodes.REL_X:
                                self._x += int(event.value)
                            elif event.code == ecodes.REL_Y:
                                self._y += int(event.value)
                            if self._pressed and self.on_move is not None:
                                self._safe_move()
                            continue

                        if event.type != ecodes.EV_KEY or event.code != target_code:
                            continue

                        pressed = event.value == 1
                        released = event.value == 0
                        if pressed:
                            self._pressed = True
                            self._safe_press()
                        elif released and self._pressed:
                            self._pressed = False
                            self._safe_release()
                except OSError:
                    continue

    def _safe_press(self) -> None:
        try:
            if self.on_press is not None:
                self.on_press(self._x, self._y)
            else:
                self.on_trigger()
        except Exception as exc:
            if self.on_error:
                self.on_error(tr("input_hook_callback_error") + str(exc))

    def _safe_release(self) -> None:
        try:
            if self.on_release is not None:
                self.on_release(self._x, self._y)
        except Exception as exc:
            if self.on_error:
                self.on_error(tr("input_hook_callback_error") + str(exc))

    def _safe_move(self) -> None:
        try:
            if self.on_move is not None:
                self.on_move(self._x, self._y)
        except Exception as exc:
            if self.on_error:
                self.on_error(tr("input_hook_callback_error") + str(exc))

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        for dev in self._devices:
            try:
                dev.close()
            except OSError:
                pass
        self._devices = []

    def update_button(self, button_name: str) -> None:
        self.button_name = button_name.lower().strip()
        self.start()
