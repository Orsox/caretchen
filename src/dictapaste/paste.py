from __future__ import annotations

import enum
import subprocess
import sys
import time

import pyperclip
from pynput.keyboard import Controller, Key

_CLIPBOARD_WRITE_ATTEMPTS = 5
_CLIPBOARD_SETTLE_SEC = 0.03
_KEY_PRESS_DELAY_SEC = 0.02


class PasteMode(str, enum.Enum):
    """How text is pasted into the focused application."""

    CTRL_V = "ctrl_v"  # Copy to clipboard + send Ctrl+V
    COPY = "copy"       # Copy to clipboard only
    XDOTOOL = "xdotool"  # Use xdotool (Linux only, falls back to Ctrl+V)


def _clipboard_matches(text: str) -> bool:
    try:
        return pyperclip.paste() == text
    except pyperclip.PyperclipException:
        return False


def _copy_with_retry(text: str) -> None:
    last_error: Exception | None = None

    for _ in range(_CLIPBOARD_WRITE_ATTEMPTS):
        try:
            pyperclip.copy(text)
        except pyperclip.PyperclipException as exc:
            last_error = exc
            time.sleep(_CLIPBOARD_SETTLE_SEC)
            continue

        time.sleep(_CLIPBOARD_SETTLE_SEC)
        if _clipboard_matches(text):
            return

    if last_error is not None:
        raise last_error

    pyperclip.copy(text)
    time.sleep(_CLIPBOARD_SETTLE_SEC)


def _send_ctrl_v(keyboard: Controller) -> None:
    keyboard.press(Key.ctrl)
    time.sleep(_KEY_PRESS_DELAY_SEC)
    keyboard.press("v")
    time.sleep(_KEY_PRESS_DELAY_SEC)
    keyboard.release("v")
    time.sleep(_KEY_PRESS_DELAY_SEC)
    keyboard.release(Key.ctrl)


def paste_text(text: str, mode: str = "ctrl_v") -> None:
    """Paste text using the specified mode.

    Args:
        text: The text to paste.
        mode: One of 'ctrl_v', 'copy', or 'xdotool'. Defaults to 'ctrl_v'.
    """
    if not text:
        return

    mode_lower = mode.lower().strip()

    if mode_lower == "copy":
        _copy_with_retry(text)
        return

    if mode_lower == "xdotool":
        if _try_xdotool(text):
            return
        # Fallback to ctrl_v if xdotool not available

    # Default: ctrl_v
    _copy_with_retry(text)
    keyboard = Controller()
    _send_ctrl_v(keyboard)


def _try_xdotool(text: str) -> bool:
    """Try to paste text using xdotool on Linux.

    Returns True if successful, False if xdotool is not available.
    """
    if sys.platform != "linux":
        return False

    try:
        subprocess.run(
            ["xdotool", "type", "--clearselection", "--", text],
            check=True,
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False
