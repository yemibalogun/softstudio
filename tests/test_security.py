import pytest

from tests.conftest import login


@pytest.fixture()
def csrf_client(app):
    """A client with CSRF protection explicitly enabled, overriding the
    test-suite-wide default, to verify the protection actually works."""
    app.config["WTF_CSRF_ENABLED"] = True
    return app.test_client()


def test_csrf_blocks_post_without_token(csrf_client):
    resp = csrf_client.post(
        "/contact/",
        data={
            "name": "Jane",
            "email": "jane@example.com",
            "project_type": "web_app",
            "project_description": "test",
        },
    )
    assert resp.status_code == 400


def test_csrf_allows_post_with_valid_token(csrf_client):
    get_resp = csrf_client.get("/contact/")
    import re

    match = re.search(r'name="csrf_token".*?value="([^"]+)"', get_resp.get_data(as_text=True))
    assert match, "CSRF token should be present in rendered form"
    token = match.group(1)

    resp = csrf_client.post(
        "/contact/",
        data={
            "csrf_token": token,
            "name": "Jane",
            "email": "jane@example.com",
            "project_type": "web_app",
            "project_description": "test",
            "website": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200


def test_admin_dashboard_blocks_anonymous_user(client):
    resp = client.get("/admin/", follow_redirects=False)
    # login_required kicks in first for anonymous users.
    assert resp.status_code in (301, 302)


def test_admin_dashboard_blocks_non_admin_user(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get("/admin/")
    assert resp.status_code == 403


def test_admin_dashboard_allows_admin_user(client, admin_user):
    login(client, "admin@example.com", "correcthorsebattery")
    resp = client.get("/admin/")
    assert resp.status_code == 200


def test_admin_inquiries_blocks_non_admin(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get("/admin/inquiries")
    assert resp.status_code == 403


def test_protected_lesson_resource_blocks_non_enrolled_user(client, user, course_with_lessons):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get(
        f"/dashboard/courses/{course_with_lessons.slug}/lessons/advanced-auth/resources/1"
    )
    # Either 403 (found lesson, denied access) or 404 (no resource seeded)
    # — never a 200, since the user isn't enrolled.
    assert resp.status_code in (403, 404)
