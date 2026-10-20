"""
Recurring bills: VPN, mailbox, domains, the VPS — anything with a date
that must not be missed, and a payment history once it is paid.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import TimestampMixin, utcnow

# How many months one billing cycle covers. one_off has no next date.
CYCLE_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12, "one_off": 0}


def add_months(start: date, months: int) -> date:
    """Same day-of-month, clamped to the end of a shorter month."""
    if months <= 0:
        return start
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(start.day, last_day))


class ServiceSubscription(db.Model, TimestampMixin):
    """One service you pay for on a schedule."""

    __tablename__ = "service_subscriptions"

    CATEGORIES = ("vpn", "email", "hosting", "domain", "software", "other")
    CYCLES = tuple(CYCLE_MONTHS)

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    vendor = db.Column(db.String(120))
    category = db.Column(db.String(20), default="other", nullable=False, index=True)

    amount = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    currency = db.Column(db.String(8), default="USD", nullable=False)
    cycle = db.Column(db.String(12), default="monthly", nullable=False)

    next_due_on = db.Column(db.Date, index=True)
    auto_renew = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    manage_url = db.Column(db.String(512))
    notes = db.Column(db.Text)

    last_paid_on = db.Column(db.Date)
    # The reminder stage (14 / 7 / 1) already emailed for the current due
    # date, so the cron job never mails the same warning twice.
    reminder_stage_sent = db.Column(db.SmallInteger)

    payments = db.relationship(
        "ServicePayment",
        back_populates="subscription",
        cascade="all, delete-orphan",
        order_by="ServicePayment.paid_on.desc()",
    )

    # ---- derived values the dashboard reads -------------------------------

    @property
    def cycle_months(self) -> int:
        return CYCLE_MONTHS.get(self.cycle, 1)

    @property
    def days_until_due(self) -> int | None:
        if not self.next_due_on:
            return None
        return (self.next_due_on - date.today()).days

    @property
    def is_overdue(self) -> bool:
        days = self.days_until_due
        return days is not None and days < 0

    @property
    def is_due_soon(self) -> bool:
        days = self.days_until_due
        return days is not None and 0 <= days <= 14

    @property
    def monthly_cost(self) -> Decimal:
        """Cost normalized to a month, for the spend totals. One-offs count 0."""
        months = self.cycle_months
        if not months or self.amount is None:
            return Decimal("0")
        return (Decimal(self.amount) / Decimal(months)).quantize(Decimal("0.01"))

    @property
    def yearly_cost(self) -> Decimal:
        return (self.monthly_cost * 12).quantize(Decimal("0.01"))

    def mark_paid(self, paid_on: date | None = None, amount=None, note: str | None = None):
        """
        Record a payment and roll the due date forward by one cycle.

        Rolling from the due date (not from today) keeps a yearly renewal on
        its anniversary even when it is paid a few days late; a missed cycle
        is caught up so the next date is always in the future.
        """
        paid_on = paid_on or date.today()
        payment = ServicePayment(
            subscription=self,
            amount=amount if amount is not None else self.amount,
            currency=self.currency,
            paid_on=paid_on,
            note=note,
        )
        db.session.add(payment)

        self.last_paid_on = paid_on
        self.reminder_stage_sent = None

        months = self.cycle_months
        if months:
            nxt = add_months(self.next_due_on or paid_on, months)
            while nxt <= paid_on:
                nxt = add_months(nxt, months)
            self.next_due_on = nxt
        else:
            self.next_due_on = None  # one-off: nothing further is owed
        return payment

    def __repr__(self):
        return f"<ServiceSubscription {self.name} due {self.next_due_on}>"


class ServicePayment(db.Model):
    """A payment made against a subscription."""

    __tablename__ = "service_payments"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer,
        db.ForeignKey("service_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    currency = db.Column(db.String(8), default="USD", nullable=False)
    paid_on = db.Column(db.Date, nullable=False, default=date.today, index=True)
    note = db.Column(db.String(255))

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    subscription = db.relationship("ServiceSubscription", back_populates="payments")

    def __repr__(self):
        return f"<ServicePayment {self.amount} on {self.paid_on}>"


def upcoming(window_days: int = 60):
    """Active subscriptions due within the window, soonest (and overdue) first."""
    horizon = date.today() + timedelta(days=window_days)
    return (
        ServiceSubscription.query.filter(
            ServiceSubscription.is_active.is_(True),
            ServiceSubscription.next_due_on.isnot(None),
            ServiceSubscription.next_due_on <= horizon,
        )
        .order_by(ServiceSubscription.next_due_on)
        .all()
    )
