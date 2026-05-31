from __future__ import annotations

import logging
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig, AudioConfig, InputConfig, LLMConfig, OutputConfig, STTConfig, StartupConfig, StreamingConfig
from .history import DictationHistory
from .i18n import tr
from .logging_setup import log_file_path
from .icon import load_app_icon
from .prompt import DEFAULT_PROMPT

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://[\w\-]+(\.[\w\-]+)+(:\d+)?(/[\w\-./]*)?$")


class _UrlValidator(QValidator):
    """Simple URL validator for QLineEdit."""

    def validate(self, text: str, pos: int) -> tuple[QValidator.State, str, int]:
        if not text.strip():
            return (QValidator.State.Intermediate, text, pos)
        if _URL_RE.match(text):
            return (QValidator.State.Acceptable, text, pos)
        return (QValidator.State.Invalid, text, pos)


_WHISPER_MODEL_HINTS = {
    "base": "~140 MB | schnell, weniger genau (~30 Sek.)",
    "small": "~460 MB | gut für Englisch (~60 Sek.)",
    "medium": "~1.5 GB | empfohlen für Deutsch (~3 Min.)",
    "large-v3": "~3 GB | beste Qualität (~6 Min.)",
}


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        prompt_template: str,
        history: DictationHistory | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.setMinimumSize(500, 400)
        self.resize(680, 560)

        self._history = history

        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        self._result_config: AppConfig | None = None
        self._result_prompt: str | None = None

        root = QVBoxLayout(self)

        # Scrollable content area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        runtime_group = QGroupBox(tr("settings_runtime"))
        runtime_form = QFormLayout(runtime_group)

        self.base_url_input = QComboBox()
        self.base_url_input.setEditable(True)
        self.base_url_input.addItems(["http://127.0.0.1:1234", "http://localhost:1234", "http://localhost:11434"])
        self.base_url_input.setCurrentText(config.llm.base_url)
        self.base_url_input.lineEdit().setPlaceholderText("http://127.0.0.1:1234")
        self.base_url_input.lineEdit().setValidator(_UrlValidator(self.base_url_input.lineEdit()))

        self.model_input = QComboBox()
        self.model_input.setEditable(True)
        self.model_input.addItems(["google/gemma-4-e4b", "qwen3:4b", "qwen3:8b", "llama3.1:8b", "borg-cpu"])
        self.model_input.setCurrentText(config.llm.model)

        self.timeout_input = QComboBox()
        self.timeout_input.setEditable(True)
        for label, seconds in [
            ("10 Sekunden", 10),
            ("20 Sekunden", 20),
            ("30 Sekunden", 30),
            ("1 Minute", 60),
            ("2 Minuten", 120),
            ("5 Minuten", 300),
        ]:
            self.timeout_input.addItem(label, seconds)
        self._set_combo_value(self.timeout_input, config.llm.timeout_sec, f"{config.llm.timeout_sec} Sekunden")

        self.temp_input = QComboBox()
        self.temp_input.setEditable(True)
        for label, value in [
            ("0.0 - deterministisch", 0.0),
            ("0.2 - empfohlen", 0.2),
            ("0.5 - ausgewogen", 0.5),
            ("0.8 - kreativ", 0.8),
            ("1.0 - sehr frei", 1.0),
        ]:
            self.temp_input.addItem(label, value)
        self._set_combo_value(self.temp_input, config.llm.temperature, f"{config.llm.temperature:.2f}")

        self.stt_model_input = QComboBox()
        self.stt_model_input.setEditable(True)
        for model in ["base", "small", "medium", "large-v3"]:
            self.stt_model_input.addItem(model, _WHISPER_MODEL_HINTS.get(model, ""))
        self.stt_model_input.setCurrentText(config.stt.model)
        self.stt_model_input.setToolTip(tr("settings_whisper_model_hint"))
        self.stt_model_input.currentTextChanged.connect(self._on_model_changed)

        self.language_input = QComboBox()
        self.language_input.setEditable(True)
        self.language_input.addItems(["auto", "de", "en", "fr", "es", "it"])
        self.language_input.setCurrentText(config.stt.language)

        self.mouse_button_input = QComboBox()
        self.mouse_button_input.addItems(["x1", "x2", "middle", "left", "right"])
        self.mouse_button_input.setCurrentText(config.input.mouse_button)

        # Audio device selector
        self.audio_device_input = QComboBox()
        self.audio_device_input.addItem(tr("settings_audio_default"), -1)
        try:
            from .audio import enumerate_input_devices
            for idx, name in enumerate_input_devices():
                if idx >= 0:
                    self.audio_device_input.addItem(name, idx)
        except Exception:
            pass  # No audio devices available

        self.refine_default_input = QCheckBox(tr("settings_refine_default"))
        self.refine_default_input.setChecked(config.llm.enabled_by_default)

        self.start_with_windows_input = QCheckBox(tr("settings_start_with_windows"))
        self.start_with_windows_input.setChecked(config.startup.start_with_windows)

        self.streaming_enabled_input = QComboBox()
        self.streaming_enabled_input.addItem("Streaming aktiviert", True)
        self.streaming_enabled_input.addItem("Streaming deaktiviert", False)
        self._set_combo_value(self.streaming_enabled_input, config.streaming.enabled, "Streaming aktiviert" if config.streaming.enabled else "Streaming deaktiviert")

        self.stt_chunking_input = QComboBox()
        self.stt_chunking_input.addItem("STT-Chunking aus", False)
        self.stt_chunking_input.addItem("STT-Chunking an", True)
        self._set_combo_value(self.stt_chunking_input, config.streaming.stt_chunking_enabled, "STT-Chunking an" if config.streaming.stt_chunking_enabled else "STT-Chunking aus")

        self.chunk_duration_input = QComboBox()
        for label, seconds in [
            ("1 Sekunde", 1),
            ("2 Sekunden", 2),
            ("3 Sekunden", 3),
            ("4 Sekunden", 4),
            ("5 Sekunden", 5),
            ("10 Sekunden", 10),
        ]:
            self.chunk_duration_input.addItem(label, seconds)
        self._set_combo_value(self.chunk_duration_input, config.streaming.chunk_duration_sec, f"{config.streaming.chunk_duration_sec} Sekunden")

        self.llm_start_mode_input = QComboBox()
        self.llm_start_mode_input.addItem("Finales Transkript verwenden", "final")
        self.llm_start_mode_input.addItem("Experimentell: Teiltranskript vorbereiten", "experimental_partial")
        self._set_combo_value(
            self.llm_start_mode_input,
            config.streaming.llm_start_mode,
            "Finales Transkript verwenden",
        )

        # Audio device with refresh button
        audio_layout = QHBoxLayout()
        self.audio_refresh_button = QPushButton(tr("settings_audio_refresh"))
        self.audio_refresh_button.clicked.connect(self._refresh_audio_devices)
        audio_layout.addWidget(self.audio_device_input)
        audio_layout.addWidget(self.audio_refresh_button)

        runtime_form.addRow(tr("settings_llm_base_url"), self.base_url_input)
        runtime_form.addRow(tr("settings_llm_model"), self.model_input)
        runtime_form.addRow(tr("settings_llm_timeout"), self.timeout_input)
        runtime_form.addRow(tr("settings_llm_temperature"), self.temp_input)
        runtime_form.addRow(tr("settings_whisper_model"), self.stt_model_input)
        self.model_info_label = QLabel(_WHISPER_MODEL_HINTS.get(config.stt.model, ""))
        self.model_info_label.setWordWrap(True)
        self.model_info_label.setStyleSheet("color: #666; font-size: 11px;")
        runtime_form.addRow("", self.model_info_label)
        runtime_form.addRow(tr("settings_language"), self.language_input)
        runtime_form.addRow(tr("settings_mouse_button"), self.mouse_button_input)

        # Paste mode selector
        self.paste_mode_input = QComboBox()
        self.paste_mode_input.addItems([tr("settings_paste_mode_ctrl_v"), tr("settings_paste_mode_copy"), tr("settings_paste_mode_xdotool")])
        mode_idx = {"ctrl_v": 0, "copy": 1, "xdotool": 2}.get(config.output.paste_mode, 0)
        self.paste_mode_input.setCurrentIndex(mode_idx)
        self.paste_mode_input.setToolTip(tr("settings_paste_mode_tooltip"))
        runtime_form.addRow(tr("settings_paste_mode_label"), self.paste_mode_input)
        runtime_form.addRow("Streaming", self.streaming_enabled_input)
        runtime_form.addRow("STT-Chunking", self.stt_chunking_input)
        runtime_form.addRow("Chunk-Länge", self.chunk_duration_input)
        runtime_form.addRow("LLM-Start", self.llm_start_mode_input)
        runtime_form.addRow(tr("settings_audio_device"), audio_layout)
        runtime_form.addRow("", self.refine_default_input)
        runtime_form.addRow("", self.start_with_windows_input)

        # LLM connection test
        self.test_llm_button = QPushButton(tr("settings_test_llm"))
        self.test_llm_button.clicked.connect(self._test_llm_connection)
        runtime_form.addRow("", self.test_llm_button)

        prompt_group = QGroupBox(tr("settings_prompt_template"))
        prompt_layout = QVBoxLayout(prompt_group)

        hint = QLabel(tr("settings_prompt_hint").format(transcript="{transcript}", language="{language}"))
        hint.setWordWrap(True)

        self.prompt_input = QPlainTextEdit(prompt_template)

        prompt_buttons = QHBoxLayout()
        self.reset_prompt_button = QPushButton(tr("settings_reset_prompt"))
        self.reset_prompt_button.clicked.connect(self._reset_prompt)
        prompt_buttons.addStretch()
        prompt_buttons.addWidget(self.reset_prompt_button)

        prompt_layout.addWidget(hint)
        prompt_layout.addWidget(self.prompt_input)
        prompt_layout.addLayout(prompt_buttons)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        scroll_layout.addWidget(runtime_group)
        scroll_layout.addWidget(prompt_group, 1)

        # History panel
        if self._history is not None:
            history_group = QGroupBox(tr("settings_history"))
            history_layout = QVBoxLayout(history_group)

            self.history_count_label = QLabel(f"{tr('settings_history_entries')}{self._history.count}")
            self.history_list = QTextEdit()
            self.history_list.setReadOnly(True)
            self.history_list.setMaximumHeight(120)
            self._refresh_history()

            # History search box
            self.history_search_input = QLineEdit()
            self.history_search_input.setPlaceholderText(tr("settings_history_search_placeholder"))
            self.history_search_input.textChanged.connect(self._on_history_search_changed)

            history_buttons = QHBoxLayout()
            self.copy_history_button = QPushButton(tr("settings_history_copy"))
            self.copy_history_button.clicked.connect(self._copy_selected_history)
            self.clear_history_button = QPushButton(tr("settings_history_clear"))
            self.clear_history_button.clicked.connect(self._clear_history)

            history_buttons.addWidget(self.copy_history_button)
            history_buttons.addStretch()
            history_buttons.addWidget(self.clear_history_button)

            history_layout.addWidget(self.history_count_label)
            history_layout.addWidget(self.history_search_input)
            history_layout.addWidget(self.history_list)
            history_layout.addLayout(history_buttons)
            scroll_layout.addWidget(history_group)

        # Log viewer panel
        log_group = QGroupBox(tr("settings_logs"))
        log_layout = QVBoxLayout(log_group)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(100)
        self._refresh_log()

        log_buttons = QHBoxLayout()
        self.open_log_button = QPushButton(tr("settings_log_open"))
        self.open_log_button.clicked.connect(self._open_log_file)
        self.clear_log_button = QPushButton(tr("settings_log_clear"))
        self.clear_log_button.clicked.connect(self._clear_log_file)

        log_buttons.addWidget(self.open_log_button)
        log_buttons.addStretch()
        log_buttons.addWidget(self.clear_log_button)

        log_layout.addWidget(self.log_view)
        log_layout.addLayout(log_buttons)
        scroll_layout.addWidget(log_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        root.addWidget(scroll)
        root.addWidget(buttons)

    def _on_model_changed(self, model: str) -> None:
        self.model_info_label.setText(_WHISPER_MODEL_HINTS.get(model, ""))

    @staticmethod
    def _set_combo_value(combo: QComboBox, value, fallback_label: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.addItem(fallback_label, value)
        combo.setCurrentIndex(combo.count() - 1)

    def _selected_timeout_sec(self) -> int:
        data = self.timeout_input.currentData()
        if data is not None:
            return int(data)
        text = self.timeout_input.currentText().lower().replace(",", ".").strip()
        number_match = re.search(r"\d+(?:\.\d+)?", text)
        if not number_match:
            return 20
        value = float(number_match.group(0))
        if "min" in text:
            value *= 60
        return max(1, min(300, int(round(value))))

    def _selected_temperature(self) -> float:
        data = self.temp_input.currentData()
        if data is not None:
            return float(data)
        text = self.temp_input.currentText().replace(",", ".").strip()
        number_match = re.search(r"\d+(?:\.\d+)?", text)
        if not number_match:
            return 0.2
        return max(0.0, min(2.0, float(number_match.group(0))))

    @staticmethod
    def _selected_bool(combo: QComboBox) -> bool:
        data = combo.currentData()
        if isinstance(data, bool):
            return data
        return combo.currentText().lower().strip() in {"true", "1", "ja", "yes", "an", "aktiviert", "enabled"}

    def _selected_chunk_duration_sec(self) -> int:
        data = self.chunk_duration_input.currentData()
        if data is not None:
            return int(data)
        text = self.chunk_duration_input.currentText().lower().replace(",", ".").strip()
        number_match = re.search(r"\d+(?:\.\d+)?", text)
        if not number_match:
            return 3
        value = int(round(float(number_match.group(0))))
        return value if value in (1, 2, 3, 4, 5, 10) else 3

    def _selected_paste_mode(self) -> str:
        mode_map = ["ctrl_v", "copy", "xdotool"]
        idx = self.paste_mode_input.currentIndex()
        return mode_map[idx] if idx < len(mode_map) else "ctrl_v"

    def _notify_error(self, message: str) -> None:
        QMessageBox.warning(self, "caretchen", message)

    def _notify_message(self, message: str) -> None:
        QMessageBox.information(self, "caretchen", message)

    def _refresh_audio_devices(self) -> None:
        """Re-enumerate audio devices and update the dropdown."""
        current_data = self.audio_device_input.currentData()
        current_index = self.audio_device_input.currentIndex()

        # Clear and rebuild
        self.audio_device_input.clear()
        self.audio_device_input.addItem(tr("settings_audio_default"), -1)

        try:
            from .audio import enumerate_input_devices
            for idx, name in enumerate_input_devices():
                if idx >= 0:
                    self.audio_device_input.addItem(name, idx)
        except Exception as exc:
            self._notify_error(tr("settings_audio_refresh_error") + str(exc))
            return

        # Restore previous selection if still available
        for i in range(self.audio_device_input.count()):
            if self.audio_device_input.itemData(i) == current_data:
                self.audio_device_input.setCurrentIndex(i)
                break
        else:
            # Selected device is no longer available
            if current_index > 0:  # Was a real device
                self._notify_error(tr("settings_audio_device_removed"))

        self._notify_message(tr("settings_audio_refreshed"))

    def _reset_prompt(self) -> None:
        self.prompt_input.setPlainText(DEFAULT_PROMPT)

    def _test_llm_connection(self) -> None:
        import httpx
        import threading

        base_url = self.base_url_input.currentText().strip()
        if not base_url:
            QMessageBox.warning(self, tr("settings_llm_test_title"), tr("settings_llm_test_no_url"))
            return

        self.test_llm_button.setEnabled(False)
        self.test_llm_button.setText(tr("settings_testing"))

        def _run_test() -> None:
            try:
                endpoint = base_url.rstrip("/") + "/v1/chat/completions"
                payload = {
                    "model": self.model_input.currentText().strip() or "test",
                    "messages": [{"role": "user", "content": "Say hi"}],
                    "max_tokens": 5,
                    "stream": False,
                }
                with httpx.Client(timeout=5) as client:
                    resp = client.post(endpoint, json=payload)
                    resp.raise_for_status()
                    resp.json()
                self._show_llm_test_result(True, tr("settings_llm_test_success"))
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else "?"
                if status in (401, 403):
                    msg = tr("settings_llm_test_http_error") + str(status) + tr("settings_llm_test_server_error")
                else:
                    msg = tr("settings_llm_test_http_error") + str(status)
                self._show_llm_test_result(status in (401, 403), msg)
            except httpx.ConnectError:
                self._show_llm_test_result(False, tr("settings_llm_test_connect_error"))
            except httpx.TimeoutException:
                self._show_llm_test_result(False, tr("settings_llm_test_timeout_error"))
            except Exception as exc:
                self._show_llm_test_result(False, tr("settings_llm_test_generic_error") + str(exc))
            finally:
                self.test_llm_button.setEnabled(True)
                self.test_llm_button.setText(tr("settings_test_llm"))

        threading.Thread(target=_run_test, daemon=True).start()

    def _show_llm_test_result(self, success: bool, message: str) -> None:
        if success:
            QMessageBox.information(self, tr("settings_llm_test_title"), message)
        else:
            QMessageBox.warning(self, tr("settings_llm_test_title"), message)

    def _validate_and_accept(self) -> None:
        prompt_template = self.prompt_input.toPlainText().strip()
        if "{transcript}" not in prompt_template:
            QMessageBox.warning(self, tr("settings_invalid_prompt"), tr("settings_invalid_prompt_hint").format(transcript="{transcript}"))
            return

        config = AppConfig(
            audio=AudioConfig(
                device_index=int(self.audio_device_input.currentData() if self.audio_device_input.currentData() is not None else -1),
            ),
            stt=STTConfig(
                model=self.stt_model_input.currentText().strip() or "medium",
                language=self.language_input.currentText().strip() or "auto",
            ),
            llm=LLMConfig(
                enabled_by_default=self.refine_default_input.isChecked(),
                base_url=self.base_url_input.currentText().strip() or "http://127.0.0.1:1234",
                model=self.model_input.currentText().strip() or "google/gemma-4-e4b",
                timeout_sec=self._selected_timeout_sec(),
                temperature=self._selected_temperature(),
            ),
            input=InputConfig(
                mouse_button=self.mouse_button_input.currentText().strip() or "x1",
            ),
            output=OutputConfig(paste_mode=self._selected_paste_mode()),
            startup=StartupConfig(
                start_with_windows=self.start_with_windows_input.isChecked(),
            ),
            streaming=StreamingConfig(
                enabled=self._selected_bool(self.streaming_enabled_input),
                stt_chunking_enabled=self._selected_bool(self.stt_chunking_input),
                chunk_duration_sec=self._selected_chunk_duration_sec(),
                llm_start_mode=str(self.llm_start_mode_input.currentData() or "final"),
            ),
        )

        self._result_config = config
        self._result_prompt = prompt_template
        self.accept()

    def result_payload(self) -> tuple[AppConfig, str]:
        if self._result_config is None or self._result_prompt is None:
            raise RuntimeError("Settings were not accepted.")
        return self._result_config, self._result_prompt

    def _refresh_history(self, filter_text: str = "") -> None:
        if self._history is None:
            return
        entries = self._history.entries[-20:]  # Last 20 entries

        # Apply filter
        if filter_text:
            ft = filter_text.lower()
            entries = [
                e for e in entries
                if ft in e.raw_text.lower() or ft in e.refined_text.lower()
            ]

        # Update count label with filter info
        if filter_text:
            self.history_count_label.setText(
                f"{tr('settings_history_entries')}{self._history.count} "
                f"({tr('settings_history_filtered')}{len(entries)})"
            )
        else:
            self.history_count_label.setText(f"{tr('settings_history_entries')}{self._history.count}")

        lines: list[str] = []
        for entry in entries:
            ts = entry.timestamp[:19].replace("T", " ") if entry.timestamp else "?"
            source = " [LLM]" if entry.was_refined else ""
            preview = (entry.refined_text if entry.was_refined else entry.raw_text)[:80]
            lines.append(f"[{ts}]{source} {preview}")
        self.history_list.setText("\n".join(lines) if lines else tr("settings_history_empty"))

    def _on_history_search_changed(self, text: str) -> None:
        self._refresh_history(filter_text=text.strip())

    def _copy_selected_history(self) -> None:
        import pyperclip
        selected = self.history_list.toPlainText().strip()
        if selected:
            pyperclip.copy(selected)

    def _clear_history(self) -> None:
        if self._history is None:
            return
        reply = QMessageBox.question(
            self, tr("settings_clear_history_title"),
            tr("settings_clear_history_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history.clear()
            self._refresh_history()

    def _refresh_log(self) -> None:
        log_path = log_file_path()
        if not log_path.exists():
            self.log_view.setText(tr("settings_log_no_file"))
            return
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.log_view.setText("\n".join(lines[-100:]))
        except Exception as exc:
            self.log_view.setText(tr("settings_log_read_error") + str(exc))

    def _open_log_file(self) -> None:
        import subprocess
        import sys

        log_path = log_file_path()
        if not log_path.exists():
            QMessageBox.warning(self, tr("settings_logs"), "Keine Log-Datei gefunden.")
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["notepad.exe", str(log_path)])
            else:
                subprocess.Popen(["xdg-open", str(log_path)])
        except Exception as exc:
            QMessageBox.warning(self, "Logs", tr("settings_log_open_error") + str(exc))

    def _clear_log_file(self) -> None:
        reply = QMessageBox.question(
            self, tr("settings_clear_log_title"),
            tr("settings_clear_log_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            log_path = log_file_path()
            try:
                if log_path.exists():
                    log_path.unlink()
                self.log_view.setText(tr("settings_log_cleared"))
            except Exception as exc:
                QMessageBox.warning(self, "Logs", tr("settings_log_clear_error") + str(exc))
