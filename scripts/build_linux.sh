#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"

"$PYTHON_EXE" -m pip install -U pip
"$PYTHON_EXE" -m pip install -e ".[dev]"

"$PYTHON_EXE" -m PyInstaller \
  --noconfirm \
  --onefile \
  --windowed \
  --name DictaPaste \
  --collect-submodules faster_whisper \
  --collect-submodules ctranslate2 \
  src/dictapaste/main.py
