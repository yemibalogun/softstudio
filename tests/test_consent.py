"""
Marketing email consent, unsubscribing, sign-up deletion and retention -
everything the privacy policy promises about download and waitlist sign-ups.
"""
import glob
import io
import os
import re
from datetime import timedelta

import pytest
from werkzeug.datastructures import FileStorage

from app.consent import email_from_token, prune_leads, unsubscribe_token
from app.downloads import store_download
from app.extensions import mail
from app.models import DownloadRequest, Product, WaitlistSubscriber, utcnow
from tests.conftest import login

EMAIL = "ada@example.com"


@pytest.fixture()
def product(db, app, tmp_path):
    app.config["PROTECTED_UPLOADS_DIR"] = str(tmp_path)
    stored = store_download(FileStorage(stream=io.BytesIO(b"%PDF-1.7\n%%EOF\n"), filename="Scorecard.pdf"))
    item = Product(title="Scorecard", slug="scorecard", short_description="Ten questions.",
                   published=True, waitlist_enabled=True,
                   download_file=stored.path, download_filename=stored.filename,
                   download_size=stored.size, download_sha256=stored.sha256, download_enabled=True)
    db.session.add(item)
    db.session.commit()
    return item


def _download(client, opt_in=False, email=EMAIL):
    data = {"download-name": "Ada", "download-email": email}
    if opt_in:
        data["download-marketing_opt_in"] = "y"
    with mail.record_messages() as outbox:
        resp = client.post("/products/scorecard/download", data=data)
    return resp, outbox


def _join(client, opt_in=False, email=EMAIL):
    data = {"email": email}
    if opt_in:
        data["marketing_opt_in"] = "y"
    return client.post("/products/scorecard/waitlist", data=data)


# ---------------------------------------------------------------------
# Opting in
# ---------------------------------------------------------------------

def test_the_box_is_offered_unticked_on_every_form(client, product):
    html = client.get("/products/scorecard").data.decode()
    boxes = re.findall(r'<input[^>]*name="(?:download-)?marketing_opt_in"[^>]*>', html)
    assert len(boxes) == 2, "download form and waitlist form"
    assert all("checked" not in box for box in boxes)
    assert "Optional. Unsubscribe any time." in html


def test_the_download_never_depends_on_the_box(client, product):
    resp, outbox = _download(client, opt_in=False)
    assert resp.status_code == 302 and "requested=sent" in resp.headers["Location"]
    assert len(outbox) == 1
    lead = DownloadRequest.query.one()
    assert lead.marketing_consent is False and lead.consent_at is None


def test_ticking_the_box_records_consent_and_when(client, product):
    _download(client, opt_in=True)
    lead = DownloadRequest.query.one()
    assert lead.marketing_consent is True
    assert lead.consent_at is not None


def test_asking_again_without_the_box_keeps_consent(client, db, product):
    _download(client, opt_in=True)
    lead = DownloadRequest.query.one()
    lead.link_sent_at = utcnow() - timedelta(minutes=10)
    db.session.commit()
    _download(client, opt_in=False)
    assert DownloadRequest.query.one().marketing_consent is True


def test_ticking_the_box_within_the_cooldown_still_counts(client, product):
    _download(client, opt_in=False)
    _, outbox = _download(client, opt_in=True)   # inside the 2-minute cooldown
    assert outbox == []
    assert DownloadRequest.query.one().marketing_consent is True


def test_waitlist_consent_and_rejoining_with_the_box(client, product):
    _join(client, opt_in=False)
    assert WaitlistSubscriber.query.one().marketing_consent is False
    _join(client, opt_in=True)
    assert WaitlistSubscriber.query.count() == 1
    assert WaitlistSubscriber.query.one().marketing_consent is True


# ---------------------------------------------------------------------
# The email and unsubscribing
# ---------------------------------------------------------------------

def test_the_download_email_carries_an_unsubscribe_link_and_headers(client, product):
    _, outbox = _download(client)
    message = outbox[0]
    link = re.search(r"http://localhost:8000/unsubscribe/(\S+)", message.body)
    assert link, "plain-text part has the link"
    assert link.group(0) in message.html, "and the HTML part"
    assert email_from_token(link.group(1)) == EMAIL
    headers = dict(message.extra_headers or {})
    assert headers["List-Unsubscribe"] == f"<{link.group(0)}>"
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_opening_the_link_changes_nothing(client, product):
    _download(client, opt_in=True)
    page = client.get(f"/unsubscribe/{unsubscribe_token(EMAIL)}")
    assert page.status_code == 200
    assert "Unsubscribe from our emails?" in page.data.decode()
    assert DownloadRequest.query.one().marketing_consent is True, "mail scanners open links"


def test_confirming_unsubscribes_from_every_product(client, product):
    _download(client, opt_in=True)
    _join(client, opt_in=True)
    resp = client.post(f"/unsubscribe/{unsubscribe_token(EMAIL)}")
    assert resp.status_code == 200 and "You’re unsubscribed." in resp.data.decode()
    for lead in (DownloadRequest.query.one(), WaitlistSubscriber.query.one()):
        assert lead.marketing_consent is False
        assert lead.unsubscribed_at is not None


def test_one_click_unsubscribe_works_without_a_session(client, app, product):
    """RFC 8058: the mail app POSTs straight to the link, no cookies, no CSRF token."""
    _download(client, opt_in=True)
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        resp = client.post(f"/unsubscribe/{unsubscribe_token(EMAIL)}",
                           data={"List-Unsubscribe": "One-Click"})
    finally:
        app.config["WTF_CSRF_ENABLED"] = False
    assert resp.status_code == 200
    assert DownloadRequest.query.one().marketing_consent is False


@pytest.mark.parametrize("token", ["not-a-token", unsubscribe_token.__name__, "x" * 40])
def test_a_forged_link_does_nothing(client, product, token):
    _download(client, opt_in=True)
    assert client.get(f"/unsubscribe/{token}").status_code == 404
    assert client.post(f"/unsubscribe/{token}").status_code == 404
    assert DownloadRequest.query.one().marketing_consent is True


def test_opting_in_again_after_unsubscribing(client, db, product):
    _download(client, opt_in=True)
    client.post(f"/unsubscribe/{unsubscribe_token(EMAIL)}")
    lead = DownloadRequest.query.one()
    lead.link_sent_at = utcnow() - timedelta(minutes=10)
    db.session.commit()
    _download(client, opt_in=True)
    lead = DownloadRequest.query.one()
    assert lead.marketing_consent is True and lead.unsubscribed_at is None


# ---------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------

def test_sign_ups_without_consent_are_removed_after_a_year(db, product):
    old = utcnow() - timedelta(days=400)
    db.session.add_all([
        DownloadRequest(product_id=product.id, name="Old", email="old@example.com",
                        token_hash="a" * 64, created_at=old),
        DownloadRequest(product_id=product.id, name="Kept", email="kept@example.com",
                        token_hash="b" * 64, created_at=old, marketing_consent=True),
        DownloadRequest(product_id=product.id, name="New", email="new@example.com", token_hash="c" * 64),
        WaitlistSubscriber(product_id=product.id, email="oldwait@example.com", created_at=old),
    ])
    db.session.commit()
    assert prune_leads(365) == 2
    left = {lead.email for lead in DownloadRequest.query.all()}
    left |= {sub.email for sub in WaitlistSubscriber.query.all()}
    assert left == {"kept@example.com", "new@example.com"}


def test_the_weekly_job_runs_the_lead_clean_up(app, db, product):
    db.session.add(DownloadRequest(product_id=product.id, name="Old", email="old@example.com",
                                   token_hash="d" * 64, created_at=utcnow() - timedelta(days=400)))
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["prune-analytics"])
    assert "1 sign-up(s) without email consent removed." in result.output
    assert DownloadRequest.query.count() == 0


# ---------------------------------------------------------------------
# Admin: delete one sign-up, consent in the list and the exports
# ---------------------------------------------------------------------

def _admin(client):
    login(client, "admin@example.com", "correcthorsebattery")


def test_admin_deletes_one_download_sign_up(client, product, admin_user):
    _download(client, email="a@example.com")
    _download(client, email="b@example.com")
    target = DownloadRequest.query.filter_by(email="a@example.com").one()
    _admin(client)
    client.post(f"/admin/products/{product.id}/downloads/{target.id}/delete")
    assert [lead.email for lead in DownloadRequest.query.all()] == ["b@example.com"]


def test_a_sign_up_can_only_be_deleted_under_its_own_product(client, db, product, admin_user):
    _download(client)
    other = Product(title="Other", slug="other", short_description="x", published=True)
    db.session.add(other)
    db.session.commit()
    _admin(client)
    lead = DownloadRequest.query.one()
    assert client.post(f"/admin/products/{other.id}/downloads/{lead.id}/delete").status_code == 404
    assert DownloadRequest.query.count() == 1


def test_admin_deletes_one_waitlist_sign_up(client, product, admin_user):
    _join(client, email="a@example.com")
    _join(client, email="b@example.com")
    target = WaitlistSubscriber.query.filter_by(email="a@example.com").one()
    _admin(client)
    client.post(f"/admin/products/{product.id}/waitlist/{target.id}/delete")
    assert [s.email for s in WaitlistSubscriber.query.all()] == ["b@example.com"]


def test_deleting_is_admin_only(client, product, user):
    _download(client)
    lead = DownloadRequest.query.one()
    login(client, "student@example.com", "correcthorsebattery")
    assert client.post(f"/admin/products/{product.id}/downloads/{lead.id}/delete").status_code == 403
    assert DownloadRequest.query.count() == 1


def test_the_admin_lists_show_consent_and_ask_before_deleting(client, product, admin_user):
    _download(client, opt_in=True)
    _join(client)
    _admin(client)
    downloads = client.get(f"/admin/products/{product.id}/downloads").data.decode()
    assert "May email" in downloads
    assert 'data-confirm="Delete the sign-up for ada@example.com for good?' in downloads
    waitlist = client.get(f"/admin/products/{product.id}/waitlist").data.decode()
    assert ">No<" in waitlist.replace("\n", "").replace(" ", "") or "No</span>" in waitlist
    assert "Export CSV" in waitlist


@pytest.mark.parametrize("which", ["downloads", "waitlist"])
def test_exports_say_who_may_be_emailed_with_their_unsubscribe_link(client, product, admin_user, which):
    if which == "downloads":
        _download(client, opt_in=True)
    else:
        _join(client, opt_in=True)
    _admin(client)
    body = client.get(f"/admin/products/{product.id}/{which}.csv").data.decode()
    header, row = body.strip().splitlines()[:2]
    columns = dict(zip(header.split(","), row.split(",")))
    assert columns["may_email"] == "yes"
    assert email_from_token(columns["unsubscribe_url"].rsplit("/", 1)[1]) == EMAIL


# ---------------------------------------------------------------------
# Confirmations and legal text
# ---------------------------------------------------------------------

def test_no_template_relies_on_inline_handlers_the_csp_blocks():
    """script-src 'self' blocks onsubmit=...; those Delete buttons never asked."""
    root = os.path.join(os.path.dirname(__file__), "..", "app", "templates")
    offenders = [p for p in glob.glob(f"{root}/**/*.html", recursive=True)
                 if re.search(r"\son(?:submit|click)=", open(p, encoding="utf-8").read())]
    assert offenders == []


def test_admin_pages_load_the_confirm_script(client, admin_user):
    _admin(client)
    assert "js/admin-confirm.js" in client.get("/admin/products").data.decode()
    assert "data-confirm" in client.get("/static/js/admin-confirm.js").data.decode()


def test_the_policies_say_what_the_site_does(client):
    cookies = re.sub(r"\s+", " ", client.get("/cookies").data.decode())
    assert "We do not use analytics cookies." in cookies
    assert "We do not use marketing or advertising cookies" in cookies
    privacy = re.sub(r"\s+", " ", client.get("/privacy").data.decode())
    for phrase in ("Downloads and waitlists", "Legal bases", "deleted automatically one year",
                   "unsubscribe", "ico.org.uk", "Nigeria Data Protection Commission",
                   "deleted automatically after 180 days"):
        assert phrase in privacy, phrase
    assert "Analytics cookies are only active if you opt in" not in privacy


def test_the_cookie_banner_matches_the_policy(client):
    html = client.get("/").data.decode()
    assert "no analytics or" in html and "advertising cookies" in html
    assert "we may also use analytics cookies" not in html
