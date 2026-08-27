from app.extensions import db
from app.models import TimestampMixin


class OAuthIdentity(db.Model, TimestampMixin):
    """
    Links a local User to an external OAuth provider identity.

    A given (provider, provider_user_id) pair is unique across the whole
    system, and a given user may only link one identity per provider.
    Account linking to an *existing* local account (e.g. same verified
    email) must go through an explicit, confirmed linking flow in
    app/auth/services.py rather than being done silently on login.
    """

    __tablename__ = "oauth_identities"
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_user_id", name="uq_provider_identity"),
        db.UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    provider = db.Column(db.String(32), nullable=False)  # 'google' | 'github'
    provider_user_id = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))

    user = db.relationship("User", back_populates="oauth_identities")

    def __repr__(self):
        return f"<OAuthIdentity {self.provider}:{self.provider_user_id}>"
