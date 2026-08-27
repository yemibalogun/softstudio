from app.extensions import db
from app.models import TimestampMixin, gen_uuid


class CookieConsent(db.Model, TimestampMixin):
    """
    Server-side record of a visitor's cookie consent choices, keyed by
    an anonymous consent_id (also mirrored into a signed cookie so
    anonymous visitors can be matched to their prior choice). When a
    user is authenticated, user_id is also set so their preference
    follows their account.
    """

    __tablename__ = "cookie_consents"

    id = db.Column(db.Integer, primary_key=True)
    consent_id = db.Column(db.String(36), unique=True, nullable=False, default=gen_uuid, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    necessary = db.Column(db.Boolean, default=True, nullable=False)  # always true
    analytics = db.Column(db.Boolean, default=False, nullable=False)
    marketing = db.Column(db.Boolean, default=False, nullable=False)

    ip_address = db.Column(db.String(64))

    user = db.relationship("User")
