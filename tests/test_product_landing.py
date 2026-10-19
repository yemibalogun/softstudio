"""
The focused landing layout for a free download (e.g. the Automation
Readiness Scorecard, linked from Instagram DMs), and PDF support behind it.

The landing page is the same URL and the same gated flow as a normal product
page - name and email in, a personal link emailed out, the file never public -
in a different, single-purpose layout.
"""
import hashlib
import io
import re

import pytest
from werkzeug.datastructures import FileStorage

from app.downloads import DownloadFileError, kind_for, store_download
from app.extensions import mail
from app.models import DownloadRequest, Product
from tests.conftest import login

PDF = b"%PDF-1.7\n" + b"1 0 obj << /Type /Catalog >> endobj\n" * 50 + b"%%EOF\n"
PDF_NAME = "Automation-Readiness-Scorecard.pdf"
URL = "/products/automation-readiness-scorecard"
HEADLINE = "Should you automate it,\nor *fix it first?*"
POINTS = (
    "The **one-line test** that separates a rule from a judgment call\n"
    "How to rank processes by **hours lost per month**\n"
    "\n"
    "The two questions that catch a **broken process**"
)


@pytest.fixture()
def protected_dir(app, tmp_path):
    path = tmp_path / "protected"
    path.mkdir()
    app.config["PROTECTED_UPLOADS_DIR"] = str(path)
    return path


def _scorecard(db, landing=True, with_file=True, enabled=True, **fields):
    product = Product(
        title="Automation Readiness Scorecard",
        slug="automation-readiness-scorecard",
        short_description="Ten questions that tell you whether a process belongs to a simple rule, "
                          "genuinely needs AI, or is not ready for either.",
        published=True,
        landing_page=landing,
        landing_headline=HEADLINE,
        landing_points=POINTS,
        landing_button_label="Send me the scorecard",
        **fields,
    )
    if with_file:
        stored = store_download(FileStorage(stream=io.BytesIO(PDF), filename=PDF_NAME))
        product.download_file = stored.path
        product.download_filename = stored.filename
        product.download_size = stored.size
        product.download_sha256 = stored.sha256
        product.download_enabled = enabled
    db.session.add(product)
    db.session.commit()
    return product


@pytest.fixture()
def scorecard(db, protected_dir):
    return _scorecard(db)


def _hidden_fields(html: str) -> dict:
    fields = {}
    for tag in re.findall(r"<input[^>]*>", html):
        if 'type="hidden"' not in tag:
            continue
        name = re.search(r'name="(download-[a-z_]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name and value:
            fields[name.group(1)] = value.group(1)
    return fields


# ---------------------------------------------------------------------
# PDFs
# ---------------------------------------------------------------------

def test_a_pdf_is_accepted_by_its_bytes(app, protected_dir):
    stored = store_download(FileStorage(stream=io.BytesIO(PDF), filename=PDF_NAME))
    assert stored.path.endswith(".pdf")
    assert stored.filename == PDF_NAME
    assert (protected_dir / stored.path).read_bytes() == PDF


def test_a_file_renamed_to_pdf_is_rejected(app, protected_dir):
    with pytest.raises(DownloadFileError, match="do not match a .pdf"):
        store_download(FileStorage(stream=io.BytesIO(b"MZ" + b"\0" * 64), filename="scorecard.pdf"))
    with pytest.raises(DownloadFileError, match="do not match a .pdf"):
        store_download(FileStorage(stream=io.BytesIO(b"<html>hi</html>"), filename="scorecard.pdf"))


def test_badges_say_pdf_for_a_document_and_the_platform_for_an_installer():
    assert kind_for(PDF_NAME) == "PDF"
    assert kind_for("JSWM Abbreviator Setup 2.0.0.exe") == "Windows"


def test_the_pdf_is_served_as_a_download_never_rendered(client, scorecard):
    with mail.record_messages() as outbox:
        client.post(f"{URL}/download", data={"download-name": "Ada", "download-email": "ada@example.com"})
    link = "/" + re.search(r"https?://[^/]+/(\S+/download/[A-Za-z0-9_-]{43})", outbox[0].body).group(1)

    resp = client.post(link)
    assert resp.data == PDF
    assert resp.mimetype == "application/octet-stream"
    assert resp.headers["Content-Disposition"].startswith("attachment")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


# ---------------------------------------------------------------------
# Which layout
# ---------------------------------------------------------------------

def test_the_landing_layout_is_used_when_switched_on(client, scorecard):
    html = client.get(URL).data.decode()
    assert "css/landing.css" in html
    assert 'class="navbar' not in html and "Start a project" not in html, "no site navigation"
    assert 'Should you automate it,<br>or <span class="g">fix it first?</span>' in html
    assert "The <b>one-line test</b> that separates" in html
    assert html.count('<li>') == 3, "blank lines in the points are skipped"
    assert "Send me the scorecard" in html
    assert f'action="{URL}/download"' in html


def test_the_landing_page_keeps_seo_and_share_tags(client, scorecard):
    html = client.get(URL).data.decode()
    canonical = "http://localhost:8000/products/automation-readiness-scorecard"
    assert f'<link rel="canonical" href="{canonical}">' in html
    assert re.search(r'<meta property="og:image" content="http://localhost:8000/', html)
    assert '<meta property="og:title" content="Automation Readiness Scorecard">' in html


def test_the_landing_page_has_no_inline_script(client, scorecard):
    """The site's CSP is script-src 'self': an inline script would just be blocked."""
    html = client.get(URL).data.decode()
    assert "<script" not in html


def test_the_normal_page_is_used_when_landing_is_off(client, db, protected_dir):
    _scorecard(db, landing=False)
    html = client.get(URL).data.decode()
    assert "css/landing.css" not in html
    assert 'id="download"' in html, "the standard page still offers the download"


@pytest.mark.parametrize("state", ["no_file", "switched_off"])
def test_a_landing_page_without_a_live_download_falls_back(client, db, protected_dir, state):
    """A landing page is one form; without a download it would be a dead end."""
    _scorecard(db, with_file=(state != "no_file"), enabled=(state != "switched_off"))
    html = client.get(URL).data.decode()
    assert "css/landing.css" not in html
    assert "Send me the scorecard" not in html


def test_headline_and_points_cannot_inject_markup(client, db, protected_dir):
    _scorecard(db).landing_headline = '<img src=x onerror=alert(1)> *ok*'
    product = Product.query.one()
    product.landing_points = '<script>alert(1)</script> **fine**'
    db.session.commit()

    html = client.get(URL).data.decode()
    assert "<img src=x" not in html and "<script>alert" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert '<span class="g">ok</span>' in html and "<b>fine</b>" in html


def test_without_a_headline_the_title_is_used(client, db, protected_dir):
    product = _scorecard(db)
    product.landing_headline = None
    db.session.commit()
    assert "<h1>Automation Readiness Scorecard</h1>" in client.get(URL).data.decode()


# ---------------------------------------------------------------------
# Signing up from the landing page
# ---------------------------------------------------------------------

def test_instagram_visitors_sign_up_and_their_source_is_kept(client, scorecard):
    page = client.get(f"{URL}?utm_source=instagram&utm_medium=dm&utm_campaign=scorecard").data.decode()
    form = _hidden_fields(page)
    assert form.get("download-utm_source") == "instagram"
    form.update({"download-name": "Ada Lovelace", "download-email": "ada@example.com"})

    with mail.record_messages() as outbox:
        resp = client.post(f"{URL}/download", data=form)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"{URL}?requested=sent#download")
    lead = DownloadRequest.query.one()
    assert (lead.name, lead.email) == ("Ada Lovelace", "ada@example.com")
    assert (lead.source, lead.utm_medium, lead.utm_campaign) == ("instagram", "dm", "scorecard")

    assert len(outbox) == 1
    message = outbox[0]
    assert message.subject == "Your download: Automation Readiness Scorecard"
    assert message.attachments == []
    assert PDF_NAME in message.body
    assert "For:" not in message.body, "no platform line for a document"

    done = client.get(resp.headers["Location"]).data.decode()
    assert "css/landing.css" in done, "the confirmation stays in the landing layout"
    assert "Check your inbox." in done
    assert "ada@example.com" not in done


def test_mistakes_are_shown_in_the_landing_layout(client, scorecard):
    resp = client.post(f"{URL}/download", data={"download-name": "", "download-email": "not-an-email"})
    assert resp.status_code == 400
    html = resp.data.decode()
    assert "css/landing.css" in html
    assert "Please enter your name." in html
    assert "doesn't look like an email address" in html or "doesn&#39;t look like an email address" in html
    assert 'aria-invalid="true"' in html
    assert DownloadRequest.query.count() == 0


def test_a_failed_send_is_shown_in_the_landing_layout(client, scorecard, monkeypatch):
    import app.products.routes as routes

    monkeypatch.setattr(routes, "send_product_download_link", lambda *a, **k: False)
    resp = client.post(f"{URL}/download", data={"download-name": "Ada", "download-email": "ada@example.com"})
    html = client.get(resp.headers["Location"]).data.decode()
    assert "css/landing.css" in html
    assert "couldn’t send the email" in html


def test_the_scorecard_is_listed_as_a_free_pdf(client, scorecard):
    assert "Free download · PDF" in client.get("/products/").data.decode()


# ---------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------

def test_admin_sets_up_a_landing_page(client, db, admin_user, protected_dir):
    login(client, "admin@example.com", "correcthorsebattery")
    resp = client.post("/admin/products/new", data={
        "title": "Automation Readiness Scorecard",
        "slug": "automation-readiness-scorecard",
        "short_description": "Ten questions.",
        "published": "y",
        "landing_page": "y",
        "landing_headline": "  " + HEADLINE + "  ",
        "landing_points": POINTS,
        "landing_button_label": "Send me the scorecard",
        "display_order": 0,
    })
    assert resp.status_code == 302
    product = Product.query.one()
    assert product.landing_page is True
    assert product.landing_headline == HEADLINE
    assert product.landing_button_label == "Send me the scorecard"

    # Then the PDF, through the same upload route installers use.
    resp = client.post(
        f"/admin/products/{product.id}/download",
        data={"file": (io.BytesIO(PDF), PDF_NAME), "enabled": "y"},
        content_type="multipart/form-data",
    )
    db.session.refresh(product)
    assert product.download_filename == PDF_NAME
    assert product.download_sha256 == hashlib.sha256(PDF).hexdigest()
    assert "css/landing.css" in client.get(URL).data.decode()


def test_clearing_the_landing_fields_stores_nothing(client, db, admin_user, protected_dir):
    login(client, "admin@example.com", "correcthorsebattery")
    product = _scorecard(db)
    client.post(f"/admin/products/{product.id}/edit", data={
        "title": product.title, "slug": product.slug, "short_description": product.short_description,
        "published": "y", "landing_headline": "   ", "landing_points": "", "landing_button_label": "",
        "display_order": 0,
    })
    db.session.refresh(product)
    assert product.landing_page is False
    assert product.landing_headline is None and product.landing_points is None
    assert product.landing_button_label is None
