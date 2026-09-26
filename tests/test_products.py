"""Product pages, their social metadata, and the waitlist."""
import re

import pytest

from app.models import Product, WaitlistSubscriber
from tests.conftest import login


@pytest.fixture()
def product(db):
    item = Product(
        title="Flask Production MCP",
        slug="flask-production-mcp",
        short_description="Ship Flask apps to production without guesswork.",
        description="Longer description.",
        image="/static/images/uploads/products/abc123.webp",
        published=True,
        waitlist_enabled=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _meta(html: str, attr: str, value: str) -> str | None:
    """The content of <meta {attr}="{value}" content="...">, order-independent."""
    pattern = (
        rf'<meta[^>]*{attr}="{re.escape(value)}"[^>]*content="([^"]*)"'
        rf'|<meta[^>]*content="([^"]*)"[^>]*{attr}="{re.escape(value)}"'
    )
    match = re.search(pattern, html)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _canonical(html: str) -> str | None:
    match = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]*)"', html)
    return match.group(1) if match else None


# =====================================================================
# Routing
# =====================================================================

def test_published_product_returns_200(client, product):
    resp = client.get(f"/products/{product.slug}")
    assert resp.status_code == 200
    assert b"Flask Production MCP" in resp.data


def test_unknown_slug_returns_404(client, product):
    assert client.get("/products/does-not-exist").status_code == 404


def test_unpublished_product_returns_404(client, db, product):
    product.published = False
    db.session.commit()
    assert client.get(f"/products/{product.slug}").status_code == 404


def test_malformed_slug_returns_404(client, product):
    for slug in ["Flask_Production", "../../etc/passwd", "a" * 200, "UPPER"]:
        assert client.get(f"/products/{slug}").status_code == 404


def test_index_lists_only_published_products(client, db, product):
    hidden = Product(
        title="Secret Tool", slug="secret-tool",
        short_description="Not ready yet.", published=False,
    )
    db.session.add(hidden)
    db.session.commit()

    resp = client.get("/products/")
    assert resp.status_code == 200
    assert b"Flask Production MCP" in resp.data
    assert b"Secret Tool" not in resp.data


def test_sitemap_includes_published_product(client, product):
    body = client.get("/sitemap.xml").data.decode()
    assert f"/products/{product.slug}" in body


# =====================================================================
# Open Graph / SEO
# =====================================================================

def test_product_page_renders_dynamic_social_metadata(client, app, product):
    html = client.get(f"/products/{product.slug}").data.decode()
    site_url = app.config["SITE_URL"].rstrip("/")
    expected_url = f"{site_url}/products/{product.slug}"

    assert f"<title>{product.title} · {app.config['SITE_NAME']}</title>" in html
    assert _canonical(html) == expected_url
    assert _meta(html, "name", "description") == product.short_description

    assert _meta(html, "property", "og:title") == product.title
    assert _meta(html, "property", "og:description") == product.short_description
    assert _meta(html, "property", "og:url") == expected_url
    assert _meta(html, "property", "og:image") == f"{site_url}{product.image}"
    assert _meta(html, "property", "og:type") == "product"
    assert _meta(html, "property", "og:site_name") == app.config["SITE_NAME"]

    assert _meta(html, "name", "twitter:card") == "summary_large_image"
    assert _meta(html, "name", "twitter:title") == product.title
    assert _meta(html, "name", "twitter:description") == product.short_description
    assert _meta(html, "name", "twitter:image") == f"{site_url}{product.image}"


def test_og_image_is_absolute_and_falls_back_to_site_default(client, app, db, product):
    product.image = None
    db.session.commit()

    html = client.get(f"/products/{product.slug}").data.decode()
    og_image = _meta(html, "property", "og:image")
    assert og_image, "og:image must never be empty"
    assert og_image.startswith(app.config["SITE_URL"].rstrip("/"))
    assert og_image.endswith("og-default.png")


def test_seo_overrides_win_over_defaults(client, app, db, product):
    product.meta_title = "MCP for Flask, in production"
    product.meta_description = "A different description for search and social."
    product.og_image = "https://cdn.example.com/card.png"
    db.session.commit()

    html = client.get(f"/products/{product.slug}").data.decode()
    assert _meta(html, "property", "og:title") == product.meta_title
    assert _meta(html, "property", "og:description") == product.meta_description
    # The uploaded product image is what gets shared; og_image is only a
    # fallback for products without one (see tests/test_social_images.py).
    assert _meta(html, "property", "og:image") == app.config["SITE_URL"].rstrip("/") + product.image

    product.image = None
    db.session.commit()
    html = client.get(f"/products/{product.slug}").data.decode()
    # With no image of its own, the field is used, absolute and untouched.
    assert _meta(html, "property", "og:image") == "https://cdn.example.com/card.png"


def test_campaign_parameters_do_not_change_the_canonical_url(client, app, product):
    html = client.get(f"/products/{product.slug}?utm_source=instagram").data.decode()
    site_url = app.config["SITE_URL"].rstrip("/")
    assert _canonical(html) == f"{site_url}/products/{product.slug}"
    assert "utm_source" not in (_canonical(html) or "")


def test_product_page_carries_structured_data(client, product):
    html = client.get(f"/products/{product.slug}").data.decode()
    assert '"@type": "Product"' in html
    assert product.title in html
    # No invented commerce claims.
    for forbidden in ["aggregateRating", "priceCurrency", "\"review\"", "availability"]:
        assert forbidden not in html


# =====================================================================
# Waitlist
# =====================================================================

def test_waitlist_form_shown_only_when_enabled(client, db, product):
    assert b"Join the Waitlist" in client.get(f"/products/{product.slug}").data

    product.waitlist_enabled = False
    db.session.commit()
    assert b"Join the Waitlist" not in client.get(f"/products/{product.slug}").data


def test_valid_email_registers(client, product):
    resp = client.post(
        f"/products/{product.slug}/waitlist",
        data={"email": "Person@Example.COM "},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"You\xe2\x80\x99re on the list." in resp.data

    subscriber = WaitlistSubscriber.query.filter_by(product_id=product.id).one()
    assert subscriber.email == "person@example.com"  # normalized
    assert subscriber.source == "direct"


def test_optional_name_is_stored(client, product):
    client.post(
        f"/products/{product.slug}/waitlist",
        data={"email": "named@example.com", "name": "Ada Lovelace"},
    )
    assert WaitlistSubscriber.query.one().name == "Ada Lovelace"


def test_invalid_email_is_rejected(client, product):
    resp = client.post(f"/products/{product.slug}/waitlist", data={"email": "not-an-email"})
    assert resp.status_code == 400
    assert WaitlistSubscriber.query.count() == 0


def test_missing_email_is_rejected(client, product):
    resp = client.post(f"/products/{product.slug}/waitlist", data={"email": ""})
    assert resp.status_code == 400
    assert WaitlistSubscriber.query.count() == 0


def test_duplicate_email_for_same_product_creates_no_second_row(client, product):
    for _ in range(2):
        resp = client.post(
            f"/products/{product.slug}/waitlist",
            data={"email": "twice@example.com"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    assert WaitlistSubscriber.query.filter_by(email="twice@example.com").count() == 1


def test_same_email_may_join_two_different_products(client, db, product):
    other = Product(
        title="AI Workflow Automation", slug="ai-workflow-automation",
        short_description="Automate the busywork.", published=True, waitlist_enabled=True,
    )
    db.session.add(other)
    db.session.commit()

    for slug in (product.slug, other.slug):
        client.post(f"/products/{slug}/waitlist", data={"email": "both@example.com"})

    assert WaitlistSubscriber.query.filter_by(email="both@example.com").count() == 2


def test_waitlist_on_unknown_product_is_404(client, product):
    resp = client.post("/products/nope/waitlist", data={"email": "a@example.com"})
    assert resp.status_code == 404


def test_waitlist_on_unpublished_product_is_404(client, db, product):
    product.published = False
    db.session.commit()
    resp = client.post(f"/products/{product.slug}/waitlist", data={"email": "a@example.com"})
    assert resp.status_code == 404
    assert WaitlistSubscriber.query.count() == 0


def test_waitlist_rejected_when_disabled(client, db, product):
    product.waitlist_enabled = False
    db.session.commit()
    resp = client.post(f"/products/{product.slug}/waitlist", data={"email": "a@example.com"})
    assert resp.status_code == 404
    assert WaitlistSubscriber.query.count() == 0


def test_honeypot_submission_stores_nothing(client, product):
    resp = client.post(
        f"/products/{product.slug}/waitlist",
        data={"email": "bot@example.com", "website": "http://spam.example"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert WaitlistSubscriber.query.count() == 0


def test_subscriber_emails_are_not_public(client, product):
    client.post(f"/products/{product.slug}/waitlist", data={"email": "private@example.com"})
    assert b"private@example.com" not in client.get(f"/products/{product.slug}").data


def test_deleting_a_product_removes_its_waitlist(client, db, product):
    client.post(f"/products/{product.slug}/waitlist", data={"email": "gone@example.com"})
    db.session.delete(product)
    db.session.commit()
    assert WaitlistSubscriber.query.count() == 0


# =====================================================================
# Attribution
# =====================================================================

def test_utm_source_from_the_landing_url_is_captured(client, product):
    """The Instagram flow: the DM link carries ?utm_source=instagram."""
    page = client.get(f"/products/{product.slug}?utm_source=instagram").data.decode()
    assert 'value="instagram"' in page  # carried into the form

    client.post(
        f"/products/{product.slug}/waitlist",
        data={"email": "reel@example.com", "utm_source": "instagram"},
    )
    assert WaitlistSubscriber.query.one().source == "instagram"


def test_full_utm_set_is_captured(client, product):
    client.post(
        f"/products/{product.slug}/waitlist",
        data={
            "email": "campaign@example.com",
            "utm_source": "linkedin",
            "utm_medium": "social",
            "utm_campaign": "launch-week",
            "utm_content": "carousel-2",
        },
    )
    subscriber = WaitlistSubscriber.query.one()
    assert (subscriber.source, subscriber.utm_medium) == ("linkedin", "social")
    assert (subscriber.utm_campaign, subscriber.utm_content) == ("launch-week", "carousel-2")


def test_utm_source_on_the_post_url_is_captured(client, product):
    client.post(
        f"/products/{product.slug}/waitlist?utm_source=whatsapp",
        data={"email": "wa@example.com"},
    )
    assert WaitlistSubscriber.query.one().source == "whatsapp"


def test_attribution_is_sanitized(client, product):
    client.post(
        f"/products/{product.slug}/waitlist",
        data={"email": "dirty@example.com", "utm_source": "  InstaGram <script>  "},
    )
    source = WaitlistSubscriber.query.one().source
    assert source == "instagram-script"
    assert "<" not in source and len(source) <= 60


def test_signup_without_any_campaign_parameters_still_works(client, product):
    client.post(f"/products/{product.slug}/waitlist", data={"email": "plain@example.com"})
    assert WaitlistSubscriber.query.one().source == "direct"


# =====================================================================
# Production URLs: never derived from the request Host
# =====================================================================

def test_forged_host_header_cannot_rewrite_public_urls(client, app, product):
    """
    Behind nginx the Host header is attacker-controllable. Canonical, og:url
    and the share URL must all come from the configured SITE_URL.
    """
    html = client.get(
        f"/products/{product.slug}", headers={"Host": "evil.example.net"}
    ).data.decode()
    expected = f"{app.config['SITE_URL'].rstrip('/')}/products/{product.slug}"

    assert _canonical(html) == expected
    assert _meta(html, "property", "og:url") == expected
    assert f'data-share-url="{expected}"' in html
    assert "evil.example.net" not in html


# =====================================================================
# Admin management
# =====================================================================

def _login_admin(client):
    return login(client, "admin@example.com", "correcthorsebattery")


def test_admin_creates_product_with_generated_slug(client, admin_user):
    _login_admin(client)
    resp = client.post(
        "/admin/products/new",
        data={
            "title": "AI Workflow Automation",
            "short_description": "Automate the busywork between your tools.",
            "published": "y",
            "waitlist_enabled": "y",
            "display_order": 0,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    product = Product.query.filter_by(title="AI Workflow Automation").one()
    assert product.slug == "ai-workflow-automation"
    assert product.published and product.waitlist_enabled

    # The new product is live with no further work: page, share URL, waitlist.
    page = client.get(f"/products/{product.slug}")
    assert page.status_code == 200
    assert b"Join the waitlist" in page.data


def test_admin_list_shows_the_shareable_url(client, admin_user, app, product):
    _login_admin(client)
    html = client.get("/admin/products").data.decode()
    expected = f"{app.config['SITE_URL'].rstrip('/')}/products/{product.slug}"
    assert f'data-share-url="{expected}"' in html
    assert "Copy link" in html


def test_admin_can_toggle_publication_and_waitlist(client, admin_user, db, product):
    _login_admin(client)
    client.post(f"/admin/products/{product.id}/toggle-published")
    client.post(f"/admin/products/{product.id}/toggle-waitlist")
    db.session.refresh(product)
    assert product.published is False
    assert product.waitlist_enabled is False


def test_admin_sees_waitlist_subscribers(client, admin_user, product):
    client.post(f"/products/{product.slug}/waitlist", data={"email": "reader@example.com"})
    _login_admin(client)
    html = client.get(f"/admin/products/{product.id}/waitlist").data.decode()
    assert "reader@example.com" in html


def test_product_admin_is_closed_to_non_admins(client, user, product):
    login(client, "student@example.com", "correcthorsebattery")
    for path in (
        "/admin/products",
        f"/admin/products/{product.id}/edit",
        f"/admin/products/{product.id}/waitlist",
    ):
        assert client.get(path).status_code == 403
