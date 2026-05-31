from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from .app_state import AppState
from .autostart import set_autostart
from .config import AppConfig, load_config, save_config
from .history import DictationHistory
from .conflict import get_conflicts_for_button
from .i18n import tr
from .icon import build_state_icon, load_app_icon
from .input_hook import MouseToggleHook
from .mode_popup import ModeSelectionPopup, ProcessingOverlay
from .pipeline import DictationPipeline
from .prompt import load_prompt, save_prompt
from .settings_dialog import SettingsDialog


APP_DISPLAY_NAME = "Krätchen"
APP_READY_MESSAGE = "ich bin verfügbar"


class _TrayEventBridge(QObject):
    """Marshals callbacks from worker/pynput threads onto the Qt UI thread."""

    trigger_recording = Signal()
    mouse_pressed = Signal(int, int)
    mouse_released = Signal(int, int)
    mouse_moved = Signal(int, int)
    state_changed = Signal(object)
    message = Signal(str)
    paste_notification = Signal(str)
    llm_chunk = Signal(str)
    audio_level = Signal(float)
    ready = Signal()


class DictaPasteTrayApp:
    def __init__(self, app: QApplication) -> None:
        self._app = app

        self._config: AppConfig = load_config()
        self._prompt_template: str = load_prompt()

        self._bridge = _TrayEventBridge()
        self._bridge.state_changed.connect(self._on_state_change)
        self._bridge.message.connect(self._notify_message)
        self._bridge.paste_notification.connect(self._on_paste_notification)
        self._bridge.llm_chunk.connect(self._on_llm_stream_chunk)
        self._bridge.audio_level.connect(self._on_audio_level)
        self._bridge.ready.connect(self._show_ready_notification)
        self._bridge.mouse_pressed.connect(self._on_mouse_pressed)
        self._bridge.mouse_released.connect(self._on_mouse_released)
        self._bridge.mouse_moved.connect(self._on_mouse_moved)

        self._pipeline = DictationPipeline(
            config=self._config,
            prompt_template=self._prompt_template,
            state_callback=self._bridge.state_changed.emit,
            message_callback=self._bridge.message.emit,
            notification_callback=self._bridge.paste_notification.emit,
            stream_callback=self._bridge.llm_chunk.emit,
            audio_level_callback=self._bridge.audio_level.emit,
            history=DictationHistory(),
            preload_stt_model=True,
        )
        self._bridge.trigger_recording.connect(self._pipeline.toggle_recording)

        icon = load_app_icon()
        if icon.isNull():
            icon = QIcon.fromTheme("audio-input-microphone")
        if icon.isNull():
            icon = self._app.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
        if icon.isNull():
            icon = self._build_fallback_icon()

        self._tray = QSystemTrayIcon(icon, self._app)
        self._tray.setToolTip(APP_DISPLAY_NAME)
        self._mode_popup = ModeSelectionPopup()
        self._processing_overlay = ProcessingOverlay()
        self._last_release_point = QPoint(0, 0)
        self._components_ready = False

        self._menu = QMenu()

        # Quick Actions section
        self._copy_last_action = QAction(tr("tray_copy_last"), self._menu)
        self._copy_last_action.setEnabled(False)
        self._copy_last_action.triggered.connect(self._copy_last_result)

        self._view_history_action = QAction(tr("tray_view_history"), self._menu)
        self._view_history_action.triggered.connect(self._open_settings)

        # State indicator (colored dot + name)
        self._status_action = QAction(tr("tray_status_prefix") + tr("tray_state_idle"), self._menu)
        self._status_action.setEnabled(False)
        self._status_dot_action = QAction("  ● ", self._menu)
        self._status_dot_action.setEnabled(False)

        # Hint
        self._hint_action = QAction(f"{tr('tray_hint_prefix')}{self._config.input.mouse_button}{tr('tray_hint_suffix')}", self._menu)
        self._hint_action.setEnabled(False)

        self._menu.addAction(self._copy_last_action)
        self._menu.addAction(self._view_history_action)
        self._menu.addSeparator()
        self._menu.addAction(self._status_dot_action)
        self._menu.addAction(self._status_action)
        self._menu.addAction(self._hint_action)
        self._menu.addSeparator()

        # Recording controls
        self._toggle_action = QAction(tr("tray_toggle_recording"), self._menu)
        self._toggle_action.triggered.connect(self._pipeline.toggle_recording)

        self._refine_action = QAction(tr("tray_refine_llm"), self._menu)
        self._refine_action.setCheckable(True)
        self._refine_action.setChecked(self._pipeline.refine_enabled)
        self._refine_action.toggled.connect(self._pipeline.set_refine_enabled)

        self._abort_action = QAction(tr("tray_abort_recording"), self._menu)
        self._abort_action.setEnabled(False)
        self._abort_action.triggered.connect(self._abort_recording)

        self._cancel_llm_action = QAction(tr("tray_cancel_llm"), self._menu)
        self._cancel_llm_action.setEnabled(False)
        self._cancel_llm_action.triggered.connect(self._cancel_llm)

        self._menu.addAction(self._toggle_action)
        self._menu.addAction(self._refine_action)
        self._menu.addAction(self._abort_action)
        self._menu.addAction(self._cancel_llm_action)
        self._menu.addSeparator()

        # Error recovery
        self._retry_action = QAction(tr("tray_retry_paste"), self._menu)
        self._retry_action.setEnabled(False)
        self._retry_action.triggered.connect(self._retry_last_paste)
        self._menu.addAction(self._retry_action)
        self._menu.addSeparator()

        # Settings and quit
        self._settings_action = QAction(tr("tray_settings"), self._menu)
        self._settings_action.triggered.connect(self._open_settings)

        self._quit_action = QAction(tr("tray_quit"), self._menu)
        self._quit_action.triggered.connect(self.shutdown)

        self._menu.addAction(self._settings_action)
        self._menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_tray_activated)

        self._mouse_hook = MouseToggleHook(
            button_name=self._config.input.mouse_button,
            on_trigger=self._bridge.trigger_recording.emit,
            on_error=self._bridge.message.emit,
            on_press=self._bridge.mouse_pressed.emit,
            on_release=self._bridge.mouse_released.emit,
            on_move=self._bridge.mouse_moved.emit,
        )

        # Timer for updating recording duration display
        self._duration_timer = QTimer(self._app)
        self._duration_timer.timeout.connect(self._update_duration_display)
        self._duration_timer.start(500)  # Update every 500ms

    def start(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, APP_DISPLAY_NAME, tr("tray_system_tray_unavailable"))
            raise RuntimeError("System tray unavailable")

        self._apply_windows_startup_setting()
        self._check_button_conflict()

        self._tray.show()
        self._mouse_hook.start()
        self._start_readiness_check()

    def _start_readiness_check(self) -> None:
        worker = threading.Thread(target=self._wait_for_components_ready, daemon=True)
        worker.start()

    def _wait_for_components_ready(self) -> None:
        if self._pipeline.wait_until_ready(timeout=None):
            self._bridge.ready.emit()

    def _show_ready_notification(self) -> None:
        self._components_ready = True
        self._tray.setToolTip(f"{APP_DISPLAY_NAME} - {APP_READY_MESSAGE}")
        self._status_action.setText(APP_READY_MESSAGE)
        self._status_dot_action.setText(APP_READY_MESSAGE)

    def _on_mouse_pressed(self, _x: int, _y: int) -> None:
        point = QCursor.pos()
        self._mode_popup.show_at(point)
        if self._pipeline.state == AppState.IDLE:
            self._pipeline.toggle_recording(self._mode_popup.selected_mode)
        else:
            self._pipeline.toggle_recording()

    def _on_mouse_moved(self, _x: int, _y: int) -> None:
        if self._mode_popup.isVisible():
            self._mode_popup.select_at_global(QCursor.pos())

    def _on_mouse_released(self, _x: int, _y: int) -> None:
        self._last_release_point = QCursor.pos()
        selected_mode = self._mode_popup.selected_mode
        self._mode_popup.hide()
        if self._pipeline.state == AppState.RECORDING:
            self._processing_overlay.show_at(self._last_release_point)
            self._pipeline.toggle_recording(selected_mode)

    def _retry_last_paste(self) -> None:
        self._pipeline.retry_last_paste()

    def _abort_recording(self) -> None:
        self._pipeline.abort_recording()

    def _cancel_llm(self) -> None:
        self._pipeline._refiner.cancel()

    def _copy_last_result(self) -> None:
        """Copy the last pasted text to clipboard."""
        import pyperclip
        text = self._pipeline.last_output_text
        if text:
            pyperclip.copy(text)
            self._notify_message(tr("tray_last_copied"))
        else:
            self._notify_message(tr("tray_no_last_result"))

    def _check_button_conflict(self) -> None:
        """Check if the current mouse button has known conflicts and warn."""
        conflicts = get_conflicts_for_button(self._config.input.mouse_button)
        if conflicts:
            conflict = conflicts[0]
            i18n_key = f"tray_conflict_{self._config.input.mouse_button.lower().strip()}"
            warning = tr(i18n_key)
            if warning:
                self._notify_message(f"{tr('tray_conflict_warning')}{warning}")

    def _update_duration_display(self) -> None:
        if self._pipeline.state == AppState.RECORDING:
            duration = self._pipeline.recording_duration_sec
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            self._tray.setToolTip(f"{APP_DISPLAY_NAME} - {tr('tray_recording_prefix')}{minutes}:{seconds:02d}")
            self._abort_action.setEnabled(True)
            self._copy_last_action.setEnabled(False)
        else:
            self._abort_action.setEnabled(False)
            self._copy_last_action.setEnabled(bool(self._pipeline.last_output_text))

    def shutdown(self) -> None:
        self._mouse_hook.stop()
        self._tray.hide()
        self._app.quit()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self._config, self._prompt_template,
            history=self._pipeline._history,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_config, new_prompt = dialog.result_payload()

        self._config = new_config
        self._prompt_template = new_prompt

        save_config(self._config)
        save_prompt(self._prompt_template)

        self._pipeline.update_runtime(self._config, self._prompt_template)

        self._refine_action.blockSignals(True)
        self._refine_action.setChecked(self._config.llm.enabled_by_default)
        self._refine_action.blockSignals(False)

        self._pipeline.set_refine_enabled(self._config.llm.enabled_by_default)

        self._mouse_hook.update_button(self._config.input.mouse_button)
        self._hint_action.setText(f"{tr('tray_hint_prefix')}{self._config.input.mouse_button}{tr('tray_hint_suffix')}")

        self._apply_windows_startup_setting()
        self._check_button_conflict()

        self._components_ready = False
        self._start_readiness_check()

    def _notify_message(self, _message: str) -> None:
        """Suppress transient tray popups; readiness is announced separately."""
        return

    def _on_paste_notification(self, _text: str) -> None:
        """Suppress dictated text previews in system notifications."""
        return

    def _on_llm_stream_chunk(self, _chunk: str) -> None:
        self._processing_overlay.show_streaming(self._last_release_point)

    def _on_audio_level(self, level: float) -> None:
        if self._pipeline.state != AppState.RECORDING:
            return
        point = QCursor.pos() - QPoint(0, 58)
        self._processing_overlay.show_recording_level(level, point)

    def _on_state_change(self, state: AppState) -> None:
        labels = {
            AppState.IDLE: tr("tray_state_idle"),
            AppState.RECORDING: tr("tray_state_recording"),
            AppState.TRANSCRIBING: tr("tray_state_transcribing"),
            AppState.REFINING: tr("tray_state_refining"),
            AppState.PASTING: tr("tray_state_pasting"),
            AppState.ERROR: tr("tray_state_error"),
        }
        state_names = {
            AppState.IDLE: "idle",
            AppState.RECORDING: "recording",
            AppState.TRANSCRIBING: "transcribing",
            AppState.REFINING: "refining",
            AppState.PASTING: "pasting",
            AppState.ERROR: "error",
        }
        label = labels.get(state, "Unknown")
        state_name = state_names.get(state, "idle")
        self._status_action.setText(f"{tr('tray_status_prefix')}{label}")
        self._tray.setToolTip(f"{APP_DISPLAY_NAME} - {label}")
        self._tray.setIcon(build_state_icon(state_name))

        self._status_dot_action.setText(f"{tr('tray_status_prefix')}{label}")
        self._status_dot_action.setIcon(build_state_icon(state_name))

        if state == AppState.IDLE:
            self._processing_overlay.show_done()
        elif state == AppState.ERROR:
            self._processing_overlay.hide()

        # Show retry action only in ERROR state
        self._retry_action.setEnabled(state == AppState.ERROR)
        # Show cancel LLM action only during REFINING state
        self._cancel_llm_action.setEnabled(state == AppState.REFINING)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open_settings()
            return

        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._bridge.trigger_recording.emit()

    def _apply_windows_startup_setting(self) -> None:
        try:
            set_autostart(self._config.startup.start_with_windows)
        except Exception as exc:
            self._notify_message(f"{tr('tray_autostart_error')}{exc}")

    @staticmethod
    def _build_fallback_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor("#1E88E5"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 63, 63)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "C")
        painter.end()

        return QIcon(pixmap)
