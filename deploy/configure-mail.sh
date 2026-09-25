#!/usr/bin/env bash
# Point the site at an SMTP mailbox, then prove it works.
#
#   bash deploy/configure-mail.sh
#
# Asks for the mail settings (the password is typed hidden and goes straight
# into .env - it is never printed or passed on a command line), checks the
# server is reachable, restarts the app and sends a test email, reporting the
# SMTP error verbatim if the provider refuses.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "ERROR: .env is missing." >&2; exit 1; }

MODE=$(sed -n 's/^DEPLOY_MODE=\(.*\)$/\1/p' .env | tail -1 | tr -d '"'"'"' ' || true)
if [ "${MODE:-standalone}" = "edge" ]; then
    COMPOSE="docker compose -f docker-compose.yml -f docker-compose.edge.yml"
else
    COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
fi

current() { sed -n "s/^$1=\(.*\)$/\1/p" .env | tail -1; }

ask() {  # ask <VAR> <prompt> <default>
    local value
    read -r -p "$2 [${3}]: " value </dev/tty
    printf '%s' "${value:-$3}"
}

echo "Mail settings for $(current SITE_NAME)"
echo "(press Enter to keep the value in brackets)"
echo

DOMAIN=$(current SITE_URL | sed 's#^https\?://##; s#/.*##')
MAIL_SERVER=$(ask MAIL_SERVER "Outgoing (SMTP) server" "$(current MAIL_SERVER || echo "mail.$DOMAIN")")
# Port 465 is blocked outbound on some hosts (this VPS included), so 587 with
# STARTTLS is the default here even though cPanel usually suggests 465.
MAIL_PORT=$(ask MAIL_PORT "SMTP port (587 = STARTTLS, 465 = SSL)" "$(current MAIL_PORT || echo 587)")
MAIL_USERNAME=$(ask MAIL_USERNAME "Mailbox (username)" "$(current MAIL_USERNAME || echo "admin@$DOMAIN")")
MAIL_DEFAULT_SENDER=$(ask MAIL_DEFAULT_SENDER "Send mail as" "$MAIL_USERNAME")
ADMIN_EMAIL=$(ask ADMIN_EMAIL "Send project inquiries to" "$(current ADMIN_EMAIL || echo "$MAIL_USERNAME")")

printf 'Mailbox password (hidden): '
read -r -s MAIL_PASSWORD </dev/tty
echo
[ -n "$MAIL_PASSWORD" ] || { echo "ERROR: no password given." >&2; exit 1; }

echo
echo "==> Checking $MAIL_SERVER:$MAIL_PORT is reachable"
python3 - "$MAIL_SERVER" "$MAIL_PORT" <<'PY' || exit 1
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    s = socket.create_connection((host, port), timeout=10)
    print("    " + s.recv(120).decode(errors="replace").strip().splitlines()[0][:80])
    s.close()
except Exception as exc:
    print(f"ERROR: cannot reach {host}:{port} ({exc}).", file=sys.stderr)
    print("       Check the hostname, or try port 587 if 465 is blocked.", file=sys.stderr)
    raise SystemExit(1)
PY

cp -p .env ".env.bak.$(date +%Y%m%d-%H%M%S)"
set_env() {  # set_env <KEY> <VALUE>
    local key=$1 value=$2 tmp
    tmp=$(mktemp)
    grep -v "^${key}=" .env > "$tmp" || true
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
    mv "$tmp" .env
    chmod 600 .env
}
set_env MAIL_SERVER "$MAIL_SERVER"
set_env MAIL_PORT "$MAIL_PORT"
set_env MAIL_USE_TLS "$([ "$MAIL_PORT" = 465 ] && echo false || echo true)"
set_env MAIL_USE_SSL "$([ "$MAIL_PORT" = 465 ] && echo true || echo false)"
set_env MAIL_USERNAME "$MAIL_USERNAME"
set_env MAIL_PASSWORD "$MAIL_PASSWORD"
set_env MAIL_DEFAULT_SENDER "$MAIL_DEFAULT_SENDER"
set_env ADMIN_EMAIL "$ADMIN_EMAIL"
unset MAIL_PASSWORD
echo "==> .env updated (previous copy kept as .env.bak.*)"

echo "==> Restarting the app"
$COMPOSE up -d --force-recreate web >/dev/null
for _ in $(seq 1 30); do
    $COMPOSE exec -T web python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/robots.txt')" >/dev/null 2>&1 && break
    sleep 2
done

echo "==> Sending a test email to $ADMIN_EMAIL"
$COMPOSE exec -T web python - <<'PY'
from app import create_app
from app.extensions import mail
from flask_mail import Message

app = create_app()
with app.app_context():
    to = app.config["ADMIN_EMAIL"]
    msg = Message(
        subject=f"Test email from {app.config['SITE_NAME']}",
        recipients=[to],
        body=("If you are reading this, the website can send email.\n\n"
              "Project inquiries and password resets will now arrive."),
        sender=app.config["MAIL_DEFAULT_SENDER"],
    )
    try:
        mail.send(msg)
        print(f"    sent to {to}")
    except Exception as exc:
        raise SystemExit(f"    REFUSED by the mail server: {type(exc).__name__}: {exc}")
PY

echo
echo "Done. Check the inbox for $ADMIN_EMAIL."
echo "If nothing arrives, look in spam, then add the SPF record for your mail host."
