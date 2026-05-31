# SPEC.md — DictaPaste (Krätchen)

## 1. Zweck und Scope

DictaPaste ist eine lokale Tray-Diktier-App für Windows und Linux/X11. Die App soll gesprochene Sprache mit möglichst wenig Interaktion in direkt verwendbaren Text umwandeln und in die aktuell fokussierte Anwendung einfügen.

Nicht-Ziele für diese Version:

- Kein Wayland-Support als offizielles Ziel.
- Keine Cloud-Pflicht für STT oder LLM.
- Kein Hauptfenster als primäre Bedienoberfläche.
- Keine garantierte Nutzung der gewählten Maustaste durch andere Anwendungen während DictaPaste läuft.

## 2. Zielplattformen

| Plattform | Status | Hinweise |
|---|---|---|
| Windows | unterstützt | Tray-App, Startup-Ordner-Autostart, Clipboard + `Ctrl+V`. |
| Linux/X11 | unterstützt | Tray-App, `.desktop`-Autostart, optional `xdotool`. |
| Linux/Wayland | nicht offiziell unterstützt | Globale Hooks und Paste-Verhalten sind nicht garantiert. |

Python-Version: **3.11 oder neuer**.

## 3. Kern-Workflow

1. App startet als System-Tray-Anwendung.
2. Konfiguration und Prompt werden geladen oder mit Defaults erzeugt.
3. Whisper-Transcriber wird optional im Hintergrund vorgewärmt.
4. Globaler Maus-Hook wird für den konfigurierten Button gestartet.
5. Nutzer drückt den Button.
6. Bei Start:
   - Modus-Popup wird angezeigt.
   - Audioaufnahme beginnt.
   - Zustand wird `RECORDING`.
   - Optional startet Streaming-Vorbereitung/STT-Chunking.
7. Nutzer beendet die Aufnahme.
8. Pipeline stoppt Recorder und wechselt zu `TRANSCRIBING`.
9. Whisper erzeugt ein finales Transkript.
10. Falls kein Text erkannt wird: Rückkehr zu `IDLE`.
11. Falls Diktat als Slash-Command auflösbar ist oder Command-Modus aktiv ist: Command-Ausgabe ohne LLM verwenden.
12. Falls der Modus **Direkt** aktiv ist: rohes Transkript ohne LLM verwenden.
13. Falls LLM-Verfeinerung aktiv ist: Zustand `REFINING`, Prompt bauen, LLM aufrufen.
13. Bei LLM-Fehler, Timeout, Abbruch oder Nichtverfügbarkeit: rohes Transkript verwenden.
14. Zustand `PASTING`; Ergebnis wird gemäß Paste-Modus ausgegeben.
15. Erfolgreiche Ergebnisse werden in der Historie gespeichert.
16. Letztes Ergebnis wird für Copy/Retry gehalten.
17. Rückkehr zu `IDLE`.

## 4. Zustandsmaschine

Enum: `src/dictapaste/app_state.py`

```text
IDLE → RECORDING → TRANSCRIBING → REFINING → PASTING → IDLE
                         │             │           │
                         └─────────────┴───────────┴→ ERROR → IDLE
```

Zustände:

- `IDLE`: bereit für neue Aufnahme.
- `RECORDING`: Audioaufnahme läuft.
- `TRANSCRIBING`: Whisper verarbeitet Audio.
- `REFINING`: optionaler LLM-Schritt läuft.
- `PASTING`: Text wird ausgegeben.
- `ERROR`: Fehlerzustand; danach Rückkehr zu `IDLE`.

## 5. Benutzeroberfläche

### 5.1 Tray-App

Implementierung: `src/dictapaste/tray.py`

Anzeigename: **Krätchen**  
Bereitschaftsnachricht: **ich bin verfügbar**

Tray-Funktionen:

- Statusanzeige mit State-Text und State-Icon.
- Hinweis auf aktive Maustaste.
- Aufnahme manuell starten/stoppen.
- LLM-Verfeinerung umschalten.
- Aufnahme abbrechen.
- LLM-Verfeinerung abbrechen.
- Letztes Ergebnis kopieren.
- Paste wiederholen.
- Settings/Historie öffnen.
- App beenden.
- Konfliktwarnung bei problematischer Maustaste.

### 5.2 Modus-Popup

Implementierung: `src/dictapaste/mode_popup.py`

Wird an der Cursorposition angezeigt, wenn die Maustaste gedrückt wird. Mausbewegung kann die Auswahl ändern. Beim Loslassen wird die gewählte Aktion für die Verarbeitung genutzt.

### 5.3 Processing-Overlay

Zeigt während Verarbeitung u. a. Audiolevel, Streaming-LLM-Ausgabe und Done-Status an.

### 5.4 Settings-Dialog

Implementierung: `src/dictapaste/settings_dialog.py`

Konfigurierbar:

- LLM-Base-URL (`http://127.0.0.1:1234`, `http://localhost:1234`, `http://localhost:11434` usw.).
- LLM-Modell (`google/gemma-4-e4b`, `qwen3:4b`, `qwen3:8b`, `llama3.1:8b`, `borg-cpu` usw.).
- LLM-Timeout: 10 s, 20 s, 30 s, 1 min, 2 min, 5 min.
- LLM-Temperatur: 0.0, 0.2, 0.5, 0.8, 1.0.
- Whisper-Modell: `base`, `small`, `medium`, `large-v3`.
- Sprache: `auto`, `de`, `en`, `fr`, `es`, `it`.
- Maustaste: `x1`, `x2`, `middle`, `left`, `right`.
- Audio-Gerät inkl. Refresh.
- Paste-Modus: `ctrl_v`, `copy`, `xdotool`.
- Streaming aktiviert/deaktiviert.
- STT-Chunking aktiviert/deaktiviert.
- Chunk-Länge: 1, 2, 3, 4, 5 Sekunden.
- LLM-Startmodus: `final` oder `experimental_partial`.
- Start mit Windows/Linux.
- Prompt-Template inklusive Reset auf Standard.
- LLM-Verbindungstest.
- Logs öffnen/leeren.
- Diktier-Historie suchen, kopieren, leeren.

## 6. Diktiermodi

Implementierung: `src/dictapaste/modes.py`

| Modus | Wert | Zweck |
|---|---|---|
| Verbessern | `improve` | Text bereinigen und als direkt verwendbare Endfassung ausgeben. |
| Prompt | `prompt` | Aus Diktat einen direkt nutzbaren Prompt erzeugen. |
| Kurzfassung | `summarize` | Text kurz und verwendbar verdichten. |
| Übersetzen | `translate` | Deutsch nach Englisch, sonst nach Deutsch übersetzen. |
| Befehl | `command` | Diktat in Slash-Befehl umwandeln. |
| Direkt | `direct` | Rohes Transkript direkt ohne LLM-Verarbeitung ausgeben. |

Jeder LLM-basierte Modus ergänzt den Basis-Prompt um eine spezifische Aufgabe und verlangt ausschließlich das finale Ergebnis ohne Überschrift, Liste, Erklärung, Analyse oder Denkprozess. Der Modus **Direkt** nutzt keinen LLM und gibt das finale STT-Transkript unverändert weiter.

## 7. Audio

Implementierung: `src/dictapaste/audio.py`

Anforderungen:

- Aufnahme über `sounddevice`.
- Mono-Verarbeitung; mehrkanaliges Audio wird zu Mono gemischt.
- Ziel-Samplerate aus Recorder-Paket, Projektkonzept: 16 kHz.
- Frames werden thread-safe gesammelt.
- `snapshot()` liefert eine Kopie der bisherigen Frames ohne Aufnahme zu stoppen.
- `stop()` liefert Audio und leert Frames.
- Audiolevel-Callback liefert geklemmte Pegel für UI.
- Geräteauflistung über `enumerate_input_devices()`.

## 8. STT

Implementierung: `src/dictapaste/stt.py`

Anforderungen:

- Transkription lokal mit `faster-whisper`.
- Model Load lazy bzw. preload-fähig.
- Sprache `auto` oder konkreter Sprachcode.
- Fortschrittsmeldungen beim Modellladen an UI weiterreichen.
- Teiltranskripte können inkrementell zusammengeführt werden.
- `merge_partial_transcripts` und `IncrementalTranscriptBuffer` vermeiden offensichtliche Dubletten beim Chunking.

## 9. LLM-Verfeinerung

Implementierung: `src/dictapaste/llm.py`

Anforderungen:

- OpenAI-kompatibler HTTP-Chat-Completion-Client über `httpx`.
- Standard-Endpoint aus `base_url`, typischerweise `/v1/chat/completions`.
- Konfigurierbares Modell, Timeout und Temperatur.
- Sync-Refinement und Streaming-Refinement.
- Verfügbarkeitstest über `is_available()`.
- Abbruch über `cancel()`.
- Reasoning-/Think-Block-Filterung, u. a. `<think>...</think>` und vergleichbare Leaks.
- Prompt-Echo- und Result-Label-Cleanup.
- Bei Fehlern oder Nichtverfügbarkeit darf die Pipeline nicht abbrechen, sondern muss auf das rohe Transkript zurückfallen.

## 10. Prompt-System

Implementierung: `src/dictapaste/prompt.py`

Lade-Reihenfolge:

1. `prompt` aus `dictapaste.yaml`.
2. `prompt.txt` im Runtime-Konfigurationsordner.
3. `DEFAULT_PROMPT` aus dem Code.

Validierung:

- `{transcript}` ist erforderlich.
- `{language}` ist optional.

Default-Anforderungen an die LLM-Ausgabe:

- Füllwörter, Fehlstarts, Wiederholungen und Selbstkorrekturen entfernen.
- Grammatik, Rechtschreibung und Zeichensetzung korrigieren.
- Sinnvoll verdichten, ohne Bedeutung, Anforderungen, Absicht oder Details zu verlieren.
- Keine Zusammenfassung statt Endfassung liefern.
- Nur direkt weiterverwendbaren Fließtext ausgeben.
- Keine Überschrift, Liste, Erklärung oder Denkprozess ausgeben.
- Keine Fakten erfinden oder hinzufügen.

## 11. Ausgabe/Paste

Implementierung: `src/dictapaste/paste.py`

Paste-Modi:

- `ctrl_v`: Clipboard setzen und `Ctrl+V` per `pynput.keyboard` senden.
- `copy`: nur Clipboard setzen.
- `xdotool`: unter Linux `xdotool type --clearselection -- <text>` nutzen; bei Fehlschlag Fallback auf `ctrl_v`.

Robustheit:

- Clipboard-Schreibversuche werden mehrfach wiederholt.
- Nach dem Kopieren wird geprüft, ob das Clipboard den erwarteten Text enthält.
- Leerer Text wird nicht ausgegeben.

## 12. Globaler Input

Implementierung: `src/dictapaste/input_hook.py`

Anforderungen:

- Globaler Mouse Listener über `pynput`.
- Konfigurierbare Buttons: `x1`, `x2`, `middle`, `left`, `right`.
- Callbacks für Trigger, Press, Release, Move und Fehler.
- Button-Wechsel zur Laufzeit über `update_button()`.

Konfliktlogik: `src/dictapaste/conflict.py`

- `left`, `right`, `middle` gelten als konfliktträchtig.
- `x1`, `x2` haben mittlere Konfliktwahrscheinlichkeit.
- Warntexte unterscheiden Plattformdetails, u. a. Windows-Clipboard und Linux/X11-Hinweise.

## 13. Konfiguration

Implementierung: `src/dictapaste/config.py`

### 13.1 Pfade

- Runtime-TOML: `config.toml`
  - Windows: `%APPDATA%/DictaPaste/config.toml`
  - Linux: `~/.config/dictapaste/config.toml`
- Prompt-Datei: `prompt.txt` im Runtime-Konfigurationsordner.
- Root-YAML: `dictapaste.yaml` im Projektroot bzw. angegebenen Root-Verzeichnis.

### 13.2 Schema und Defaults

```toml
version = 3

[audio]
device_index = -1

[stt]
model = "medium"
language = "auto"

[llm]
enabled_by_default = true
base_url = "http://127.0.0.1:1234"
model = "google/gemma-4-e4b"
timeout_sec = 20
temperature = 0.2

[input]
mouse_button = "x1"

[output]
paste_mode = "ctrl_v"

[startup]
start_with_windows = false

[streaming]
enabled = true
stt_chunking_enabled = false
chunk_duration_sec = 3
llm_start_mode = "final"
```

### 13.3 Root-YAML-Overrides

Root-YAML darf überschreiben:

- `llm.enabled_by_default`
- `llm.base_url`
- `llm.model`
- `llm.timeout_sec`
- `llm.temperature`
- `input.mouse_button`
- `startup.start_with_windows`
- `streaming.enabled`
- `streaming.stt_chunking_enabled`
- `streaming.chunk_duration_sec`
- `streaming.llm_start_mode`
- `prompt`

### 13.4 Migration

Aktuelle Version: `3`

- v0 → v1: Audio-Section ergänzen.
- v1 → v2: Streaming-Controls ergänzen.
- v2 → v3: `streaming.llm_start_mode` ergänzen.
- Zukünftige Versionen werden mit Warnung geladen und nicht migriert.

## 14. Streaming und Teilverarbeitung

Implementierung: `DictationPipeline` in `src/dictapaste/pipeline.py`

Optionen:

- `streaming.enabled`: aktiviert STT-Warmup und vorbereitende Logik.
- `streaming.stt_chunking_enabled`: nutzt Recorder-Snapshots während der Aufnahme.
- `streaming.chunk_duration_sec`: Intervall für Chunk-Transkription.
- `streaming.llm_start_mode`:
  - `final`: LLM startet nach finaler STT.
  - `experimental_partial`: LLM kann auf einem Teiltranskript vorab starten; Ergebnis wird nur genutzt, wenn Teiltranskript und finales Transkript übereinstimmen.

## 15. Historie

Implementierung: `src/dictapaste/history.py`

Anforderungen:

- Persistente JSON-Historie.
- Einträge enthalten Rohtext, verfeinerten Text, Zeitstempel und Refinement-Status.
- Thread-sicheres Hinzufügen, Laden, Speichern und Leeren.
- Maximale Eintragsanzahl wird begrenzt.
- Historie ist im Settings-Dialog such- und kopierbar.

## 16. Autostart

Implementierung: `src/dictapaste/autostart.py`

Windows:

- Startup-Ordner-Skript wird erzeugt/entfernt.
- Startkommando verweist auf ausführbare App bzw. Python-Start.

Linux:

- `.desktop`-Datei im Autostart-Verzeichnis wird erzeugt/entfernt.

Dispatcher:

- `set_autostart()` entscheidet anhand der Plattform.
- Andere Plattformen sind No-op.

## 17. Logging und i18n

Logging:

- Implementierung: `src/dictapaste/logging_setup.py`
- Logdatei: `dictapaste.log` im Konfigurationsverzeichnis.
- Pipeline loggt Timing-Metriken: STT, LLM First Token, LLM gesamt, Paste, Total und Outcome.

Lokalisierung:

- Implementierung: `src/dictapaste/i18n.py`
- Unterstützte Sprachen: Englisch und Deutsch.
- Locale-Erkennung mit Fallback auf Englisch.
- Konfliktwarnungen sind lokalisierbar.

## 18. Slash-Commands

Implementierung: `src/dictapaste/commands.py`

Anforderungen:

- Gesprochene oder geschriebene Slash-Commands können normalisiert werden.
- Direkte Slash-Commands werden erkannt.
- Ohne Force muss ein Prefix/Slash-Kriterium erfüllt sein.
- Im Command-Modus wird Force-Auflösung genutzt.
- Unbekannte Commands liefern `None` und werden normal weiterverarbeitet.

## 19. Paketierung und Entry Points

`pyproject.toml`:

- Paketname: `dictapaste`
- Version: `0.1.0`
- Beschreibung: Cross-platform tray dictation app with optional local LLM refinement.
- Build-Backend: `setuptools.build_meta`
- Source Layout: `src/`
- Console Script: `dictapaste = dictapaste.main:main`
- pytest-Testpfad: `tests`

Runtime-Abhängigkeiten:

- `PySide6>=6.7`
- `pynput>=1.7`
- `sounddevice>=0.4`
- `soundfile>=0.12`
- `numpy>=1.26`
- `faster-whisper>=1.0`
- `httpx>=0.27`
- `pyperclip>=1.9`
- `tomli-w>=1.0`
- `PyYAML>=6.0`

Dev-Abhängigkeiten:

- `pytest>=8.0`
- `pyinstaller>=6.0`

## 20. Build

Windows:

```powershell
./scripts/build_windows.ps1
```

Linux:

```bash
chmod +x ./scripts/build_linux.sh
./scripts/build_linux.sh
```

PyInstaller-Spec: `DictaPaste.spec`

- Entry: `src/dictapaste/main.py`
- Asset: `src/dictapaste/assets/caretchen_tray.svg`
- Hidden Imports: `faster_whisper`, `ctranslate2`

## 21. Tests und Qualitätsanforderungen

Testkommando:

```bash
pytest
```

Aktueller Umfang: 16 Testdateien, 181 Tests.

Abgedeckte Bereiche:

- Audioaufnahme, Audiolevel, Snapshot, Stop-Verhalten.
- Autostart Windows/Linux.
- Slash-Command-Auflösung.
- Konfiguration, YAML-Overrides, Typ-Fallbacks und Migration.
- Konfliktwarnungen für Maustasten.
- Historie und Thread-Sicherheit.
- i18n Deutsch/Englisch und Fallbacks.
- Icon-Erzeugung.
- LLM-Requests, Streaming, Cancel, Think-Block-/Prompt-Echo-Bereinigung.
- Diktiermodi und Prompt-Building.
- Paste-Modi und xdotool-Fallback.
- Pipeline-Erfolg, Fehlerfälle, Fallbacks, Retry, Streaming und Teiltranskripte.
- Prompt-Laden/Speichern/Rendering.
- State Machine.
- STT und Merge von Teiltranskripten.

## 22. Modulverantwortlichkeiten

| Modul | Verantwortung |
|---|---|
| `main.py` | Qt-App initialisieren, Logging starten, Tray-App starten. |
| `cli.py`, `__main__.py` | CLI-/Modul-Entry-Points. |
| `tray.py` | Tray-Menü, UI-Thread-Brücke, Maus-Hook, Settings, Overlays. |
| `pipeline.py` | Aufnahme-, STT-, LLM-, Paste- und History-Orchestrierung. |
| `app_state.py` | App-Zustände. |
| `audio.py` | Audioaufnahme und Geräteauflistung. |
| `stt.py` | Whisper-Transkription, Preload, Teiltranskript-Merge. |
| `llm.py` | OpenAI-kompatible LLM-Verfeinerung und Streaming. |
| `paste.py` | Clipboard, `Ctrl+V`, `xdotool`. |
| `input_hook.py` | Globaler Maus-Listener. |
| `config.py` | Konfigurationsschema, Pfade, TOML/YAML, Migration. |
| `prompt.py` | Prompt-Laden, Speichern und Rendering. |
| `settings_dialog.py` | Vollständige Laufzeitkonfiguration. |
| `mode_popup.py` | Modusauswahl und Processing-Overlay. |
| `modes.py` | Diktiermodi und Modus-spezifische Prompt-Instruktionen. |
| `commands.py` | Slash-Command-Normalisierung und Auflösung. |
| `history.py` | Persistente Diktierhistorie. |
| `autostart.py` | Windows/Linux-Autostart. |
| `conflict.py` | Maustasten-Konfliktmodell und Warnungen. |
| `i18n.py` | Übersetzungen und Locale. |
| `icon.py` | App- und State-Icons. |
| `logging_setup.py` | Logdateipfad und Logging-Konfiguration. |

## 23. Fehler- und Fallback-Verhalten

- Aufnahme-Startfehler → Meldung, `ERROR`, dann `IDLE`.
- Aufnahme-Stopfehler → Meldung, `ERROR`, dann `IDLE`.
- Kein Audio → Meldung, `IDLE`.
- STT-Fehler → Meldung, `ERROR`, dann `IDLE`.
- Kein erkannter Text → Meldung, `IDLE`.
- Direkt-Modus → LLM wird übersprungen, Rohtranskript wird ausgegeben.
- LLM-Fehler/Timeout/Nichtverfügbarkeit → Meldung und Fallback auf Rohtranskript.
- LLM-Abbruch → Fallback auf Rohtranskript.
- Paste-Fehler → Meldung, `ERROR`, danach `IDLE`; letzter Output bleibt für Retry erhalten.
- Clipboard-Fehler → Retry-Logik, danach Exception an Pipeline.

## 24. Sicherheits- und Datenschutzannahmen

- STT läuft lokal.
- LLM-Verarbeitung ist für lokale OpenAI-kompatible Server vorgesehen.
- Audio und Text werden nicht absichtlich an Cloud-Dienste gesendet, außer Nutzer konfiguriert `base_url` entsprechend.
- Diktierhistorie und Logs liegen lokal im Benutzer-/Projektkontext.
- Clipboard wird aktiv überschrieben; Nutzer muss sensible Inhalte entsprechend behandeln.

## 25. Bekannte Risiken und Einschränkungen

- Global Hooks sind plattform- und Desktop-abhängig.
- Wayland kann globale Maus- und Paste-Funktionen blockieren.
- Maustasten wie `left`, `right`, `middle` können normale Bedienung stören.
- Whisper-Modellinitialisierung kann beim ersten Start langsam sein.
- Große Whisper-Modelle benötigen mehr RAM/CPU.
- Lokaler LLM muss OpenAI-kompatible Chat-Completions korrekt implementieren.
- Experimentelles Partial-LLM ist konservativ: Es wird nur genutzt, wenn Teil- und Finaltranskript übereinstimmen.
