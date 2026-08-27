from app.extensions import db
from app.models import Enrollment, Payment
from app.payments import services


def _purchase(user, course, amount=15000):
    purchase = services.create_purchase(user, course)
    purchase.amount = amount  # server-authoritative amount, set explicitly for the test
    db.session.commit()
    return purchase


def test_successful_payment_activates_enrollment(user, course_with_lessons):
    purchase = _purchase(user, course_with_lessons)
    result = services.VerificationResult(
        success=True,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={"status": "successful"},
    )

    payment = services.process_verified_payment(purchase, result, "flutterwave")

    assert payment.status == "successful"
    enrollment = Enrollment.query.filter_by(user_id=user.id, course_id=course_with_lessons.id).first()
    assert enrollment is not None
    assert enrollment.status == "active"


def test_failed_payment_does_not_activate_enrollment(user, course_with_lessons):
    purchase = _purchase(user, course_with_lessons)
    result = services.VerificationResult(
        success=False,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={"status": "failed"},
    )

    services.process_verified_payment(purchase, result, "flutterwave")

    enrollment = Enrollment.query.filter_by(user_id=user.id, course_id=course_with_lessons.id).first()
    assert enrollment is None


def test_amount_mismatch_does_not_activate_enrollment(user, course_with_lessons):
    """A provider confirming a *different* amount than the server-computed
    price must never be trusted into granting access — defense in depth
    against tampered client-side price manipulation."""
    purchase = _purchase(user, course_with_lessons, amount=15000)
    result = services.VerificationResult(
        success=True,
        provider_reference=purchase.public_id,
        amount=1.00,  # attacker-controlled mismatch
        currency="NGN",
        raw_response={"status": "successful"},
    )

    services.process_verified_payment(purchase, result, "flutterwave")

    enrollment = Enrollment.query.filter_by(user_id=user.id, course_id=course_with_lessons.id).first()
    assert enrollment is None


def test_duplicate_webhook_is_idempotent(user, course_with_lessons):
    purchase = _purchase(user, course_with_lessons)
    result = services.VerificationResult(
        success=True,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={"status": "successful"},
    )

    services.process_verified_payment(purchase, result, "flutterwave")
    services.process_verified_payment(purchase, result, "flutterwave")  # simulate webhook retry

    payments = Payment.query.filter_by(provider="flutterwave", provider_reference=purchase.public_id).all()
    assert len(payments) == 1  # no duplicate Payment rows created

    enrollments = Enrollment.query.filter_by(user_id=user.id, course_id=course_with_lessons.id).all()
    assert len(enrollments) == 1  # no duplicate enrollment either


def test_refund_revokes_enrollment(user, course_with_lessons):
    purchase = _purchase(user, course_with_lessons)
    result = services.VerificationResult(
        success=True,
        provider_reference=purchase.public_id,
        amount=float(purchase.amount),
        currency="NGN",
        raw_response={},
    )
    payment = services.process_verified_payment(purchase, result, "flutterwave")

    services.revoke_enrollment_for_refund(payment)

    enrollment = Enrollment.query.filter_by(user_id=user.id, course_id=course_with_lessons.id).first()
    assert enrollment.status == "revoked"
    assert purchase.status == "refunded"


def test_coupon_reduces_server_computed_price(user, course_with_lessons):
    from app.models import Coupon

    coupon = Coupon(code="SAVE20", percent_off=20, active=True)
    db.session.add(coupon)
    db.session.commit()

    price = services.compute_price(course_with_lessons, coupon)
    assert price == float(course_with_lessons.effective_price) * 0.8
