#!/usr/bin/env bash
# Put the shared front door in front of both sites.
#
#   bash deploy/edge/setup-edge.sh you@example.com
#
# What it does, in order:
#   1. checks both domains point at this server and both sites are running
#   2. copies the food store's existing certificate into the edge, so that
#      site keeps serving HTTPS the moment the front door takes over
#   3. takes ports 80/443 away from the food store's nginx (an override file
#      next to its compose; its own files are not edited)
#   4. starts the edge and proves the food store still answers - if it does
#      not, everything is rolled back automatically
#   5. issues the certificate for jaybalostudio.com and reloads
#
# Safe to re-run. Undo with: bash deploy/edge/setup-edge.sh --undo
set -euo pipefail

cd "$(dirname "$0")"
EDGE_DIR=$PWD
EDGE="docker compose -f $EDGE_DIR/docker-compose.yml"

FOOD_DIR=${FOOD_DIR:-/opt/food_store}
FOOD_OVERRIDE="$FOOD_DIR/docker-compose.override.yml"
FOOD_DOMAINS=(shamsfoodstore.com www.shamsfoodstore.com)
SITE_DOMAINS=(jaybalostudio.com www.jaybalostudio.com)
PRIMARY=${SITE_DOMAINS[0]}
LE=/etc/letsencrypt
MARKER="# Added by softstudio deploy/edge/setup-edge.sh"

die() { echo "ERROR: $*" >&2; exit 1; }
note() { echo "==> $*"; }

certsh() { $EDGE run --rm --no-deps -T --entrypoint sh certbot -c "$1"; }

# Is there a real certificate for this domain, as opposed to none at all or
# one of the placeholders below? A placeholder is self-signed, so its issuer
# and subject match. Checking only that a file exists once let a placeholder
# masquerade as the food store's certificate, and the site served a
# self-signed certificate until it was spotted.
is_real_cert() {
    local out subject issuer
    out=$(certsh "openssl x509 -in $LE/live/$1/fullchain.pem -noout -subject -issuer 2>/dev/null" 2>/dev/null | tr -d '\r')
    subject=$(printf '%s\n' "$out" | sed -n 's/^subject=//p')
    issuer=$(printf '%s\n' "$out" | sed -n 's/^issuer=//p')
    [ -n "$subject" ] && [ -n "$issuer" ] && [ "$subject" != "$issuer" ]
}

# A placeholder certificate so nginx can start before the real one exists.
make_temp_cert() {
    certsh "rm -rf $LE/live/$PRIMARY $LE/archive/$PRIMARY $LE/renewal/$PRIMARY.conf \
        && mkdir -p $LE/live/$PRIMARY \
        && openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=$PRIMARY \
             -keyout $LE/live/$PRIMARY/privkey.pem -out $LE/live/$PRIMARY/fullchain.pem 2>/dev/null"
}

food_compose() { (cd "$FOOD_DIR" && docker compose -p food_store "$@"); }

# Any HTTP answer means the site is being served; 000 means nothing answered.
answers() {  # $1 = scheme, $2 = domain
    local code
    code=$(curl -sk -o /dev/null -m 15 -w '%{http_code}' \
        --resolve "$2:443:127.0.0.1" --resolve "$2:80:127.0.0.1" "$1://$2/" || true)
    [ -n "$code" ] && [ "$code" != 000 ]
}

restore_food_store() {
    note "Restoring the food store's own front door"
    [ -f "$FOOD_OVERRIDE" ] && mv "$FOOD_OVERRIDE" "$FOOD_OVERRIDE.rolledback.$(date +%Y%m%d-%H%M%S)"
    food_compose up -d nginx >/dev/null 2>&1 || true
}

if [ "${1:-}" = "--undo" ]; then
    note "Stopping the edge"
    $EDGE down || true
    restore_food_store
    sleep 3
    answers https "${FOOD_DOMAINS[0]}" && echo "Done: ${FOOD_DOMAINS[0]} is served by its own nginx again." \
        || die "${FOOD_DOMAINS[0]} is not answering; check: cd $FOOD_DIR && docker compose ps"
    exit 0
fi

EMAIL=${1:-}
[ -n "$EMAIL" ] || die "Give the email address for certificate notices: bash deploy/edge/setup-edge.sh you@example.com"

# ---------------------------------------------------------------- checks
note "Checking"
docker info >/dev/null 2>&1 || die "Cannot talk to Docker."

server_ips=" $(hostname -I 2>/dev/null) $(curl -4 -fsS -m 5 https://api.ipify.org 2>/dev/null || true) "
for domain in "${SITE_DOMAINS[@]}" "${FOOD_DOMAINS[@]}"; do
    resolved=$(getent ahostsv4 "$domain" | awk 'NR==1{print $1}')
    [ -n "$resolved" ] || die "$domain has no A record yet. Point it at this server first."
    case "$server_ips" in
        *" $resolved "*) ;;
        *) die "$domain points at $resolved, which is not this server." ;;
    esac
    echo "    $domain -> $resolved"
done

docker network inspect food_store_default >/dev/null 2>&1 || die "The food store stack is not running."
docker network inspect softstudio_default >/dev/null 2>&1 \
    || die "The softstudio stack is not running. Start it first: bash deploy/deploy.sh"
docker ps --format '{{.Names}}' | grep -qx food_store-web-1 || die "food_store-web-1 is not running."
docker ps --format '{{.Names}}' | grep -q '^softstudio-web-' || die "The softstudio web container is not running."

mkdir -p "$EDGE_DIR/certbot/conf" "$EDGE_DIR/certbot/www"

# ------------------------------------------- the food store's certificate
if ! is_real_cert "${FOOD_DOMAINS[0]}"; then
    note "Importing the food store's certificate so it keeps serving HTTPS"
    [ -d "$FOOD_DIR/certbot/conf/live/${FOOD_DOMAINS[0]}" ] \
        || die "No certificate found at $FOOD_DIR/certbot/conf/live/${FOOD_DOMAINS[0]}"
    # Root-owned files, so the copy runs in a container. Any placeholder is
    # cleared first: cp would not replace a live/ directory that is in the way.
    docker run --rm -v "$EDGE_DIR/certbot/conf:/dst" alpine:3.20 sh -c \
        "rm -rf /dst/live/${FOOD_DOMAINS[0]} /dst/archive/${FOOD_DOMAINS[0]} /dst/renewal/${FOOD_DOMAINS[0]}.conf"
    docker run --rm \
        -v "$FOOD_DIR/certbot/conf:/src:ro" \
        -v "$EDGE_DIR/certbot/conf:/dst" \
        alpine:3.20 sh -c 'cp -a /src/. /dst/'
    is_real_cert "${FOOD_DOMAINS[0]}" \
        || die "The food store's certificate did not copy across."
fi

# ------------------------------------------ a certificate so nginx starts
if ! is_real_cert "$PRIMARY" || ! certsh "test -f $LE/renewal/$PRIMARY.conf"; then
    note "Creating a temporary certificate for $PRIMARY so nginx can start"
    make_temp_cert
    BOOTSTRAP=true
else
    BOOTSTRAP=false
fi

# --------------------------------------------------------- the handover
if [ ! -f "$FOOD_OVERRIDE" ]; then
    note "Taking ports 80/443 from the food store's nginx"
    cat > "$FOOD_OVERRIDE" <<EOF
$MARKER
# The shared front door (softstudio/deploy/edge) now owns 80/443 and proxies
# shamsfoodstore.com to this project's app. This nginx keeps running but is
# no longer published. Undo: delete this file, then \`docker compose up -d\`.
services:
  nginx:
    ports: !override []
EOF
    food_compose config >/dev/null || { rm -f "$FOOD_OVERRIDE"; die "The override broke the food store's compose file; nothing changed."; }
fi
food_compose up -d nginx >/dev/null

note "Starting the front door"
if ! $EDGE up -d; then
    restore_food_store
    die "The edge did not start; the food store was put back."
fi

note "Checking the food store still answers"
ok=false
for _ in $(seq 1 12); do
    if answers https "${FOOD_DOMAINS[0]}"; then ok=true; break; fi
    sleep 3
done
if ! $ok; then
    $EDGE down || true
    restore_food_store
    die "${FOOD_DOMAINS[0]} stopped answering, so everything was rolled back. Nothing else changed."
fi
echo "    ${FOOD_DOMAINS[0]} OK"

# ------------------------------------------ the real jaybalostudio.com cert
if $BOOTSTRAP; then
    note "Checking $PRIMARY reaches the front door"
    token="check-$(date +%s)"
    certsh "mkdir -p /var/www/certbot/.well-known/acme-challenge && echo $token > /var/www/certbot/.well-known/acme-challenge/$token"
    for domain in "${SITE_DOMAINS[@]}"; do
        got=$(curl -fsS -m 15 "http://$domain/.well-known/acme-challenge/$token" 2>/dev/null || true)
        [ "$got" = "$token" ] || {
            certsh "rm -f /var/www/certbot/.well-known/acme-challenge/$token"
            die "http://$domain did not reach the front door, so no certificate was requested (no rate limit used)."
        }
        echo "    $domain OK"
    done
    certsh "rm -f /var/www/certbot/.well-known/acme-challenge/$token"

    note "Requesting the certificate for $PRIMARY"
    domain_args=()
    for domain in "${SITE_DOMAINS[@]}"; do domain_args+=(-d "$domain"); done
    # certbot will not write over the placeholder's live/ directory ("live
    # directory exists"), so clear it first. nginx keeps serving from the
    # copy it already loaded until the reload below.
    certsh "rm -rf $LE/live/$PRIMARY $LE/archive/$PRIMARY $LE/renewal/$PRIMARY.conf"
    # Importing another site's certificates brings its ACME account along, and
    # certbot refuses to guess between accounts, so name one explicitly.
    account=$(certsh "ls /etc/letsencrypt/accounts/acme-v02.api.letsencrypt.org/directory 2>/dev/null | head -1" 2>/dev/null | tr -d '\r' | tail -1)
    account_args=()
    [ -n "$account" ] && account_args=(--account "$account")
    if ! $EDGE run --rm --no-deps -T --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
            "${domain_args[@]}" "${account_args[@]}" --email "$EMAIL" --agree-tos --no-eff-email -n; then
        make_temp_cert  # put a placeholder back so nginx can restart
        die "The certificate request failed (see above). Both sites are still up; re-run when it is fixed."
    fi
    $EDGE exec -T nginx nginx -s reload
fi

note "Verifying"
for domain in "${FOOD_DOMAINS[@]}" "${SITE_DOMAINS[@]}"; do
    # Validates the chain on purpose (no -k): a placeholder certificate left
    # in place has to fail here rather than look like success.
    code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' "https://$domain/" || true)
    [ -n "$code" ] && [ "$code" != 000 ] \
        || die "https://$domain is not answering with a valid certificate. Check: docker logs edge-nginx-1 --tail=50"
    echo "    https://$domain $code"
done

echo
echo "Both sites are served by the front door:"
echo "  https://${FOOD_DOMAINS[0]}   -> food_store app"
echo "  https://$PRIMARY  -> softstudio app"
echo "Certificates renew automatically (edge certbot). Undo: bash deploy/edge/setup-edge.sh --undo"
