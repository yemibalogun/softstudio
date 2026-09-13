#!/usr/bin/env bash
# Build, migrate and (re)start jaybalostudio.com with its own nginx + HTTPS.
#   bash deploy/deploy.sh you@example.com   # first run: also obtains the certificate
#   bash deploy/deploy.sh                   # every release after that
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
DOMAINS=(jaybalostudio.com www.jaybalostudio.com)
PRIMARY=${DOMAINS[0]}
EMAIL=${1:-}
LE=/etc/letsencrypt

die() { echo "$*" >&2; exit 1; }
# Run a shell snippet in the certbot image with the certificate volumes mounted.
# (The certificate files are root-only on the host.)
certsh() { $COMPOSE run --rm --no-deps -T --entrypoint sh certbot -c "$1"; }
make_temp_cert() {
  certsh "rm -rf $LE/live/$PRIMARY $LE/archive/$PRIMARY $LE/renewal/$PRIMARY.conf \
    && mkdir -p $LE/live/$PRIMARY \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=localhost \
         -keyout $LE/live/$PRIMARY/privkey.pem -out $LE/live/$PRIMARY/fullchain.pem 2>/dev/null"
}

docker info >/dev/null 2>&1 || die "Cannot talk to Docker. If setup-server.sh just added you to the docker group, log out and SSH back in."
[ -f .env ] || die ".env is missing. Run: cp .env.example .env && nano .env"
if ! grep -q '^DATABASE_URL=postgresql://' .env || grep -q 'REPLACE_WITH' .env; then
  die ".env: DATABASE_URL is not filled in."
fi
mkdir -p certbot/conf certbot/www

if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  echo "==> Pulling latest code"
  git pull --ff-only
fi

echo "==> Building image"
$COMPOSE build web

echo "==> Starting database"
$COMPOSE up -d db

echo "==> Applying migrations"
$COMPOSE run --rm -T web flask db upgrade

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
is using those ports on this IP. Set HTTP_BIND/HTTPS_BIND in .env to an IP address of our own."
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
