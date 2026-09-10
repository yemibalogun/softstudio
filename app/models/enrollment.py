from app.extensions import db
from app.models import TimestampMixin


class Enrollment(db.Model, TimestampMixin):
    """
    The authoritative record that a user may access a course's paid
    lessons. Created only after server-side payment verification
    (see app/payments/services.py) — never from client-submitted state.
    """

    __tablename__ = "enrollments"
    __table_args__ = (
        db.UniqueConstraint("user_id", "course_id", name="uq_enrollment_user_course"),
    )

    STATUS_CHOICES = ("active", "revoked", "expired")

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)

    status = db.Column(db.String(20), default="active", nullable=False, index=True)
    source = db.Column(db.String(20), default="purchase", nullable=False)  # purchase | admin_grant | coupon

    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"))

    enrolled_at = db.Column(db.DateTime(timezone=True))
    revoked_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="enrollments")
    course = db.relationship("Course", back_populates="enrollments")
    purchase = db.relationship("Purchase", back_populates="enrollment", uselist=False)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class LessonProgress(db.Model, TimestampMixin):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        db.UniqueConstraint("user_id", "lesson_id", name="uq_progress_user_lesson"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)

    completed = db.Column(db.Boolean, default=False, nullable=False, index=True)
    completed_at = db.Column(db.DateTime(timezone=True))
    last_position_seconds = db.Column(db.Integer, default=0)

    lesson = db.relationship("Lesson", back_populates="progress_records")
    user = db.relationship("User")
