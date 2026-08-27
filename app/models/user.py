from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.models import TimestampMixin, gen_uuid


class Role(db.Model, TimestampMixin):
    """Coarse-grained role for authorization (student, admin, etc.)."""

    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)  # e.g. 'student', 'admin'
    description = db.Column(db.String(255))

    users = db.relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"


class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=gen_uuid, index=True)

    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verified_at = db.Column(db.DateTime(timezone=True))

    # Nullable so OAuth-only accounts (no local password) are supported.
    password_hash = db.Column(db.String(255), nullable=True)

    full_name = db.Column(db.String(120), nullable=False)
    avatar_url = db.Column(db.String(512))

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    role = db.relationship("Role", back_populates="users")

    last_login_at = db.Column(db.DateTime(timezone=True))

    oauth_identities = db.relationship(
        "OAuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    sessions = db.relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    enrollments = db.relationship(
        "Enrollment", back_populates="user", cascade="all, delete-orphan"
    )
    purchases = db.relationship(
        "Purchase", back_populates="user", cascade="all, delete-orphan"
    )
    course_reviews = db.relationship(
        "CourseReview", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self) -> bool:
        return bool(self.role and self.role.name == "admin")

    # Flask-Login expects get_id(); default UserMixin uses primary key,
    # which is fine, but we override to use the public_id so raw
    # database IDs are never exposed via session cookies.
    def get_id(self):
        return self.public_id

    def __repr__(self):
        return f"<User {self.email}>"
