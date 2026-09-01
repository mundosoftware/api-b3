#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${LOCAL_VENV_DIR:-venv}"
HOST="${LOCAL_SERVER_HOST:-127.0.0.1}"
PORT="${LOCAL_SERVER_PORT:-8000}"
INSTALL_KRONOS=false
SKIP_TESTS=false
NO_START=false
SMOKE_TICKER="${SMOKE_TICKER:-PETR4}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-kronos)
      INSTALL_KRONOS=true
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=true
      shift
      ;;
    --no-start)
      NO_START=true
      shift
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --ticker)
      SMOKE_TICKER="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

python3 -m venv "$VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

export DATABASE_PATH="${LOCAL_DATABASE_PATH:-database/local-ai.db}"
export SERVER_HOST="$HOST"
export SERVER_PORT="$PORT"
export CHECK_LOOP_ENABLED="${LOCAL_CHECK_LOOP_ENABLED:-false}"
export ONESIGNAL_ENABLED="${LOCAL_ONESIGNAL_ENABLED:-false}"
export KRONOS_ENABLED="${KRONOS_ENABLED:-true}"
export KRONOS_MODEL_NAME="${KRONOS_MODEL_NAME:-NeoQuasar/Kronos-base}"
export KRONOS_TOKENIZER_NAME="${KRONOS_TOKENIZER_NAME:-NeoQuasar/Kronos-Tokenizer-base}"
export KRONOS_MAX_CONTEXT="${KRONOS_MAX_CONTEXT:-512}"
export KRONOS_SAMPLE_COUNT="${KRONOS_SAMPLE_COUNT:-4}"
export CANDLE_CACHE_TTL_SECONDS="${CANDLE_CACHE_TTL_SECONDS:-3600}"
export PREDICTION_CACHE_TTL_SECONDS="${PREDICTION_CACHE_TTL_SECONDS:-900}"

if [[ "$INSTALL_KRONOS" == true ]]; then
  python -m pip install -r requirements-ai.txt
  mkdir -p .deps
  if [[ -d .deps/Kronos/.git ]]; then
    git -C .deps/Kronos pull --ff-only
  else
    git clone https://github.com/shiyu-coder/Kronos.git .deps/Kronos
  fi
  export KRONOS_REPO_PATH="$ROOT_DIR/.deps/Kronos"
fi

if [[ "$SKIP_TESTS" == false ]]; then
  python -m unittest discover -s tests
fi

python - <<'PY'
from src.config import get_settings
from src.database import init_db

settings = get_settings()
init_db(settings)
print(f"Database ready: {settings.database_path}")
print(f"Kronos model: {settings.kronos_model_name}")
PY

if [[ "$NO_START" == true ]]; then
  exit 0
fi

echo "Starting local API on http://$HOST:$PORT"
echo "Try: curl 'http://$HOST:$PORT/companies/$SMOKE_TICKER/ai-analysis?horizon=10&refresh=true'"
python -m uvicorn main:app --host "$HOST" --port "$PORT" --reload
