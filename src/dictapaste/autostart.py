from __future__ import annotations

from pathlib import Path
import os
import platform
import sys

AUTOSTART_SCRIPT_NAME = "caretchen_autostart.cmd"
_LINUX_DESKTOP_NAME = "caretchen.desktop"


def _linux_autostart_dir() -> Path:
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "autostart"
    return Path.home() / ".config" / "autostart"


def _linux_desktop_path() -> Path:
    return _linux_autostart_dir() / _LINUX_DESKTOP_NAME


def _desktop_file_content() -> str:
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        cmd = f'"{exe}"'
    else:
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            cmd = f'"{pythonw}" -m dictapaste.main'
        else:
            cmd = f'"{exe}" -m dictapaste.main'
    return (
        f"[Desktop Entry]\n"
        f"Type=Application\n"
        f"Name=caretchen\n"
        f"Comment=System tray dictation app\n"
        f"Exec={cmd}\n"
        f"Hidden=false\n"
        f"NoDisplay=false\n"
        f"X-GNOME-Autostart-enabled=true\n"
    )


def is_linux_autostart_enabled() -> bool:
    if platform.system() != "Linux":
        return False
    return _linux_desktop_path().exists()


def set_linux_autostart(enabled: bool) -> None:
    if platform.system() != "Linux":
        return

    desktop_path = _linux_desktop_path()

    if enabled:
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        desktop_path.write_text(_desktop_file_content(), encoding="utf-8")
        return

    if desktop_path.exists():
        desktop_path.unlink()


def _windows_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _windows_startup_script_path() -> Path:
    return _windows_startup_dir() / AUTOSTART_SCRIPT_NAME


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}"'

    python_exe = Path(sys.executable)
    pythonw_exe = python_exe.with_name("pythonw.exe")
    if pythonw_exe.exists():
        python_exe = pythonw_exe

    return f'"{python_exe}" -m dictapaste.main'


def _startup_script_content() -> str:
    command = _startup_command()
    return f"@echo off\r\nstart \"\" {command}\r\n"


def is_windows_startup_enabled() -> bool:
    if platform.system() != "Windows":
        return False
    return _windows_startup_script_path().exists()


def set_windows_startup(enabled: bool) -> None:
    if platform.system() != "Windows":
        return

    script_path = _windows_startup_script_path()

    if enabled:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(_startup_script_content(), encoding="utf-8")
        return

    if script_path.exists():
        script_path.unlink()


def set_autostart(enabled: bool) -> None:
    """Unified entry point: dispatches to platform-specific autostart."""
    system = platform.system()
    if system == "Windows":
        set_windows_startup(enabled)
    elif system == "Linux":
        set_linux_autostart(enabled)
    # macOS and others: no-op
