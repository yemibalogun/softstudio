#!/usr/bin/env bash
# Put jaybalostudio.com behind the nginx that already serves shamsfoodstore.com
# on this VPS, and give it an HTTPS certificate. Run after deploy/deploy.sh:
#   sudo bash deploy/front-proxy.sh you@example.com   # add / update
#   sudo bash deploy/front-proxy.sh --remove          # undo
#
# Every change to the food store's nginx config is backed up, validated with
# `nginx -t`, and rolled back automatically if validation fails.
set -euo pipefail

FRONT_CONF=${FRONT_CONF:-/opt/food_store/nginx/nginx.conf}
FRONT_CONTAINER=${FRONT_CONTAINER:-food_store-nginx-1}
CERTBOT_DIR=${CERTBOT_DIR:-/opt/food_store/certbot}
FRONT_NETWORK=${FRONT_NETWORK:-food_store_default}
CERTBOT_IMAGE=${CERTBOT_IMAGE:-certbot/certbot}
IN_CONTAINER_CONF=/etc/nginx/conf.d/default.conf
DOMAINS=(jaybalostudio.com www.jaybalostudio.com)
BEGIN='# BEGIN jaybalostudio (managed by /opt/softstudio/deploy/front-proxy.sh)'
END='# END jaybalostudio'
HERE="$(cd "$(dirname "$0")" && pwd)"

die() { echo "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run with sudo: sudo bash deploy/front-proxy.sh ${1:-you@example.com}"
[ -f "$FRONT_CONF" ] || die "Front nginx config not found: $FRONT_CONF"
docker inspect "$FRONT_CONTAINER" >/dev/null 2>&1 || die "Front container not running: $FRONT_CONTAINER"

# Rewrites the managed block. $1 = snippet file, or empty to remove the block.
apply_block() {
  local snippet=$1 backup stripped
  backup="$FRONT_CONF.bak.$(date +%Y%m%d-%H%M%S)"
  cp -p "$FRONT_CONF" "$backup"

  stripped=$(awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1;next} $0==e{skip=0;next} !skip' "$FRONT_CONF")
  {
    printf '%s\n' "$stripped"
    if [ -n "$snippet" ]; then
      printf '\n%s\n' "$BEGIN"
      cat "$snippet"
      printf '%s\n' "$END"
    fi
  } > "$FRONT_CONF.new"

  # Write in place, never mv: the file is bind-mounted into the container, and
  # a replaced file (new inode) would stay invisible to it.
  cat "$FRONT_CONF.new" > "$FRONT_CONF"
  rm -f "$FRONT_CONF.new"

  # Make sure the container actually sees what we wrote.
  if [ -n "$snippet" ] && ! docker exec "$FRONT_CONTAINER" grep -qF "$BEGIN" "$IN_CONTAINER_CONF"; then
    cat "$backup" > "$FRONT_CONF"
    die "The container does not see the updated $FRONT_CONF (stale bind mount). Restored the backup.
Restart the front proxy once (docker restart $FRONT_CONTAINER), then re-run this script."
  fi

  if ! docker exec "$FRONT_CONTAINER" nginx -t; then
    cat "$backup" > "$FRONT_CONF"
    die "nginx config test failed. Restored $backup; nothing was reloaded, shamsfoodstore.com is unaffected."
  fi
  docker exec "$FRONT_CONTAINER" nginx -s reload
  echo "==> Front proxy reloaded (backup: $backup)"
}

have_cert() {
  docker exec "$FRONT_CONTAINER" test -f /etc/letsencrypt/live/jaybalostudio.com/fullchain.pem
}

if [ "${1:-}" = "--remove" ]; then
  apply_block ""
  echo "jaybalostudio.com removed from the front proxy. Certificates were left in $CERTBOT_DIR."
  exit 0
fi

EMAIL=${1:?Usage: sudo bash deploy/front-proxy.sh you@example.com}

docker network inspect "$FRONT_NETWORK" >/dev/null 2>&1 \
  || die "Docker network $FRONT_NETWORK not found."
docker network inspect "$FRONT_NETWORK" --format '{{range .Containers}}{{.Name}} {{end}}' | grep -q softstudio \
  || die "softstudio is not on the food store network yet. Run first: bash deploy/deploy.sh"

if ! have_cert; then
  echo "==> Step 1/3: serving Let's Encrypt challenges for jaybalostudio.com"
  apply_block "$HERE/front-proxy/jaybalostudio.http.conf"

  echo "==> Checking the challenge path is reachable from the internet"
  token="check-$(date +%s)"
  mkdir -p "$CERTBOT_DIR/www/.well-known/acme-challenge"
  echo ok > "$CERTBOT_DIR/www/.well-known/acme-challenge/$token"
  for d in "${DOMAINS[@]}"; do
    got=$(curl -fsS -m 10 "http://$d/.well-known/acme-challenge/$token" || true)
    [ "$got" = ok ] || { rm -f "$CERTBOT_DIR/www/.well-known/acme-challenge/$token"; die "http://$d/.well-known/acme-challenge/ is not reachable. Check DNS for $d."; }
    echo "    $d OK"
  done
  rm -f "$CERTBOT_DIR/www/.well-known/acme-challenge/$token"

  echo "==> Step 2/3: requesting the certificate"
  domain_args=()
  for d in "${DOMAINS[@]}"; do domain_args+=(-d "$d"); done
  docker run --rm \
    -v "$CERTBOT_DIR/conf:/etc/letsencrypt" \
    -v "$CERTBOT_DIR/www:/var/www/certbot" \
    "$CERTBOT_IMAGE" certonly --webroot -w /var/www/certbot \
    "${domain_args[@]}" --email "$EMAIL" --agree-tos --no-eff-email -n
  have_cert || die "Certificate was not created; see certbot output above."
fi

echo "==> Step 3/3: enabling HTTPS for jaybalostudio.com"
apply_block "$HERE/front-proxy/jaybalostudio.https.conf"

CRON_FILE=/etc/cron.d/jaybalostudio-cert-renew
if [ -d /etc/cron.d ] && [ ! -f "$CRON_FILE" ]; then
  echo "==> Scheduling daily certificate renewal ($CRON_FILE)"
  cat > "$CRON_FILE" <<CRON
# Renews all certificates in $CERTBOT_DIR and reloads $FRONT_CONTAINER.
17 3 * * * root bash $HERE/renew-certs.sh >> /var/log/cert-renew.log 2>&1
CRON
  chmod 644 "$CRON_FILE"
fi

code=$(curl -s -o /dev/null -m 15 -w '%{http_code}' https://jaybalostudio.com/robots.txt || true)
if [ "$code" = 200 ]; then
  echo "Live: https://jaybalostudio.com"
else
  echo "HTTPS is configured but the site answered $code. Check: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 web nginx" >&2
  exit 1
fi
