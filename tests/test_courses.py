from app.extensions import db
from app.models import Enrollment
from tests.conftest import login


def test_course_listing(client, course_with_lessons):
    resp = client.get("/courses/")
    assert resp.status_code == 200
    assert b"Flask Production Applications" in resp.data


def test_course_detail(client, course_with_lessons):
    resp = client.get(f"/courses/{course_with_lessons.slug}")
    assert resp.status_code == 200


def test_free_preview_lesson_accessible_when_logged_in(client, user, course_with_lessons):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get(f"/dashboard/courses/{course_with_lessons.slug}/lessons/introduction")
    assert resp.status_code == 200
    assert b"Introduction" in resp.data


def test_free_preview_lesson_requires_login(client, course_with_lessons):
    resp = client.get(
        f"/dashboard/courses/{course_with_lessons.slug}/lessons/introduction",
        follow_redirects=False,
    )
    # login_required decorator should redirect unauthenticated visitors.
    assert resp.status_code in (301, 302)


def test_paid_lesson_blocked_without_enrollment(client, user, course_with_lessons):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get(
        f"/dashboard/courses/{course_with_lessons.slug}/lessons/advanced-auth",
        follow_redirects=False,
    )
    # Must redirect away from the lesson page rather than rendering the
    # protected video/content. (Lesson *titles* are not secret and may
    # legitimately still appear in a course's public curriculum listing —
    # only the lesson content itself must be gated.)
    assert resp.status_code in (301, 302)
    assert "/courses/" in resp.headers["Location"]


def test_paid_lesson_accessible_with_active_enrollment(client, user, course_with_lessons):
    enrollment = Enrollment(
        user_id=user.id, course_id=course_with_lessons.id, status="active"
    )
    db.session.add(enrollment)
    db.session.commit()

    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get(f"/dashboard/courses/{course_with_lessons.slug}/lessons/advanced-auth")
    assert resp.status_code == 200
    assert b"Advanced Auth" in resp.data


def test_paid_lesson_blocked_after_enrollment_revoked(client, user, course_with_lessons):
    enrollment = Enrollment(
        user_id=user.id, course_id=course_with_lessons.id, status="revoked"
    )
    db.session.add(enrollment)
    db.session.commit()

    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get(
        f"/dashboard/courses/{course_with_lessons.slug}/lessons/advanced-auth",
        follow_redirects=True,
    )
    assert b"Enroll in this course" in resp.data
