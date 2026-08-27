import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SITE_URL", "http://localhost:8000")
os.environ.setdefault("WTF_CSRF_ENABLED", "false")
# Falls back to local SQLite if no TEST_DATABASE_URL/DATABASE_URL is
# configured, so the suite is runnable without Postgres for quick local
# iteration. CI (see .github/workflows/ci.yml) always runs against a
# real Postgres service container, which is what the brief requires.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TEST_DATABASE_URL", os.environ["DATABASE_URL"])

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.models import Role, User, Course, CourseCategory, CourseSection, Lesson  # noqa: E402
from app.auth.services import get_or_create_default_role  # noqa: E402


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def admin_role(db):
    role = Role(name="admin", description="Full administrative access")
    db.session.add(role)
    db.session.commit()
    return role


@pytest.fixture()
def student_role(db):
    return get_or_create_default_role("student")


@pytest.fixture()
def user(db, student_role):
    u = User(email="student@example.com", full_name="Student User", role=student_role, email_verified=True)
    u.set_password("correcthorsebattery")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def admin_user(db, admin_role):
    u = User(email="admin@example.com", full_name="Admin User", role=admin_role, email_verified=True)
    u.set_password("correcthorsebattery")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def course_with_lessons(db):
    category = CourseCategory(name="Flask", slug="flask")
    db.session.add(category)
    db.session.flush()

    course = Course(
        title="Flask Production Applications",
        slug="flask-production-applications",
        short_description="Build and ship real-world Flask apps.",
        price=15000,
        currency="NGN",
        published=True,
        category_id=category.id,
    )
    db.session.add(course)
    db.session.flush()

    section = CourseSection(course_id=course.id, title="Getting Started", display_order=1)
    db.session.add(section)
    db.session.flush()

    free_lesson = Lesson(
        section_id=section.id, title="Introduction", slug="introduction",
        is_free_preview=True, display_order=1,
    )
    paid_lesson = Lesson(
        section_id=section.id, title="Advanced Auth", slug="advanced-auth",
        is_free_preview=False, display_order=2,
    )
    db.session.add_all([free_lesson, paid_lesson])
    db.session.commit()
    return course


def login(client, email, password):
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)
