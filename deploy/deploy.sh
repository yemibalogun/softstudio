#!/usr/bin/env bash
# Build, migrate and (re)start jaybalostudio.com.
#
# Two modes, chosen by DEPLOY_MODE in .env:
#
#   DEPLOY_MODE=edge        this site runs behind the shared front door
#                           (deploy/edge), which owns 80/443 and the
#                           certificates for every site on the host.
#                             bash deploy/deploy.sh
#
#   DEPLOY_MODE=standalone  (default) this site owns 80/443 and manages its
#                           own certificate. For a host with nothing else on
#                           those ports.
#                             bash deploy/deploy.sh you@example.com   # first run
#                             bash deploy/deploy.sh                   # releases
set -euo pipefail

cd "$(dirname "$0")/.."

DOMAINS=(jaybalostudio.com www.jaybalostudio.com)
PRIMARY=${DOMAINS[0]}
EMAIL=${1:-}
LE=/etc/letsencrypt

die() { echo "$*" >&2; exit 1; }

docker info >/dev/null 2>&1 || die "Cannot talk to Docker. If setup-server.sh just added you to the docker group, log out and SSH back in."
[ -f .env ] || die ".env is missing. Run: cp .env.example .env && nano .env"
if ! grep -q '^DATABASE_URL=postgresql://' .env || grep -q 'REPLACE_WITH' .env; then
  die ".env: DATABASE_URL is not filled in."
fi

MODE=$(sed -n 's/^DEPLOY_MODE=\(.*\)$/\1/p' .env | tail -1 | tr -d '"'"'"' ' || true)
MODE=${MODE:-standalone}

if [ "$MODE" = "edge" ]; then
  COMPOSE="docker compose -f docker-compose.yml -f docker-compose.edge.yml"
else
  COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
  mkdir -p certbot/conf certbot/www
fi

# Run a shell snippet in the certbot image with the certificate volumes
# mounted (the certificate files are root-only on the host). Standalone only.
certsh() { $COMPOSE run --rm --no-deps -T --entrypoint sh certbot -c "$1"; }
make_temp_cert() {
  certsh "rm -rf $LE/live/$PRIMARY $LE/archive/$PRIMARY $LE/renewal/$PRIMARY.conf \
    && mkdir -p $LE/live/$PRIMARY \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=localhost \
         -keyout $LE/live/$PRIMARY/privkey.pem -out $LE/live/$PRIMARY/fullchain.pem 2>/dev/null"
}

if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  echo "==> Pulling latest code"
  git pull --ff-only
fi

echo "==> Building image ($MODE mode)"
$COMPOSE build web

echo "==> Starting database"
$COMPOSE up -d db

echo "==> Applying migrations"
$COMPOSE run --rm -T web flask db upgrade

# ---------------------------------------------------------------- edge mode
if [ "$MODE" = "edge" ]; then
  echo "==> Starting the app"
  $COMPOSE up -d --remove-orphans

  echo "==> Waiting for the app"
  for i in $(seq 1 30); do
    $COMPOSE exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/robots.txt')" >/dev/null 2>&1 && break
    [ "$i" = 30 ] && die "App did not respond. Check: $COMPOSE logs --tail=100 web"
    sleep 2
  done
  echo "    app OK"

  if ! docker ps --format '{{.Names}}' | grep -q '^edge-nginx'; then
    echo
    echo "The app is running, but the shared front door is not."
    echo "Start it once with: bash deploy/edge/setup-edge.sh you@example.com"
    exit 0
  fi

  docker exec edge-nginx-1 nginx -s reload >/dev/null 2>&1 || true
  if curl -fsS -o /dev/null -m 15 "https://$PRIMARY/robots.txt" 2>/dev/null; then
    echo "Live: https://$PRIMARY"
  else
    echo "App is up, but https://$PRIMARY did not answer from here. Check: docker logs edge-nginx-1 --tail=50" >&2
    exit 1
  fi
  exit 0
fi

# ------------------------------------------------------------ standalone mode
bootstrap=false
if ! certsh "test -f $LE/renewal/$PRIMARY.conf"; then
  [ -n "$EMAIL" ] || die "No HTTPS certificate yet. First deploy: bash deploy/deploy.sh you@example.com"
  bootstrap=true

  echo "==> Checking DNS"
  bind_ip=$(sed -n 's/^HTTP_BIND=\(.*\):[0-9]*$/\1/p' .env | tail -1)
  server_ips=" $(hostname -I 2>/dev/null) $(curl -4 -fsS -m 5 https://api.ipify.org 2>/dev/null || true) "
  for d in "${DOMAINS[@]}"; do
    resolved=$(getent ahostsv4 "$d" | awk 'NR==1{print $1}')
    echo "    $d -> ${resolved:-<no A record>}"
    [ -n "$resolved" ] || die "$d has no A record."
    if [ -n "$bind_ip" ]; then
      [ "$resolved" = "$bind_ip" ] || die "$d points to $resolved, but nginx is set to listen on $bind_ip (HTTP_BIND). Update the DNS A record."
    else
      case "$server_ips" in *" $resolved "*) ;; *) die "$d points to $resolved, which is not this server." ;; esac
    fi
  done

  echo "==> Creating a temporary certificate so nginx can start"
  make_temp_cert
fi

echo "==> Starting services"
if ! $COMPOSE up -d --remove-orphans; then
  die "Could not start. If the error says port 80/443 is already allocated, another site on this server
is using those ports. Either put this site behind the shared front door (DEPLOY_MODE=edge in .env,
then bash deploy/edge/setup-edge.sh), or give it an IP of its own with HTTP_BIND/HTTPS_BIND."
fi

echo "==> Waiting for the app"
for i in $(seq 1 30); do
  $COMPOSE exec -T nginx wget -q -O /dev/null http://softstudio-web:8000/robots.txt 2>/dev/null && break
  [ "$i" = 30 ] && die "App did not respond. Check: $COMPOSE logs --tail=100 web nginx"
  sleep 2
done

if $bootstrap; then
  echo "==> Checking jaybalostudio.com reaches this site's nginx"
  token="check-$(date +%s)"
  certsh "mkdir -p /var/www/certbot/.well-known/acme-challenge && echo $token > /var/www/certbot/.well-known/acme-challenge/$token"
  for d in "${DOMAINS[@]}"; do
    got=$(curl -fsS -m 10 "http://$d/.well-known/acme-challenge/$token" 2>/dev/null || true)
    if [ "$got" != "$token" ]; then
      certsh "rm -f /var/www/certbot/.well-known/acme-challenge/$token"
      die "http://$d is not answered by this site's nginx (another web server answered, or port 80 is blocked).
No certificate was requested, so no Let's Encrypt rate limit was used."
    fi
    echo "    $d OK"
  done
  certsh "rm -f /var/www/certbot/.well-known/acme-challenge/$token"

  echo "==> Requesting the Let's Encrypt certificate"
  certsh "rm -rf $LE/live/$PRIMARY $LE/archive/$PRIMARY $LE/renewal/$PRIMARY.conf"
  domain_args=()
  for d in "${DOMAINS[@]}"; do domain_args+=(-d "$d"); done
  if ! $COMPOSE run --rm --no-deps -T --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
       "${domain_args[@]}" --email "$EMAIL" --agree-tos --no-eff-email -n; then
    make_temp_cert  # keep nginx restartable
    die "Certificate request failed; see the certbot output above."
  fi
  $COMPOSE exec -T nginx nginx -s reload
fi

if curl -fsS -o /dev/null -m 15 "https://$PRIMARY/robots.txt" 2>/dev/null; then
  echo "Live: https://$PRIMARY"
else
  echo "Services are up, but https://$PRIMARY did not answer from here. Check: $COMPOSE logs --tail=100 nginx web" >&2
  exit 1
fi
