from app.extensions import db
from app.payments import services
from tests.conftest import login


def _captured(app):
    """Flask-Mail's testing hook: records outgoing messages instead of
    sending them, without needing a real SMTP server."""
    mail = app.extensions["mail"]
    return mail.record_messages()


# =====================================================================
# Auth emails
# =====================================================================

def test_register_sends_welcome_and_verification_emails(app, client, db, student_role):
    with _captured(app) as outbox:
        client.post(
            "/auth/register",
            data={
                "full_name": "New User",
                "email": "new@example.com",
                "password": "correcthorsebattery",
                "confirm_password": "correcthorsebattery",
            },
            follow_redirects=True,
        )

    subjects = [m.subject for m in outbox]
    recipients = [m.recipients for m in outbox]
    assert any("Welcome" in s for s in subjects)
    assert any("Verify" in s for s in subjects)
    assert all(["new@example.com"] == r for r in recipients)


def test_forgot_password_sends_reset_email_for_existing_user(app, client, user):
    with _captured(app) as outbox:
        client.post(
            "/auth/forgot-password", data={"email": "student@example.com"}, follow_redirects=True
        )
    assert len(outbox) == 1
    assert "Reset" in outbox[0].subject
    assert outbox[0].recipients == ["student@example.com"]


def test_forgot_password_sends_nothing_for_unknown_email(app, client):
    """No email should be sent for a non-existent account — and, just as
    importantly, the HTTP response must not reveal that difference."""
    with _captured(app) as outbox:
        resp = client.post(
            "/auth/forgot-password", data={"email": "nobody@example.com"}, follow_redirects=True
        )
    assert len(outbox) == 0
    assert b"a reset link has been sent" in resp.data.lower()


# =====================================================================
# Contact / inquiry emails
# =====================================================================

def test_valid_inquiry_sends_confirmation_and_admin_notification(app, client):
    with _captured(app) as outbox:
        client.post(
            "/contact/",
            data={
                "name": "Jane Doe",
                "email": "jane@example.com",
                "project_type": "web_app",
                "project_description": "Need a dashboard for tracking inventory.",
                "website": "",
            },
            follow_redirects=True,
        )

    assert len(outbox) == 2
    to_user = [m for m in outbox if m.recipients == ["jane@example.com"]]
    to_admin = [m for m in outbox if m.recipients == [app.config["ADMIN_EMAIL"]]]
    assert len(to_user) == 1
    assert len(to_admin) == 1
    assert "received your project inquiry" in to_user[0].subject.lower()
    assert "new project inquiry" in to_admin[0].subject.lower()


def test_honeypot_submission_sends_no_email(app, client):
    with _captured(app) as outbox:
        client.post(
            "/contact/",
            data={
                "name": "Bot",
                "email": "bot@spam.com",
                "project_type": "web_app",
                "project_description": "spam",
                "website": "http://spam.example.com",
            },
            follow_redirects=True,
        )
    assert len(outbox) == 0


# =====================================================================
# Payment / enrollment / refund emails
# =====================================================================

def test_successful_payment_sends_confirmation_and_enrollment_emails(app, user, course_with_lessons):
    purchase = services.create_purchase(user, course_with_lessons)
    purchase.amount = 15000
    db.session.commit()

    result = services.VerificationResult(
        success=True,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={},
    )

    with _captured(app) as outbox:
        services.process_verified_payment(purchase, result, "flutterwave")

    subjects = [m.subject for m in outbox]
    assert any("enrolled" in s.lower() for s in subjects)
    assert any("payment confirmed" in s.lower() for s in subjects)
    assert all(m.recipients == [user.email] for m in outbox)


def test_failed_payment_sends_no_confirmation_email(app, user, course_with_lessons):
    purchase = services.create_purchase(user, course_with_lessons)
    result = services.VerificationResult(
        success=False,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={},
    )

    with _captured(app) as outbox:
        services.process_verified_payment(purchase, result, "flutterwave")

    assert len(outbox) == 0


def test_duplicate_webhook_does_not_resend_confirmation(app, user, course_with_lessons):
    """Idempotent processing must also be idempotent on side effects —
    a retried webhook must not spam the user with duplicate emails."""
    purchase = services.create_purchase(user, course_with_lessons)
    result = services.VerificationResult(
        success=True,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={},
    )

    services.process_verified_payment(purchase, result, "flutterwave")  # first call, real send

    with _captured(app) as outbox:
        services.process_verified_payment(purchase, result, "flutterwave")  # retry
    assert len(outbox) == 0


def test_refund_sends_refund_email(app, user, course_with_lessons):
    purchase = services.create_purchase(user, course_with_lessons)
    result = services.VerificationResult(
        success=True,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={},
    )
    payment = services.process_verified_payment(purchase, result, "flutterwave")

    with _captured(app) as outbox:
        services.revoke_enrollment_for_refund(payment)

    assert len(outbox) == 1
    assert "refund" in outbox[0].subject.lower()
    assert outbox[0].recipients == [user.email]


# =====================================================================
# Security notification emails
# =====================================================================

def test_password_change_sends_security_notification(app, client, user):
    login(client, "student@example.com", "correcthorsebattery")
    with _captured(app) as outbox:
        client.post(
            "/account/change-password",
            data={
                "current_password": "correcthorsebattery",
                "new_password": "anothersecurepassword",
                "confirm_password": "anothersecurepassword",
            },
            follow_redirects=True,
        )
    assert len(outbox) == 1
    assert "password changed" in outbox[0].subject.lower()
    assert outbox[0].recipients == [user.email]


def test_session_revocation_sends_security_notification(app, client, user, db):
    from app.models import UserSession

    session_record = UserSession(user_id=user.id, user_agent="Test Browser")
    db.session.add(session_record)
    db.session.commit()

    login(client, "student@example.com", "correcthorsebattery")
    with _captured(app) as outbox:
        client.post(f"/account/sessions/{session_record.id}/revoke", follow_redirects=True)

    assert len(outbox) == 1
    assert "session revoked" in outbox[0].subject.lower()


# =====================================================================
# Failure resilience
# =====================================================================

def test_email_send_failure_does_not_break_registration(app, client, db, student_role, monkeypatch):
    """A broken SMTP connection must never turn into a 500 for the user
    completing an unrelated action — send_email() must fail closed."""
    from app import emails

    def _boom(msg):
        raise ConnectionRefusedError("SMTP unreachable")

    monkeypatch.setattr(emails.mail, "send", _boom)

    resp = client.post(
        "/auth/register",
        data={
            "full_name": "Resilient User",
            "email": "resilient@example.com",
            "password": "correcthorsebattery",
            "confirm_password": "correcthorsebattery",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    from app.models import User

    assert User.query.filter_by(email="resilient@example.com").first() is not None
