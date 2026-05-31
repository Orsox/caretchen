from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from .modes import DictationMode, MODE_LABELS


class ModeSelectionPopup(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._selected_mode = DictationMode.IMPROVE
        self._buttons: dict[DictationMode, QPushButton] = {}

        frame = QFrame(self)
        frame.setObjectName("modeFrame")
        frame.setStyleSheet(
            "#modeFrame { background: rgba(24, 28, 36, 235); border: 1px solid rgba(255,255,255,70); border-radius: 12px; }"
            "QPushButton { color: white; background: rgba(255,255,255,28); border: 0; border-radius: 9px; padding: 8px 12px; font-weight: 600; }"
            "QPushButton[selected='true'] { background: #2f80ed; }"
            "QPushButton:hover { background: #2f80ed; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        for mode in DictationMode:
            button = QPushButton(MODE_LABELS[mode], frame)
            button.setMouseTracking(True)
            button.installEventFilter(self)
            button.setProperty("mode", mode.value)
            layout.addWidget(button)
            self._buttons[mode] = button

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(frame)
        self._refresh_selection()

    @property
    def selected_mode(self) -> DictationMode:
        return self._selected_mode

    def show_at(self, point: QPoint) -> None:
        self.adjustSize()
        self.move(point - QPoint(self.width() // 2, self.height() // 2))
        self.show()
        self.raise_()
        self.select_at_global(point)

    def select_at_global(self, point: QPoint) -> None:
        child = self.childAt(self.mapFromGlobal(point))
        while child is not None and not isinstance(child, QPushButton):
            child = child.parentWidget()
        if child is None:
            return

        mode_value = child.property("mode")
        for mode in DictationMode:
            if mode.value == mode_value:
                self._selected_mode = mode
                self._refresh_selection()
                break

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API name
        if event.type() == QEvent.Type.Enter:
            mode_value = obj.property("mode")
            for mode in DictationMode:
                if mode.value == mode_value:
                    self._selected_mode = mode
                    self._refresh_selection()
                    break
        return super().eventFilter(obj, event)

    def _refresh_selection(self) -> None:
        for mode, button in self._buttons.items():
            button.setProperty("selected", mode == self._selected_mode)
            button.style().unpolish(button)
            button.style().polish(button)


class ProcessingOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._tick = 0
        self._done = False
        self._level: float | None = None
        self._streaming = False
        self._label = QLabel("●", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self._label.setStyleSheet("color: white; background: transparent;")
        self.resize(54, 54)
        self._label.setGeometry(0, 0, 54, 54)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

    def show_at(self, point: QPoint) -> None:
        self.move(point - QPoint(27, 27))
        self._tick = 0
        self._done = False
        self._level = None
        self._streaming = False
        self._timer.start(120)
        self.show()
        self.raise_()

    def show_recording_level(self, level: float, point: QPoint | None = None) -> None:
        if point is not None and not self.isVisible():
            self.show_at(point)
        self._done = False
        self._streaming = False
        self._level = max(0.0, min(1.0, level))
        self._label.setText("")
        self.update()

    def show_streaming(self, point: QPoint | None = None) -> None:
        if point is not None and not self.isVisible():
            self.show_at(point)
        self._level = None
        self._streaming = True
        self._label.setText("↯")
        self.update()

    def show_done(self) -> None:
        if not self.isVisible():
            return
        self._timer.stop()
        self._done = True
        self._level = None
        self._streaming = False
        self._label.setText("✓")
        self.update()
        QTimer.singleShot(900, self.hide)

    def hide(self) -> None:  # noqa: A003 - Qt method override
        self._timer.stop()
        self._level = None
        self._streaming = False
        super().hide()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._level is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            bar_width = 6
            base = 44
            level = max(0.04, self._level)
            color_phases = [QColor("#27ae60"), QColor("#2f80ed"), QColor("#9b51e0")]
            color = color_phases[(self._tick // 10) % len(color_phases)]
            for index in range(5):
                wave = 0.72 + 0.14 * ((index + self._tick // 3) % 3)
                height = int(8 + min(1.0, level * 3.2 * wave) * 32)
                x = 8 + index * 8
                painter.setBrush(color.lighter(100 + index * 7))
                painter.drawRoundedRect(x, base - height, bar_width, height, 3, 3)
            return

        if self._done:
            painter.setBrush(QColor("#27ae60"))
        else:
            if self._streaming:
                colors = [QColor("#2f80ed"), QColor("#9b51e0"), QColor("#27ae60"), QColor("#f2994a")]
                painter.setBrush(colors[(self._tick // 18) % len(colors)])
            else:
                colors = [QColor("#2f80ed"), QColor("#9b51e0"), QColor("#27ae60"), QColor("#f2994a")]
                painter.setBrush(colors[(self._tick // 5) % len(colors)])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 46, 46)

    def _animate(self) -> None:
        self._tick += 1
        if self._streaming:
            self._label.setText("↯")
            return
        dots = ["●", "●·", "●··", "●···"]
        self._label.setText(dots[(self._tick // 2) % len(dots)])
        self.update()
