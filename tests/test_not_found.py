"""
What a 404 does, and which ones reach the admin error log.

Built from the 482 unresolved errors on production on 2026-10-30: 18 were
real pages asked for with a trailing slash, one was /favicon.ico, and the
rest were bots working through wordlists of other people's config and
credential files. The log should show the first kind, the site should
answer the second, and the third should never appear.
"""
import pytest

from app.models import ErrorEvent, Product, Service


@pytest.fixture()
def pages(db):
    db.session.add(Service(title="AI automation", slug="ai-automation",
                           summary="x", description="x"))
    db.session.add(Product(title="JSWM Abbreviator", slug="jswm-abbreviator",
                           short_description="x", published=True))
    db.session.commit()


def _logged():
    return ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_NOT_FOUND).count()


# ---------------------------------------------------------------------
# Trailing slashes
# ---------------------------------------------------------------------

@pytest.mark.parametrize("url,target", [
    ("/about/", "/about"),
    ("/privacy/", "/privacy"),
    ("/terms/", "/terms"),
    ("/services/ai-automation/", "/services/ai-automation"),
    ("/products/jswm-abbreviator/", "/products/jswm-abbreviator"),
    ("/products/jswm-abbreviator/?utm_source=instagram&utm_medium=dm",
     "/products/jswm-abbreviator?utm_source=instagram&utm_medium=dm"),
    ("/about//", "/about"),
])
def test_a_real_page_with_a_trailing_slash_redirects_to_it(client, pages, url, target):
    resp = client.get(url)
    assert resp.status_code == 301
    assert resp.headers["Location"] == target
    assert client.get(target).status_code == 200
    assert _logged() == 0, "a redirect is not an error"


def test_routes_that_want_the_slash_are_untouched(client):
    assert client.get("/blog/").status_code == 200
    assert client.get("/blog").status_code in (301, 308)   # Flask's own redirect, to /blog/


def test_a_missing_page_with_a_slash_is_still_a_404(client, pages):
    """
    /services/<slug> matches any slug, so the slash is dropped first and the
    miss is reported once, at the canonical address.
    """
    resp = client.get("/services/no-such-service/", follow_redirects=True)
    assert resp.status_code == 404
    assert resp.request.path == "/services/no-such-service"
    assert ErrorEvent.query.one().path == "/services/no-such-service"
    assert client.get("/no-such-top-level-page/").status_code == 404


def test_only_reads_are_redirected(client, pages):
    assert client.post("/about/").status_code in (404, 405)


# ---------------------------------------------------------------------
# Things browsers and people ask for by name
# ---------------------------------------------------------------------

def test_favicon_ico_is_served(client):
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.mimetype == "image/vnd.microsoft.icon"
    assert resp.data[:4] == b"\x00\x00\x01\x00", "a real .ico file"
    assert _logged() == 0


@pytest.mark.parametrize("url,target", [
    ("/login", "/auth/login"),
    ("/register", "/auth/register"),
    ("/register/", "/auth/register"),
])
def test_login_and_register_shortcuts(client, url, target):
    resp = client.get(url, follow_redirects=True)
    assert resp.status_code == 200
    assert resp.request.path == target


# ---------------------------------------------------------------------
# Which 404s are logged
# ---------------------------------------------------------------------

PRODUCTION_PROBES = [
    # A sample of the 440-odd from production, across every family seen.
    "/config.json", "/config/secrets.yml", "/aws/credentials", "/aws/s3/credentials",
    "/terraform.tfstate", "/$(pwd)/terraform.tfvars", "/id_rsa", "/id_ed25519",
    "/etc/passwd", "/proc/self/environ", "/latest/meta-data/iam/security-credentials",
    "/v1.40/containers/json", "/api/session/properties", "/metabase/api/session/properties",
    "/dashboard/api/session/properties", "/swagger.json", "/api-docs", "/graphql",
    "/admin/elmah.axd/", "/_profiler/phpinfo", "/debug/pprof", "/docker-compose.yml",
    "/backup.zip", "/dump.sql.gz", "/config.php~", "/assets/env.js", "/firebase-config.json",
    "/stripe_secret_key.txt", "/sendgrid_api_key.txt", "/msmtprc", "/internal/config",
    "/internal/env", "/ipfs/bafkreicyqcbhpicbos7ev4mrxofwqx6hvvge7pahpta6xuspr44crai5by",
    "/llms.txt", "/feed/", "/settings", "/�",
]


@pytest.mark.parametrize("url", PRODUCTION_PROBES)
def test_wordlist_probes_are_not_logged(client, url):
    assert client.get(url).status_code == 404
    assert _logged() == 0


@pytest.mark.parametrize("url", ["/aws/credentials", "/id_rsa", "/secrets.txt", "/.well-known/stripe"])
def test_a_faked_home_page_referrer_does_not_get_a_probe_logged(client, url):
    """Scanners set Referer to the home page while asking for credentials."""
    client.get(url, headers={"Referer": "http://localhost:8000/"})
    assert _logged() == 0


@pytest.mark.parametrize("url", [
    "/blog/a-post-that-moved",
    "/products/discontinued-thing",
    "/services/old-offer",
    "/projects/renamed-project",
])
def test_a_missing_page_inside_a_real_section_is_logged(client, url):
    client.get(url)
    assert _logged() == 1


def test_a_dead_link_on_one_of_our_pages_is_logged(client):
    """Our own broken link: a different page of ours pointed here."""
    client.get("/case-studies", headers={"Referer": "http://localhost:8000/about"})
    event = ErrorEvent.query.one()
    assert event.path == "/case-studies"
    assert event.last_referrer == "http://localhost:8000/about"


def test_a_self_referring_request_is_not_a_link_of_ours(client):
    client.get("/case-studies", headers={"Referer": "http://localhost:8000/case-studies"})
    assert _logged() == 0


def test_expired_reel_links_are_not_logged(client, app, tmp_path):
    """/r/<id>.mp4 is deleted on purpose once Instagram has the video."""
    app.config["REEL_HOST_TOKEN"] = "t"
    app.config["PROTECTED_UPLOADS_DIR"] = str(tmp_path)  # never the real /data
    client.get("/r/" + "a" * 32 + ".mp4")
    assert _logged() == 0


def test_every_logged_production_path_is_now_handled(client, pages):
    """
    The 20 production paths the log rule still considered real: after the
    fixes each one either answers or redirects, so none can be logged again.
    """
    for url in ["/about/", "/cookies/", "/privacy/", "/refunds/", "/terms/",
                "/services/ai-automation/", "/products/jswm-abbreviator/", "/favicon.ico"]:
        assert client.get(url).status_code in (200, 301), url
    assert _logged() == 0
