# DictaPaste (caretchen) — Projektübersicht

## Was ist das?

DictaPaste ist eine **Cross-Platform Tray-App** (Windows + Linux/X11), die Freisprach-Eingabe ermöglicht:

1. **Globale Maustaste** (x1/x2) drücken → Aufnahme startet
2. **Nochmal drücken** → Aufnahme stoppt
3. **Sprache → Text** lokal mit Whisper (`faster-whisper`, medium-Modell)
4. **Optional: LLM-Verfeinerung** über lokalen OpenAI-kompatiblen Router (Ollama/LM Studio)
5. **Einfügen** via Clipboard + Ctrl+V in die fokusierte Anwendung

Wenn kein LLM verfügbar ist → Fallback auf rohen Transkripts.

---

## Tech Stack

| Bereich | Technologie |
|---|---|
| **UI** | PySide6 (Qt6) — System-Tray-App, kein Hauptfenster |
| **Spracherkennung** | `faster-whisper` (medium, CPU, int8) |
| **Audio** | `sounddevice` + `soundfile` (16kHz, Mono, float32) |
| **LLM-Interface** | `httpx` (OpenAI-kompatibles HTTP-Chat-Completion) |
| **Clipboard/Eingabe** | `pyperclip` + `pynput` (keyboard) |
| **Global Input** | `pynput` (MouseToggleHook) |
| **Konfiguration** | TOML (Laufzeit) + YAML (Root-Config) |
| **Build** | PyInstaller (One-File Binary) |
| **Tests** | pytest |

**Python ≥ 3.11** erforderlich.

---

## Projektstruktur

```
caretchen/
├── src/dictapaste/          # Hauptpaket
│   ├── main.py              # Entry Point (QApplication → TrayApp → start)
│   ├── app_state.py         # Zustandsmaschine: IDLE → RECORDING → TRANSCRIBING → REFINING → PASTING → ERROR
│   ├── pipeline.py          # DictationPipeline — Orchestrator aller Schritte (threaded)
│   ├── audio.py             # AudioRecorder (sounddevice Stream, threading-safe)
│   ├── stt.py               # WhisperTranscriber (faster-whisper, lazy model load)
│   ├── llm.py               # LLMRefiner (httpx Client, prompt rendering, echo-prefix cleanup)
│   ├── paste.py             # paste_text() (clipboard + keyboard simulation)
│   ├── input_hook.py        # MouseToggleHook (pynput global mouse listener)
│   ├── config.py            # AppConfig dataclass (TOML + YAML, laden/speichern)
│   ├── prompt.py            # Prompt laden/ speichern (YAML oder prompt.txt)
│   ├── settings_dialog.py   # Qt Settings-Dialog (vollständig konfigurierbar)
│   ├── tray.py              # DictaPasteTrayApp (Tray-Menü, State-Icons, Action-Handling)
│   ├── autostart.py         # Windows Auto-Start (Startup-Ordner Script)
│   ├── icon.py              # Icon-Loader (dev + PyInstaller bundle)
│   ├── logging_setup.py     # Logging → config_dir/dictapaste.log
│   ├── cli.py               # CLI Wrapper
│   └── __main__.py          # python -m dictapaste
├── tests/                   # pytest (5 Testdateien, ~450 Zeilen)
├── scripts/                 # Build-Skripte (Windows .ps1, Linux .sh)
├── dictapaste.yaml          # Root-Config (LLM + Maus-Taste, wird automatisch erstellt)
├── config.toml              # Laufzeit-Konfiguration (Platform-spezifischer Pfad)
├── pyproject.toml           # Project metadata + dependencies
├── requirements.txt         # Abhängigkeiten
├── cli.py                   # CLI Entry Point (dev)
└── README.md
```

---

## Konfiguration

### Laufzeit-Konfiguration (TOML)
- **Windows:** `%APPDATA%/DictaPaste/config.toml`
- **Linux:** `~/.config/dictapaste/config.toml`

```toml
[stt]
model = "medium"
language = "auto"

[llm]
enabled_by_default = true
base_url = "http://localhost:1234"
model = "borg-cpu"
timeout_sec = 20
temperature = 0.2

[input]
mouse_button = "x1"

[output]
paste_mode = "ctrl_v"
```

### Root-Config (YAML) — `dictapaste.yaml`
Überschreibt gleiche Werte aus TOML. Wird beim ersten Start automatisch erstellt.

### Prompt
- Standard-Prompt in `src/dictapaste/prompt.py` (`DEFAULT_PROMPT`)
- Kann in `prompt.txt` neben der TOML-Config überschrieben werden
- Kann im Settings-Dialog editiert und gespeichert werden
- Muss `{transcript}` und optional `{language}` enthalten

---

## Zustandsmaschine

```
IDLE → RECORDING → TRANSCRIBING → REFINING → PASTING → IDLE
                                      ↓
                                   ERROR → IDLE
```

Jeder Zustand wird im Tray-Menü und als Icon angezeigt.

---

## Wichtige Dateien für Änderungen

| Ziel | Datei |
|---|---|
| Pipeline-Logik (Kern) | `src/dictapaste/pipeline.py` |
| UI/Tray-Menü | `src/dictapaste/tray.py` |
| Settings-Dialog | `src/dictapaste/settings_dialog.py` |
| Konfiguration | `src/dictapaste/config.py` |
| Audio-Aufnahme | `src/dictapaste/audio.py` |
| Spracherkennung | `src/dictapaste/stt.py` |
| LLM-Integration | `src/dictapaste/llm.py` |
| Einfüge-Logik | `src/dictapaste/paste.py` |
| Globale Maus-Taste | `src/dictapaste/input_hook.py` |

---

## Entwicklung

```bash
# Setup
python -m venv .venv
. .venv/Scripts/activate        # Windows PowerShell
python -m pip install -e ".[dev]"

# Ausführen
python cli.py
# oder
python -m dictapaste.main

# Tests
pytest

# Binary bauen
./scripts/build_windows.ps1     # Windows
./scripts/build_linux.sh        # Linux
```

---

## Einschränkungen

- **Wayland** wird in v1 nicht unterstützt (Linux = X11)
- Whisper-Modell wird beim ersten Start heruntergeladen (kann langsam sein)
- LLM ist optional — bei Ausfall wird roher Transkript verwendet
- Maus-Hook blockiert die gewählte Maustaste für normale Nutzung

---

## Abhängigkeiten (Kern)

`PySide6`, `pynput`, `sounddevice`, `soundfile`, `numpy`, `faster-whisper`, `httpx`, `pyperclip`, `tomli-w`, `PyYAML`

## Dev-Abhängigkeiten

`pytest`, `pyinstaller`
