#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="vps"
NO_START="false"
SKIP_INSTALL="false"
ENV_FILE=""

usage() {
  cat <<EOF
Usage:
  ./scripts/deploy_vps.sh local [local.env] [--no-start] [--skip-install]
  ./scripts/deploy_vps.sh vps [local.env]
  ./scripts/deploy_vps.sh [local.env]

Modes:
  local        Prepare a local development environment and start Uvicorn with reload.
  vps          Deploy to the VPS over SSH and install/restart systemd service.

Options:
  --no-start       Local mode only: install/init but do not start Uvicorn.
  --skip-install   Local mode only: skip pip install, useful when venv is ready.
  -h, --help       Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    local|dev|--local|--dev)
      MODE="local"
      ;;
    vps|remote|--vps|--remote)
      MODE="vps"
      ;;
    --no-start)
      NO_START="true"
      ;;
    --skip-install)
      SKIP_INSTALL="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -n "${ENV_FILE}" ]]; then
        echo "Unexpected argument: $1" >&2
        usage >&2
        exit 1
      fi
      ENV_FILE="$1"
      ;;
  esac
  shift
done

ENV_FILE="${ENV_FILE:-${ROOT_DIR}/local.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ "${MODE}" == "local" && -f "${ROOT_DIR}/local.env.example" ]]; then
    cp "${ROOT_DIR}/local.env.example" "${ENV_FILE}"
    echo "Created ${ENV_FILE} from local.env.example"
  else
    echo "Missing env file: ${ENV_FILE}" >&2
    echo "Create it from local.env.example and fill in the required values." >&2
    exit 1
  fi
fi

set -a
source "${ENV_FILE}"
set +a

VPS_SSH_PORT="${VPS_SSH_PORT:-22}"
SERVER_HOST="${SERVER_HOST:-0.0.0.0}"
SERVER_PORT="${SERVER_PORT:-8000}"
DATABASE_PATH="${DATABASE_PATH:-database/app.db}"
DEFAULT_TIMEZONE="${DEFAULT_TIMEZONE:-America/Sao_Paulo}"
QUOTE_CACHE_TTL_SECONDS="${QUOTE_CACHE_TTL_SECONDS:-60}"
CHECK_LOOP_SECONDS="${CHECK_LOOP_SECONDS:-30}"
CHECK_LOOP_ENABLED="${CHECK_LOOP_ENABLED:-true}"
ONESIGNAL_ENABLED="${ONESIGNAL_ENABLED:-true}"
LOCAL_VENV_DIR="${LOCAL_VENV_DIR:-venv}"
LOCAL_SERVER_HOST="${LOCAL_SERVER_HOST:-127.0.0.1}"
LOCAL_SERVER_PORT="${LOCAL_SERVER_PORT:-${SERVER_PORT}}"
LOCAL_DATABASE_PATH="${LOCAL_DATABASE_PATH:-database/local-dev.db}"
LOCAL_CHECK_LOOP_ENABLED="${LOCAL_CHECK_LOOP_ENABLED:-false}"
LOCAL_ONESIGNAL_ENABLED="${LOCAL_ONESIGNAL_ENABLED:-false}"

quote_env_value() {
  local value="${1:-}"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

write_env_line() {
  local key="$1"
  local value="${2:-}"
  printf '%s=' "${key}"
  quote_env_value "${value}"
  printf '\n'
}

run_local() {
  cd "${ROOT_DIR}"

  export DATABASE_PATH="${LOCAL_DATABASE_PATH}"
  export SERVER_HOST="${LOCAL_SERVER_HOST}"
  export SERVER_PORT="${LOCAL_SERVER_PORT}"
  export CHECK_LOOP_ENABLED="${LOCAL_CHECK_LOOP_ENABLED}"
  export ONESIGNAL_ENABLED="${LOCAL_ONESIGNAL_ENABLED}"

  echo "Preparing local development environment"
  python3 -m venv "${LOCAL_VENV_DIR}"

  if [[ "${SKIP_INSTALL}" != "true" ]]; then
    echo "Installing Python dependencies into ${LOCAL_VENV_DIR}"
    "${LOCAL_VENV_DIR}/bin/pip" install --upgrade pip
    "${LOCAL_VENV_DIR}/bin/pip" install -r requirements.txt
  fi

  echo "Initializing SQLite database at ${DATABASE_PATH}"
  "${LOCAL_VENV_DIR}/bin/python" -c "from src.config import get_settings; from src.database import init_db; init_db(get_settings())"

  echo "Local API URL: http://${LOCAL_SERVER_HOST}:${LOCAL_SERVER_PORT}"
  echo "Docs URL: http://${LOCAL_SERVER_HOST}:${LOCAL_SERVER_PORT}/docs"

  if [[ "${NO_START}" == "true" ]]; then
    echo "Local setup finished. Start later with:"
    echo "  DATABASE_PATH=${DATABASE_PATH} CHECK_LOOP_ENABLED=${CHECK_LOOP_ENABLED} ONESIGNAL_ENABLED=${ONESIGNAL_ENABLED} ${LOCAL_VENV_DIR}/bin/uvicorn main:app --host ${LOCAL_SERVER_HOST} --port ${LOCAL_SERVER_PORT} --reload"
    return
  fi

  exec "${LOCAL_VENV_DIR}/bin/uvicorn" main:app \
    --host "${LOCAL_SERVER_HOST}" \
    --port "${LOCAL_SERVER_PORT}" \
    --reload
}

if [[ "${MODE}" == "local" ]]; then
  run_local
  exit 0
fi

: "${VPS_HOST:?VPS_HOST is required}"
: "${VPS_USER:?VPS_USER is required}"
: "${APP_DIR:?APP_DIR is required}"
: "${SERVICE_NAME:?SERVICE_NAME is required}"
: "${APP_USER:?APP_USER is required}"
: "${ONESIGNAL_APP_ID:?ONESIGNAL_APP_ID is required}"
: "${ONESIGNAL_REST_API_KEY:?ONESIGNAL_REST_API_KEY is required}"
: "${ADMIN_TOKEN:?ADMIN_TOKEN is required}"

SSH_TARGET="${VPS_USER}@${VPS_HOST}"
SSH_ARGS=(-p "${VPS_SSH_PORT}")
RSYNC_SSH="ssh -p ${VPS_SSH_PORT}"

if [[ -n "${SSH_KEY_PATH:-}" ]]; then
  SSH_ARGS=(-i "${SSH_KEY_PATH/#\~/${HOME}}" "${SSH_ARGS[@]}")
  RSYNC_SSH="ssh -i ${SSH_KEY_PATH/#\~/${HOME}} -p ${VPS_SSH_PORT}"
fi

remote() {
  ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "$@"
}

remote_sudo() {
  remote "sudo bash -lc '$*'"
}

echo "Preparing ${SSH_TARGET}:${APP_DIR}"
remote_sudo "apt-get update && apt-get install -y python3 python3-venv python3-pip rsync curl"
remote_sudo "mkdir -p '${APP_DIR}' && chown -R '${APP_USER}:${APP_USER}' '${APP_DIR}'"

echo "Syncing source"
rsync -az --delete \
  --exclude ".git" \
  --exclude ".env" \
  --exclude ".env.*" \
  --exclude "local.env" \
  --exclude "local.env.*" \
  --exclude ".deploy.env" \
  --exclude "database" \
  --exclude "venv" \
  --exclude "__pycache__" \
  -e "${RSYNC_SSH}" \
  "${ROOT_DIR}/" "${SSH_TARGET}:${APP_DIR}/"

echo "Writing remote runtime env"
TMP_ENV="$(mktemp)"
trap 'rm -f "${TMP_ENV}"' EXIT
{
  write_env_line "APP_NAME" "${APP_NAME:-B3 Watch API}"
  write_env_line "DATABASE_PATH" "${DATABASE_PATH}"
  write_env_line "SERVER_HOST" "${SERVER_HOST}"
  write_env_line "SERVER_PORT" "${SERVER_PORT}"
  write_env_line "DEFAULT_TIMEZONE" "${DEFAULT_TIMEZONE}"
  write_env_line "QUOTE_CACHE_TTL_SECONDS" "${QUOTE_CACHE_TTL_SECONDS}"
  write_env_line "CHECK_LOOP_SECONDS" "${CHECK_LOOP_SECONDS}"
  write_env_line "CHECK_LOOP_ENABLED" "${CHECK_LOOP_ENABLED}"
  write_env_line "ONESIGNAL_ENABLED" "${ONESIGNAL_ENABLED}"
  write_env_line "ONESIGNAL_APP_ID" "${ONESIGNAL_APP_ID}"
  write_env_line "ONESIGNAL_REST_API_KEY" "${ONESIGNAL_REST_API_KEY}"
  write_env_line "ADMIN_TOKEN" "${ADMIN_TOKEN}"
} > "${TMP_ENV}"
rsync -az -e "${RSYNC_SSH}" "${TMP_ENV}" "${SSH_TARGET}:${APP_DIR}/local.env"
remote "chmod 600 '${APP_DIR}/local.env'"

echo "Installing Python dependencies"
remote "cd '${APP_DIR}' && python3 -m venv venv && ./venv/bin/pip install --upgrade pip && ./venv/bin/pip install -r requirements.txt"

echo "Installing systemd service"
remote_sudo "cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=B3 Watch API
After=network-online.target
Wants=network-online.target

[Service]
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/local.env
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host ${SERVER_HOST} --port ${SERVER_PORT} --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}"

if [[ -n "${UFW_ALLOW_PORT:-}" ]]; then
  remote_sudo "ufw allow '${SERVER_PORT}/tcp' || true"
fi

echo "Deployment finished."
echo "Health URL: http://${VPS_HOST}:${SERVER_PORT}/health"
