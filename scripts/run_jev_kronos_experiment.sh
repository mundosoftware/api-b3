#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${LOCAL_VENV_DIR:-venv}"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Missing $VENV_DIR. Create it and install the project dependencies first." >&2
  exit 2
fi

if [[ $# -eq 0 ]]; then
  set -- --mode all --tickers PETR4,VALE3,ITUB4 --horizon 10
fi

exec "$VENV_DIR/bin/python" -m experiments.jev_post_forecast.cli "$@"
