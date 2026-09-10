from app.extensions import db
from app.models import TimestampMixin, gen_uuid


class Coupon(db.Model, TimestampMixin):
    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)

    percent_off = db.Column(db.SmallInteger)  # 1-100
    amount_off = db.Column(db.Numeric(10, 2))

    max_redemptions = db.Column(db.Integer)
    times_redeemed = db.Column(db.Integer, default=0, nullable=False)

    valid_from = db.Column(db.DateTime(timezone=True))
    valid_until = db.Column(db.DateTime(timezone=True))
    active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<Coupon {self.code}>"


class Purchase(db.Model, TimestampMixin):
    """
    Represents a user's intent/record of buying a course. Holds the
    server-computed price actually charged (never trust a client-
    submitted price). One Purchase maps to one Payment attempt sequence
    and, on success, one Enrollment.
    """

    __tablename__ = "purchases"

    STATUS_CHOICES = ("pending", "completed", "failed", "refunded")

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=gen_uuid, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupons.id"))

    amount = db.Column(db.Numeric(10, 2), nullable=False)  # server-computed, authoritative
    currency = db.Column(db.String(8), nullable=False)

    status = db.Column(db.String(20), default="pending", nullable=False, index=True)

    user = db.relationship("User", back_populates="purchases")
    course = db.relationship("Course")
    coupon = db.relationship("Coupon")
    payments = db.relationship("Payment", back_populates="purchase", cascade="all, delete-orphan")
    enrollment = db.relationship("Enrollment", back_populates="purchase", uselist=False)


class Payment(db.Model, TimestampMixin):
    """
    An individual payment-provider transaction attempt tied to a
    Purchase. Status is only ever updated from server-verified provider
    responses or verified webhooks — never from a client callback alone.
    """

    __tablename__ = "payments"
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_reference", name="uq_payment_provider_ref"),
    )

    STATUS_CHOICES = ("initiated", "successful", "failed", "refunded")

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)

    provider = db.Column(db.String(40), nullable=False)  # 'flutterwave' | 'paystack' | ...
    provider_reference = db.Column(db.String(120), nullable=False, index=True)

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(8), nullable=False)
    status = db.Column(db.String(20), default="initiated", nullable=False)

    # Idempotency guard for webhook processing.
    webhook_event_id = db.Column(db.String(120), unique=True, index=True)

    raw_provider_response = db.Column(db.JSON)

    verified_at = db.Column(db.DateTime(timezone=True))
    refunded_at = db.Column(db.DateTime(timezone=True))

    purchase = db.relationship("Purchase", back_populates="payments")
