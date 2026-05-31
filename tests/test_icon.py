import pytest
from PySide6.QtWidgets import QApplication

from dictapaste.icon import build_state_icon, _build_state_pixmap, _STATE_COLORS


@pytest.fixture(autouse=True)
def _qt_app():
    """Ensure a QApplication exists for icon tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_build_state_pixmap_creates_valid_pixmap():
    pixmap = _build_state_pixmap("idle")
    assert not pixmap.isNull()
    assert pixmap.width() == 64
    assert pixmap.height() == 64


def test_build_state_pixmap_custom_size():
    pixmap = _build_state_pixmap("idle", size=32)
    assert pixmap.width() == 32
    assert pixmap.height() == 32


def test_build_state_icon_creates_valid_icon():
    icon = build_state_icon("recording")
    assert not icon.isNull()


def test_state_colors_defined():
    expected = {"idle", "recording", "transcribing", "refining", "pasting", "error"}
    assert set(_STATE_COLORS.keys()) == expected


def test_state_colors_have_hex_values():
    for color in _STATE_COLORS.values():
        assert color.startswith("#")
        assert len(color) == 7


def test_build_state_pixmap_unknown_state_falls_back():
    pixmap = _build_state_pixmap("unknown_state")
    assert not pixmap.isNull()
