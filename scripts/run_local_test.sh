#!/bin/bash
# Local dev runner: unit tests, then single-player pole mode.
# Uses the dedicated venv at ~/.venvs/shadowclash (see DECISIONS.md D-001).
set -e
cd "$(dirname "$0")/.."
PY="$HOME/.venvs/shadowclash/bin/python"
[ -x "$PY" ] || { echo "venv missing: python3.12 -m venv ~/.venvs/shadowclash && ~/.venvs/shadowclash/bin/pip install -r requirements.txt pytest"; exit 1; }
"$PY" -m pytest tests/ -q
"$PY" -m shadowclash.main --mode "${1:-singleplayer}" "${@:2}"
