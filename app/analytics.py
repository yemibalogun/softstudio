"""
Recording side of the dashboard: page views and error events.

Two rules hold everywhere in this module:

1. Recording must never break the request. Every write is wrapped, and a
   failure is logged and swallowed — a dashboard is not worth a 500.
2. Nothing identifying is stored. Visitors are counted by a hash of IP and
   user agent salted with SECRET_KEY *and the date*, so the value cannot be
   linked back to a person and stops matching once the day rolls over. No
   raw IP, no cookie, which is also why this needs no consent banner.
"""
import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import current_app, request

from app.extensions import db
from app.models import ErrorEvent, PageView

# Paths that are never interesting as "visits".
SKIP_PREFIXES = ("/static/", "/admin", "/payments/webhook", "/favicon", "/robots.txt",
                 "/sitemap.xml", "/health", "/r/", "/internal/")

BOT_RE = re.compile(
    r"bot|crawler|spider|crawl|slurp|bingpreview|facebookexternalhit|whatsapp|telegram|"
    r"preview|monitor|uptime|curl|wget|python-requests|httpx|headless|lighthouse|pingdom|"
    r"semrush|ahrefs|mj12|dotbot|petalbot|gptbot|claudebot|ccbot|duckduckbot",
    re.I,
)
MOBILE_RE = re.compile(r"iphone|android(?!.*tablet)|ipod|mobile|windows phone", re.I)
TABLET_RE = re.compile(r"ipad|tablet|kindle|silk|playbook", re.I)

_SOURCE_CLEAN_RE = re.compile(r"[^a-z0-9_.-]+")

# Vulnerability scanners. Bots sweep every site on the internet for
# WordPress, Joomla, PHP admin tools and leaked dotfiles; on this Flask site
# those 404s are the correct answer, not broken links, and recording them
# buries the 404 that matters (a dead link on one of our own pages). Each
# pattern targets something this app can never serve, so no real page can
# match: no PHP, no WordPress or Joomla, no dotfiles except /.well-known/.
_PROBE_PATH_RE = re.compile(
    r"\.(?:php\d?|phtml|aspx?|jsp|cgi|env|ini|bak|sql|swp)(?:/|$)"   # server-side files, backups
    r"|/wp-(?:admin|content|includes|json|login|config|cron|signup|trackback|links|load|mail"
    r"|settings|blog-header|activate|comments-post)"   # WordPress's own folders and files
    r"|/(?:wp|wordpress|xmlrpc|phpmyadmin|pma|cgi-bin|administrator|vendor/phpunit"
    r"|media/system/js|boaform|hnap1|actuator|solr|owa|autodiscover)(?:/|$|\.)"
    r"|/\.(?!well-known/)[^/]+",                       # /.env, /.git/config, /.aws, /.DS_Store
    re.I,
)
# WordPress REST probes hit innocent-looking directories: /cms/?rest_route=/
_PROBE_QUERY_RE = re.compile(r"(?:^|&)rest_route=", re.I)

# Credential and config hunters. These rotate through thousands of names
# (/config.json, /aws/credentials, /terraform.tfstate, /id_rsa...), so they
# are recognised by shape rather than listed: a file type this site never
# serves outside /static/, an /api/ segment (the site has none), or a known
# debug console.
_PROBE_SHAPE_RE = re.compile(
    r"\.(?:json|ya?ml|toml|properties|xml|config|cfg|conf|ini|env|key|pem|crt|p12|pfx"
    r"|tfstate|tfvars|backup|sqlite3?|db|zip|tar|t?gz|rar|7z|log|lock|axd|old|save|orig"
    r"|pub|plist|rb|py|ts|hcl|sls|sh|js)~?$"
    r"|~$|/\$\("                                       # editor backups, shell-quoted paths
    r"|(?:^|/)(?:api|graphql|swagger(?:-ui)?|elmah|_profiler|phpinfo|actuator)(?:/|$|\.)"
    r"|/debug/(?:default|pprof|vars)|/session/properties"
    r"|^/(?:etc|proc|var|opt|latest|v1\.\d+|ipfs)/",     # filesystem, cloud metadata, docker API
    re.I,
)

# 404s here are machine endpoints or admin-only pages, never a visitor's
# broken link; their misses are probes (/internal/env, /admin/elmah.axd).
_UNLOGGED_SECTIONS = frozenset({"admin", "internal", "static", "r"})  # /r/: reel links expire by design

# Outside the site's sections, a "link from our own page" is only believed
# for something that could be a page. Scanners fake a Referer of the home
# page while asking for /aws/credentials or /id_rsa.
_SECRETISH_RE = re.compile(
    r"credential|secret|token|passw|private|apikey|api[_-]|(?:^|/)api(?:$|/)|key|id_(?:rsa|dsa|ecdsa|ed25519)"
    r"|msmtprc|aws|s3|bucket|settings|config|well-known|\.txt$",
    re.I,
)


def is_scanner_probe(path: str | None, query_string: str | bytes | None = None) -> bool:
    """True for requests that are bots probing for software this site does not run."""
    if path and "\ufffd" in path:
        return True  # bytes that are not valid UTF-8: no page of ours, only fuzzers
    if path and (_PROBE_PATH_RE.search(path) or (
        not path.startswith("/static/") and _PROBE_SHAPE_RE.search(path)
    )):
        return True
    if isinstance(query_string, bytes):
        query_string = query_string.decode("latin-1", "replace")
    return bool(query_string) and bool(_PROBE_QUERY_RE.search(query_string))


def site_sections() -> frozenset[str]:
    """
    The first path segment of every page this site serves: "blog",
    "products", "services", "about"... Worked out from the URL map, so a new
    blueprint is covered without anyone remembering to update a list.
    """
    cached = current_app.extensions.get("site_sections")
    if cached is None:
        sections = set()
        for rule in current_app.url_map.iter_rules():
            first = rule.rule.lstrip("/").split("/", 1)[0]
            if first and "<" not in first:
                sections.add(first)
        cached = frozenset(sections - _UNLOGGED_SECTIONS)
        current_app.extensions["site_sections"] = cached
    return cached


def _linked_from_our_own_page(path: str, referrer: str | None) -> bool:
    """
    A different page on this site pointed at the missing one: our own broken
    link. Scanners often set the Referer to the very URL they are requesting,
    which a real browser never does, so that does not count.
    """
    if not referrer:
        return False
    parts = urlsplit(referrer)
    site_host = (urlsplit(current_app.config.get("SITE_URL", "")).hostname or "").removeprefix("www.")
    host = (parts.hostname or "").removeprefix("www.")
    return bool(site_host) and host == site_host and (parts.path or "/") != path


def is_reportable_404(path: str | None, query_string: str | bytes | None = None,
                      referrer: str | None = None) -> bool:
    """
    Whether a 404 belongs in the error log as a broken link.

    The internet's background noise is bots requesting names from wordlists
    of other people's software; a list of their patterns is always one
    wordlist behind. So the test is inverted: log a 404 only when it is
    plausibly ours - one of our pages links to it, or it sits under a section
    the site really has (/blog/<slug> that no longer exists) - and never when
    it has the shape of a probe.
    """
    path = path or "/"
    first = path.lstrip("/").split("/", 1)[0]
    if first in _UNLOGGED_SECTIONS or is_scanner_probe(path, query_string):
        return False
    if first in site_sections():
        return True
    return _linked_from_our_own_page(path, referrer) and not _SECRETISH_RE.search(path)


def _clean(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    cleaned = _SOURCE_CLEAN_RE.sub("-", value.strip().lower()).strip("-")
    return cleaned[:limit] or None


def is_bot(user_agent: str | None) -> bool:
    return bool(user_agent) and bool(BOT_RE.search(user_agent))


def device_of(user_agent: str | None) -> str:
    ua = user_agent or ""
    if TABLET_RE.search(ua):
        return "tablet"
    if MOBILE_RE.search(ua):
        return "mobile"
    return "desktop"


def visitor_hash(when: date | None = None) -> str:
    """Daily-rotating, salted hash of IP + user agent. Not reversible."""
    raw = "|".join([
        request.remote_addr or "",
        request.headers.get("User-Agent", ""),
        current_app.config.get("SECRET_KEY", ""),
        (when or date.today()).isoformat(),
    ])
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()


def _referrer_parts() -> tuple[str | None, str | None]:
    """(host, source) for the referring page; our own pages are not a source."""
    referrer = request.referrer or ""
    if not referrer:
        return None, None
    host = (urlsplit(referrer).hostname or "").removeprefix("www.")
    own = (urlsplit(current_app.config.get("SITE_URL") or "").hostname or "").removeprefix("www.")
    if not host or host == own or host in {"localhost", "127.0.0.1"}:
        return None, None
    return host[:120], _clean(host, 60)


def should_track(response_status: int) -> bool:
    path = request.path or "/"
    if request.method not in ("GET", "HEAD"):
        return False
    if request.method == "HEAD":
        return False
    if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    if response_status >= 400:
        return False  # errors are recorded separately, with their own context
    if is_bot(request.headers.get("User-Agent")):
        return False
    return True


def record_page_view(response):
    """after_request hook. Returns the response untouched, always."""
    try:
        if not current_app.config.get("ANALYTICS_ENABLED", True):
            return response
        if not should_track(response.status_code):
            return response
        if "text/html" not in (response.content_type or ""):
            return response

        from flask_login import current_user

        host, referrer_source = _referrer_parts()
        source = _clean(request.args.get("utm_source"), 60) or referrer_source or "direct"

        view = PageView(
            path=(request.path or "/")[:255],
            status_code=response.status_code,
            source=source,
            referrer_host=host,
            device=device_of(request.headers.get("User-Agent")),
            is_authenticated=bool(getattr(current_user, "is_authenticated", False)),
            visitor_hash=visitor_hash(),
            product_id=_product_id_for_path(),
        )
        db.session.add(view)
        db.session.commit()
    except Exception:  # never let analytics break a page
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.warning("page view not recorded for %s", request.path, exc_info=True)
    return response


def _product_id_for_path():
    """Product pages are counted directly, so 'most viewed' is a grouped count."""
    view_args = request.view_args or {}
    slug = view_args.get("slug")
    if not slug or not (request.endpoint or "").startswith("products."):
        return None
    from app.models import Product

    row = Product.query.with_entities(Product.id).filter_by(slug=slug).first()
    return row[0] if row else None


def _fingerprint(kind: str, path: str | None, message: str) -> str:
    raw = "|".join([kind, (path or "")[:120], message[:120]])
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()


def record_error(
    kind: str,
    message: str,
    *,
    status_code: int | None = None,
    path: str | None = None,
    method: str | None = None,
    detail: str | None = None,
    referrer: str | None = None,
) -> None:
    """
    Record one problem, merged into its group.

    Called from the error handlers and from code that knows a delivery
    failed. Like page views, a failure here is swallowed.
    """
    try:
        if not current_app.config.get("ANALYTICS_ENABLED", True):
            return
        if kind not in ErrorEvent.KINDS:
            kind = ErrorEvent.KIND_SERVER

        in_request = bool(request)
        path = path or (request.path if in_request else None)
        method = method or (request.method if in_request else None)
        referrer = referrer or (request.referrer if in_request else None)

        message = (message or "Unknown error").strip()[:300]
        fingerprint = _fingerprint(kind, path, message)
        now = datetime.now(timezone.utc)

        event = ErrorEvent.query.filter_by(fingerprint=fingerprint).first()
        if event is None:
            event = ErrorEvent(
                kind=kind,
                status_code=status_code,
                path=(path or "")[:255] or None,
                method=(method or "")[:10] or None,
                message=message,
                detail=detail,
                fingerprint=fingerprint,
                occurrences=1,
                first_seen=now,
                last_seen=now,
                last_referrer=(referrer or "")[:255] or None,
            )
            db.session.add(event)
        else:
            event.occurrences = (event.occurrences or 0) + 1
            event.last_seen = now
            event.resolved = False  # it is happening again
            if detail:
                event.detail = detail
            if referrer:
                event.last_referrer = referrer[:255]
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        current_app.logger.warning("error event not recorded: %s", message, exc_info=True)


def record_delivery_failure(what: str, target: str | None = None, detail: str | None = None) -> None:
    """An email that would not send, or a download that could not be served."""
    suffix = f" to {target}" if target else ""
    record_error(
        ErrorEvent.KIND_DELIVERY,
        f"{what}{suffix}",
        detail=detail,
    )


def prune_page_views(older_than_days: int) -> int:
    """Retention: drop raw page views past the window. Returns rows deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    deleted = PageView.query.filter(PageView.created_at < cutoff).delete(synchronize_session=False)
    db.session.commit()
    return deleted
