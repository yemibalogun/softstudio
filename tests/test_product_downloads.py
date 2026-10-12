"""
Gated product downloads: leave a name and email, get a link by email, and
only that link releases the installer.

What is being protected, and how the tests show it:
* the file is unreachable without a link (no static URL, random name on disk)
* a link is personal, expires, has a use cap, and dies when replaced
* opening a link (GET) never releases the file or spends a use - only the
  page's Download button (POST) does, so mail scanners cannot burn uses
* the database holds only a hash of each link's token, and no link carries
  a database id
* uploads are typed by their bytes, and only the one admin route that takes
  installers is allowed past the site-wide 8 MB request cap
"""
import hashlib
import io
import os
import re
from datetime import timedelta

import pytest
from werkzeug.datastructures import FileStorage

from app.downloads import (
    DownloadFileError,
    clean_download_name,
    delete_download,
    format_size,
    store_download,
)
from app.extensions import mail
from app.models import DownloadRequest, Product, utcnow
from tests.conftest import login

EXE = b"MZ\x90\x00" + os.urandom(4096)
FILENAME = "JSWM Abbreviator Setup 2.0.0.exe"
LINK_RE = re.compile(r"https?://[^\s\"'<>]+/products/([a-z0-9-]+)/download/([A-Za-z0-9_-]{43})")


# ---------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------

@pytest.fixture()
def protected_dir(app, tmp_path):
    path = tmp_path / "protected"
    path.mkdir()
    app.config["PROTECTED_UPLOADS_DIR"] = str(path)
    return path


def _upload(data: bytes, filename: str) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=filename)


def _make_product(db, slug="jswm-abbreviator", title="JSWM Abbreviator", published=True,
                  data=EXE, filename=FILENAME, enabled=True):
    product = Product(title=title, slug=slug, short_description="Expands abbreviations.",
                      published=published)
    if data is not None:
        stored = store_download(_upload(data, filename), fallback_stem=slug)
        product.download_file = stored.path
        product.download_filename = stored.filename
        product.download_size = stored.size
        product.download_sha256 = stored.sha256
        product.download_version = "2.0.0"
        product.download_enabled = enabled
    db.session.add(product)
    db.session.commit()
    return product


@pytest.fixture()
def product(db, protected_dir):
    return _make_product(db)


def _request_link(client, slug="jswm-abbreviator", name="Ada Lovelace", email="ada@example.com", **extra):
    data = {"download-name": name, "download-email": email}
    data.update(extra)
    return client.post(f"/products/{slug}/download", data=data)


def _link_in(message) -> tuple[str, str, str]:
    """(full url, slug, token) from a captured email."""
    match = LINK_RE.search(message.body)
    assert match, f"no download link in the email:\n{message.body}"
    return match.group(0), match.group(1), match.group(2)


def _get_link(client, app, **kwargs):
    """Request a link and return its site-relative path."""
    with mail.record_messages() as outbox:
        resp = _request_link(client, **kwargs)
    assert resp.status_code == 302, resp.data[:400]
    assert len(outbox) == 1
    url, _, _ = _link_in(outbox[0])
    return "/" + url.split("://", 1)[1].split("/", 1)[1]


def _lead(email="ada@example.com"):
    return DownloadRequest.query.filter_by(email=email).one()


# ---------------------------------------------------------------------
# app/downloads.py: what may be stored
# ---------------------------------------------------------------------

def test_an_installer_is_stored_under_a_random_name(app, protected_dir):
    stored = store_download(_upload(EXE, FILENAME))

    assert re.fullmatch(r"downloads/[0-9a-f]{32}\.exe", stored.path)
    assert stored.filename == FILENAME
    assert stored.size == len(EXE)
    assert stored.sha256 == hashlib.sha256(EXE).hexdigest()
    assert (protected_dir / stored.path).read_bytes() == EXE
    assert not list(protected_dir.rglob("*.part")), "temporary file left behind"


@pytest.mark.parametrize("filename,data", [
    ("setup.exe", b"MZ" + b"\0" * 64),
    ("setup.msi", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64),
    ("app.msix", b"PK\x03\x04" + b"\0" * 64),
    ("app.zip", b"PK\x03\x04" + b"\0" * 64),
    ("app.pkg", b"xar!" + b"\0" * 64),
    ("App.AppImage", b"\x7fELF" + b"\0" * 64),
    ("app.deb", b"!<arch>\n" + b"\0" * 64),
    ("app.rpm", b"\xed\xab\xee\xdb" + b"\0" * 64),
    ("app.dmg", b"\0" * 2048 + b"koly" + b"\0" * 508),
])
def test_each_supported_type_is_recognised_by_its_bytes(app, protected_dir, filename, data):
    stored = store_download(_upload(data, filename))
    assert (protected_dir / stored.path).read_bytes() == data


@pytest.mark.parametrize("filename,data", [
    ("setup.exe", b"<html><script>alert(1)</script></html>"),   # a page renamed .exe
    ("setup.msi", b"PK\x03\x04" + b"\0" * 64),                  # a zip renamed .msi
    ("app.dmg", b"MZ" + b"\0" * 2048),                          # no DMG trailer
])
def test_bytes_that_do_not_match_the_extension_are_rejected(app, protected_dir, filename, data):
    with pytest.raises(DownloadFileError, match="do not match"):
        store_download(_upload(data, filename))
    assert not [p for p in protected_dir.rglob("*") if p.is_file()], "rejected file left on disk"


@pytest.mark.parametrize("filename", ["run.bat", "run.ps1", "app.js", "page.html", "page.svg", "noextension"])
def test_unsupported_types_are_rejected(app, protected_dir, filename):
    with pytest.raises(DownloadFileError, match="not supported"):
        store_download(_upload(b"MZ" + b"\0" * 64, filename))


def test_an_empty_file_is_rejected(app, protected_dir):
    with pytest.raises(DownloadFileError, match="empty"):
        store_download(_upload(b"", "setup.exe"))
    assert not [p for p in protected_dir.rglob("*") if p.is_file()]


def test_the_size_limit_is_enforced_while_streaming(app, protected_dir):
    app.config["MAX_DOWNLOAD_UPLOAD_BYTES"] = 1024
    with pytest.raises(DownloadFileError, match="larger than"):
        store_download(_upload(b"MZ" + b"\0" * 4096, "setup.exe"))
    assert not [p for p in protected_dir.rglob("*") if p.is_file()], "partial file left on disk"


@pytest.mark.parametrize("given,expected", [
    (FILENAME, FILENAME),
    ("C:\\Users\\yemi\\dist\\Setup.exe", "Setup.exe"),          # old browsers send the full path
    ("../../etc/passwd.exe", "passwd.exe"),
    ('evil"; name=.exe', "evil name.exe"),
    ("Setup\r\nX-Header: 1.exe", "Setup X-Header 1.exe"),
    ("SETUP.EXE", "SETUP.exe"),
    ("....exe", "download.exe"),
])
def test_the_name_shown_to_visitors_is_cleaned(given, expected):
    assert clean_download_name(given) == expected


def test_delete_only_touches_files_it_created(app, protected_dir, tmp_path):
    outside = tmp_path / "keep.exe"
    outside.write_bytes(b"MZ")
    for path in ["../keep.exe", "downloads/../../keep.exe", str(outside), "downloads/x.exe"]:
        delete_download(path)
    assert outside.exists()


def test_sizes_read_like_windows_explorer():
    assert format_size(15513636) == "14.8 MB"
    assert format_size(512) == "512 bytes"
    assert format_size(2048) == "2.0 KB"
    assert format_size(None) == ""


# ---------------------------------------------------------------------
# The product page
# ---------------------------------------------------------------------

def test_the_page_offers_the_download_when_it_is_ready(client, product):
    html = client.get("/products/jswm-abbreviator").data.decode()
    assert 'id="download"' in html
    assert "Email me the download link" in html
    assert "Download for Windows" in html
    assert "Version 2.0.0" in html


def test_nothing_is_offered_while_switched_off(client, db, product):
    product.download_enabled = False
    db.session.commit()
    html = client.get("/products/jswm-abbreviator").data.decode()
    assert 'id="download"' not in html
    assert _request_link(client).status_code == 404


def test_nothing_is_offered_if_the_file_is_missing_from_disk(client, product, protected_dir):
    os.remove(protected_dir / product.download_file)
    html = client.get("/products/jswm-abbreviator").data.decode()
    assert 'id="download"' not in html, "a form whose links could never work"
    assert _request_link(client).status_code == 404


def test_an_unpublished_product_offers_nothing(client, db, product):
    product.published = False
    db.session.commit()
    assert client.get("/products/jswm-abbreviator").status_code == 404
    assert _request_link(client).status_code == 404


def test_the_two_forms_on_one_page_do_not_share_ids(client, db, product):
    product.waitlist_enabled = True
    db.session.commit()
    html = client.get("/products/jswm-abbreviator").data.decode()
    ids = re.findall(r'\sid="([^"]+)"', html)
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"duplicate element ids: {duplicates}"


# ---------------------------------------------------------------------
# Asking for the link
# ---------------------------------------------------------------------

@pytest.mark.parametrize("name,email", [
    ("", "ada@example.com"),
    ("   ", "ada@example.com"),
    ("Ada", ""),
    ("Ada", "not-an-email"),
])
def test_name_and_email_are_both_required(client, product, name, email):
    with mail.record_messages() as outbox:
        resp = _request_link(client, name=name, email=email)
    assert resp.status_code == 400
    assert DownloadRequest.query.count() == 0
    assert outbox == []


def test_a_request_saves_the_lead_and_emails_a_personal_link(client, product):
    with mail.record_messages() as outbox:
        resp = _request_link(client, name="  Ada Lovelace ", email="  Ada@Example.COM ",
                             **{"download-utm_source": "LinkedIn", "download-utm_campaign": "launch"})

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/products/jswm-abbreviator?requested=sent#download")

    lead = _lead()
    assert lead.name == "Ada Lovelace"
    assert lead.email == "ada@example.com"
    assert lead.source == "linkedin" and lead.utm_campaign == "launch"
    assert lead.email_delivered is True

    assert len(outbox) == 1
    message = outbox[0]
    assert message.recipients == ["ada@example.com"]
    assert message.subject == "Your download: JSWM Abbreviator"
    assert message.attachments == [], "the installer must never be attached"
    url, slug, token = _link_in(message)
    assert slug == "jswm-abbreviator"
    assert url.startswith("http://localhost:8000/"), "links are built from SITE_URL"
    assert token in message.html, "the HTML part carries the same link"


def test_only_a_hash_of_the_token_is_stored(client, product):
    with mail.record_messages() as outbox:
        _request_link(client)
    _, _, token = _link_in(outbox[0])
    lead = _lead()
    assert lead.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(lead.__dict__.values())


def test_a_link_carries_no_database_id(client, product):
    with mail.record_messages() as outbox:
        _request_link(client)
    url, _, token = _link_in(outbox[0])
    assert re.fullmatch(r"http://localhost:8000/products/jswm-abbreviator/download/[A-Za-z0-9_-]{43}", url)


def test_the_confirmation_shows_without_echoing_the_address(client, product):
    resp = _request_link(client)
    page = client.get(resp.headers["Location"]).data.decode()
    assert "Check your inbox." in page
    assert "ada@example.com" not in page
    assert "ada%40example.com" not in resp.headers["Location"]


def test_the_honeypot_looks_like_success_but_does_nothing(client, product):
    with mail.record_messages() as outbox:
        resp = _request_link(client, **{"download-website": "https://spam.example"})
    assert resp.status_code == 302 and "requested=sent" in resp.headers["Location"]
    assert DownloadRequest.query.count() == 0
    assert outbox == []


def test_asking_twice_in_quick_succession_sends_one_email(client, product):
    """The form must not become a way to flood someone else's inbox."""
    with mail.record_messages() as outbox:
        first = _request_link(client)
        second = _request_link(client)
    assert first.headers["Location"] == second.headers["Location"], "replies must be identical"
    assert len(outbox) == 1
    assert DownloadRequest.query.count() == 1


def test_asking_again_later_replaces_the_link_on_the_same_lead(client, app, db, product):
    old_link = _get_link(client, app)
    lead = _lead()
    lead.link_sent_at = utcnow() - timedelta(minutes=10)
    db.session.commit()

    new_link = _get_link(client, app, name="Ada King")

    assert DownloadRequest.query.count() == 1, "one lead per person per product"
    lead = _lead()
    assert lead.request_count == 2
    assert lead.name == "Ada King"
    assert client.get(old_link).status_code == 404, "a replaced link stops working"
    assert client.get(new_link).status_code == 200


def test_a_failed_email_says_so_and_can_be_retried_at_once(client, product, monkeypatch):
    import app.products.routes as routes

    monkeypatch.setattr(routes, "send_product_download_link", lambda *a, **k: False)
    resp = _request_link(client)
    assert "requested=failed" in resp.headers["Location"]
    assert "couldn’t send the email" in client.get(resp.headers["Location"]).data.decode()
    assert _lead().email_delivered is False

    monkeypatch.undo()
    with mail.record_messages() as outbox:
        _request_link(client)
    assert len(outbox) == 1, "the cooldown must not block a retry after a failure"


# ---------------------------------------------------------------------
# Opening the link, and the Download button
# ---------------------------------------------------------------------

def test_opening_a_link_shows_a_page_and_spends_nothing(client, app, product):
    """Mail scanners open every link: a GET must not release the file."""
    link = _get_link(client, app)
    resp = client.get(link)

    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert EXE not in resp.data
    html = resp.data.decode()
    assert "Download JSWM Abbreviator Setup 2.0.0.exe" in html
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "no-store" in resp.headers["Cache-Control"]
    assert "noindex" in resp.headers["X-Robots-Tag"]
    assert _lead().link_uses == 0


def test_the_download_button_releases_exactly_the_file(client, app, product):
    link = _get_link(client, app)
    resp = client.post(link)

    assert resp.status_code == 200
    assert resp.data == EXE
    assert resp.mimetype == "application/octet-stream"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in resp.headers["Cache-Control"]
    disposition = resp.headers["Content-Disposition"]
    assert disposition.startswith("attachment")
    assert "JSWM" in disposition and "2.0.0.exe" in disposition

    lead = _lead()
    assert lead.link_uses == 1 and lead.download_count == 1
    assert lead.first_downloaded_at is not None and lead.last_downloaded_at is not None


def test_a_link_stops_after_its_use_limit(client, app, product):
    app.config["DOWNLOAD_LINK_MAX_USES"] = 2
    link = _get_link(client, app)
    assert client.post(link).data == EXE
    assert client.post(link).data == EXE

    third = client.post(link)
    assert third.status_code == 410
    assert EXE not in third.data
    assert "used up" in third.data.decode()
    assert _lead().download_count == 2


def test_an_expired_link_releases_nothing(client, app, db, product):
    link = _get_link(client, app)
    lead = _lead()
    lead.link_sent_at = utcnow() - timedelta(days=8)
    db.session.commit()

    page = client.get(link)
    assert page.status_code == 410 and "expired" in page.data.decode()
    post = client.post(link)
    assert post.status_code == 410 and EXE not in post.data
    assert "Get a new link" in page.data.decode()


@pytest.mark.parametrize("token", [
    "A" * 43,                       # well-formed, never issued
    "short",
    "A" * 44,
    "..%2F..%2Fetc%2Fpasswd",
])
def test_unknown_tokens_release_nothing(client, product, token):
    for resp in (client.get(f"/products/jswm-abbreviator/download/{token}"),
                 client.post(f"/products/jswm-abbreviator/download/{token}")):
        assert resp.status_code == 404
        assert EXE not in resp.data


def test_a_token_only_opens_its_own_product(client, app, db, product):
    _make_product(db, slug="other-tool", title="Other Tool", data=b"MZ" + b"\1" * 256)
    link = _get_link(client, app)
    token = link.rsplit("/", 1)[1]

    wrong = client.post(f"/products/other-tool/download/{token}")
    assert wrong.status_code == 404
    assert wrong.data != b"MZ" + b"\1" * 256


@pytest.mark.parametrize("change", ["unpublish", "switch_off", "delete_file"])
def test_withdrawing_the_download_kills_existing_links(client, app, db, product, protected_dir, change):
    link = _get_link(client, app)
    if change == "unpublish":
        product.published = False
    elif change == "switch_off":
        product.download_enabled = False
    else:
        os.remove(protected_dir / product.download_file)
    db.session.commit()

    resp = client.post(link)
    assert resp.status_code == 404
    assert EXE not in resp.data


def test_the_download_button_requires_its_csrf_token(client, app, product):
    link = _get_link(client, app)
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        resp = client.post(link)  # no token
        assert EXE not in resp.data
        assert _lead().link_uses == 0
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


def test_lead_details_never_appear_on_public_pages(client, app, product):
    _get_link(client, app)
    for path in ["/products/", "/products/jswm-abbreviator"]:
        html = client.get(path).data.decode()
        assert "ada@example.com" not in html
        assert "Ada Lovelace" not in html


def test_the_products_index_marks_downloadable_products(client, product):
    html = client.get("/products/").data.decode()
    assert "Free download · Windows" in html


# ---------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------

def _login_admin(client):
    return login(client, "admin@example.com", "correcthorsebattery")


def _bare_product(db):
    return _make_product(db, data=None)


def _post_installer(client, product_id, data=EXE, filename=FILENAME, version="2.0.0", enabled=True, **extra):
    form = {"file": (io.BytesIO(data), filename), "version": version}
    if enabled:
        form["enabled"] = "y"
    form.update(extra)
    return client.post(
        f"/admin/products/{product_id}/download",
        data=form,
        content_type="multipart/form-data",
    )


def test_admin_uploads_an_installer(client, db, admin_user, protected_dir):
    _login_admin(client)
    product = _bare_product(db)

    resp = _post_installer(client, product.id)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/admin/products/{product.id}/edit#download")

    db.session.refresh(product)
    assert product.download_filename == FILENAME
    assert product.download_size == len(EXE)
    assert product.download_sha256 == hashlib.sha256(EXE).hexdigest()
    assert product.download_version == "2.0.0"
    assert product.download_enabled is True
    assert (protected_dir / product.download_file).read_bytes() == EXE


def test_an_installer_larger_than_the_site_wide_cap_uploads_with_csrf_on(
    client, app, db, admin_user, protected_dir
):
    """
    The production path. Installers are bigger than the 8 MB cap, and with
    CSRF on, the global hook reads the body before any view runs - which is
    why this route is exempt from the hook and checks its own token.
    """
    _login_admin(client)
    product = _bare_product(db)
    big = b"MZ" + os.urandom(app.config["MAX_CONTENT_LENGTH"] + 1024 * 1024)

    app.config["WTF_CSRF_ENABLED"] = True
    try:
        page = client.get(f"/admin/products/{product.id}/edit").data.decode()
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)

        resp = _post_installer(client, product.id, data=big, csrf_token=token)
        assert resp.status_code == 302, resp.status_code
        db.session.refresh(product)
        assert product.download_size == len(big)

        # ...and the exemption is narrow: everything else keeps the 8 MB cap.
        edit = client.post(
            f"/admin/products/{product.id}/edit",
            data={"csrf_token": token, "title": "x", "short_description": "x",
                  "image_file": (io.BytesIO(big), "big.png")},
            content_type="multipart/form-data",
        )
        assert edit.status_code == 413
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


def test_the_upload_route_still_rejects_a_missing_csrf_token(client, app, db, admin_user, protected_dir):
    _login_admin(client)
    product = _bare_product(db)
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        _post_installer(client, product.id)
    finally:
        app.config["WTF_CSRF_ENABLED"] = False
    db.session.refresh(product)
    assert product.download_file is None
    assert not [p for p in protected_dir.rglob("*") if p.is_file()]


def test_admin_cannot_upload_a_disguised_file(client, db, admin_user, protected_dir):
    _login_admin(client)
    product = _bare_product(db)
    resp = _post_installer(client, product.id, data=b"<html>not an exe</html>")
    assert resp.status_code == 302
    db.session.refresh(product)
    assert product.download_file is None
    page = client.get(resp.headers["Location"]).data.decode()
    assert "do not match a .exe file" in page


def test_replacing_the_installer_removes_the_old_file(client, db, admin_user, product, protected_dir):
    _login_admin(client)
    old_path = protected_dir / product.download_file

    _post_installer(client, product.id, data=b"MZ" + b"\2" * 512, filename="JSWM Abbreviator Setup 2.1.0.exe",
                    version="2.1.0")

    db.session.refresh(product)
    assert not old_path.exists(), "the replaced installer must not linger"
    assert (protected_dir / product.download_file).read_bytes() == b"MZ" + b"\2" * 512
    assert product.download_filename == "JSWM Abbreviator Setup 2.1.0.exe"


def test_saving_settings_without_a_new_file_keeps_the_current_one(client, db, admin_user, product):
    _login_admin(client)
    before = product.download_file
    client.post(f"/admin/products/{product.id}/download",
                data={"version": "2.0.1"}, content_type="multipart/form-data")
    db.session.refresh(product)
    assert product.download_file == before
    assert product.download_version == "2.0.1"
    assert product.download_enabled is False, "unticked box switches it off"


def test_removing_the_download_deletes_the_file_and_kills_links(
    client, app, db, admin_user, product, protected_dir
):
    link = _get_link(client, app)
    path = protected_dir / product.download_file
    _login_admin(client)

    client.post(f"/admin/products/{product.id}/download/remove")

    db.session.refresh(product)
    assert product.download_file is None and product.download_enabled is False
    assert not path.exists()
    assert client.post(link).status_code == 404


def test_deleting_a_product_removes_its_installer_and_leads(
    client, app, db, admin_user, product, protected_dir
):
    _get_link(client, app)
    path = protected_dir / product.download_file
    _login_admin(client)

    client.post(f"/admin/products/{product.id}/delete")

    assert not path.exists()
    assert DownloadRequest.query.count() == 0


def test_the_lead_list_is_admin_only(client, app, db, product, user):
    _get_link(client, app)
    assert client.get(f"/admin/products/{product.id}/downloads").status_code in (302, 401)
    login(client, "student@example.com", "correcthorsebattery")
    assert client.get(f"/admin/products/{product.id}/downloads").status_code == 403
    assert client.get(f"/admin/products/{product.id}/downloads.csv").status_code == 403


def test_admin_sees_who_requested_and_who_downloaded(client, app, db, admin_user, product):
    link = _get_link(client, app)
    client.post(link)
    _login_admin(client)

    html = client.get(f"/admin/products/{product.id}/downloads").data.decode()
    assert "Ada Lovelace" in html and "ada@example.com" in html
    assert "1 person requested it" in html and "1 downloaded it" in html


def test_the_csv_export_cannot_smuggle_spreadsheet_formulas(client, app, db, admin_user, product):
    _get_link(client, app, name='=HYPERLINK("http://evil.example","click")', email="x@example.com")
    _login_admin(client)

    resp = client.get(f"/admin/products/{product.id}/downloads.csv")
    assert resp.mimetype == "text/csv"
    body = resp.data.decode()
    assert "'=HYPERLINK" in body
    assert ',=HYPERLINK' not in body and '\n=HYPERLINK' not in body
    assert "x@example.com" in body
