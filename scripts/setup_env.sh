#!/usr/bin/env sh

VENV_DIR="venv"
REQ_FILE="scripts/requirements.txt"

fail() {
  echo "❌ $1"
  return 1 2>/dev/null || exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 non trovato nel PATH."
[ -f "$REQ_FILE" ] || fail "File requirements non trovato: $REQ_FILE"

if [ ! -d "$VENV_DIR" ]; then
  echo "📦 Creo ambiente virtuale in $VENV_DIR ..."
  python3 -m venv "$VENV_DIR" || fail "Creazione venv fallita."
else
  echo "📦 Ambiente virtuale gia presente: $VENV_DIR"
fi

# Attivazione nella shell corrente (funziona se lanciato con: source scripts/setup_env.sh)
# shellcheck source=/dev/null
. "$VENV_DIR/bin/activate" || fail "Attivazione venv fallita."

echo "⬆️  Installo dipendenze da $REQ_FILE ..."
python -m pip install -r "$REQ_FILE" || fail "Installazione dipendenze fallita."

echo "✅ Ambiente pronto e attivo ($(python --version 2>&1))"
echo "💡 Per riattivarlo in futuro: source $VENV_DIR/bin/activate"
