from flask import Blueprint, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user

from app.extensions import csrf, limiter
from app.models import Course, Enrollment
from app.payments import services

bp = Blueprint("payments", __name__)


@bp.route("/checkout/<course_slug>", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def checkout(course_slug):
    course = Course.query.filter_by(slug=course_slug, published=True).first_or_404()

    already_enrolled = Enrollment.query.filter_by(
        user_id=current_user.id, course_id=course.id, status="active"
    ).first()
    if already_enrolled:
        flash("You're already enrolled in this course.", "info")
        return redirect(url_for("learning.course_overview", course_slug=course_slug))

    purchase = services.create_purchase(current_user, course)
    provider = services.get_provider()
    callback_url = url_for("payments.verify", purchase_id=purchase.public_id, _external=True)

    checkout_url = provider.initiate_transaction(purchase, callback_url)
    return redirect(checkout_url)


@bp.route("/verify/<purchase_id>")
@login_required
def verify(purchase_id):
    from app.models import Purchase

    purchase = Purchase.query.filter_by(public_id=purchase_id, user_id=current_user.id).first_or_404()
    provider = services.get_provider()
    provider_name = provider.__class__.__name__.replace("Provider", "").lower()

    reference = request.args.get("tx_ref") or request.args.get("reference") or purchase.public_id
    result = provider.verify_transaction(reference)
    services.process_verified_payment(purchase, result, provider_name)

    if result.success:
        flash("Payment confirmed — you're enrolled!", "success")
        return redirect(url_for("learning.course_overview", course_slug=purchase.course.slug))

    flash("Payment could not be verified. Please try again or contact support.", "error")
    return redirect(url_for("courses.detail", slug=purchase.course.slug))


@bp.route("/webhook/<provider_name>", methods=["POST"])
@csrf.exempt  # webhooks are authenticated via signature header, not CSRF token
def webhook(provider_name):
    from app.models import Purchase

    provider = services.get_provider()
    signature = request.headers.get("Verif-Hash") or request.headers.get("X-Paystack-Signature", "")

    if not provider.verify_webhook_signature(request.get_data(), signature):
        abort(403)

    payload = request.get_json(silent=True) or {}
    reference = payload.get("data", {}).get("tx_ref") or payload.get("data", {}).get("reference")
    if not reference:
        abort(400)

    purchase = Purchase.query.filter_by(public_id=reference).first()
    if not purchase:
        # Unknown reference — acknowledge to stop retries, but do nothing.
        return jsonify({"status": "ignored"}), 200

    result = provider.verify_transaction(reference)
    services.process_verified_payment(purchase, result, provider_name)

    return jsonify({"status": "ok"}), 200
