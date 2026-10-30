"""
The /reels page: Instagram posts embedded on the site, loaded only on play.
"""
import base64
import io

import pytest
from PIL import Image

from app.models import InstagramPost
from app.models.instagram import parse_instagram_url
from tests.conftest import login

TOKEN = "test-reel-token"
API = "/internal/instagram-posts"
REEL_URL = "https://www.instagram.com/reel/De8x_erjofy/"


@pytest.fixture()
def upload_dir(app, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)   # never the real uploads folder
    return tmp_path


@pytest.fixture()
def api(app, upload_dir):
    app.config["REEL_HOST_TOKEN"] = TOKEN
    return {"Authorization": f"Bearer {TOKEN}"}


def _jpeg(size=(90, 160)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (20, 60, 160)).save(buf, "JPEG")
    return buf.getvalue()


def _post(db, shortcode="De8x_erjofy", **fields):
    post = InstagramPost(shortcode=shortcode, kind="reel", **fields)
    db.session.add(post)
    db.session.commit()
    return post


# ---------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.instagram.com/reel/De8x_erjofy/", ("reel", "De8x_erjofy")),
    ("https://instagram.com/reel/De8x_erjofy", ("reel", "De8x_erjofy")),
    ("https://www.instagram.com/reels/DfDIYhaCsO6/", ("reel", "DfDIYhaCsO6")),
    ("https://www.instagram.com/p/C1abcDEF234/?igsh=xyz", ("post", "C1abcDEF234")),
    ("https://www.instagram.com/jaybalo_studio/reel/DfEXkuVlPkH/", ("reel", "DfEXkuVlPkH")),
    ("https://www.instagram.com/tv/B9abcdEFGH1/", ("reel", "B9abcdEFGH1")),
    ("  https://www.instagram.com/reel/De8x_erjofy/#comments  ", ("reel", "De8x_erjofy")),
])
def test_instagram_links_are_understood(url, expected):
    assert parse_instagram_url(url) == expected


@pytest.mark.parametrize("url", [
    "https://www.instagram.com.evil.example/reel/De8x_erjofy/",
    "https://evil.example/instagram.com/reel/De8x_erjofy/",
    "javascript:alert(1)//instagram.com/reel/De8x_erjofy/",
    "https://www.instagram.com/jaybalo_studio/",
    "https://www.instagram.com/reel/<script>/",
    "",
    None,
])
def test_anything_else_is_refused(url):
    assert parse_instagram_url(url) is None


def test_embed_and_link_addresses():
    post = InstagramPost(shortcode="De8x_erjofy", kind="reel")
    assert post.permalink == "https://www.instagram.com/reel/De8x_erjofy/"
    assert post.embed_url == "https://www.instagram.com/reel/De8x_erjofy/embed/"
    post = InstagramPost(shortcode="C1abcDEF234", kind="post")
    assert post.embed_url.endswith("/p/C1abcDEF234/embed/")


def test_the_heading_falls_back_to_the_caption_without_hashtags():
    caption = "\n#automation #ai Stop automating the wrong things\nmore"
    post = InstagramPost(shortcode="x" * 11, caption=caption)
    assert post.heading == "Stop automating the wrong things"
    assert InstagramPost(shortcode="x" * 11, title="Own title", caption="cap").heading == "Own title"


# ---------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------

def test_published_posts_are_cards_that_load_nothing_from_instagram(client, db):
    _post(db, title="AI is not always the answer")
    _post(db, shortcode="DfDIYhaCsO6", title="Hidden one", published=False)
    html = client.get("/reels").data.decode()

    assert "AI is not always the answer" in html
    assert "Hidden one" not in html
    assert 'data-embed-src="https://www.instagram.com/reel/De8x_erjofy/embed/"' in html
    assert "<iframe" not in html, "the player loads only when a visitor presses play"
    assert "instagram.com/embed.js" not in html
    assert 'href="https://www.instagram.com/reel/De8x_erjofy/"' in html, "works without JavaScript"
    assert "js/instagram-embed.js" in html


def test_only_this_page_may_frame_instagram(client, db):
    _post(db)
    policy = client.get("/reels").headers["Content-Security-Policy"]
    assert "frame-src https://www.instagram.com" in policy
    assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy, "the rest is unchanged"
    for other in ("/", "/blog/", "/products/"):
        assert "instagram" not in client.get(other).headers["Content-Security-Policy"]


def test_an_empty_page_points_to_instagram(client):
    html = client.get("/reels").data.decode()
    assert "New reels appear here as they are published" in html
    assert "https://www.instagram.com/jaybalo_studio/" in html


def test_the_page_is_linked_and_listed(client):
    assert 'href="/reels"' in client.get("/").data.decode()
    assert "/reels</loc>" in client.get("/sitemap.xml").data.decode()


def test_the_click_to_play_script_is_served(client):
    js = client.get("/static/js/instagram-embed.js").data.decode()
    assert "replaceChildren" in js and "embedSrc" in js


# ---------------------------------------------------------------------
# The autoposter's report
# ---------------------------------------------------------------------

def test_reporting_needs_the_token(client, app, api):
    assert client.post(API, json={"permalink": REEL_URL}).status_code == 403
    assert client.post(API, json={"permalink": REEL_URL},
                       headers={"Authorization": "Bearer wrong"}).status_code == 403
    app.config["REEL_HOST_TOKEN"] = None
    assert client.post(API, json={"permalink": REEL_URL}, headers=api).status_code == 404
    assert InstagramPost.query.count() == 0


def test_a_reported_reel_appears_with_its_cover(client, api, upload_dir):
    resp = client.post(API, headers=api, json={
        "permalink": REEL_URL,
        "title": "AI is not always the answer",
        "caption": "When a rule beats a model.\n#automation",
        "posted_at": "2026-10-27T09:00:00Z",
        "cover_jpeg_b64": base64.b64encode(_jpeg()).decode(),
    })
    assert resp.status_code == 201
    assert resp.get_json() == {"shortcode": "De8x_erjofy", "created": True, "cover": "stored"}

    post = InstagramPost.query.one()
    assert post.source == "autoposter" and post.kind == "reel"
    assert post.cover_image.startswith("/static/images/uploads/reels/")
    assert list(upload_dir.rglob("*.*")), "the cover file was written"
    assert post.posted_at.year == 2026
    assert "AI is not always the answer" in client.get("/reels").data.decode()


def test_reporting_again_fills_gaps_but_never_overwrites_edits(client, db, api):
    _post(db, title="Edited by admin")
    resp = client.post(API, headers=api, json={"permalink": REEL_URL, "title": "From autoposter",
                                               "caption": "caption"})
    assert resp.status_code == 200 and resp.get_json()["created"] is False
    post = InstagramPost.query.one()
    assert post.title == "Edited by admin"
    assert post.caption == "caption", "an empty field is filled in"


def test_a_bad_cover_does_not_lose_the_post(client, api):
    resp = client.post(API, headers=api, json={
        "permalink": REEL_URL,
        "cover_jpeg_b64": base64.b64encode(b"<svg onload=alert(1)>").decode(),
    })
    assert resp.status_code == 201 and resp.get_json()["cover"] == "rejected"
    assert InstagramPost.query.one().cover_image is None


@pytest.mark.parametrize("body", [
    {"permalink": "https://evil.example/reel/De8x_erjofy/"},
    {"permalink": ""},
    {},
])
def test_a_report_without_an_instagram_link_is_refused(client, api, body):
    assert client.post(API, headers=api, json=body).status_code == 400
    assert InstagramPost.query.count() == 0


def test_the_report_is_not_blocked_by_csrf(client, app, api):
    """Machine-to-machine, authenticated by the token; CSRF is for browsers."""
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        assert client.post(API, headers=api, json={"permalink": REEL_URL}).status_code == 201
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


# ---------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------

def _admin(client):
    login(client, "admin@example.com", "correcthorsebattery")


def test_admin_adds_a_post_by_its_link(client, admin_user, upload_dir):
    _admin(client)
    resp = client.post("/admin/instagram", data={
        "url": "https://www.instagram.com/reel/DfEXkuVlPkH/?igsh=abc",
        "title": "WhatsApp alone is not a system",
        "published": "y", "display_order": 0,
        "cover_file": (io.BytesIO(_jpeg()), "cover.jpg"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 302
    post = InstagramPost.query.one()
    assert (post.shortcode, post.kind, post.source) == ("DfEXkuVlPkH", "reel", "admin")
    assert post.cover_image.startswith("/static/images/uploads/reels/")


def test_admin_cannot_add_a_link_that_is_not_instagram(client, admin_user):
    _admin(client)
    resp = client.post("/admin/instagram", data={"url": "https://youtube.com/watch?v=x", "display_order": 0})
    assert resp.status_code == 200
    assert "Paste a link to an Instagram reel or post" in resp.data.decode()
    assert InstagramPost.query.count() == 0


def test_the_same_post_is_not_added_twice(client, db, admin_user):
    _post(db)
    _admin(client)
    client.post("/admin/instagram", data={"url": REEL_URL, "display_order": 0})
    assert InstagramPost.query.count() == 1


def test_admin_edits_hides_and_removes(client, db, admin_user, upload_dir):
    post = _post(db)
    _admin(client)
    client.post(f"/admin/instagram/{post.id}/edit", data={
        "url": REEL_URL, "title": "New title", "published": "y", "display_order": 3})
    db.session.refresh(post)
    assert post.title == "New title" and post.display_order == 3

    client.post(f"/admin/instagram/{post.id}/toggle")
    db.session.refresh(post)
    assert post.published is False
    assert "New title" not in client.get("/reels").data.decode()

    client.post(f"/admin/instagram/{post.id}/delete")
    assert InstagramPost.query.count() == 0


def test_the_admin_pages_are_admin_only(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    assert client.get("/admin/instagram").status_code == 403
    assert client.post("/admin/instagram", data={"url": REEL_URL}).status_code == 403


@pytest.mark.parametrize("path", ["/cookies", "/privacy"])
def test_the_legal_pages_explain_the_instagram_player(client, path):
    html = client.get(path).data.decode()
    assert "Instagram" in html and 'href="/reels"' in html
    assert "only when you press play" in html or "Only when you press play" in html
    assert "October 30, 2026" in html, "the effective date moved with the change"
    assert "privacycenter.instagram.com" in html
