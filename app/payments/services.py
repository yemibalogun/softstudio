"""
Provider-agnostic payment service.

Course/enrollment logic talks only to `PaymentService`, never to a
specific provider SDK directly. This keeps Flutterwave/Paystack/future
providers swappable via PAYMENT_PROVIDER config without touching
checkout or enrollment code.

Security invariants enforced here:
- The charged amount is always the server-computed course price
  (Course.effective_price minus any validated coupon), never a
  client-submitted amount.
- An Enrollment is only ever created after `verify_transaction()`
  returns a successful, provider-confirmed result.
- Webhook signatures are verified before any state changes, and
  processing is idempotent via Payment.webhook_event_id.
"""
from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from flask import current_app

from app.extensions import db
from app.models import Purchase, Payment, Enrollment, Course, Coupon


@dataclass
class VerificationResult:
    success: bool
    provider_reference: str
    amount: float
    currency: str
    raw_response: dict


class BasePaymentProvider(ABC):
    @abstractmethod
    def initiate_transaction(self, purchase: Purchase, callback_url: str) -> str:
        """Returns the hosted checkout URL to redirect the user to."""

    @abstractmethod
    def verify_transaction(self, provider_reference: str) -> VerificationResult:
        """Server-side verification call against the provider's API."""

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        ...


class FlutterwaveProvider(BasePaymentProvider):
    def initiate_transaction(self, purchase: Purchase, callback_url: str) -> str:
        # Real implementation calls Flutterwave's /payments endpoint with
        # tx_ref=purchase.public_id, amount=purchase.amount (server value),
        # and redirect_url=callback_url. Left as an integration point.
        raise NotImplementedError("Wire up Flutterwave SDK/API call here.")

    def verify_transaction(self, provider_reference: str) -> VerificationResult:
        raise NotImplementedError("Call Flutterwave's transaction verify endpoint here.")

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        secret = current_app.config["PAYMENT_WEBHOOK_SECRET"] or ""
        expected = hashlib.sha256(secret.encode()).hexdigest()
        return hmac.compare_digest(expected, signature_header or "")


class PaystackProvider(BasePaymentProvider):
    def initiate_transaction(self, purchase: Purchase, callback_url: str) -> str:
        raise NotImplementedError("Wire up Paystack SDK/API call here.")

    def verify_transaction(self, provider_reference: str) -> VerificationResult:
        raise NotImplementedError("Call Paystack's transaction verify endpoint here.")

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        secret = current_app.config["PAYMENT_WEBHOOK_SECRET"] or ""
        expected = hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature_header or "")


_PROVIDERS = {
    "flutterwave": FlutterwaveProvider,
    "paystack": PaystackProvider,
}


def get_provider() -> BasePaymentProvider:
    name = current_app.config["PAYMENT_PROVIDER"]
    provider_cls = _PROVIDERS.get(name)
    if not provider_cls:
        raise RuntimeError(f"Unknown PAYMENT_PROVIDER '{name}'")
    return provider_cls()


def compute_price(course: Course, coupon: Coupon | None = None) -> float:
    """Server-authoritative price calculation. Never trust a client amount."""
    price = float(course.effective_price)
    if coupon and coupon.active:
        if coupon.percent_off:
            price -= price * (coupon.percent_off / 100)
        if coupon.amount_off:
            price -= float(coupon.amount_off)
    return max(price, 0.0)


def create_purchase(user, course: Course, coupon: Coupon | None = None) -> Purchase:
    amount = compute_price(course, coupon)
    purchase = Purchase()
    purchase.user_id=user.id
    purchase.course_id=course.id
    purchase.coupon_id=coupon.id if coupon else None
    purchase.amount=amount
    purchase.currency=course.currency
    purchase.status="pending"
    
    db.session.add(purchase)
    db.session.commit()
    return purchase


def activate_enrollment(purchase: Purchase) -> Enrollment:
    enrollment = Enrollment.query.filter_by(user_id=purchase.user_id, course_id=purchase.course_id).first()
    if enrollment:
        enrollment.status = "active"
        enrollment.purchase_id = purchase.id
        enrollment.enrolled_at = datetime.now(timezone.utc)
    else:
        enrollment = Enrollment()
        enrollment.user_id=purchase.user_id
        enrollment.course_id=purchase.course_id
        enrollment.purchase_id=purchase.id
        enrollment.status="active"
        enrollment.enrolled_at=datetime.now(timezone.utc)
        
        db.session.add(enrollment)
    purchase.status = "completed"
    db.session.commit()

    from app import emails
    emails.send_enrollment_email(enrollment)

    return enrollment


def revoke_enrollment_for_refund(payment: Payment) -> None:
    purchase = cast(Purchase, payment.purchase)
    purchase.status = "refunded"

    enrollment = cast(Enrollment | None, purchase.enrollment)
    if enrollment is not None:
        enrollment.status = "revoked"
        enrollment.revoked_at = datetime.now(timezone.utc)

    payment.status = "refunded"
    payment.refunded_at = datetime.now(timezone.utc)
    db.session.commit()

    from app import emails
    emails.send_refund_email(payment)


def process_verified_payment(purchase: Purchase, result: VerificationResult, provider_name: str) -> Payment:
    """
    Idempotently record a provider-confirmed payment result and, on
    success, activate enrollment. Safe to call more than once for the
    same provider_reference (e.g. webhook arriving after redirect
    verification already processed it).
    """
    payment = Payment.query.filter_by(
        provider=provider_name, provider_reference=result.provider_reference
    ).first()

    if payment and payment.status == "successful":
        return payment  # already processed — idempotent no-op

    if not payment:
        payment = Payment()
        payment.purchase_id=purchase.id
        payment.provider=provider_name
        payment.provider_reference=result.provider_reference
        payment.amount=result.amount
        payment.currency=result.currency
        
        db.session.add(payment)

    payment.raw_provider_response = result.raw_response
    payment.status = "successful" if result.success else "failed"
    payment.verified_at = datetime.now(timezone.utc)
    db.session.commit()

    # Defense in depth: re-check the server-computed amount matches what
    # was actually confirmed by the provider before activating access.
    if result.success and abs(float(purchase.amount) - float(result.amount)) < 0.01:
        activate_enrollment(purchase)

        from app import emails
        emails.send_payment_confirmation(payment)

    return payment
