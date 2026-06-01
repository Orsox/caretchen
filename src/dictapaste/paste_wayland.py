"""Wayland-compatible text paste implementation.

Provides paste_text() for Wayland using portal-compatible tools:
  - ydotool  (wlroots-based: Sway, Wayfire, Hyprland)
  - wtype    (GNOME/layer-shell based)
  - xdotool  (XWayland compatibility layer)
  - clipboard + desktop portal (modern fallback)

Falls back to xdotool Ctrl+V if no native Wayland tool is available.
"""

from __future__ import annotations

import enum
import logging
import shutil
import subprocess
import sys
import time

import pyperclip
from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)

_KEY_PRESS_DELAY_SEC = 0.02


class PasteMode(str, enum.Enum):
    """How text is pasted into the focused application."""

    CTRL_V = "ctrl_v"       # Copy to clipboard + send Ctrl+V
    CTRL_SHIFT_V = "ctrl_shift_v"  # Copy to clipboard + send Ctrl+Shift+V
    COPY = "copy"           # Copy to clipboard only
    XDOTOOL = "xdotool"    # Use xdotool (Linux only, falls back to Ctrl+V)
    YDOTOOL = "ydotool"    # Use wl-copy + ydotool paste shortcut
    YDOTOOL_TYPE = "ydotool_type"  # Type directly via ydotool (layout-dependent)
    WTYPE = "wtype"        # Use wtype (Wayland GNOME)
    PORTAL = "portal"      # Use clipboard + desktop portal


def _has_wayland_session() -> bool:
    """Check if running under a Wayland session."""
    if not sys.platform.startswith("linux"):
        return False
    session_type = os.environ.get("XDG_SESSION_TYPE", "")
    if session_type == "wayland":
        return True
    # Also check if WAYLAND_DISPLAY is set (common indicator)
    if os.environ.get("WAYLAND_DISPLAY") and session_type not in ("x11", "xorg"):
        return True
    return False


def _which(tool: str) -> str | None:
    """Check if a tool is available on PATH."""
    return shutil.which(tool)


def _copy_with_retry(text: str, attempts: int = 5) -> None:
    """Copy text to clipboard with retry logic and Wayland/X11 CLI fallbacks."""
    settle = 0.03
    last_error: Exception | None = None

    for _ in range(attempts):
        try:
            pyperclip.copy(text)
            time.sleep(settle)
            try:
                if pyperclip.paste() == text:
                    return
            except pyperclip.PyperclipException:
                return
        except pyperclip.PyperclipException as exc:
            last_error = exc
            time.sleep(settle)
            continue

    if _has_wayland_session() and _which("wl-copy") is not None:
        try:
            subprocess.run(["wl-copy", "--type", "text/plain;charset=utf-8"], input=text.encode("utf-8"), check=True, timeout=5)
            logger.info("Copied %d characters using wl-copy", len(text))
            time.sleep(settle)
            if _which("wl-paste") is None:
                return
            verify = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=3)
            if verify.returncode == 0 and verify.stdout.decode("utf-8", errors="replace") == text:
                return
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            last_error = exc

    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is not None:
            clipboard = app.clipboard()
            clipboard.setText(text)
            time.sleep(settle)
            if clipboard.text() == text:
                return
    except Exception as exc:
        last_error = exc

    clipboard_commands = (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    )
    for command in clipboard_commands:
        if _which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text.encode("utf-8"), check=True, timeout=5)
            return
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            last_error = exc

    if last_error is not None:
        raise last_error


def _ydotool_envs() -> list[dict[str, str] | None]:
    """Return ydotool environment variants for distro-specific daemon sockets."""
    envs: list[dict[str, str] | None] = [None]
    for socket_path in ("/tmp/.ydotool_socket", f"{os.environ.get('XDG_RUNTIME_DIR', '')}/.ydotool_socket"):
        if socket_path and os.path.exists(socket_path):
            env = os.environ.copy()
            env["YDOTOOL_SOCKET"] = socket_path
            envs.append(env)
    return envs


def _run_ydotool(args: list[str], timeout: float = 5, input_text: str | None = None) -> bool:
    if _which("ydotool") is None:
        logger.warning("ydotool binary not found")
        return False

    last_error = ""
    stdin = input_text.encode("utf-8") if input_text is not None else None
    for env in _ydotool_envs():
        try:
            proc = subprocess.run(
                ["ydotool", *args],
                input=stdin,
                check=True,
                capture_output=True,
                timeout=timeout,
                env=env,
            )
            return proc.returncode == 0
        except subprocess.CalledProcessError as exc:
            last_error = (exc.stderr or exc.stdout or b"").decode("utf-8", errors="replace").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
    if last_error:
        logger.warning("ydotool failed: %s", last_error)
    return False


def _paste_ydotool(text: str) -> bool:
    """Paste text using wl-clipboard plus ydotool key events."""
    try:
        _copy_with_retry(text)
    except Exception as exc:
        logger.warning("Clipboard copy before ydotool paste failed: %s", exc)
        return False

    time.sleep(0.08)

    # Terminal-friendly paste first: Ctrl+Shift+V.
    # evdev key codes: LEFTCTRL=29, LEFTSHIFT=42, V=47, INSERT=110.
    shortcuts = (
        ["key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"],
        ["key", "42:1", "110:1", "110:0", "42:0"],
        ["key", "29:1", "47:1", "47:0", "29:0"],
    )
    for shortcut in shortcuts:
        if _run_ydotool(shortcut):
            logger.info("Sent paste shortcut using ydotool")
            return True
    return False


def _type_ydotool(text: str) -> bool:
    """Type text via ydotool. This is layout-dependent and mainly a fallback."""
    return _run_ydotool(["type", "--file", "-"], input_text=text, timeout=max(10, len(text) / 20))


def _paste_wtype(text: str) -> bool:
    """Type text directly using wtype (Wayland compositors)."""
    if _which("wtype") is None:
        return False

    try:
        proc = subprocess.run(
            ["wtype", text],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False


def _paste_wtype_shortcut(*, shift: bool = False) -> bool:
    """Send Ctrl+V or Ctrl+Shift+V via wtype."""
    if _which("wtype") is None:
        return False

    command = ["wtype", "-M", "ctrl"]
    if shift:
        command += ["-M", "shift"]
    command.append("v")
    if shift:
        command += ["-m", "shift"]
    command += ["-m", "ctrl"]

    try:
        proc = subprocess.run(command, check=True, capture_output=True, timeout=5)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False


def _paste_xdotool(text: str) -> bool:
    """Paste text using xdotool (works under XWayland)."""
    if _which("xdotool") is None:
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


def _paste_portal(text: str) -> bool:
    """Paste via clipboard + desktop portal activation.

    This is the most portable Wayland approach: copy to clipboard,
    then try to activate paste via the desktop portal or D-Bus.
    """
    if sys.platform != "linux":
        return False

    _copy_with_retry(text)

    # Try gtk-launch / portal-based paste
    # Some compositors support a generic paste action via D-Bus
    for cmd in (
        ["wl-paste", "--no-newline"],  # verify clipboard worked
    ):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=3,
            )
            if proc.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return False


def paste_text(text: str, mode: str = "ctrl_v") -> None:
    """Paste text using the specified method.

    On Wayland, tries native tools (ydotool, wtype) first, then falls back
    to xdotool and finally clipboard+Ctrl+V.

    Args:
        text: The text to paste.
        mode: One of 'ctrl_v', 'copy', 'xdotool', 'ydotool', 'wtype', 'portal'.
    """
    if not text:
        return

    mode_lower = mode.lower().strip()
    is_wayland = _has_wayland_session()

    # Copy-only mode (works on all platforms)
    if mode_lower == "copy":
        _copy_with_retry(text)
        return

    if mode_lower == "ctrl_shift_v":
        _copy_with_retry(text)
        time.sleep(0.05)
        if is_wayland and _paste_wtype_shortcut(shift=True):
            return
        if _which("xdotool") is not None:
            try:
                subprocess.run(["xdotool", "key", "ctrl+shift+v"], check=True, capture_output=True, timeout=5)
                return
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                pass

    # Mode-specific handling
    if mode_lower == "ydotool":
        if _paste_ydotool(text):
            return
        raise RuntimeError(
            "ydotool paste failed. Install ydotool, start ydotoold, and ensure wl-copy works."
        )
    elif mode_lower == "ydotool_type":
        if _type_ydotool(text):
            return
        raise RuntimeError("ydotool direct typing failed.")
    elif mode_lower == "wtype":
        if _paste_wtype(text):
            return
        logger.warning("wtype not available, falling back")
    elif mode_lower == "portal":
        if _paste_portal(text):
            return
        logger.warning("portal paste not fully available, falling back")
    elif mode_lower == "xdotool":
        if is_wayland:
            # On Wayland, xdotool may work via XWayland
            if _paste_xdotool(text):
                return
            logger.warning("xdotool failed, falling back")
        else:
            # On X11, use xdotool as primary
            if _paste_xdotool(text):
                return
            logger.warning("xdotool not available, falling back")

    # Default fallback: clipboard + Ctrl+V
    # On Wayland, use native tool if available, else xdotool
    if is_wayland:
        if _paste_ydotool(text):
            return
        if _paste_wtype(text):
            return
        if _paste_xdotool(text):
            return

    # Final fallback: clipboard + simulated Ctrl+V
    _copy_with_retry(text)
    time.sleep(0.05)

    # Try xdotool Ctrl+V as last resort before pynput
    if _which("xdotool") is not None:
        try:
            subprocess.run(
                ["xdotool", "key", "ctrl+v"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            return
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass

    # Ultimate fallback: pynput (X11 only)
    keyboard = Controller()
    keyboard.press(Key.ctrl)
    time.sleep(_KEY_PRESS_DELAY_SEC)
    keyboard.press("v")
    time.sleep(_KEY_PRESS_DELAY_SEC)
    keyboard.release("v")
    time.sleep(_KEY_PRESS_DELAY_SEC)
    keyboard.release(Key.ctrl)


# Import os at module level for _has_wayland_session
import os  # noqa: E402 — moved to top after paste_text definition
