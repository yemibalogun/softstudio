from app.extensions import db
from app.models import TimestampMixin, gen_uuid


class ProjectInquiry(db.Model, TimestampMixin):
    """A lead submitted via the project inquiry / contact form."""

    __tablename__ = "project_inquiries"

    STATUS_CHOICES = ("new", "contacted", "qualified", "closed", "spam")

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=gen_uuid, index=True)

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    company = db.Column(db.String(160))
    phone = db.Column(db.String(40))

    project_type = db.Column(db.String(80))
    project_description = db.Column(db.Text, nullable=False)
    current_process = db.Column(db.Text)
    desired_outcome = db.Column(db.Text)
    budget_range = db.Column(db.String(60))
    timeline = db.Column(db.String(60))
    referral_source = db.Column(db.String(120))

    status = db.Column(db.String(20), default="new", nullable=False, index=True)
    admin_notes = db.Column(db.Text)

    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))

    def __repr__(self):
        return f"<ProjectInquiry {self.email}>"
