from app.extensions import db
from app.models import TimestampMixin, gen_uuid


class UserSession(db.Model, TimestampMixin):
    """
    A server-tracked record of an active login session, shown on the
    account Security page so users can review and revoke sessions.

    This is metadata about the session (for display/revocation), not the
    Flask session cookie itself. `session_token` is a random identifier
    stored in the signed session cookie; revoking a UserSession here
    should be checked on each request to reject stale cookies.
    """

    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    session_token = db.Column(db.String(64), unique=True, nullable=False, default=gen_uuid, index=True)

    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))

    last_active_at = db.Column(db.DateTime(timezone=True))
    revoked_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="sessions")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __repr__(self):
        return f"<UserSession user={self.user_id} active={self.is_active}>"
