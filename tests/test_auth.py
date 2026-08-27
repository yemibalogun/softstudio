from app.models import User
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
