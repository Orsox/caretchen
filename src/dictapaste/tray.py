from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

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
from .paste import paste_text
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
            paste_func=self._paste_output,
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
        self._paste_target_point = QPoint(0, 0)
        self._paste_target_window_id: str | None = None
        self._components_ready = False
        self._activity_phase = 0
        self._activity_state_name = "idle"
        self._activity_started_at = 0.0
        self._activity_generation = 0

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

        # Focus-independent feedback: the floating overlay is best-effort and can
        # be restacked/hidden by the window manager when the user clicks back into
        # the target app. The tray animation is decoupled from focus and remains
        # visible while processing continues.
        self._activity_timer = QTimer(self._app)
        self._activity_timer.timeout.connect(self._tick_tray_activity)
        self._activity_timer.setInterval(140)

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
        if self._pipeline.state == AppState.IDLE:
            self._paste_target_point = point
            self._paste_target_window_id = self._window_id_at_cursor()
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
            self._processing_overlay.show_at(self._processing_overlay_point())
            self._pipeline.toggle_recording(selected_mode)

    def _processing_overlay_point(self) -> QPoint:
        # Keep the processing overlay away from the original click target. On
        # Wayland floating Qt overlays are disabled entirely because they can steal
        # focus from the target app; this offset remains useful on X11.
        return self._last_release_point - QPoint(0, 112)

    def _retry_last_paste(self) -> None:
        self._pipeline.retry_last_paste()

    def _abort_recording(self) -> None:
        self._pipeline.abort_recording()

    def _cancel_llm(self) -> None:
        self._pipeline.cancel_llm()

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
            history=self._pipeline.history,
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

    def _notify_message(self, message: str) -> None:
        """Suppress routine popups, but surface errors that would otherwise be invisible."""
        error_markers = ("failed", "error", "unavailable", "No speech", "Paste failed", "Transcription failed")
        if message and any(marker in message for marker in error_markers):
            self._tray.setToolTip(f"{APP_DISPLAY_NAME} - {message}")
            self._status_action.setText(message)
            self._tray.showMessage(APP_DISPLAY_NAME, message, QSystemTrayIcon.MessageIcon.Warning, 4000)

    def _on_paste_notification(self, _text: str) -> None:
        """Suppress dictated text previews in system notifications."""
        return

    def _on_llm_stream_chunk(self, _chunk: str) -> None:
        self._processing_overlay.show_streaming(self._processing_overlay_point())

    def _on_audio_level(self, level: float) -> None:
        if self._pipeline.state != AppState.RECORDING:
            return
        if self._mode_popup.isVisible():
            # The recording equalizer is part of the mode popup layout, above the
            # buttons. This guarantees it cannot overlap labels like "Kurzfassung".
            self._mode_popup.show_recording_level(level)
            return

        point = QCursor.pos() - QPoint(0, 170)
        self._processing_overlay.show_recording_level(level, point)

    def _on_state_change(self, state: AppState) -> None:
        if state == AppState.TRANSCRIBING:
            self._processing_overlay.show_at(self._processing_overlay_point())
        elif state == AppState.REFINING:
            self._processing_overlay.show_streaming(self._processing_overlay_point())
        elif state == AppState.PASTING:
            self._processing_overlay.show_streaming(self._processing_overlay_point())

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

        if state in (AppState.TRANSCRIBING, AppState.REFINING, AppState.PASTING):
            self._start_tray_activity(state_name)
        elif state == AppState.ERROR:
            self._stop_tray_activity(state_name, keep_minimum_visible=False)
        else:
            self._stop_tray_activity(state_name)

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

    def _paste_output(self, text: str) -> None:
        """Paste after restoring the original target window when possible.

        The X2 mouse button can make the target application lose focus. If the
        user has to click back manually, the focused app often covers the overlay.
        Capturing the window under the cursor at recording start and activating it
        here decouples paste from that manual click.
        """
        if self._config.output.paste_mode.lower().strip() != "copy":
            self._restore_paste_target_window()
        paste_text(text, mode=self._config.output.paste_mode)

    def _window_id_at_cursor(self) -> str | None:
        if not sys.platform.startswith("linux"):
            return None

        if shutil.which("xdotool") is not None:
            try:
                proc = subprocess.run(
                    ["xdotool", "getmouselocation", "--shell"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                for line in proc.stdout.splitlines():
                    if not line.startswith("WINDOW="):
                        continue
                    window_id = line.split("=", 1)[1].strip()
                    if window_id and window_id != "0":
                        return window_id
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                pass

        return self._x11_window_id_at_cursor()

    def _x11_window_id_at_cursor(self) -> str | None:
        try:
            from Xlib import display

            disp = display.Display()
            root = disp.screen().root
            pointer = root.query_pointer()
            window = pointer.child
            if window is None:
                focus = disp.get_input_focus().focus
                if getattr(focus, "id", 0):
                    return str(focus.id)
                return None

            while True:
                tree = window.query_tree()
                if tree.parent.id == root.id:
                    return str(window.id)
                window = tree.parent
        except Exception:
            return None

    def _restore_paste_target_window(self) -> None:
        if self._restore_wayland_target_by_click():
            return

        window_id = self._paste_target_window_id
        if not window_id:
            return

        if shutil.which("xdotool") is not None:
            commands = (
                ["xdotool", "windowactivate", "--sync", window_id],
                ["xdotool", "windowfocus", "--sync", window_id],
            )
            for command in commands:
                try:
                    subprocess.run(command, check=True, capture_output=True, timeout=2)
                    time.sleep(0.12)
                    return
                except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    continue

        if self._x11_activate_window(window_id):
            time.sleep(0.12)

    def _restore_wayland_target_by_click(self) -> bool:
        # Wayland deliberately does not allow applications to activate arbitrary
        # windows. If the X2 button made the target lose focus, the only reliable
        # compositor-agnostic way to restore focus is an input event. Do it
        # automatically at the original cursor position so the user does not have
        # to click manually after processing.
        if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland" and not os.environ.get("WAYLAND_DISPLAY"):
            return False
        if shutil.which("ydotool") is None:
            return False

        x = self._paste_target_point.x()
        y = self._paste_target_point.y()
        if x <= 0 and y <= 0:
            return False

        commands = (
            ["ydotool", "mousemove", "--absolute", "--xpos", str(x), "--ypos", str(y)],
            ["ydotool", "click", "0xC0"],
        )
        try:
            # The overlay is offset from this point, but lower it once more before
            # the synthetic click so it cannot intercept input on strict WMs.
            if self._floating_overlays_enabled():
                self._processing_overlay.lower()
            for command in commands:
                subprocess.run(command, check=True, capture_output=True, timeout=2)
            if self._floating_overlays_enabled():
                self._processing_overlay.raise_()
            time.sleep(0.18)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return False

    def _x11_activate_window(self, window_id: str) -> bool:
        try:
            from Xlib import X, display, protocol

            disp = display.Display()
            root = disp.screen().root
            window = disp.create_resource_object("window", int(window_id))
            active_window_atom = disp.intern_atom("_NET_ACTIVE_WINDOW")
            event = protocol.event.ClientMessage(
                window=window,
                client_type=active_window_atom,
                data=(32, [1, X.CurrentTime, 0, 0, 0]),
            )
            root.send_event(
                event,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
            )
            try:
                window.set_input_focus(X.RevertToParent, X.CurrentTime)
            except Exception:
                pass
            disp.sync()
            return True
        except Exception:
            return False

    def _start_tray_activity(self, state_name: str) -> None:
        self._activity_generation += 1
        self._activity_state_name = state_name
        self._activity_started_at = time.monotonic()
        self._activity_phase = 0
        if not self._activity_timer.isActive():
            self._activity_timer.start()
        self._tick_tray_activity()

    def _stop_tray_activity(self, state_name: str, *, keep_minimum_visible: bool = True) -> None:
        if not self._activity_timer.isActive():
            self._tray.setIcon(build_state_icon(state_name))
            return

        elapsed_ms = int((time.monotonic() - self._activity_started_at) * 1000) if self._activity_started_at else 0
        if keep_minimum_visible and elapsed_ms < 1600:
            generation = self._activity_generation
            QTimer.singleShot(1600 - elapsed_ms, lambda: self._finish_tray_activity(generation, state_name))
            return

        self._finish_tray_activity(self._activity_generation, state_name)

    def _finish_tray_activity(self, generation: int, state_name: str) -> None:
        if generation != self._activity_generation:
            return
        self._activity_timer.stop()
        self._tray.setIcon(build_state_icon(state_name))

    def _tick_tray_activity(self) -> None:
        self._activity_phase += 1
        self._tray.setIcon(self._build_activity_icon(self._activity_state_name, self._activity_phase))

    @staticmethod
    def _build_activity_icon(state_name: str, phase: int) -> QIcon:
        colors = {
            "transcribing": "#FFC107",
            "refining": "#2196F3",
            "pasting": "#FF9800",
        }
        letters = {
            "transcribing": "T",
            "refining": "R",
            "pasting": "P",
        }
        dot_positions = [
            (32, 7),
            (48, 13),
            (57, 29),
            (51, 46),
            (35, 56),
            (18, 51),
            (8, 35),
            (13, 18),
        ]

        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.get(state_name, "#2f80ed")))
        painter.drawEllipse(2, 2, 59, 59)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, letters.get(state_name, "…"))

        x, y = dot_positions[phase % len(dot_positions)]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(x - 5, y - 5, 10, 10)
        painter.end()
        return QIcon(pixmap)

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
