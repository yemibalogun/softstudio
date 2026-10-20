"""
First-party analytics: what visitors did, and what went wrong.

Both tables are written from request hooks (app/analytics.py) and read by
the admin dashboard. Nothing here identifies a person: visitors are counted
through a salted hash that changes every day, and no raw IP is stored.
"""
from app.extensions import db
from app.models import utcnow


class PageView(db.Model):
    """One rendered page. Bots, assets and admin pages are never recorded."""

    __tablename__ = "page_views"

    id = db.Column(db.Integer, primary_key=True)

    path = db.Column(db.String(255), nullable=False, index=True)
    status_code = db.Column(db.SmallInteger, nullable=False, default=200)

    # Where it came from: utm_source when present, else the referring host,
    # else "direct". Same vocabulary as the waitlist/download attribution.
    source = db.Column(db.String(60), index=True)
    referrer_host = db.Column(db.String(120))

    device = db.Column(db.String(10))  # desktop | mobile | tablet
    is_authenticated = db.Column(db.Boolean, default=False, nullable=False)

    # Salted daily hash of IP + user agent. Lets us count unique visitors per
    # day without keeping anything that identifies them, and it stops being
    # linkable to a person once the day's salt rolls over.
    visitor_hash = db.Column(db.String(64), index=True)

    # Set when the page is a product page, so "most viewed products" is a
    # simple grouped count instead of parsing paths.
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), index=True
    )

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    product = db.relationship("Product")

    def __repr__(self):
        return f"<PageView {self.path}>"


class ErrorEvent(db.Model):
    """
    Something that went wrong, grouped by fingerprint.

    One recurring bug is one row with a growing count, not a thousand rows,
    so the dashboard shows "this is still happening" instead of a flood.
    """

    KIND_SERVER = "server_error"   # unhandled 500s, with traceback
    KIND_NOT_FOUND = "not_found"   # broken links, with referrer
    KIND_SECURITY = "security"     # 403s, rate limits, failed admin logins
    KIND_DELIVERY = "delivery"     # emails that failed, downloads that broke
    KINDS = (KIND_SERVER, KIND_NOT_FOUND, KIND_SECURITY, KIND_DELIVERY)

    __tablename__ = "error_events"

    id = db.Column(db.Integer, primary_key=True)

    kind = db.Column(db.String(20), nullable=False, index=True)
    status_code = db.Column(db.SmallInteger)

    path = db.Column(db.String(255))
    method = db.Column(db.String(10))
    message = db.Column(db.String(300), nullable=False)
    detail = db.Column(db.Text)  # traceback, or context for delivery failures

    # Identity of the problem, not of the person: kind + path + message head.
    fingerprint = db.Column(db.String(64), unique=True, nullable=False, index=True)
    occurrences = db.Column(db.Integer, default=1, nullable=False)

    first_seen = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    last_referrer = db.Column(db.String(255))
    resolved = db.Column(db.Boolean, default=False, nullable=False, index=True)

    def __repr__(self):
        return f"<ErrorEvent {self.kind} {self.message[:40]}>"
