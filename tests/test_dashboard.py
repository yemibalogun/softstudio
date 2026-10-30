"""The admin dashboard: tracking, error capture, metrics and renewals."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.analytics import record_error, record_page_view, visitor_hash
from app.extensions import db as _db
from app.models import (
    ErrorEvent, PageView, Product, ServicePayment, ServiceSubscription, WaitlistSubscriber,
)
from app.models.subscription import add_months
from tests.conftest import login


def _login_admin(client, admin_user):
    return login(client, "admin@example.com", "correcthorsebattery")


@pytest.fixture()
def product(db):
    item = Product(
        title="Flask Production MCP", slug="flask-production-mcp",
        short_description="Ship Flask apps without guesswork.",
        published=True, waitlist_enabled=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture()
def vpn(db):
    sub = ServiceSubscription(
        name="Mullvad VPN", vendor="Mullvad", category="vpn",
        amount=5, currency="EUR", cycle="monthly",
        next_due_on=date.today() + timedelta(days=7),
    )
    db.session.add(sub)
    db.session.commit()
    return sub


# =====================================================================
# Visit tracking
# =====================================================================

def test_a_public_page_is_recorded(client, product):
    client.get(f"/products/{product.slug}")
    view = PageView.query.one()
    assert view.path == f"/products/{product.slug}"
    assert view.product_id == product.id  # product pages are attributed
    assert view.source == "direct"
    assert view.device == "desktop"


def test_utm_source_becomes_the_traffic_source(client, product):
    client.get(f"/products/{product.slug}?utm_source=instagram")
    assert PageView.query.one().source == "instagram"


def test_admin_and_static_paths_are_not_tracked(client, admin_user):
    _login_admin(client, admin_user)
    client.get("/admin/")
    client.get("/static/css/tailwind.css")
    tracked = [v.path for v in PageView.query.all()]
    assert not any(p.startswith(("/admin", "/static")) for p in tracked)


def test_bots_are_not_counted(client, product):
    client.get(f"/products/{product.slug}", headers={"User-Agent": "Googlebot/2.1"})
    client.get(f"/products/{product.slug}", headers={"User-Agent": "python-requests/2.31"})
    assert PageView.query.count() == 0


def test_mobile_user_agent_is_classified(client, product):
    client.get(f"/products/{product.slug}", headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"
    })
    assert PageView.query.one().device == "mobile"


def test_post_requests_are_not_page_views(client, product):
    client.post(f"/products/{product.slug}/waitlist", data={"email": "a@example.com"})
    assert PageView.query.filter_by(path=f"/products/{product.slug}/waitlist").count() == 0


def test_no_raw_ip_is_stored_and_the_hash_rotates_daily(client, app, product):
    client.get(f"/products/{product.slug}")
    view = PageView.query.one()
    assert view.visitor_hash and len(view.visitor_hash) == 64

    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        today = visitor_hash()
        tomorrow = visitor_hash(date.today() + timedelta(days=1))
        assert today != tomorrow
        assert "203.0.113.9" not in today


def test_tracking_can_be_switched_off(client, app, product):
    app.config["ANALYTICS_ENABLED"] = False
    client.get(f"/products/{product.slug}")
    assert PageView.query.count() == 0


def test_a_tracking_failure_never_breaks_the_page(client, app, product, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database gone")

    monkeypatch.setattr(_db.session, "commit", boom)
    resp = client.get(f"/products/{product.slug}")
    assert resp.status_code == 200  # the page still renders


# =====================================================================
# Error capture
# =====================================================================

def test_a_404_is_recorded_as_a_broken_link(client):
    client.get("/products/this-does-not-exist")
    event = ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_NOT_FOUND).one()
    assert event.status_code == 404
    assert "/products/this-does-not-exist" in event.message


@pytest.mark.parametrize("url", [
    # The 18 that filled the production log on 2026-10-21, and their cousins.
    "/wp-admin/install.php", "/xmlrpc.php", "/wp-json/", "/wp-includes/js/jquery/jquery.js",
    "/wp/", "/wordpress/", "/blog/wp-json/", "/cms/wp-json/", "/media/system/js/core.js",
    "/cms/?rest_route=/", "/news/?rest_route=/", "/press/?rest_route=/",
    "/.env", "/.git/config", "/phpmyadmin/", "/administrator/", "/index.php", "/backup.sql",
])
def test_scanner_probes_are_not_logged_as_broken_links(client, url):
    """
    Bots sweep every site for WordPress, Joomla and leaked files. A 404 is
    the right answer and not a fault of ours; logging them buried real
    broken links, and they reopened every time the bots came back.
    """
    resp = client.get(url)
    assert resp.status_code == 404, "still a plain 404 for the bot"
    assert ErrorEvent.query.count() == 0


@pytest.mark.parametrize("url", [
    "/products/wp-guide",          # a slug that merely starts with wp-
    "/blog/cms",                   # a section path that happens to share a probe word
    "/blog/a-post-that-moved",
    "/products/nope?utm_source=instagram&utm_medium=dm",
])
def test_genuine_broken_links_are_still_logged(client, url):
    client.get(url)
    assert ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_NOT_FOUND).count() == 1


def test_repeated_errors_group_into_one_row(client):
    for _ in range(3):
        client.get("/blog/nope")
    event = ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_NOT_FOUND).one()
    assert event.occurrences == 3
    assert event.last_seen >= event.first_seen


def test_different_paths_are_different_problems(client):
    client.get("/blog/nope-one")
    client.get("/blog/nope-two")
    assert ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_NOT_FOUND).count() == 2


def test_a_server_error_keeps_its_traceback(client, app):
    # TESTING re-raises by default; let the error handler do its job instead.
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/boom-for-test")
    def boom():
        raise ValueError("exploded on purpose")

    client.get("/boom-for-test")
    event = ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_SERVER).one()
    assert "ValueError" in event.message
    assert "exploded on purpose" in event.detail
    assert "Traceback" in event.detail


def test_a_forbidden_page_is_a_security_event(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    client.get("/admin/")  # a signed-in non-admin
    assert ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_SECURITY).count() == 1


def test_a_failed_email_is_recorded_as_a_delivery_problem(app, monkeypatch):
    from app import emails

    def refuse(*args, **kwargs):
        raise RuntimeError("smtp refused")

    monkeypatch.setattr(emails.mail, "send", refuse)
    with app.test_request_context("/"):
        assert emails.send_email("Subject", ["a@example.com"], "welcome", user=None) is False

    event = ErrorEvent.query.filter_by(kind=ErrorEvent.KIND_DELIVERY).one()
    assert "failed to send" in event.message
    assert "a@example.com" not in (event.detail or "")  # recipients stay private


def test_resolving_an_error_and_reopening_it(client, admin_user, app):
    client.get("/blog/missing-page")
    event = ErrorEvent.query.one()
    _login_admin(client, admin_user)

    client.post(f"/admin/errors/{event.id}/resolve", follow_redirects=True)
    assert ErrorEvent.query.get(event.id).resolved is True

    # it happening again reopens it, because it clearly is not fixed
    client.get("/blog/missing-page")
    assert ErrorEvent.query.get(event.id).resolved is False


# =====================================================================
# Dashboard
# =====================================================================

def test_dashboard_requires_an_admin(client, user):
    assert client.get("/admin/").status_code == 302  # anonymous -> login
    login(client, "student@example.com", "correcthorsebattery")
    assert client.get("/admin/").status_code == 403
    assert client.get("/admin/dashboard.json").status_code == 403


def test_dashboard_renders_with_no_data_at_all(client, admin_user):
    _login_admin(client, admin_user)
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data


def test_dashboard_json_shape(client, admin_user, product):
    client.get(f"/products/{product.slug}")
    _login_admin(client, admin_user)

    data = client.get("/admin/dashboard.json").get_json()
    for key in ["range", "live", "totals", "series", "top_pages", "top_sources",
                "devices", "products", "emails", "recent_signups", "errors", "renewals"]:
        assert key in data
    assert data["totals"]["views"] >= 1
    assert data["totals"]["visitors"] >= 1
    assert data["series"], "the chart needs a zero-filled series"
    assert all("views" in point and "visitors" in point for point in data["series"])


def test_dashboard_counts_emails_from_every_funnel(client, admin_user, product, db):
    db.session.add(WaitlistSubscriber(product_id=product.id, email="w@example.com", source="instagram"))
    db.session.commit()

    _login_admin(client, admin_user)
    emails = client.get("/admin/dashboard.json").get_json()["emails"]
    assert emails["waitlist"] == 1
    assert emails["total"] >= 1
    assert emails["all_time"] >= 1


def test_most_viewed_products_are_ranked(client, admin_user, db, product):
    other = Product(title="Second", slug="second", short_description="x", published=True)
    db.session.add(other)
    db.session.commit()

    for _ in range(3):
        client.get(f"/products/{product.slug}")
    client.get(f"/products/{other.slug}")

    _login_admin(client, admin_user)
    rows = client.get("/admin/dashboard.json").get_json()["products"]
    assert rows[0]["slug"] == product.slug
    assert rows[0]["views"] == 3


def test_range_parameter_is_validated(client, admin_user):
    _login_admin(client, admin_user)
    assert client.get("/admin/dashboard.json?range=7d").get_json()["range"] == "7d"
    # anything unknown falls back instead of erroring
    assert client.get("/admin/dashboard.json?range=../etc").get_json()["range"] == "24h"


def test_json_is_serialisable_with_renewals_and_errors(client, admin_user, vpn):
    client.get("/blog/missing")
    _login_admin(client, admin_user)
    data = client.get("/admin/dashboard.json").get_json()
    assert data["renewals"]["due"][0]["name"] == "Mullvad VPN"
    assert isinstance(data["renewals"]["due"][0]["due_on"], str)  # dates as ISO strings
    assert data["errors"]["total"] >= 1


# =====================================================================
# Renewals
# =====================================================================

def test_add_months_clamps_to_short_months():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # leap year
    assert add_months(date(2026, 11, 30), 12) == date(2027, 11, 30)


def test_days_until_due_and_overdue(db):
    sub = ServiceSubscription(name="Domain", next_due_on=date.today() - timedelta(days=2))
    db.session.add(sub)
    db.session.commit()
    assert sub.days_until_due == -2
    assert sub.is_overdue is True


def test_monthly_and_yearly_cost_normalisation(db):
    yearly = ServiceSubscription(name="Domain", amount=120, cycle="yearly")
    monthly = ServiceSubscription(name="Mailbox", amount=10, cycle="monthly")
    one_off = ServiceSubscription(name="Logo", amount=400, cycle="one_off")
    db.session.add_all([yearly, monthly, one_off])
    db.session.commit()

    assert float(yearly.monthly_cost) == 10.0
    assert float(yearly.yearly_cost) == 120.0
    assert float(monthly.yearly_cost) == 120.0
    assert float(one_off.monthly_cost) == 0.0  # a one-off is not a running cost


def test_mark_paid_records_payment_and_rolls_the_date(client, admin_user, vpn):
    original_due = vpn.next_due_on
    _login_admin(client, admin_user)

    resp = client.post(f"/admin/renewals/{vpn.id}/paid", follow_redirects=True)
    assert resp.status_code == 200

    payment = ServicePayment.query.one()
    assert float(payment.amount) == 5.0
    assert vpn.last_paid_on == date.today()
    assert vpn.next_due_on == add_months(original_due, 1)
    assert vpn.reminder_stage_sent is None  # warnings start again for the new date


def test_mark_paid_catches_up_a_missed_cycle(client, admin_user, db):
    sub = ServiceSubscription(
        name="Old mailbox", amount=3, cycle="monthly",
        next_due_on=date.today() - timedelta(days=75),
    )
    db.session.add(sub)
    db.session.commit()

    _login_admin(client, admin_user)
    client.post(f"/admin/renewals/{sub.id}/paid", follow_redirects=True)
    assert sub.next_due_on > date.today()  # never leaves the date in the past


def test_a_one_off_has_nothing_further_due(client, admin_user, db):
    sub = ServiceSubscription(name="Audit", amount=200, cycle="one_off", next_due_on=date.today())
    db.session.add(sub)
    db.session.commit()

    _login_admin(client, admin_user)
    client.post(f"/admin/renewals/{sub.id}/paid", follow_redirects=True)
    assert sub.next_due_on is None


def test_renewal_crud_through_the_admin(client, admin_user):
    _login_admin(client, admin_user)

    client.post("/admin/renewals/new", data={
        "name": "Proton Mail", "vendor": "Proton", "category": "email",
        "amount": "48", "currency": "chf", "cycle": "yearly",
        "next_due_on": (date.today() + timedelta(days=30)).isoformat(),
        "auto_renew": "y", "is_active": "y",
    }, follow_redirects=True)

    sub = ServiceSubscription.query.filter_by(name="Proton Mail").one()
    assert sub.currency == "CHF"  # normalised
    assert sub.category == "email"

    client.post(f"/admin/renewals/{sub.id}/edit", data={
        "name": "Proton Mail", "category": "email", "amount": "60",
        "currency": "CHF", "cycle": "yearly",
        "next_due_on": sub.next_due_on.isoformat(), "is_active": "y",
    }, follow_redirects=True)
    assert float(ServiceSubscription.query.get(sub.id).amount) == 60.0

    client.post(f"/admin/renewals/{sub.id}/delete", follow_redirects=True)
    assert ServiceSubscription.query.count() == 0


def test_deleting_a_service_removes_its_payments(client, admin_user, vpn):
    _login_admin(client, admin_user)
    client.post(f"/admin/renewals/{vpn.id}/paid", follow_redirects=True)
    assert ServicePayment.query.count() == 1

    client.post(f"/admin/renewals/{vpn.id}/delete", follow_redirects=True)
    assert ServicePayment.query.count() == 0


def test_spend_totals_group_by_currency(client, admin_user, db, vpn):
    db.session.add(ServiceSubscription(name="VPS", amount=24, currency="USD", cycle="monthly"))
    db.session.commit()

    _login_admin(client, admin_user)
    totals = client.get("/admin/dashboard.json").get_json()["renewals"]
    assert totals["monthly_by_currency"]["EUR"] == 5.0
    assert totals["monthly_by_currency"]["USD"] == 24.0
    assert totals["yearly_by_currency"]["USD"] == 288.0


# =====================================================================
# Reminder emails
# =====================================================================

def _run_reminders(app):
    runner = app.test_cli_runner()
    return runner.invoke(args=["send-renewal-reminders"])


def test_reminder_is_sent_once_per_stage(app, db, monkeypatch):
    sub = ServiceSubscription(
        name="Mullvad VPN", amount=5, cycle="monthly",
        next_due_on=date.today() + timedelta(days=7),
    )
    db.session.add(sub)
    db.session.commit()

    sent = []
    from app import emails
    monkeypatch.setattr(emails, "send_renewal_reminder",
                        lambda subscription, days_left: sent.append(days_left) or True)

    _run_reminders(app)
    assert sent == [7]
    assert sub.reminder_stage_sent == 7

    _run_reminders(app)  # running again the same day must not re-send
    assert sent == [7]


def test_a_closer_stage_sends_a_fresh_reminder(app, db, monkeypatch):
    sub = ServiceSubscription(
        name="Domain", amount=12, cycle="yearly",
        next_due_on=date.today() + timedelta(days=1), reminder_stage_sent=14,
    )
    db.session.add(sub)
    db.session.commit()

    sent = []
    from app import emails
    monkeypatch.setattr(emails, "send_renewal_reminder",
                        lambda subscription, days_left: sent.append(days_left) or True)

    _run_reminders(app)
    assert sent == [1]
    assert sub.reminder_stage_sent == 1


def test_distant_and_inactive_services_are_left_alone(app, db, monkeypatch):
    db.session.add_all([
        ServiceSubscription(name="Far away", next_due_on=date.today() + timedelta(days=90)),
        ServiceSubscription(name="Cancelled", is_active=False,
                            next_due_on=date.today() + timedelta(days=1)),
    ])
    db.session.commit()

    sent = []
    from app import emails
    monkeypatch.setattr(emails, "send_renewal_reminder",
                        lambda subscription, days_left: sent.append(days_left) or True)

    _run_reminders(app)
    assert sent == []


def test_overdue_service_is_nudged_once(app, db, monkeypatch):
    sub = ServiceSubscription(name="Lapsed", next_due_on=date.today() - timedelta(days=3))
    db.session.add(sub)
    db.session.commit()

    sent = []
    from app import emails
    monkeypatch.setattr(emails, "send_renewal_reminder",
                        lambda subscription, days_left: sent.append(days_left) or True)

    _run_reminders(app)
    assert sent == [-3]
    _run_reminders(app)
    assert sent == [-3]


def test_the_reminder_email_renders(app, db):
    """The real template, not a stub — a broken template would be silent."""
    from app import emails

    sub = ServiceSubscription(
        name="Mullvad VPN", vendor="Mullvad", amount=5, currency="EUR", cycle="monthly",
        next_due_on=date.today() + timedelta(days=7), auto_renew=False,
        manage_url="https://mullvad.net/account",
    )
    db.session.add(sub)
    db.session.commit()

    with app.app_context():
        assert emails.send_renewal_reminder(sub, 7) is True  # MAIL_SUPPRESS_SEND in testing


# =====================================================================
# Retention
# =====================================================================

def test_pruning_drops_old_views_and_keeps_recent_ones(app, db):
    old = PageView(path="/old", visitor_hash="a" * 64,
                   created_at=datetime.now(timezone.utc) - timedelta(days=200))
    recent = PageView(path="/new", visitor_hash="b" * 64,
                      created_at=datetime.now(timezone.utc) - timedelta(days=2))
    db.session.add_all([old, recent])
    db.session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["prune-analytics", "--days", "180"])
    assert result.exit_code == 0

    remaining = [v.path for v in PageView.query.all()]
    assert remaining == ["/new"]
