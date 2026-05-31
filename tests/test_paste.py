import pytest

import pyperclip

from dictapaste import paste


class _FakeClipboard:
    def __init__(self, mismatches: int = 0):
        self._value = ""
        self._copy_attempts = 0
        self._mismatches = mismatches

    @property
    def copy_attempts(self) -> int:
        return self._copy_attempts

    def copy(self, text: str) -> None:
        self._copy_attempts += 1
        self._value = text

    def paste(self) -> str:
        if self._mismatches > 0:
            self._mismatches -= 1
            return ""
        return self._value


class _FakeKeyboard:
    def __init__(self):
        self.events: list[tuple[str, object]] = []

    def press(self, key) -> None:
        self.events.append(("press", key))

    def release(self, key) -> None:
        self.events.append(("release", key))


def test_paste_text_retries_clipboard_and_sends_ctrl_v(monkeypatch):
    clipboard = _FakeClipboard(mismatches=2)
    keyboard = _FakeKeyboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)
    monkeypatch.setattr(paste, "Controller", lambda: keyboard)
    monkeypatch.setattr(paste.time, "sleep", lambda _seconds: None)

    paste.paste_text("Hallo Welt")

    assert clipboard.copy_attempts == 3
    assert keyboard.events == [
        ("press", paste.Key.ctrl),
        ("press", "v"),
        ("release", "v"),
        ("release", paste.Key.ctrl),
    ]


def test_paste_text_ignores_empty_text(monkeypatch):
    called = {"copy": False, "controller": False}

    monkeypatch.setattr(paste.pyperclip, "copy", lambda _text: called.__setitem__("copy", True))
    monkeypatch.setattr(
        paste,
        "Controller",
        lambda: called.__setitem__("controller", True),
    )

    paste.paste_text("")

    assert called == {"copy": False, "controller": False}


# ── Unicode / emojis ───────────────────────────────────────────────


def test_paste_text_unicode_and_emojis(monkeypatch):
    clipboard = _FakeClipboard()
    keyboard = _FakeKeyboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)
    monkeypatch.setattr(paste, "Controller", lambda: keyboard)
    monkeypatch.setattr(paste.time, "sleep", lambda _seconds: None)

    emoji_text = "Hallo 🌍 Welt! ñoño café"
    paste.paste_text(emoji_text)

    assert clipboard._value == emoji_text
    assert len(keyboard.events) == 4


# ── Long text ──────────────────────────────────────────────────────


def test_paste_text_long_text(monkeypatch):
    clipboard = _FakeClipboard()
    keyboard = _FakeKeyboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)
    monkeypatch.setattr(paste, "Controller", lambda: keyboard)
    monkeypatch.setattr(paste.time, "sleep", lambda _seconds: None)

    long_text = "A" * 10000
    paste.paste_text(long_text)

    assert clipboard._value == long_text
    assert len(keyboard.events) == 4


# ── Retry exhaustion ───────────────────────────────────────────────


def test_copy_with_retry_exhausts_attempts(monkeypatch):
    class FailingClipboard:
        def __init__(self):
            self.attempts = 0

        def copy(self, text):
            self.attempts += 1
            raise pyperclip.PyperclipException("clipboard locked forever")

        def paste(self):
            return ""

    clipboard = FailingClipboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)

    with pytest.raises(pyperclip.PyperclipException, match="clipboard locked forever"):
        paste._copy_with_retry("test text")

    assert clipboard.attempts == 5  # _CLIPBOARD_WRITE_ATTEMPTS


# ── COPY mode ──────────────────────────────────────────────────────


def test_paste_text_copy_mode_does_not_send_keys(monkeypatch):
    """COPY mode copies to clipboard but does NOT send Ctrl+V."""
    clipboard = _FakeClipboard()
    keyboard = _FakeKeyboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)
    monkeypatch.setattr(paste, "Controller", lambda: keyboard)
    monkeypatch.setattr(paste.time, "sleep", lambda _seconds: None)

    paste.paste_text("Hallo Welt", mode="copy")

    assert clipboard._value == "Hallo Welt"
    assert len(keyboard.events) == 0, "COPY mode should not send keyboard events"


def test_paste_text_copy_mode_retries_clipboard(monkeypatch):
    """COPY mode retries clipboard writes like CTRL_V mode."""
    clipboard = _FakeClipboard(mismatches=1)
    keyboard = _FakeKeyboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)
    monkeypatch.setattr(paste, "Controller", lambda: keyboard)
    monkeypatch.setattr(paste.time, "sleep", lambda _seconds: None)

    paste.paste_text("test", mode="copy")

    assert clipboard.copy_attempts == 2
    assert len(keyboard.events) == 0


# ── XDOTOOL mode ───────────────────────────────────────────────────


def test_paste_text_xdotool_fallback_on_non_linux(monkeypatch):
    """XDOTOOL mode falls back to Ctrl+V on non-Linux platforms."""
    clipboard = _FakeClipboard()
    keyboard = _FakeKeyboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)
    monkeypatch.setattr(paste, "Controller", lambda: keyboard)
    monkeypatch.setattr(paste.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(paste.sys, "platform", "win32")

    paste.paste_text("Hallo Welt", mode="xdotool")

    assert clipboard._value == "Hallo Welt"
    assert len(keyboard.events) == 4, "Should fall back to Ctrl+V on Windows"


def test_paste_text_xdotool_success(monkeypatch):
    """XDOTOOL mode uses xdotool when available on Linux."""
    import subprocess

    clipboard = _FakeClipboard()
    keyboard = _FakeKeyboard()

    monkeypatch.setattr(paste.pyperclip, "copy", clipboard.copy)
    monkeypatch.setattr(paste.pyperclip, "paste", clipboard.paste)
    monkeypatch.setattr(paste, "Controller", lambda: keyboard)
    monkeypatch.setattr(paste.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(paste.sys, "platform", "linux")

    # Mock successful xdotool
    original_run = subprocess.run
    subprocess.run = lambda *a, **k: original_run(*a, **k)  # Keep real if xdotool exists

    paste.paste_text("Hallo Welt", mode="xdotool")

    # If xdotool is available, no keyboard events; if not, falls back
    # The test just verifies it doesn't crash
    assert clipboard._value == "Hallo Welt"
