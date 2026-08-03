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
HTTPS_ENABLED="${HTTPS_ENABLED:-true}"
HTTP_SERVER_PORT="${HTTP_SERVER_PORT:-80}"
HTTPS_SERVER_PORT="${HTTPS_SERVER_PORT:-443}"
if [[ -z "${PUBLIC_SERVER_PORT:-}" ]]; then
  if [[ "${HTTPS_ENABLED}" == "true" || "${HTTPS_ENABLED}" == "1" || "${HTTPS_ENABLED}" == "yes" || "${HTTPS_ENABLED}" == "on" ]]; then
    PUBLIC_SERVER_PORT="${HTTPS_SERVER_PORT}"
  else
    PUBLIC_SERVER_PORT="${HTTP_SERVER_PORT}"
  fi
fi
ENABLE_REVERSE_PROXY="${ENABLE_REVERSE_PROXY:-auto}"
DATABASE_PATH="${DATABASE_PATH:-database/app.db}"
DEFAULT_TIMEZONE="${DEFAULT_TIMEZONE:-America/Sao_Paulo}"
QUOTE_CACHE_TTL_SECONDS="${QUOTE_CACHE_TTL_SECONDS:-60}"
CHECK_LOOP_SECONDS="${CHECK_LOOP_SECONDS:-30}"
CHECK_LOOP_ENABLED="${CHECK_LOOP_ENABLED:-true}"
ONESIGNAL_ENABLED="${ONESIGNAL_ENABLED:-true}"
HEALTH_CHECK_RETRIES="${HEALTH_CHECK_RETRIES:-30}"
HEALTH_CHECK_INTERVAL_SECONDS="${HEALTH_CHECK_INTERVAL_SECONDS:-2}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
LETSENCRYPT_STAGING="${LETSENCRYPT_STAGING:-false}"
if [[ -z "${HOST_FIREWALL_ALLOW_PORTS:-}" ]]; then
  if [[ "${HTTPS_ENABLED}" == "true" || "${HTTPS_ENABLED}" == "1" || "${HTTPS_ENABLED}" == "yes" || "${HTTPS_ENABLED}" == "on" ]]; then
    HOST_FIREWALL_ALLOW_PORTS="${HTTP_SERVER_PORT},${HTTPS_SERVER_PORT}"
  else
    HOST_FIREWALL_ALLOW_PORTS="${HOST_FIREWALL_ALLOW_PORT:-${UFW_ALLOW_PORT:-${PUBLIC_SERVER_PORT}}}"
  fi
fi
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

truthy() {
  [[ "$1" == "true" || "$1" == "1" || "$1" == "yes" || "$1" == "on" ]]
}

https_enabled() {
  truthy "${HTTPS_ENABLED}"
}

reverse_proxy_enabled() {
  https_enabled || [[ "${ENABLE_REVERSE_PROXY}" == "true" ]] || {
    [[ "${ENABLE_REVERSE_PROXY}" == "auto" && "${PUBLIC_SERVER_PORT}" != "${SERVER_PORT}" ]]
  }
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

SERVICE_BIND_HOST="${SERVER_HOST}"
if reverse_proxy_enabled && [[ "${SERVER_HOST}" == "0.0.0.0" ]]; then
  SERVICE_BIND_HOST="127.0.0.1"
fi

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

print_remote_diagnostics() {
  echo "Remote diagnostics:"
  remote "systemctl is-active '${SERVICE_NAME}' || true"
  remote_sudo "systemctl status ${SERVICE_NAME} --no-pager -l || true"
  remote_sudo "journalctl -u ${SERVICE_NAME} -n 120 --no-pager || true"
  remote_sudo "ss -ltnp | grep \":${SERVER_PORT} \" || true"
  remote_sudo "ss -ltnp | grep \":${HTTP_SERVER_PORT} \" || true"
  remote_sudo "ss -ltnp | grep \":${HTTPS_SERVER_PORT} \" || true"
  remote_sudo "ss -ltnp | grep \":${PUBLIC_SERVER_PORT} \" || true"
  if reverse_proxy_enabled; then
    remote_sudo "systemctl status nginx --no-pager -l || true"
    remote_sudo "journalctl -u nginx -n 80 --no-pager || true"
  fi
  remote_sudo "ufw status verbose || true"
  remote_sudo "iptables -S INPUT || true"
  remote_sudo "nft list ruleset 2>/dev/null | sed -n \"1,180p\" || true"
}

wait_for_remote_health() {
  local remote_health_url="http://127.0.0.1:${SERVER_PORT}/health"
  echo "Waiting for service health inside VPS: ${remote_health_url}"
  if remote "for attempt in \$(seq 1 '${HEALTH_CHECK_RETRIES}'); do curl -fsS --max-time 3 '${remote_health_url}' && exit 0; sleep '${HEALTH_CHECK_INTERVAL_SECONDS}'; done; exit 1"; then
    echo
    return 0
  fi

  echo "Service did not become healthy inside the VPS." >&2
  print_remote_diagnostics
  return 1
}

public_health_url() {
  if https_enabled; then
    if [[ "${HTTPS_SERVER_PORT}" == "443" ]]; then
      printf 'https://%s/health' "${VPS_HOST}"
    else
      printf 'https://%s:%s/health' "${VPS_HOST}" "${HTTPS_SERVER_PORT}"
    fi
  elif [[ "${PUBLIC_SERVER_PORT}" == "80" ]]; then
    printf 'http://%s/health' "${VPS_HOST}"
  else
    printf 'http://%s:%s/health' "${VPS_HOST}" "${PUBLIC_SERVER_PORT}"
  fi
}

wait_for_remote_public_health() {
  local remote_health_url="http://127.0.0.1:${PUBLIC_SERVER_PORT}/health"
  local curl_tls_flag=""
  if https_enabled; then
    remote_health_url="https://127.0.0.1:${HTTPS_SERVER_PORT}/health"
    curl_tls_flag="-k"
  fi
  echo "Waiting for public port health inside VPS: ${remote_health_url}"
  if remote "for attempt in \$(seq 1 '${HEALTH_CHECK_RETRIES}'); do curl ${curl_tls_flag} -fsS --max-time 3 '${remote_health_url}' && exit 0; sleep '${HEALTH_CHECK_INTERVAL_SECONDS}'; done; exit 1"; then
    echo
    return 0
  fi

  echo "Public port did not become healthy inside the VPS." >&2
  print_remote_diagnostics
  return 1
}

check_public_health() {
  local public_health_url
  public_health_url="$(public_health_url)"
  echo "Checking public health URL: ${public_health_url}"
  if curl -fsS --max-time 8 "${public_health_url}"; then
    echo
    return 0
  fi

  echo "The service is running on the VPS, but the public health URL is not reachable from this machine." >&2
  echo "Most common causes: VPS firewall/security-group port ${PUBLIC_SERVER_PORT} is closed, nginx is not listening on the public port, TLS certificate issuance failed, or the provider blocks direct inbound traffic." >&2
  print_remote_diagnostics
  return 1
}

configure_reverse_proxy() {
  echo "Installing nginx HTTP reverse proxy on :${HTTP_SERVER_PORT} -> 127.0.0.1:${SERVER_PORT}"
  remote_sudo "cat > /etc/nginx/sites-available/${SERVICE_NAME} <<EOF
server {
    listen ${HTTP_SERVER_PORT} default_server;
    listen [::]:${HTTP_SERVER_PORT} default_server;
    server_name _;
    client_max_body_size 2m;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://127.0.0.1:${SERVER_PORT};
    }
}
EOF
mkdir -p /var/www/certbot
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/${SERVICE_NAME}
nginx -t
systemctl enable nginx
systemctl restart nginx"
}

certificate_name() {
  printf '%s' "${TLS_CERT_NAME:-${VPS_HOST}}"
}

install_certbot() {
  echo "Installing Certbot 5.4+ for Let's Encrypt IP certificates"
  remote_sudo "python3 -m venv /opt/certbot-venv
/opt/certbot-venv/bin/pip install --upgrade pip
/opt/certbot-venv/bin/pip install --upgrade \"certbot>=5.4\""
}

issue_tls_certificate() {
  local cert_name
  local certbot_email_args="--register-unsafely-without-email"
  local certbot_staging_arg=""
  cert_name="$(certificate_name)"
  if [[ -n "${LETSENCRYPT_EMAIL}" ]]; then
    certbot_email_args="--email ${LETSENCRYPT_EMAIL}"
  fi
  if truthy "${LETSENCRYPT_STAGING}"; then
    certbot_staging_arg="--staging"
  fi

  echo "Requesting Let's Encrypt IP certificate for ${VPS_HOST}"
  remote_sudo "/opt/certbot-venv/bin/certbot certonly \
    --non-interactive \
    --agree-tos \
    ${certbot_staging_arg} \
    ${certbot_email_args} \
    --preferred-profile shortlived \
    --webroot \
    --webroot-path /var/www/certbot \
    --ip-address ${VPS_HOST} \
    --cert-name ${cert_name} \
    --keep-until-expiring \
    --deploy-hook \"systemctl reload nginx\""
}

configure_https_reverse_proxy() {
  local cert_name
  cert_name="$(certificate_name)"
  echo "Installing nginx HTTPS reverse proxy on :${HTTPS_SERVER_PORT} -> 127.0.0.1:${SERVER_PORT}"
  remote_sudo "cat > /etc/nginx/sites-available/${SERVICE_NAME} <<EOF
server {
    listen ${HTTP_SERVER_PORT} default_server;
    listen [::]:${HTTP_SERVER_PORT} default_server;
    server_name _;
    client_max_body_size 2m;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://${VPS_HOST};
    }
}

server {
    listen ${HTTPS_SERVER_PORT} ssl default_server;
    listen [::]:${HTTPS_SERVER_PORT} ssl default_server;
    server_name _;
    client_max_body_size 2m;

    ssl_certificate /etc/letsencrypt/live/${cert_name}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${cert_name}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    location / {
        proxy_pass http://127.0.0.1:${SERVER_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host ${VPS_HOST};
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF
nginx -t
systemctl restart nginx"
}

install_certificate_renewal_timer() {
  echo "Installing Let's Encrypt renewal timer"
  remote_sudo "cat > /etc/systemd/system/${SERVICE_NAME}-cert-renew.service <<EOF
[Unit]
Description=Renew B3 Watch API TLS certificate

[Service]
Type=oneshot
ExecStart=/opt/certbot-venv/bin/certbot renew --quiet --deploy-hook \"systemctl reload nginx\"
EOF
cat > /etc/systemd/system/${SERVICE_NAME}-cert-renew.timer <<EOF
[Unit]
Description=Renew B3 Watch API TLS certificate twice daily

[Timer]
OnCalendar=*-*-* 03,15:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now ${SERVICE_NAME}-cert-renew.timer"
}

allow_public_ports() {
  if [[ "${HOST_FIREWALL_ALLOW_PORTS}" == "false" || "${HOST_FIREWALL_ALLOW_PORTS}" == "none" ]]; then
    return
  fi

  local ports
  ports="${HOST_FIREWALL_ALLOW_PORTS//,/ }"
  for port in ${ports}; do
    echo "Allowing inbound TCP port ${port} in host firewall when available"
    remote_sudo "if command -v ufw >/dev/null 2>&1; then
      ufw allow ${port}/tcp || true
    fi
    if command -v iptables >/dev/null 2>&1; then
      iptables -C INPUT -p tcp --dport ${port} -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport ${port} -j ACCEPT
      if command -v netfilter-persistent >/dev/null 2>&1; then
        netfilter-persistent save || true
      elif [ -d /etc/iptables ] && command -v iptables-save >/dev/null 2>&1; then
        iptables-save > /etc/iptables/rules.v4 || true
      fi
    fi"
  done
}

echo "Preparing ${SSH_TARGET}:${APP_DIR}"
REMOTE_PACKAGES="python3 python3-venv python3-pip rsync curl"
if reverse_proxy_enabled; then
  REMOTE_PACKAGES="${REMOTE_PACKAGES} nginx"
fi
remote_sudo "apt-get update && apt-get install -y ${REMOTE_PACKAGES}"
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
  write_env_line "SERVER_HOST" "${SERVICE_BIND_HOST}"
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
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host ${SERVICE_BIND_HOST} --port ${SERVER_PORT} --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}"

if reverse_proxy_enabled; then
  configure_reverse_proxy
fi

allow_public_ports

if https_enabled; then
  install_certbot
  issue_tls_certificate
  configure_https_reverse_proxy
  install_certificate_renewal_timer
fi

wait_for_remote_health
if reverse_proxy_enabled; then
  wait_for_remote_public_health
fi
check_public_health

echo "Deployment finished."
echo "Health URL: $(public_health_url)"
