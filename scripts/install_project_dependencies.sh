#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_URL="${UNIVERSAL_NOTIFIER_REPO_URL:-https://github.com/mundosoftware/Universal-Notifier.git}"
REPO_PATH="${UNIVERSAL_NOTIFIER_REPO_PATH:-${ROOT_DIR}/.deps/Universal-Notifier}"
REPO_USERNAME="${UNIVERSAL_NOTIFIER_REPO_USERNAME:-mundosoftware}"

read -r -s -p "GitHub password or token for ${REPO_USERNAME}: " REPO_PASSWORD
printf '\n'

PASSWORD_FILE="$(mktemp)"
chmod 600 "${PASSWORD_FILE}"
printf '%s' "${REPO_PASSWORD}" > "${PASSWORD_FILE}"
trap 'rm -f "${PASSWORD_FILE}"' EXIT

ASKPASS_SCRIPT="$(mktemp)"
chmod 700 "${ASKPASS_SCRIPT}"
cat > "${ASKPASS_SCRIPT}" <<EOF
#!/usr/bin/env bash
cat "${PASSWORD_FILE}"
EOF
trap 'rm -f "${PASSWORD_FILE}" "${ASKPASS_SCRIPT}"' EXIT

GIT_AUTH=(env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="${ASKPASS_SCRIPT}")

mkdir -p "$(dirname "${REPO_PATH}")"

if [[ -d "${REPO_PATH}/.git" ]]; then
  "${GIT_AUTH[@]}" git -c "credential.username=${REPO_USERNAME}" -C "${REPO_PATH}" pull --ff-only
elif [[ -e "${REPO_PATH}" ]]; then
  echo "Dependency path exists and is not a git checkout: ${REPO_PATH}" >&2
  exit 1
else
  "${GIT_AUTH[@]}" git -c "credential.username=${REPO_USERNAME}" clone --depth 1 "${REPO_URL}" "${REPO_PATH}"
fi

echo "Universal Notifier is available at ${REPO_PATH}"