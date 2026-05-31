from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def load_app_icon() -> QIcon:
    module_dir = Path(__file__).resolve().parent
    candidates = [
        module_dir / "assets" / "caretchen_tray.svg",
    ]

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "dictapaste" / "assets" / "caretchen_tray.svg")

    for path in candidates:
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon

    return QIcon()


# Color palette for state icons
_STATE_COLORS = {
    "idle": "#27AE60",       # green, never gray
    "recording": "#4CAF50",  # green
    "transcribing": "#FFC107",  # yellow/amber
    "refining": "#2196F3",   # blue
    "pasting": "#FF9800",    # orange
    "error": "#F44336",      # red
}


def _build_state_pixmap(state: str, size: int = 64) -> QPixmap:
    """Build a colored circle pixmap for a given state."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    color = _STATE_COLORS.get(state, "#27AE60")
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, size - 5, size - 5)

    # Draw state letter
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 26, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, state[0].upper())
    painter.end()

    return pixmap


def build_state_icon(state: str) -> QIcon:
    """Build a QIcon from a state name string."""
    return QIcon(_build_state_pixmap(state))
