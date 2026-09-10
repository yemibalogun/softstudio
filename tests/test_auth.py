import pytest

from app.models import User
from app.models.oauth import OAuthIdentity
from app.auth import services
from tests.conftest import login


def test_register_creates_user(client, db, student_role):
    resp = client.post(
        "/auth/register",
        data={
            "full_name": "New User",
            "email": "new@example.com",
            "password": "correcthorsebattery",
            "confirm_password": "correcthorsebattery",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    user = User.query.filter_by(email="new@example.com").first()
    assert user is not None
    assert user.check_password("correcthorsebattery")
    # Password must never be stored in plaintext.
    assert user.password_hash != "correcthorsebattery"


def test_register_rejects_duplicate_email(client, user):
    resp = client.post(
        "/auth/register",
        data={
            "full_name": "Dupe",
            "email": user.email,
            "password": "correcthorsebattery",
            "confirm_password": "correcthorsebattery",
        },
        follow_redirects=True,
    )
    assert b"already exists" in resp.data


def test_login_success(client, user):
    resp = login(client, "student@example.com", "correcthorsebattery")
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert "_user_id" in sess


def test_login_wrong_password_fails(client, user):
    resp = login(client, "student@example.com", "wrong-password")
    assert b"Invalid email or password" in resp.data
    with client.session_transaction() as sess:
        assert "_user_id" not in sess


def test_logout_clears_session(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    client.get("/auth/logout")
    with client.session_transaction() as sess:
        assert "_user_id" not in sess


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard/", follow_redirects=False)
    # Flask-Login's login_required must redirect unauthenticated visitors
    # to the login page rather than rendering dashboard content.
    assert resp.status_code in (301, 302)
    assert "/auth/login" in resp.headers["Location"]


# --- OAuth account resolution -------------------------------------------------

def test_oauth_adopts_unverified_local_account(app, db, student_role):
    """A half-finished local registration (never email-verified) must be
    adopted by an OAuth login for the same address, not collide on the
    unique email index (regression: IntegrityError on ix_users_email)."""
    stale = User(email="yemi@example.com", full_name="", role=student_role, email_verified=False)
    stale.set_password("some-password-they-set-then-abandoned")
    db.session.add(stale)
    db.session.commit()
    stale_id = stale.id

    user = services.resolve_oauth_login(
        "github", "gh-12345", "yemi@example.com", "Yemi Balogun", "https://avatars/x.png"
    )

    assert user.id == stale_id                     # same row, adopted
    assert user.email_verified is True
    assert user.password_hash is None              # pre-set password neutralised
    assert user.full_name == "Yemi Balogun"        # blank field backfilled
    assert OAuthIdentity.query.filter_by(user_id=stale_id, provider="github").count() == 1
    assert User.query.filter_by(email="yemi@example.com").count() == 1


def test_oauth_verified_local_account_requires_linking(app, db, user):
    """An already-verified account is never silently taken over."""
    with pytest.raises(services.AccountLinkingRequired):
        services.resolve_oauth_login(
            "google", "goog-1", user.email, "Someone Else", None
        )


def test_oauth_creates_fresh_account_when_no_match(app, db, student_role):
    user = services.resolve_oauth_login(
        "github", "gh-999", "brand-new@example.com", "Brand New", None
    )
    assert user.id is not None
    assert user.email == "brand-new@example.com"
    assert user.email_verified is True
    assert OAuthIdentity.query.filter_by(user_id=user.id, provider="github").count() == 1


def test_oauth_existing_identity_logs_in_directly(app, db, student_role):
    first = services.resolve_oauth_login("github", "gh-777", "repeat@example.com", "Repeat", None)
    again = services.resolve_oauth_login("github", "gh-777", "repeat@example.com", "Repeat", None)
    assert first.id == again.id
    assert User.query.filter_by(email="repeat@example.com").count() == 1
