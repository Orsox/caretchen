# DictaPaste (Krätchen)

DictaPaste ist eine Cross-Platform-Tray-App für Windows und Linux (X11 + Wayland). Sie nimmt Sprache per globaler Maustaste auf, transkribiert lokal mit Whisper, verfeinert den Text optional über einen lokalen OpenAI-kompatiblen LLM-Server und fügt das Ergebnis in die aktuell fokussierte Anwendung ein.

Kurzablauf:

1. Globale Maustaste drücken (`x1`, `x2`, `middle`, `left` oder `right`) → Aufnahme startet.
2. Taste erneut bzw. nach Loslassen drücken → Aufnahme stoppt.
3. Audio wird lokal mit `faster-whisper` transkribiert.
4. Optional wird der Text mit einem lokalen LLM bereinigt, zusammengefasst, übersetzt oder in einen Prompt/Befehl umgewandelt.
5. Ergebnis wird per Clipboard + `Ctrl+V`, nur Clipboard oder `xdotool` eingefügt.

Wenn der LLM nicht erreichbar ist, verwendet DictaPaste automatisch das rohe Transkript.

## Features

- System-Tray-App ohne Hauptfenster, Anzeigename: **Krätchen**.
- Zustandsanzeige im Tray: `IDLE`, `RECORDING`, `TRANSCRIBING`, `REFINING`, `PASTING`, `ERROR`.
- Globale Maussteuerung über `pynput` (X11) oder `pyinputcapture` (Wayland).
- Modus-Popup an der Cursorposition:
  - **Verbessern**: diktierten Text bereinigen und verbessern.
  - **Prompt**: aus Diktat einen direkt nutzbaren Prompt erstellen.
  - **Kurzfassung**: Diktat verdichten.
  - **Übersetzen**: Deutsch ↔ natürliches Englisch/Deutsch.
  - **Befehl**: Diktat in einen Slash-Befehl umwandeln.
  - **Direkt**: rohes Transkript ohne LLM-Verarbeitung direkt ausgeben.
- Verarbeitungs-Overlay mit Audiolevel, Streaming-Ausgabe und Abschlussanzeige.
- Lokale Transkription mit `faster-whisper` (`medium` standardmäßig, CPU/int8 im Projektkonzept).
- Optionaler lokaler LLM über OpenAI-kompatible Chat-Completions (`/v1/chat/completions`).
- Streaming-Unterstützung für LLM-Ausgaben und optionales STT-Chunking während der Aufnahme.
- Abbruch laufender Aufnahme und Abbruch laufender LLM-Verfeinerung.
- Retry für den letzten Paste-Vorgang und Copy-last-result im Tray.
- Diktier-Historie mit Rohtext, verfeinertem Text und Such-/Kopierfunktionen im Settings-Dialog.
- Settings-Dialog für LLM, Whisper, Sprache, Mausbutton, Audio-Gerät, Paste-Modus, Streaming, Prompt, Autostart, Logs und Historie.
- Konfigurationsmigration mit Versionsnummer (`CURRENT_CONFIG_VERSION = 3`).
- Bekannte Konfliktwarnungen für problematische Maustasten.
- Lokalisierung Deutsch/Englisch.
- Logging nach `dictapaste.log` im Konfigurationsverzeichnis.
- Autostart-Unterstützung für Windows Startup-Ordner und Linux `.desktop`-Autostart.
- PyInstaller-One-File-Builds für Windows und Linux.

## Voraussetzungen

- Python **3.11+**
- Linux mit X11 oder Wayland
- Mikrofon/Input-Gerät
- Optional: lokaler OpenAI-kompatibler LLM-Router, z. B. LM Studio oder Ollama-kompatibler Router
- Für Linux-Paste-Modi:
  - `xdotool` (X11 / XWayland)
  - `ydotool` (Wayland mit wlroots: Sway, Hyprland, Wayfire)
  - `wtype` (Wayland mit GNOME)
- Für Wayland-Maus-Hook (optional): `pyinputcapture` (`pip install pyinputcapture`)

## Installation für Entwicklung

```bash
python -m venv .venv

# Windows PowerShell
. .venv/Scripts/activate

# Linux/macOS Shell
# . .venv/bin/activate

python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Alternativ können die Runtime-Abhängigkeiten aus `requirements.txt` installiert werden:

```bash
python -m pip install -r requirements.txt
```

## Starten

```bash
python cli.py
```

oder nach editable install:

```bash
dictapaste
```

oder als Modul:

```bash
python -m dictapaste.main
```

## Bedienung

1. App starten; das Tray-Icon erscheint.
2. Konfigurierte Maustaste drücken.
3. Während der Aufnahme sprechen.
4. Maustaste loslassen/erneut triggern, um die Aufnahme zu stoppen.
5. Modus wählen bzw. Standardmodus verwenden.
6. DictaPaste transkribiert, verfeinert je nach Modus optional und fügt den Text ein.

Tray-Menü:

- Letztes Ergebnis kopieren
- Historie/Settings öffnen
- Statusanzeige und Maustasten-Hinweis
- Aufnahme manuell umschalten
- LLM-Verfeinerung ein/aus
- Aufnahme abbrechen
- LLM abbrechen
- Paste wiederholen
- Settings
- Beenden

## Konfiguration

DictaPaste nutzt zwei Konfigurationsebenen:

1. Runtime-TOML im Benutzer-Konfigurationsverzeichnis.
2. Root-YAML `dictapaste.yaml`, die ausgewählte Werte überschreibt und automatisch erstellt wird.

### Runtime-Konfiguration

Pfade:

- Windows: `%APPDATA%/DictaPaste/config.toml`
- Linux: `~/.config/dictapaste/config.toml`

Beispiel:

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

### Root-Konfiguration `dictapaste.yaml`

Diese Datei liegt standardmäßig im Projektroot und überschreibt LLM-, Input-, Startup- und Streaming-Werte aus der TOML-Datei. Zusätzlich kann sie den Prompt speichern.

```yaml
llm:
  enabled_by_default: true
  base_url: http://127.0.0.1:1234
  model: google/gemma-4-e4b
  timeout_sec: 20
  temperature: 0.2
input:
  mouse_button: x1
startup:
  start_with_windows: false
streaming:
  enabled: true
  stt_chunking_enabled: false
  chunk_duration_sec: 3
  llm_start_mode: final
prompt: "... {transcript} ..."
```

### Wichtige Optionen

| Bereich | Option | Standard | Beschreibung |
|---|---:|---:|---|
| `audio` | `device_index` | `-1` | `-1` nutzt das System-Standardgerät. |
| `stt` | `model` | `medium` | Whisper-Modellname, z. B. `base`, `small`, `medium`, `large-v3`. |
| `stt` | `language` | `auto` | Automatische Erkennung oder Sprachcode wie `de`, `en`, `fr`, `es`, `it`. |
| `llm` | `enabled_by_default` | `true` | LLM-Verfeinerung beim Start aktivieren. |
| `llm` | `base_url` | `http://127.0.0.1:1234` | OpenAI-kompatible Server-URL. |
| `llm` | `model` | `google/gemma-4-e4b` | Modellname des lokalen LLM-Servers. |
| `llm` | `timeout_sec` | `20` | HTTP-Timeout. |
| `llm` | `temperature` | `0.2` | Kreativität/Determinismus der Antwort. |
| `input` | `mouse_button` | `x1` | Globaler Triggerbutton. |
| `output` | `paste_mode` | `ctrl_v` | `ctrl_v`, `copy` oder `xdotool`. |
| `startup` | `start_with_windows` | `false` | Autostart aktivieren. |
| `streaming` | `enabled` | `true` | Streaming-/Vorbereitungslogik aktivieren. |
| `streaming` | `stt_chunking_enabled` | `false` | Teiltranskripte während Aufnahme erzeugen. |
| `streaming` | `chunk_duration_sec` | `3` | Chunk-Intervall: `1`, `2`, `3`, `4`, `5` oder `10`. |
| `streaming` | `llm_start_mode` | `final` | `final` oder experimentell `experimental_partial`. |

## Prompt

Der Prompt wird in folgender Reihenfolge geladen:

1. `prompt` aus `dictapaste.yaml`
2. `prompt.txt` im Runtime-Konfigurationsverzeichnis
3. eingebauter Standard-Prompt aus `src/dictapaste/prompt.py`

Der Prompt muss `{transcript}` enthalten; `{language}` ist optional. Der Standard-Prompt korrigiert Grammatik und Zeichensetzung, entfernt Füllwörter und Wiederholungen, verdichtet ohne Bedeutungsverlust und verbietet erfundene Fakten sowie Denkprozess-Ausgaben.

## Paste-Modi

- `ctrl_v`: Text ins Clipboard kopieren und `Ctrl+V` simulieren (pynput unter X11, Fallback unter Wayland).
- `copy`: Text nur ins Clipboard kopieren.
- `xdotool`: unter Linux per `xdotool type` schreiben, mit Fallback auf `ctrl_v`.
- `ydotool`: unter Wayland (wlroots) per `ydotool` simulieren.
- `wtype`: unter Wayland (GNOME) per `wtype` simulieren.
- `portal`: Clipboard + Desktop-Portal-Fallback.

## Build

Windows:

```powershell
./scripts/build_windows.ps1
```

Linux:

```bash
chmod +x ./scripts/build_linux.sh
./scripts/build_linux.sh
```

Die PyInstaller-Spezifikation `DictaPaste.spec` bündelt das Tray-Asset `src/dictapaste/assets/caretchen_tray.svg` und Hidden Imports für `faster_whisper` und `ctranslate2`.

## Tests

```bash
pytest
```

Die Test-Suite umfasst aktuell 16 Testdateien mit 181 Tests für Audio, Autostart, Slash-Commands, Konfiguration/Migration, Konfliktwarnungen, Historie, i18n, Icons, LLM, Modi, Paste, Pipeline, Prompt, State Machine und STT.

## Projektstruktur

```text
caretchen/
├── src/dictapaste/          # Hauptpaket
│   ├── main.py              # QApplication + Tray-App-Start
│   ├── tray.py              # Tray-Menü, Hook, Overlays, Settings-Anbindung
│   ├── pipeline.py          # Diktier-Orchestrierung und Zustandswechsel
│   ├── audio.py             # Aufnahme und Geräteauflistung
│   ├── stt.py               # Whisper-Transkription und Teiltranskripte
│   ├── llm.py               # OpenAI-kompatible LLM-Verfeinerung
│   ├── paste.py             # Clipboard/Keyboard/xdotool/ydotool-Paste
│   ├── paste_wayland.py     # Wayland-Paste-Implementierung
│   ├── input_hook.py        # Globaler Maus-Hook (X11/Wayland)
│   ├── input_hook_x11.py    # X11-Maus-Hook (pynput)
│   ├── input_hook_wayland.py # Wayland-Maus-Hook (pyinputcapture)
│   ├── config.py            # TOML/YAML-Konfiguration und Migration
│   ├── prompt.py            # Prompt-Laden, Speichern und Rendering
│   ├── settings_dialog.py   # Vollständiger Settings-Dialog
│   ├── mode_popup.py        # Modus-Popup und Processing-Overlay
│   ├── modes.py             # Diktiermodi und Modus-Prompts
│   ├── history.py           # Persistente Diktierhistorie
│   ├── autostart.py         # Windows/Linux-Autostart
│   ├── conflict.py          # Warnungen für Mausbutton-Konflikte
│   ├── i18n.py              # Deutsch/Englisch-Übersetzungen
│   ├── icon.py              # Tray- und State-Icons
│   └── logging_setup.py     # App-Logging
├── tests/                   # pytest-Suite
├── scripts/                 # Build-Skripte
├── docs/plans/              # Planungsdokumente
├── dictapaste.yaml          # Root-Overrides und Prompt
├── config.toml              # Beispiel/Runtime-Konfiguration
├── pyproject.toml           # Packaging und Dependencies
├── requirements.txt         # Runtime-Abhängigkeiten
└── DictaPaste.spec          # PyInstaller-Spec
```

## Bekannte Einschränkungen

- Der Maus-Hook unter Wayland erfordert `pyinputcapture` (`pip install pyinputcapture`). Ohne Installation wird auf X11/pynput fallbacken (funktioniert nur unter X11).
- Paste unter Wayland erfordert `ydotool`, `wtype` oder `xdotool` — je nach Compositor.
- Die erste Whisper-Modellinitialisierung bzw. der erste Modelldownload kann dauern.
- LLM-Verfeinerung ist optional und fällt bei Fehlern auf das rohe Transkript zurück.
- Der Modus **Direkt** überspringt den LLM immer und fügt das rohe Transkript ein.
- Der globale Maus-Hook kann die konfigurierte Maustaste in anderen Anwendungen beeinträchtigen.
- `left`, `right` und `middle` können starke Konflikte mit normaler Desktop-Bedienung verursachen; `x1`/`x2` sind empfohlen.
