#!/usr/bin/env bash
# Obtain the first HTTPS certificate. Run once, after DNS points at this server
# and before the first deploy:
#   bash deploy/init-letsencrypt.sh you@example.com
set -euo pipefail

EMAIL=${1:?Usage: bash deploy/init-letsencrypt.sh you@example.com}
DOMAINS=(jaybalostudio.com www.jaybalostudio.com)

cd "$(dirname "$0")/.."
if ! docker info >/dev/null 2>&1; then
  echo "Cannot talk to Docker. If setup-server.sh just added you to the docker group," >&2
  echo "log out and SSH back in (check with: groups | grep docker)." >&2
  exit 1
fi
mkdir -p certbot/conf certbot/www

# live/ is root-only on the host, so check from inside a container.
if docker run --rm -v "$PWD/certbot/conf:/etc/letsencrypt" --entrypoint test certbot/certbot -d "/etc/letsencrypt/live/${DOMAINS[0]}"; then
  echo "Certificate for ${DOMAINS[0]} already exists; nothing to do."
  exit 0
fi

SERVER_IP=$(curl -fsS https://api.ipify.org || true)
for d in "${DOMAINS[@]}"; do
  resolved=$(getent ahostsv4 "$d" | awk 'NR==1{print $1}')
  echo "$d -> ${resolved:-<no A record>} (this server: ${SERVER_IP:-unknown})"
  if [ -n "$SERVER_IP" ] && [ "$resolved" != "$SERVER_IP" ]; then
    echo "DNS for $d does not point at this server yet. Fix the A record and retry." >&2
    exit 1
  fi
done

# Port 80 must be free for the standalone challenge.
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop nginx 2>/dev/null || true

holders=$(docker ps --filter publish=80 --format '{{.Names}}  ({{.Image}})')
if [ -n "$holders" ]; then
  echo "Port 80 is still held by these containers:" >&2
  echo "$holders" >&2
  echo "Stop them (docker stop NAME) and re-run this script." >&2
  exit 1
fi

domain_args=()
for d in "${DOMAINS[@]}"; do domain_args+=(-d "$d"); done

docker run --rm -p 80:80 \
  -v "$PWD/certbot/conf:/etc/letsencrypt" \
  -v "$PWD/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --standalone \
  "${domain_args[@]}" --email "$EMAIL" --agree-tos --no-eff-email -n

echo "Certificate obtained. Now run: bash deploy/deploy.sh"
