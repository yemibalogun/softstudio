#!/usr/bin/env bash
# Renew every certificate in the shared certbot directory (jaybalostudio.com and
# shamsfoodstore.com) and reload the front proxy. certbot only renews
# certificates within 30 days of expiry, so running this daily is cheap.
# Installed as a daily cron job by deploy/front-proxy.sh. Manual use:
#   sudo bash deploy/renew-certs.sh             # renew if due
#   sudo bash deploy/renew-certs.sh --dry-run   # test against Let's Encrypt staging
set -euo pipefail

FRONT_CONTAINER=${FRONT_CONTAINER:-food_store-nginx-1}
CERTBOT_DIR=${CERTBOT_DIR:-/opt/food_store/certbot}
CERTBOT_IMAGE=${CERTBOT_IMAGE:-certbot/certbot}

# --webroot overrides whatever authenticator each certificate was first issued
# with (e.g. --standalone, which cannot work while nginx holds port 80).
docker run --rm \
  -v "$CERTBOT_DIR/conf:/etc/letsencrypt" \
  -v "$CERTBOT_DIR/www:/var/www/certbot" \
  "$CERTBOT_IMAGE" renew --webroot -w /var/www/certbot --quiet "$@"

docker exec "$FRONT_CONTAINER" nginx -s reload
