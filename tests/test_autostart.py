from unittest.mock import patch, MagicMock

from dictapaste.autostart import (
    AUTOSTART_SCRIPT_NAME,
    _LINUX_DESKTOP_NAME,
    _desktop_file_content,
    _linux_autostart_dir,
    _linux_desktop_path,
    _startup_script_content,
    _windows_startup_dir,
    _windows_startup_script_path,
    is_linux_autostart_enabled,
    is_windows_startup_enabled,
    set_autostart,
    set_linux_autostart,
    set_windows_startup,
)


# ── Windows ────────────────────────────────────────────────────────


def test_windows_startup_script_path():
    with patch("platform.system", return_value="Windows"):
        path = _windows_startup_script_path()

    assert path.name == AUTOSTART_SCRIPT_NAME
    assert "Startup" in str(path)


def test_windows_startup_script_content():
    content = _startup_script_content()
    assert content.startswith("@echo off")
    assert "dictapaste" in content.lower()


def test_set_windows_startup_creates_script(tmp_path):
    import dictapaste.autostart as autostart

    def fake_startup_dir():
        return tmp_path

    def fake_script_path():
        return tmp_path / AUTOSTART_SCRIPT_NAME

    original_dir = autostart._windows_startup_dir
    original_path = autostart._windows_startup_script_path

    autostart._windows_startup_dir = fake_startup_dir
    autostart._windows_startup_script_path = fake_script_path

    try:
        with patch("platform.system", return_value="Windows"):
            set_windows_startup(True)
            script = (tmp_path / AUTOSTART_SCRIPT_NAME).read_text(encoding="utf-8")
            assert script.startswith("@echo off")
            assert is_windows_startup_enabled() is True

            set_windows_startup(False)
            assert not (tmp_path / AUTOSTART_SCRIPT_NAME).exists()
            assert is_windows_startup_enabled() is False
    finally:
        autostart._windows_startup_dir = original_dir
        autostart._windows_startup_script_path = original_path


def test_set_windows_startup_noop_on_linux():
    with patch("platform.system", return_value="Linux"):
        set_windows_startup(True)
        # Should not raise, just no-op


# ── Linux ──────────────────────────────────────────────────────────


def test_linux_desktop_path():
    with patch("platform.system", return_value="Linux"):
        path = _linux_desktop_path()

    assert path.name == _LINUX_DESKTOP_NAME
    assert ".config" in str(path)


def test_desktop_file_content():
    content = _desktop_file_content()
    assert "[Desktop Entry]" in content
    assert "Type=Application" in content
    assert "Name=caretchen" in content
    assert "Exec=" in content


def test_set_linux_autostart_creates_desktop(tmp_path):
    import dictapaste.autostart as autostart

    def fake_autostart_dir():
        return tmp_path

    def fake_desktop_path():
        return tmp_path / _LINUX_DESKTOP_NAME

    original_dir = autostart._linux_autostart_dir
    original_path = autostart._linux_desktop_path

    autostart._linux_autostart_dir = fake_autostart_dir
    autostart._linux_desktop_path = fake_desktop_path

    try:
        with patch("platform.system", return_value="Linux"):
            set_linux_autostart(True)
            desktop = (tmp_path / _LINUX_DESKTOP_NAME).read_text(encoding="utf-8")
            assert "[Desktop Entry]" in desktop
            assert "Name=caretchen" in desktop
            assert is_linux_autostart_enabled() is True

            set_linux_autostart(False)
            assert not (tmp_path / _LINUX_DESKTOP_NAME).exists()
            assert is_linux_autostart_enabled() is False
    finally:
        autostart._linux_autostart_dir = original_dir
        autostart._linux_desktop_path = original_path


def test_set_linux_autostart_noop_on_windows():
    with patch("platform.system", return_value="Windows"):
        set_linux_autostart(True)
        # Should not raise, just no-op


# ── Unified ────────────────────────────────────────────────────────


def test_set_autostart_dispatches_to_windows():
    with patch("platform.system", return_value="Windows"), \
         patch("dictapaste.autostart.set_windows_startup") as mock_win:
        set_autostart(True)
        mock_win.assert_called_once_with(True)


def test_set_autostart_dispatches_to_linux():
    with patch("platform.system", return_value="Linux"), \
         patch("dictapaste.autostart.set_linux_autostart") as mock_linux:
        set_autostart(True)
        mock_linux.assert_called_once_with(True)


def test_set_autostart_noop_on_other_platforms():
    with patch("platform.system", return_value="Darwin"):
        set_autostart(True)
        # Should not raise
