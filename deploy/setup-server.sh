#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu/Debian VPS. Run as root on the server:
#   curl -fsSL https://raw.githubusercontent.com/yemibalogun/softstudio/main/deploy/setup-server.sh | bash
set -euo pipefail

APP_DIR=/opt/softstudio
REPO_URL=${REPO_URL:-https://github.com/yemibalogun/softstudio.git}

echo "==> Installing base packages"
apt-get update
apt-get install -y ca-certificates curl git ufw

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi

echo "==> Configuring firewall (SSH, HTTP, HTTPS)"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Cloning $REPO_URL into $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
[ -f .env ] || cp .env.example .env

echo
echo "Done. Next:"
echo "  1. nano $APP_DIR/.env          # fill in SECRET_KEY, POSTGRES_PASSWORD, DATABASE_URL, ..."
echo "  2. bash deploy/init-letsencrypt.sh you@example.com"
echo "  3. bash deploy/deploy.sh"
