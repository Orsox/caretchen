from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# Translations dictionary — German (existing) and English (new)
TRANSLATIONS: dict[str, dict[str, str]] = {
    "de": {
        # tray.py
        "tray_state_idle": "Idle",
        "tray_state_recording": "Recording",
        "tray_state_transcribing": "Transcribing",
        "tray_state_refining": "Refining",
        "tray_state_pasting": "Pasting",
        "tray_state_error": "Error",
        "tray_status_prefix": "State: ",
        "tray_hint_prefix": "Mouse ",
        "tray_hint_suffix": " toggles dictation",
        "tray_toggle_recording": "Toggle Recording",
        "tray_refine_llm": "Refine with LLM",
        "tray_retry_paste": "Einfügen wiederholen",
        "tray_settings": "Einstellungen...",
        "tray_quit": "Beenden",
        "tray_abort_recording": "Aufnahme abbrechen",
        "tray_cancel_llm": "LLM anhalten",
        "tray_copy_last": "Letztes Ergebnis kopieren",
        "tray_view_history": "Verlauf anzeigen",
        "tray_last_copied": "Letztes Ergebnis in die Zwischenablage kopiert.",
        "tray_no_last_result": "Kein vorheriges Ergebnis vorhanden.",
        "tray_conflict_warning": "Warnung: ",
        "tray_conflict_middle": "Middle-click pastet oft die Zwischenablage. Erwäge X1 oder X2.",
        "tray_conflict_left": "Linksklick ist die Hauptmaustaste. Erwäge X1/X2.",
        "tray_conflict_right": "Rechtsklick öffnet Kontextmenüs. Erwäge X1/X2.",
        "tray_conflict_x1": "X1 wird oft für 'Zurück'-Navigation verwendet. Erwäge X2.",
        "tray_conflict_x2": "X2 wird oft für 'Vorwärts'-Navigation verwendet. Erwäge X1.",
        "tray_settings_saved": "Einstellungen gespeichert.",
        "tray_autostart_error": "Autostart konnte nicht gesetzt werden: ",
        "tray_paste_notification": "Eingefügt: ",
        "tray_system_tray_unavailable": "System tray is not available on this system.",
        "tray_recording_prefix": "Recording ",

        # settings_dialog.py
        "settings_title": "caretchen Einstellungen",
        "settings_runtime": "Laufzeit",
        "settings_llm_base_url": "LLM Base-URL",
        "settings_llm_model": "LLM Modell",
        "settings_llm_timeout": "LLM Timeout (Sek)",
        "settings_llm_temperature": "LLM Temperatur",
        "settings_whisper_model": "Whisper Modell",
        "settings_whisper_model_hint": "Wähle das Whisper STT-Modell",
        "settings_language": "Sprache (auto oder Code)",
        "settings_mouse_button": "Maus-Taste zum Umschalten",
        "settings_audio_device": "Audio-Eingabegeraet",
        "settings_audio_refresh": "Aktualisieren",
        "settings_audio_refreshed": "Audio-Gerate aktualisiert.",
        "settings_audio_device_removed": "Ausgewaehltes Audio-Geraet ist nicht mehr verfuegbar.",
        "settings_audio_refresh_error": "Fehler beim Aktualisieren: ",
        "settings_paste_mode_label": "Einfuge-Modus",
        "settings_paste_mode_ctrl_v": "Strg+V (Kopieren + Einfugen)",
        "settings_paste_mode_copy": "Nur kopieren (nur Zwischenablage)",
        "settings_paste_mode_xdotool": "Xdotool (Linux, mit Fallback)",
        "settings_paste_mode_tooltip": "Wahle, wie Text eingefugt wird.",
        "settings_refine_default": "LLM-Nachbearbeitung standardmaessig aktivieren",
        "settings_start_with_windows": "Mit Windows starten",
        "settings_test_llm": "LLM-Verbindung testen",
        "settings_testing": "Teste Verbindung...",
        "settings_prompt_template": "Prompt-Template",
        "settings_prompt_hint": "Template muss {transcript} enthalten. Optional: {language}.",
        "settings_reset_prompt": "Auf Standard zuruecksetzen",
        "settings_audio_default": "System-Standard",
        "settings_history": "Diktierverlauf",
        "settings_history_entries": "Eintraege: ",
        "settings_history_copy": "Auswahl kopieren",
        "settings_history_clear": "Verlauf loeschen",
        "settings_history_empty": "Keine Eintraege.",
        "settings_history_search_placeholder": "Verlauf durchsuchen...",
        "settings_history_filtered": "Gezeigt: ",
        "settings_logs": "Logs",
        "settings_log_no_file": "Keine Log-Datei gefunden.",
        "settings_log_open": "Log-Datei oeffnen",
        "settings_log_clear": "Log loeschen",
        "settings_log_cleared": "Log geloescht.",
        "settings_log_read_error": "Fehler beim Lesen: ",
        "settings_llm_test_title": "LLM-Test",
        "settings_llm_test_success": "Verbindung erfolgreich!",
        "settings_llm_test_http_error": "HTTP ",
        "settings_llm_test_server_error": " — Server antwortet, aber Zugriff verweigert.",
        "settings_llm_test_connect_error": "Verbindung fehlgeschlagen — Server nicht erreichbar.",
        "settings_llm_test_timeout_error": "Timeout — Server antwortet nicht.",
        "settings_llm_test_generic_error": "Fehler: ",
        "settings_llm_test_no_url": "Bitte gib eine Base-URL ein.",
        "settings_invalid_prompt": "Ungueltiger Prompt",
        "settings_invalid_prompt_hint": "Das Template muss {transcript} enthalten.",
        "settings_clear_history_title": "Verlauf loeschen",
        "settings_clear_history_confirm": "Wirklich den gesamten Diktierverlauf loeschen?",
        "settings_clear_log_title": "Log loeschen",
        "settings_clear_log_confirm": "Wirklich die Log-Datei loeschen?",
        "settings_log_open_error": "Konnte Log nicht oeffnen: ",
        "settings_log_clear_error": "Konnte Log nicht loeschen: ",

        # input_hook.py
        "input_hook_callback_error": "Mouse hook callback failed: ",
        "input_hook_wayland_missing": "pyinputcapture not installed — Wayland portal mouse capture unavailable. Falling back to evdev.",
        "input_hook_wayland_error": "Wayland mouse hook failed: {error}",
        "input_hook_evdev_missing": "evdev is not installed — install with: pip install evdev",
        "input_hook_evdev_permission": "No readable mouse input devices. Add your user to the input group or configure a udev rule.",

        # pipeline.py
        "pipeline_busy": "Dictation is busy. Wait for current processing to finish.",
        "pipeline_recording_started": "Recording started.",
        "pipeline_recording_start_error": "Could not start recording: ",
        "pipeline_recording_stop_error": "Could not stop recording: ",
        "pipeline_no_audio": "No audio captured.",
        "pipeline_transcription_failed": "Transcription failed: ",
        "pipeline_no_speech": "No speech detected.",
        "pipeline_llm_unavailable": "LLM unavailable, using raw transcript. (",
        "pipeline_llm_error": "Unexpected LLM error, using raw transcript. (",
        "pipeline_contacting_llm": "Contacting LLM...",
        "pipeline_llm_cancelled": "LLM request cancelled, using raw transcript.",
        "pipeline_pasted": "Dictation pasted.",
        "pipeline_paste_failed": "Paste failed: ",
        "pipeline_retry_no_result": "No previous result to retry.",
        "pipeline_retry_failed": "Retry paste failed: ",
        "pipeline_recording_aborted": "Recording aborted.",

        # history.py
        "history_save_error": "Could not save history: ",
        "history_load_error": "Could not load history: ",

        # autostart.py
        "autostart_error": "Autostart error: ",
    },
    "en": {
        # tray.py
        "tray_state_idle": "Idle",
        "tray_state_recording": "Recording",
        "tray_state_transcribing": "Transcribing",
        "tray_state_refining": "Refining",
        "tray_state_pasting": "Pasting",
        "tray_state_error": "Error",
        "tray_status_prefix": "State: ",
        "tray_hint_prefix": "Mouse ",
        "tray_hint_suffix": " toggles dictation",
        "tray_toggle_recording": "Toggle Recording",
        "tray_refine_llm": "Refine with LLM",
        "tray_retry_paste": "Retry Paste",
        "tray_settings": "Settings...",
        "tray_quit": "Quit",
        "tray_abort_recording": "Abort Recording",
        "tray_cancel_llm": "Cancel LLM",
        "tray_copy_last": "Copy Last Result",
        "tray_view_history": "View History",
        "tray_last_copied": "Last result copied to clipboard.",
        "tray_no_last_result": "No previous result available.",
        "tray_conflict_warning": "Warning: ",
        "tray_conflict_middle": "Middle-click often pastes clipboard. Consider X1 or X2.",
        "tray_conflict_left": "Left-click is the primary button. Consider X1/X2.",
        "tray_conflict_right": "Right-click opens context menus. Consider X1/X2.",
        "tray_conflict_x1": "X1 is often used for 'Back' navigation. Consider X2.",
        "tray_conflict_x2": "X2 is often used for 'Forward' navigation. Consider X1.",
        "tray_settings_saved": "Settings saved.",
        "tray_autostart_error": "Could not set autostart: ",
        "tray_paste_notification": "Pasted: ",
        "tray_system_tray_unavailable": "System tray is not available on this system.",
        "tray_recording_prefix": "Recording ",

        # settings_dialog.py
        "settings_title": "caretchen Settings",
        "settings_runtime": "Runtime",
        "settings_llm_base_url": "LLM Base URL",
        "settings_llm_model": "LLM Model",
        "settings_llm_timeout": "LLM Timeout (sec)",
        "settings_llm_temperature": "LLM Temperature",
        "settings_whisper_model": "Whisper Model",
        "settings_whisper_model_hint": "Select the Whisper STT model",
        "settings_language": "Language (auto or code)",
        "settings_mouse_button": "Mouse button to toggle",
        "settings_audio_device": "Audio input device",
        "settings_audio_refresh": "Refresh",
        "settings_audio_refreshed": "Audio devices refreshed.",
        "settings_audio_device_removed": "Selected audio device is no longer available.",
        "settings_audio_refresh_error": "Error refreshing devices: ",
        "settings_paste_mode_label": "Paste Mode",
        "settings_paste_mode_ctrl_v": "Ctrl+V (Copy + Paste)",
        "settings_paste_mode_copy": "Copy Only (clipboard only)",
        "settings_paste_mode_xdotool": "Xdotool (Linux, with fallback)",
        "settings_paste_mode_tooltip": "Choose how text is pasted.",
        "settings_refine_default": "Enable LLM refinement by default",
        "settings_start_with_windows": "Start with Windows",
        "settings_test_llm": "Test LLM Connection",
        "settings_testing": "Testing...",
        "settings_prompt_template": "Prompt Template",
        "settings_prompt_hint": "Template must contain {transcript}. Optional: {language}.",
        "settings_reset_prompt": "Reset to Default",
        "settings_audio_default": "System Default",
        "settings_history": "Dictation History",
        "settings_history_entries": "Entries: ",
        "settings_history_copy": "Copy Selection",
        "settings_history_clear": "Clear History",
        "settings_history_empty": "No entries.",
        "settings_history_search_placeholder": "Search history...",
        "settings_history_filtered": "Showing: ",
        "settings_logs": "Logs",
        "settings_log_no_file": "No log file found.",
        "settings_log_open": "Open Log File",
        "settings_log_clear": "Clear Log",
        "settings_log_cleared": "Log cleared.",
        "settings_log_read_error": "Error reading: ",
        "settings_llm_test_title": "LLM Test",
        "settings_llm_test_success": "Connection successful!",
        "settings_llm_test_http_error": "HTTP ",
        "settings_llm_test_server_error": " — Server responded but access denied.",
        "settings_llm_test_connect_error": "Connection failed — server unreachable.",
        "settings_llm_test_timeout_error": "Timeout — server not responding.",
        "settings_llm_test_generic_error": "Error: ",
        "settings_llm_test_no_url": "Please enter a Base URL.",
        "settings_invalid_prompt": "Invalid Prompt",
        "settings_invalid_prompt_hint": "The template must contain {transcript}.",
        "settings_clear_history_title": "Clear History",
        "settings_clear_history_confirm": "Really delete the entire dictation history?",
        "settings_clear_log_title": "Clear Log",
        "settings_clear_log_confirm": "Really delete the log file?",
        "settings_log_open_error": "Could not open log: ",
        "settings_log_clear_error": "Could not clear log: ",

        # input_hook.py
        "input_hook_callback_error": "Mouse hook callback failed: ",
        "input_hook_wayland_missing": "pyinputcapture not installed — Wayland portal mouse capture unavailable. Falling back to evdev.",
        "input_hook_wayland_error": "Wayland mouse hook failed: {error}",
        "input_hook_evdev_missing": "evdev is not installed — install with: pip install evdev",
        "input_hook_evdev_permission": "No readable mouse input devices. Add your user to the input group or configure a udev rule.",

        # pipeline.py
        "pipeline_busy": "Dictation is busy. Wait for current processing to finish.",
        "pipeline_recording_started": "Recording started.",
        "pipeline_recording_start_error": "Could not start recording: ",
        "pipeline_recording_stop_error": "Could not stop recording: ",
        "pipeline_no_audio": "No audio captured.",
        "pipeline_transcription_failed": "Transcription failed: ",
        "pipeline_no_speech": "No speech detected.",
        "pipeline_llm_unavailable": "LLM unavailable, using raw transcript. (",
        "pipeline_llm_error": "Unexpected LLM error, using raw transcript. (",
        "pipeline_contacting_llm": "Contacting LLM...",
        "pipeline_llm_cancelled": "LLM request cancelled, using raw transcript.",
        "pipeline_pasted": "Dictation pasted.",
        "pipeline_paste_failed": "Paste failed: ",
        "pipeline_retry_no_result": "No previous result to retry.",
        "pipeline_retry_failed": "Retry paste failed: ",
        "pipeline_recording_aborted": "Recording aborted.",

        # history.py
        "history_save_error": "Could not save history: ",
        "history_load_error": "Could not load history: ",

        # autostart.py
        "autostart_error": "Autostart error: ",
    },
}


def _detect_locale() -> str:
    """Detect the system locale and return the best-matching translation key.

    Returns 'de' for German locale, 'en' as fallback.
    """
    import locale

    try:
        locale.setlocale(locale.LC_ALL, "")
        loc = locale.getlocale(locale.LC_ALL)
        if loc is not None:
            lang = loc[0].split("_")[0].lower() if loc[0] else ""
            if lang == "de":
                return "de"
    except Exception:
        pass

    # Fallback to environment variable
    env_lang = (
        __import__("os").environ.get("LC_ALL", "")
        or __import__("os").environ.get("LC_MESSAGES", "")
        or __import__("os").environ.get("LANG", "")
    )
    if env_lang.lower().startswith("de"):
        return "de"

    return "en"


# Cached locale — determined once at module import
_LOCALE: str = _detect_locale()


def tr(key: str) -> str:
    """Translate a string key to the current locale.

    Falls back to English if the locale is unknown, then to the key itself.
    """
    translations = TRANSLATIONS.get(_LOCALE, TRANSLATIONS["en"])
    return translations.get(key, key)


def set_locale(locale_name: str) -> None:
    """Override the auto-detected locale (for testing)."""
    global _LOCALE
    if locale_name not in TRANSLATIONS:
        logger.warning("Unknown locale '%s', falling back to English", locale_name)
        locale_name = "en"
    _LOCALE = locale_name


def get_locale() -> str:
    """Return the current locale."""
    return _LOCALE


def tr_conflict(button: str) -> str:
    """Get a conflict warning message for a mouse button.

    Returns an empty string if there is no known conflict.
    """
    key = f"tray_conflict_{button.lower().strip()}"
    return TRANSLATIONS.get(_LOCALE, TRANSLATIONS["en"]).get(key, "")
