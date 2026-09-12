#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu/Debian VPS. Copy to the server and run as root:
#   scp deploy/setup-server.sh root@SERVER_IP:~ && ssh root@SERVER_IP bash setup-server.sh
# The repo is private: the first run prints a deploy key to add on GitHub,
# then re-run to clone.
set -euo pipefail

APP_DIR=/opt/softstudio
REPO_URL=${REPO_URL:-git@github.com:yemibalogun/softstudio.git}

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
  KEY=/root/.ssh/softstudio_deploy
  if [ ! -f "$KEY" ]; then
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    ssh-keygen -t ed25519 -N "" -C "softstudio-deploy" -f "$KEY"
    cat >> /root/.ssh/config <<CFG
Host github.com
  IdentityFile $KEY
  IdentitiesOnly yes
CFG
    ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null
  fi
  if ! ssh -o BatchMode=yes -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo
    echo "Add this deploy key on GitHub (repo > Settings > Deploy keys > Add, read-only):"
    echo
    cat "$KEY.pub"
    echo
    echo "Then re-run: bash setup-server.sh"
    exit 1
  fi
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
