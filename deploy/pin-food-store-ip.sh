#!/usr/bin/env bash
# Pin shamsfoodstore.com's nginx to its own IP address, so jaybalostudio.com's
# nginx can use the server's second IP on ports 80/443.
#
# Adds docker-compose.override.yml next to the food store's compose file (its
# tracked files are not edited) and recreates only the food store's nginx
# container: about 10 seconds of downtime. If the food store does not answer
# on its IP afterwards, the change is undone automatically.
#
#   sudo bash deploy/pin-food-store-ip.sh 156.232.88.138           # preview only
#   sudo bash deploy/pin-food-store-ip.sh 156.232.88.138 --apply   # apply
#   sudo bash deploy/pin-food-store-ip.sh --undo                   # revert
set -euo pipefail

FOOD_CONTAINER=${FOOD_CONTAINER:-food_store-nginx-1}
FOOD_DOMAIN=${FOOD_DOMAIN:-shamsfoodstore.com}
MARKER="# Added by softstudio/deploy/pin-food-store-ip.sh"

die() { echo "$*" >&2; exit 1; }
label() { docker inspect -f "{{index .Config.Labels \"$1\"}}" "$FOOD_CONTAINER"; }

[ "$(id -u)" -eq 0 ] || die "Run with sudo: sudo bash deploy/pin-food-store-ip.sh ..."
docker inspect "$FOOD_CONTAINER" >/dev/null 2>&1 || die "Container $FOOD_CONTAINER not found."
project=$(label com.docker.compose.project)
service=$(label com.docker.compose.service)
workdir=$(label com.docker.compose.project.working_dir)
config_files=$(label com.docker.compose.project.config_files)
override="$workdir/docker-compose.override.yml"
[ -n "$project" ] && [ -n "$workdir" ] || die "$FOOD_CONTAINER was not started by Docker Compose; pin its ports manually."

# Recreate just the nginx service, exactly the way the food store stack is defined.
compose_up_nginx() {
  (cd "$workdir" && docker compose -p "$project" up -d --no-deps "$service")
}
answers_on() {  # $1 = IP; any HTTP response on 80 and 443 means nginx is serving there
  local http https
  http=$(curl -s -o /dev/null -m 10 -w '%{http_code}' --resolve "$FOOD_DOMAIN:$HTTP_PORT:$1" "http://$FOOD_DOMAIN:$HTTP_PORT/" || true)
  https=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' --resolve "$FOOD_DOMAIN:$HTTPS_PORT:$1" "https://$FOOD_DOMAIN:$HTTPS_PORT/" || true)
  echo "    http $http, https $https"
  [ "$http" != 000 ] && [ "$https" != 000 ]
}

if [ "${1:-}" = "--undo" ]; then
  [ -f "$override" ] && grep -qF "$MARKER" "$override" || die "No override created by this script at $override."
  mv "$override" "$override.removed.$(date +%Y%m%d-%H%M%S)"
  echo "==> Recreating $service without the IP pin"
  compose_up_nginx
  docker port "$FOOD_CONTAINER"
  echo "Undone. The food store's nginx listens on all IPs again."
  exit 0
fi

FOOD_IP=${1:?Usage: sudo bash deploy/pin-food-store-ip.sh FOOD_STORE_IP [--apply] | --undo}
APPLY=${2:-}

echo "==> Checks"
case "$config_files" in *,*) die "The food store is started with several compose files ($config_files); pin its ports manually." ;; esac
[ "$(basename "$config_files")" != docker-compose.override.yml ] || die "Unexpected compose file layout: $config_files"
if [ -f "$override" ] && ! grep -qF "$MARKER" "$override"; then
  die "$override already exists and was not created by this script; not touching it."
fi

ver=$(docker compose version --short | sed 's/^v//; s/-.*//')
if [ "$(printf '%s\n' 2.24.4 "$ver" | sort -V | head -1)" != 2.24.4 ]; then
  die "Docker Compose $ver is too old for '!override' (need 2.24.4+). Upgrade Docker first."
fi

ip -4 -o addr show | grep -qw "inet $FOOD_IP" || die "$FOOD_IP is not an address on this server (see: ip -4 addr)."
resolved=$(getent ahostsv4 "$FOOD_DOMAIN" | awk 'NR==1{print $1}')
[ "$resolved" = "$FOOD_IP" ] || die "$FOOD_DOMAIN resolves to ${resolved:-nothing}, not $FOOD_IP. Pinning would take it offline."
if getent ahostsv6 "$FOOD_DOMAIN" 2>/dev/null | awk '{print $1}' | grep -v '^::ffff:' | grep -q ':'; then
  die "$FOOD_DOMAIN has an IPv6 (AAAA) record; pinning to IPv4 only would break IPv6 visitors."
fi
echo "    $FOOD_DOMAIN -> $FOOD_IP (on this server), compose $ver, service '$service' in $workdir"

# Keep the same host/container ports the container publishes today.
mapfile -t mappings < <(docker port "$FOOD_CONTAINER" | awk '{split($1,c,"/"); n=split($3,h,":"); print h[n]":"c[1]}' | sort -u)
[ "${#mappings[@]}" -gt 0 ] || die "$FOOD_CONTAINER publishes no ports."
HTTP_PORT=80; HTTPS_PORT=443
for m in "${mappings[@]}"; do
  case "${m#*:}" in 80) HTTP_PORT=${m%%:*} ;; 443) HTTPS_PORT=${m%%:*} ;; esac
done

new_override="$MARKER
# Keeps $FOOD_DOMAIN on $FOOD_IP so another site can use a different IP.
# Undo: sudo bash /opt/softstudio/deploy/pin-food-store-ip.sh --undo
services:
  $service:
    ports: !override"
for m in "${mappings[@]}"; do new_override+="
      - \"$FOOD_IP:$m\""; done

echo
echo "Current published ports:"
docker port "$FOOD_CONTAINER" | sed 's/^/    /'
echo "Will write $override:"
printf '%s\n' "$new_override" | sed 's/^/    /'

tmp=$(mktemp -d)
printf '%s\n' "$new_override" > "$tmp/override.yml"
merged=$(cd "$workdir" && docker compose -p "$project" -f "$config_files" -f "$tmp/override.yml" config --format json)
rm -rf "$tmp"
echo "Resulting $service ports (validated by docker compose):"
printf '%s' "$merged" | python3 -c "
import json,sys
for p in json.load(sys.stdin)['services']['$service'].get('ports',[]):
    print('    %s:%s -> %s' % (p.get('host_ip','0.0.0.0'), p['published'], p['target']))
"

if [ "$APPLY" != "--apply" ]; then
  echo
  echo "Preview only; nothing changed. To apply (about 10 seconds of downtime for $FOOD_DOMAIN):"
  echo "  sudo bash deploy/pin-food-store-ip.sh $FOOD_IP --apply"
  exit 0
fi

echo
echo "==> Applying"
[ -f "$override" ] && cp -p "$override" "$override.bak.$(date +%Y%m%d-%H%M%S)"
printf '%s\n' "$new_override" > "$override"
compose_up_nginx

echo "==> Verifying $FOOD_DOMAIN answers on $FOOD_IP"
for i in $(seq 1 15); do
  if answers_on "$FOOD_IP"; then
    echo
    docker port "$FOOD_CONTAINER" | sed 's/^/    /'
    echo "Done. $FOOD_DOMAIN is pinned to $FOOD_IP; the other IP is free for jaybalostudio.com."
    exit 0
  fi
  sleep 2
done

echo "==> $FOOD_DOMAIN did not answer; rolling back" >&2
mv "$override" "$override.failed.$(date +%Y%m%d-%H%M%S)"
compose_up_nginx
die "Rolled back: the food store's nginx listens on all IPs again. Nothing else was changed."
