"""
Transactional email service.

Every email has a matching HTML template and a plain-text fallback
(templates/emails/<name>.html + <name>.txt), per the project brief's
requirement for HTML emails with plain-text fallbacks.

Sending failures are logged, not raised — a broken SMTP connection
should never turn into a 500 for the user completing an unrelated
action (registering, submitting an inquiry, etc.). Callers that need
to guarantee delivery (e.g. a dedicated "resend verification" flow)
can check the return value.
"""
from collections.abc import Sequence

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail


def send_email(
    subject: str,
    recipients: Sequence[str | tuple[str, str]],
    template_base: str,
    headers: dict | None = None,
    **context,
) -> bool:
    context.setdefault("site_name", current_app.config["SITE_NAME"])
    context.setdefault("site_url", current_app.config["SITE_URL"])

    try:
        html_body = render_template(f"emails/{template_base}.html", **context)
        text_body = render_template(f"emails/{template_base}.txt", **context)
    except Exception as exc:
        current_app.logger.exception("Failed to render email template '%s'", template_base)
        _note_delivery_failure(template_base, recipients, exc)
        return False

    msg = Message()
    msg.subject = subject
    msg.recipients = list(recipients)
    msg.html = html_body
    msg.body = text_body
    msg.sender = current_app.config["MAIL_DEFAULT_SENDER"]
    if headers:
        msg.extra_headers = dict(headers)

    try:
        mail.send(msg)
        return True
    except Exception as exc:
        current_app.logger.exception("Failed to send email '%s' to %s", template_base, recipients)
        _note_delivery_failure(template_base, recipients, exc)
        return False


def _note_delivery_failure(template_base: str, recipients, exc: Exception) -> None:
    """
    Surface the failure on the admin dashboard as well as in the log, so a
    silently broken mailbox shows up instead of only costing a lead.

    The recipient address is not stored on the error row — the dashboard
    needs to know that sending broke, not who it was for.
    """
    from app.analytics import record_delivery_failure

    record_delivery_failure(
        f"Email '{template_base}' failed to send",
        detail=f"{type(exc).__name__}: {exc} (recipients: {len(list(recipients))})",
    )


def send_welcome_email(user) -> bool:
    return send_email(
        subject=f"Welcome to {current_app.config['SITE_NAME']}",
        recipients=[user.email],
        template_base="welcome",
        user=user,
    )


def send_verification_email(user, token: str) -> bool:
    from flask import url_for

    verify_url = url_for("auth.verify_email", token=token, _external=True)
    return send_email(
        subject="Verify your email address",
        recipients=[user.email],
        template_base="verify_email",
        user=user,
        verify_url=verify_url,
    )


def send_password_reset_email(user, token: str) -> bool:
    from flask import url_for

    reset_url = url_for("auth.reset_password", token=token, _external=True)
    return send_email(
        subject="Reset your password",
        recipients=[user.email],
        template_base="password_reset",
        user=user,
        reset_url=reset_url,
    )


def send_inquiry_confirmation(inquiry) -> bool:
    return send_email(
        subject="We've received your project inquiry",
        recipients=[inquiry.email],
        template_base="inquiry_confirmation",
        inquiry=inquiry,
    )


def send_inquiry_admin_notification(inquiry) -> bool:
    admin_email = current_app.config["ADMIN_EMAIL"]
    return send_email(
        subject=f"New project inquiry: {inquiry.name}",
        recipients=[admin_email],
        template_base="inquiry_admin_notification",
        inquiry=inquiry,
    )


def send_payment_confirmation(payment) -> bool:
    purchase = payment.purchase
    return send_email(
        subject="Payment confirmed",
        recipients=[purchase.user.email],
        template_base="payment_confirmation",
        payment=payment,
        purchase=purchase,
        course=purchase.course,
        user=purchase.user,
    )


def send_enrollment_email(enrollment) -> bool:
    from flask import url_for

    course_url = url_for("learning.course_overview", course_slug=enrollment.course.slug, _external=True)
    return send_email(
        subject=f"You're enrolled: {enrollment.course.title}",
        recipients=[enrollment.user.email],
        template_base="enrollment",
        enrollment=enrollment,
        course=enrollment.course,
        user=enrollment.user,
        course_url=course_url,
    )


def send_refund_email(payment) -> bool:
    purchase = payment.purchase
    return send_email(
        subject="Your refund has been processed",
        recipients=[purchase.user.email],
        template_base="refund",
        payment=payment,
        purchase=purchase,
        course=purchase.course,
        user=purchase.user,
    )


def send_renewal_reminder(subscription, days_left: int) -> bool:
    """Tell the owner a service is about to renew. Sent by the cron command."""
    when_phrase = {0: "today", 1: "tomorrow"}.get(days_left, f"in {days_left} days")
    if days_left < 0:
        when_phrase = f"{abs(days_left)} days ago (overdue)"
    return send_email(
        subject=f"{subscription.name} renews {when_phrase}",
        recipients=[current_app.config["ADMIN_EMAIL"]],
        template_base="renewal_reminder",
        subscription=subscription,
        when_phrase=when_phrase,
        days_left=days_left,
    )


def send_security_notification(user, event: str, detail: str | None = None) -> bool:
    """
    event: short label like "Password changed" or "New session signed in".
    Used for account.change_password, session revocation, etc.
    """
    return send_email(
        subject=f"Security alert: {event}",
        recipients=[user.email],
        template_base="security_notification",
        user=user,
        event=event,
        detail=detail,
    )


def send_product_download_link(download_request, product, download_url: str) -> bool:
    """
    The emailed link for a gated download. Deliberately a link and not the
    file: Gmail and Outlook.com refuse any message carrying an .exe, and an
    installer is usually past attachment size limits anyway.
    """
    from app.consent import unsubscribe_url
    from app.downloads import format_size

    max_age = current_app.config["DOWNLOAD_LINK_MAX_AGE"]
    unsubscribe = unsubscribe_url(download_request.email)
    return send_email(
        subject=f"Your download: {product.title}",
        recipients=[download_request.email],
        template_base="product_download",
        # Mail apps' own "Unsubscribe" button (RFC 2369 / RFC 8058 one-click).
        headers={
            "List-Unsubscribe": f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
        unsubscribe_url=unsubscribe,
        download_request=download_request,
        product=product,
        download_url=download_url,
        file_size=format_size(product.download_size),
        valid_days=max(1, max_age // 86400),
        max_uses=current_app.config["DOWNLOAD_LINK_MAX_USES"],
    )
