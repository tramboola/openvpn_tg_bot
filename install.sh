#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

fail() {
  echo "Ошибка: $*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "запустите установщик через sudo: sudo ./install.sh"
fi

if [[ ! -r /etc/os-release ]]; then
  fail "не удалось определить операционную систему"
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  fail "автоматическая установка поддерживает Ubuntu; для другой системы используйте README"
fi

install_docker() {
  echo "Устанавливаю Docker Engine и Docker Compose из официального репозитория…"
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-${VERSION_CODENAME}}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

  apt-get update
  apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
}

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  install_docker
fi

systemctl enable --now docker

read -r -s -p "Токен бота от BotFather: " BOT_TOKEN_VALUE
echo
[[ "${BOT_TOKEN_VALUE}" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]] || \
  fail "токен бота имеет неверный формат"

read -r -p "Ваш числовой Telegram ID: " ADMIN_TELEGRAM_ID_VALUE
[[ "${ADMIN_TELEGRAM_ID_VALUE}" =~ ^[0-9]+$ ]] || \
  fail "Telegram ID должен состоять только из цифр"

cd "${PROJECT_DIR}"
umask 077
install -d -m 0700 data secrets
printf '%s\n' "${BOT_TOKEN_VALUE}" > secrets/bot_token
chmod 0600 secrets/bot_token

cat > .env <<EOF
ADMIN_TELEGRAM_ID=${ADMIN_TELEGRAM_ID_VALUE}
STATE_FILE=/app/data/state.json
OPENVPN_IMAGE=kylemanna/openvpn:2.4@sha256:4de5e6690818c7c4025ae605369f681e813a7f9fe5d99feed988412c2d07987c
DOCKER_BIN=/usr/bin/docker
EOF
chmod 0600 .env

echo "Собираю и запускаю Telegram-бота…"
docker compose up -d --build
docker compose ps

echo
echo "Установка завершена. Откройте бота в Telegram, нажмите /start и выберите UDP или TCP."
