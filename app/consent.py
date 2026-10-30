"""
Marketing email consent for download and waitlist sign-ups.

The rules the privacy policy promises, in one place:

* Consent is given only by ticking the optional, unticked box on a form,
  and never as a condition of the download or the waitlist. Signing up
  again without ticking it does not withdraw consent already given.
* Every email to a sign-up carries an unsubscribe link. Using it withdraws
  consent for that address on every product at once.
* The link is a signed token of the email address, so it needs no database
  lookup to verify and cannot be forged; it does not expire, because an
  unsubscribe link must keep working for as long as the email exists.
* Sign-ups that never opted in are removed a year after they were made
  (prune_leads, run weekly with the analytics clean-up).
"""
from datetime import timedelta

from flask import current_app, url_for
from itsdangerous import BadSignature, URLSafeSerializer

from app.extensions import db
from app.models import DownloadRequest, WaitlistSubscriber, utcnow

_SALT = "marketing-unsubscribe"
LEAD_MODELS = (DownloadRequest, WaitlistSubscriber)


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def unsubscribe_token(email: str) -> str:
    return _serializer().dumps((email or "").strip().lower())


def email_from_token(token: str) -> str | None:
    try:
        email = _serializer().loads(token)
    except BadSignature:
        return None
    return email if isinstance(email, str) and "@" in email else None


def unsubscribe_url(email: str) -> str:
    from app.seo import site_base_url
    return f"{site_base_url()}{url_for('consent.unsubscribe', token=unsubscribe_token(email))}"


def record_opt_in(lead, opted_in: bool) -> None:
    """Called on every sign-up. Only a ticked box changes anything."""
    if not opted_in:
        return
    lead.marketing_consent = True
    lead.consent_at = utcnow()
    lead.unsubscribed_at = None


def unsubscribe(email: str) -> int:
    """Withdraw consent for this address everywhere. Returns sign-ups affected."""
    email = (email or "").strip().lower()
    now = utcnow()
    affected = 0
    for model in LEAD_MODELS:
        for lead in model.query.filter_by(email=email).all():
            lead.marketing_consent = False
            lead.unsubscribed_at = lead.unsubscribed_at or now
            affected += 1
    db.session.commit()
    return affected


def prune_leads(older_than_days: int = 365) -> int:
    """
    Delete sign-ups that never opted in to marketing email, once they are
    older than the retention period. Opted-in sign-ups stay until the person
    unsubscribes and the period passes, or asks for deletion.
    """
    cutoff = utcnow() - timedelta(days=older_than_days)
    removed = 0
    for model in LEAD_MODELS:
        removed += model.query.filter(
            model.marketing_consent.is_(False), model.created_at < cutoff
        ).delete(synchronize_session=False)
    db.session.commit()
    return removed
