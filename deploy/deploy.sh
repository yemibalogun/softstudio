#!/usr/bin/env bash
# Build and (re)start the production stack. Safe to run on every release:
#   bash deploy/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

if [ ! -f .env ]; then
  echo ".env is missing. Run: cp .env.example .env && nano .env" >&2
  exit 1
fi
if ! grep -q '^DATABASE_URL=postgresql://' .env || grep -q 'REPLACE_WITH' .env; then
  echo ".env: DATABASE_URL is not filled in." >&2
  exit 1
fi
# live/ is root-only on the host, so check from inside a container.
if ! docker run --rm -v "$PWD/certbot/conf:/etc/letsencrypt" --entrypoint test certbot/certbot -d /etc/letsencrypt/live/jaybalostudio.com; then
  echo "No HTTPS certificate yet. Run: bash deploy/init-letsencrypt.sh you@example.com" >&2
  exit 1
fi

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Building image"
$COMPOSE build web

echo "==> Starting database"
$COMPOSE up -d db

echo "==> Applying migrations"
$COMPOSE run --rm web flask db upgrade

echo "==> Starting services"
$COMPOSE up -d --remove-orphans

echo "==> Waiting for the app"
for i in $(seq 1 30); do
  if curl -fsS -o /dev/null https://jaybalostudio.com/robots.txt; then
    echo "Live: https://jaybalostudio.com"
    exit 0
  fi
  sleep 2
done
echo "App did not respond over HTTPS. Check: $COMPOSE logs --tail=100 web nginx" >&2
exit 1
