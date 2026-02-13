#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_DIR="$ROOT_DIR/venv"
REQ_FILE="$ROOT_DIR/scripts/requirements.txt"
STAMP_FILE="$VENV_DIR/.requirements.sha256"
PYTHON_BIN="$VENV_DIR/bin/python"

hash_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
    return
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
    return
  fi
  echo ""
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 non trovato nel PATH."
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "📦 Creo venv in $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
else
  echo "📦 Venv presente: $VENV_DIR"
fi

if [ ! -f "$PYTHON_BIN" ]; then
  echo "❌ Python del venv non trovato: $PYTHON_BIN"
  exit 1
fi

REQ_HASH=$(hash_file "$REQ_FILE")
OLD_HASH=""
if [ -f "$STAMP_FILE" ]; then
  OLD_HASH=$(cat "$STAMP_FILE")
fi

if [ -z "$REQ_HASH" ] || [ "$REQ_HASH" != "$OLD_HASH" ]; then
  echo "⬆️  Installo/aggiorno dipendenze ..."
  "$PYTHON_BIN" -m pip install -r "$REQ_FILE"
  if [ -n "$REQ_HASH" ]; then
    echo "$REQ_HASH" > "$STAMP_FILE"
  fi
else
  echo "✅ Dipendenze gia allineate."
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/quiz_cli.py" "$@"
