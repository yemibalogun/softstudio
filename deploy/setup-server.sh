#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu/Debian VPS. Run from your normal login user:
#   curl -fsSL https://raw.githubusercontent.com/yemibalogun/softstudio/main/deploy/setup-server.sh | sudo bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "This script needs root. Re-run it with sudo:" >&2
  echo "  curl -fsSL https://raw.githubusercontent.com/yemibalogun/softstudio/main/deploy/setup-server.sh | sudo bash" >&2
  exit 1
fi

# The user who invoked sudo owns the app and runs deploys without root.
APP_USER=${SUDO_USER:-root}

APP_DIR=/opt/softstudio
REPO_URL=${REPO_URL:-https://github.com/yemibalogun/softstudio.git}

echo "==> Installing base packages"
apt-get update
apt-get install -y ca-certificates curl git ufw iproute2

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi

echo "==> Configuring firewall (SSH, HTTP, HTTPS)"
ufw allow OpenSSH
# Also allow whatever port sshd actually listens on, so a custom port can't lock us out.
for port in $(ss -tlnpH 2>/dev/null | awk '/sshd/ {n=split($4,a,":"); print a[n]}' | sort -u); do
  ufw allow "$port/tcp"
done
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Cloning $REPO_URL into $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi

if [ "$APP_USER" != root ]; then
  echo "==> Giving $APP_USER ownership of $APP_DIR and Docker access"
  usermod -aG docker "$APP_USER"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

cd "$APP_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  chown "$APP_USER:$APP_USER" .env
fi
chmod 600 .env

echo
echo "Done. Log out and back in so the docker group applies, then:"
echo "  cd $APP_DIR"
echo "  1. nano $APP_DIR/.env          # fill in SECRET_KEY, POSTGRES_PASSWORD, DATABASE_URL, ..."
echo "  2. bash deploy/init-letsencrypt.sh you@example.com"
echo "  3. bash deploy/deploy.sh"
