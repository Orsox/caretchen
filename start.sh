#!/usr/bin/env bash
# start.sh — DictaPaste für Wayland (GNOME) starten
#
# System-Abhängigkeiten (einmalig, benötigt sudo):
#   sudo apt install python3.14-dev libportaudio2 wtype
#
# Dann: ./start.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── System-Prüfung ─────────────────────────────────────────────────
echo "🔍 System-Abhängigkeiten prüfen ..."

MISSING=0

# PortAudio
if ldconfig -p 2>/dev/null | grep -q "libportaudio"; then
    echo "✅ libportaudio2 gefunden"
else
    # Fallback: direkt nach der .so suchen
    if find /usr/lib -name "libportaudio*" -type f 2>/dev/null | head -1 | grep -q .; then
        echo "✅ libportaudio2 gefunden"
    else
        echo "❌ libportaudio2 fehlt (für Audio-Aufnahme)"
        MISSING=$((MISSING + 1))
    fi
fi

# wtype (Paste)
if command -v wtype &>/dev/null; then
    echo "✅ wtype gefunden (für Paste unter Wayland)"
else
    echo "❌ wtype fehlt (für Paste unter Wayland)"
    MISSING=$((MISSING + 1))
fi

# gcc (für pyinputcapture falls benötigt)
if command -v gcc &>/dev/null; then
    echo "✅ gcc gefunden"
else
    echo "❌ gcc fehlt"
    MISSING=$((MISSING + 1))
fi

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "📦 Fehlende System-Abhängigkeiten installieren:"
    echo ""
    echo "   sudo apt install python3.14-dev libportaudio2 wtype"
    echo ""
    echo "Danach: ./start.sh"
    exit 1
fi

# ── venv automatisch finden, prüfen oder erstellen ──────────────────
VENV_DIR=""
VENV_BIN=""

for candidate in .venv venv; do
    if [ -d "$SCRIPT_DIR/$candidate" ] && [ -f "$SCRIPT_DIR/$candidate/bin/activate" ]; then
        VENV_DIR="$SCRIPT_DIR/$candidate"
        VENV_BIN="$SCRIPT_DIR/$candidate/bin"
        break
    fi
done

if [ -z "$VENV_DIR" ]; then
    echo "📦 Keine gültige venv gefunden — erstelle .venv ..."

    PY=""
    for candidate in python3 python python3.12 python3.11; do
        if command -v "$candidate" &>/dev/null; then
            PY="$candidate"
            break
        fi
    done

    if [ -z "$PY" ]; then
        echo "❌ Kein Python 3.11+ gefunden."
        exit 1
    fi

    echo "   Verwende: $PY ($($PY --version 2>&1))"
    $PY -m venv .venv

    if [ ! -f ".venv/bin/activate" ]; then
        echo "❌ venv-Erstellung fehlgeschlagen."
        exit 1
    fi
fi

echo "🔍 venv aktiviert: $VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_BIN/activate"

# ── Python-Dependencies installieren ────────────────────────────────
echo "📦 Python-Dependencies prüfen ..."
python -m pip install -q --upgrade pip 2>/dev/null || true
python -m pip install -q -e ".[dev]" 2>&1 | grep -v "already satisfied" || true

# ── Wayland-Prüfung ────────────────────────────────────────────────
echo ""
echo "🐧 Wayland-Sitzung: $WAYLAND_DISPLAY (GNOME)"
echo ""

# Maus-Hook: Python 3.14-kompatibel via evdev
if python -c "import evdev" 2>/dev/null; then
    if id -nG | tr ' ' '\n' | grep -qx input; then
        echo "✅ Maus-Hook: evdev installiert und User ist in input-Gruppe"
    else
        echo "⚠️  Maus-Hook: evdev installiert, aber User ist NICHT in der input-Gruppe"
        echo "   Für globale Maus-Tasten unter Wayland ausführen:"
        echo "     sudo usermod -aG input $USER"
        echo "   Danach abmelden/anmelden oder neu starten."
        echo "   Bis dahin: Tray-Icon doppelt klicken oder Tray-Menü verwenden."
    fi
else
    echo "❌ Maus-Hook: evdev fehlt"
    echo "   Installieren: pip install evdev"
fi

if python -c "import pyinputcapture" 2>/dev/null; then
    echo "✅ Wayland-Portal-Hook: pyinputcapture verfügbar"
else
    echo "ℹ️  Wayland-Portal-Hook: pyinputcapture nicht verfügbar (Python 3.14 wird upstream noch nicht unterstützt)"
fi

echo ""

# ── Starten ────────────────────────────────────────────────────────
echo "🚀 Starte DictaPaste ..."
echo ""

exec python cli.py "$@"
