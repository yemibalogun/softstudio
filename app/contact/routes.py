import bleach
from flask import Blueprint, render_template, redirect, url_for, request

from app.extensions import db, limiter
from app.contact.forms import ProjectInquiryForm
from app.models import ProjectInquiry
from app import emails

bp = Blueprint("contact", __name__)


def _clean(text: str | None) -> str | None:
    """Strip any HTML from free-text fields before storage/display."""
    if text is None:
        return None
    return bleach.clean(text, tags=[], strip=True)


@bp.route("/", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def index():
    form = ProjectInquiryForm()

    if form.validate_on_submit():
        if form.website.data:
            # Honeypot tripped — silently pretend success, don't persist.
            return redirect(url_for("contact.success"))

        inquiry = ProjectInquiry()
        inquiry.name = _clean(form.name.data)
        inquiry.email = (form.email.data or "").strip().lower()
        inquiry.company = _clean(form.company.data)
        inquiry.phone = _clean(form.phone.data)
        inquiry.project_type = form.project_type.data
        inquiry.project_description = _clean(form.project_description.data)
        inquiry.current_process = _clean(form.current_process.data)
        inquiry.desired_outcome = _clean(form.desired_outcome.data)
        inquiry.budget_range = _clean(form.budget_range.data)
        inquiry.timeline = _clean(form.timeline.data)
        inquiry.referral_source = _clean(form.referral_source.data)
        # request.remote_addr is now the real client IP - ProxyFix (app/__init__.py)
        # parses the trusted X-Forwarded-For hop instead of us reading the raw header.
        inquiry.ip_address = request.remote_addr
        inquiry.user_agent = request.headers.get("User-Agent", "")[:255]

        db.session.add(inquiry)
        db.session.commit()

        emails.send_inquiry_admin_notification(inquiry)
        emails.send_inquiry_confirmation(inquiry)

        return redirect(url_for("contact.success"))

    return render_template("contact/index.html", form=form)


@bp.route("/success")
def success():
    return render_template("contact/success.html")
