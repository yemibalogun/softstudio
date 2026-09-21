"""
SQLAlchemy models package.

Importing this package registers all models with SQLAlchemy's metadata,
which Flask-Migrate needs in order to autogenerate migrations correctly.
"""
import uuid
from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


def gen_uuid():
    return str(uuid.uuid4())


class TimestampMixin:
    """Adds created_at / updated_at columns to any model."""

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# Import order matters only for readability here; SQLAlchemy resolves
# relationships lazily via string references, so circular references
# between modules (e.g. Course <-> Enrollment) are fine.
from app.models.user import User, Role  # noqa: E402,F401
from app.models.oauth import OAuthIdentity  # noqa: E402,F401
from app.models.session import UserSession  # noqa: E402,F401
from app.models.project import Project, ProjectImage, Technology  # noqa: E402,F401
from app.models.service import Service  # noqa: E402,F401
from app.models.course import (  # noqa: E402,F401
    Course,
    CourseCategory,
    CourseSection,
    Lesson,
    LessonResource,
    CourseReview,
)
from app.models.enrollment import Enrollment, LessonProgress  # noqa: E402,F401
from app.models.payment import Purchase, Payment, Coupon  # noqa: E402,F401
from app.models.inquiry import ProjectInquiry  # noqa: E402,F401
from app.models.blog import BlogPost, BlogCategory, BlogTag  # noqa: E402,F401
from app.models.product import Product, WaitlistSubscriber  # noqa: E402,F401
from app.models.testimonial import Testimonial  # noqa: E402,F401
from app.models.consent import CookieConsent  # noqa: E402,F401

__all__ = [
    "User", "Role", "OAuthIdentity", "UserSession",
    "Project", "ProjectImage", "Technology", "Service",
    "Course", "CourseCategory", "CourseSection", "Lesson", "LessonResource", "CourseReview",
    "Enrollment", "LessonProgress",
    "Purchase", "Payment", "Coupon",
    "ProjectInquiry",
    "BlogPost", "BlogCategory", "BlogTag",
    "Product", "WaitlistSubscriber",
    "Testimonial", "CookieConsent",
]
