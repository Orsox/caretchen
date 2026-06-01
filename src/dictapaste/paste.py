"""Text paste implementation with Wayland support.

Provides paste_text() with platform-aware backends:
  - X11: pynput.keyboard.Controller (Ctrl+V)
  - Wayland: ydotool → wtype → xdotool → clipboard fallback

On Wayland, tries native tools first, then falls back to xdotool and
clipboard-based methods. On X11, uses the original pynput approach.
"""

from __future__ import annotations

import sys as _sys
import time as _time

import pyperclip
from pynput.keyboard import Controller, Key  # noqa: F401 — for monkeypatch compatibility

from . import paste_wayland as _backend

PasteMode = _backend.PasteMode
_has_wayland_session = _backend._has_wayland_session
_paste_portal = _backend._paste_portal
_paste_wtype = _backend._paste_wtype
_paste_xdotool = _backend._paste_xdotool
_paste_ydotool = _backend._paste_ydotool

# Make sys and time accessible as module attributes for test monkeypatching.
sys = _sys
time = _time


def _sync_backend() -> None:
    """Propagate compatibility monkeypatches to the backend module."""
    _backend.pyperclip = pyperclip
    _backend.Controller = Controller
    _backend.Key = Key
    _backend.sys = sys
    _backend.time = time


def _copy_with_retry(text: str, attempts: int = 5) -> None:
    _sync_backend()
    return _backend._copy_with_retry(text, attempts=attempts)


def paste_text(text: str, mode: str = "ctrl_v") -> None:
    _sync_backend()
    return _backend.paste_text(text, mode=mode)


__all__ = [
    "PasteMode",
    "Controller",
    "Key",
    "_copy_with_retry",
    "_has_wayland_session",
    "_paste_portal",
    "_paste_wtype",
    "_paste_xdotool",
    "_paste_ydotool",
    "paste_text",
    "sys",
    "time",
    "pyperclip",
]
