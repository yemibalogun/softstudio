#!/usr/bin/env bash
# Build and (re)start the softstudio stack. Safe to run on every release:
#   bash deploy/deploy.sh
# The first time, follow with: sudo bash deploy/front-proxy.sh you@example.com
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
FRONT_NETWORK=${FRONT_NETWORK:-food_store_default}

if ! docker info >/dev/null 2>&1; then
  echo "Cannot talk to Docker. If setup-server.sh just added you to the docker group," >&2
  echo "log out and SSH back in (check with: groups | grep docker)." >&2
  exit 1
fi
if [ ! -f .env ]; then
  echo ".env is missing. Run: cp .env.example .env && nano .env" >&2
  exit 1
fi
if ! grep -q '^DATABASE_URL=postgresql://' .env || grep -q 'REPLACE_WITH' .env; then
  echo ".env: DATABASE_URL is not filled in." >&2
  exit 1
fi
if ! docker network inspect "$FRONT_NETWORK" >/dev/null 2>&1; then
  echo "Docker network $FRONT_NETWORK not found; is the food store stack running?" >&2
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
  if $COMPOSE exec -T nginx wget -q -O /dev/null http://127.0.0.1/robots.txt 2>/dev/null; then
    echo "softstudio is running (internal)."
    if curl -fsS -o /dev/null -m 10 https://jaybalostudio.com/robots.txt 2>/dev/null; then
      echo "Live: https://jaybalostudio.com"
    else
      echo "Not public yet. First time? Run: sudo bash deploy/front-proxy.sh you@example.com"
    fi
    exit 0
  fi
  sleep 2
done
echo "App did not respond. Check: $COMPOSE logs --tail=100 web nginx" >&2
exit 1
