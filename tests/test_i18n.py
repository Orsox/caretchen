from __future__ import annotations

from dictapaste.i18n import TRANSLATIONS, tr, set_locale, get_locale


class TestI18nCore:
    """Tests for the i18n translation infrastructure."""

    def test_tr_returns_key_when_missing(self) -> None:
        """Missing keys fall back to the key itself."""
        # Ensure we're on a known locale
        set_locale("en")
        assert tr("nonexistent_key") == "nonexistent_key"

    def test_tr_returns_english_translation(self) -> None:
        set_locale("en")
        assert tr("tray_quit") == "Quit"
        assert tr("tray_settings") == "Settings..."
        assert tr("tray_toggle_recording") == "Toggle Recording"

    def test_tr_returns_german_translation(self) -> None:
        set_locale("de")
        assert tr("tray_quit") == "Beenden"
        assert tr("tray_settings") == "Einstellungen..."
        assert tr("tray_toggle_recording") == "Toggle Recording"

    def test_tr_state_labels(self) -> None:
        set_locale("en")
        assert tr("tray_state_idle") == "Idle"
        assert tr("tray_state_recording") == "Recording"
        assert tr("tray_state_error") == "Error"

        set_locale("de")
        assert tr("tray_state_idle") == "Idle"
        assert tr("tray_state_error") == "Error"

    def test_tr_settings_labels(self) -> None:
        set_locale("en")
        assert tr("settings_runtime") == "Runtime"
        assert tr("settings_llm_base_url") == "LLM Base URL"
        assert tr("settings_history") == "Dictation History"
        assert tr("settings_logs") == "Logs"

        set_locale("de")
        assert tr("settings_runtime") == "Laufzeit"
        assert tr("settings_llm_base_url") == "LLM Base-URL"
        assert tr("settings_history") == "Diktierverlauf"
        assert tr("settings_logs") == "Logs"

    def test_tr_pipeline_messages(self) -> None:
        set_locale("en")
        assert tr("pipeline_busy") == "Dictation is busy. Wait for current processing to finish."
        assert tr("pipeline_pasted") == "Dictation pasted."
        assert tr("pipeline_no_speech") == "No speech detected."

        set_locale("de")
        assert tr("pipeline_busy") == "Dictation is busy. Wait for current processing to finish."
        assert tr("pipeline_pasted") == "Dictation pasted."

    def test_tr_history_labels(self) -> None:
        set_locale("en")
        assert tr("settings_history_entries") == "Entries: "
        assert tr("settings_history_copy") == "Copy Selection"
        assert tr("settings_history_clear") == "Clear History"
        assert tr("settings_history_empty") == "No entries."

        set_locale("de")
        assert tr("settings_history_entries") == "Eintraege: "
        assert tr("settings_history_copy") == "Auswahl kopieren"
        assert tr("settings_history_clear") == "Verlauf loeschen"
        assert tr("settings_history_empty") == "Keine Eintraege."

    def test_tr_log_labels(self) -> None:
        set_locale("en")
        assert tr("settings_log_open") == "Open Log File"
        assert tr("settings_log_clear") == "Clear Log"
        assert tr("settings_log_cleared") == "Log cleared."
        assert tr("settings_log_no_file") == "No log file found."

        set_locale("de")
        assert tr("settings_log_open") == "Log-Datei oeffnen"
        assert tr("settings_log_clear") == "Log loeschen"
        assert tr("settings_log_cleared") == "Log geloescht."
        assert tr("settings_log_no_file") == "Keine Log-Datei gefunden."

    def test_set_locale_invalid_falls_back_to_en(self) -> None:
        set_locale("xx")
        assert get_locale() == "en"
        assert tr("tray_quit") == "Quit"

    def test_get_locale(self) -> None:
        set_locale("de")
        assert get_locale() == "de"
        set_locale("en")
        assert get_locale() == "en"

    def test_translations_have_both_locales(self) -> None:
        """Every key should exist in both 'de' and 'en'."""
        de_keys = set(TRANSLATIONS["de"].keys())
        en_keys = set(TRANSLATIONS["en"].keys())
        assert de_keys == en_keys, f"Keys differ: de-only={de_keys - en_keys}, en-only={en_keys - de_keys}"
