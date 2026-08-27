from app.extensions import db
from app.models import TimestampMixin


class Service(db.Model, TimestampMixin):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)

    summary = db.Column(db.String(280), nullable=False)
    description = db.Column(db.Text)

    # Stored as newline-delimited or JSON text; rendered as lists in templates.
    problems_solved = db.Column(db.Text)
    process = db.Column(db.Text)
    technologies = db.Column(db.Text)
    expected_outcomes = db.Column(db.Text)

    icon = db.Column(db.String(120))
    display_order = db.Column(db.Integer, default=0, nullable=False)
    published = db.Column(db.Boolean, default=True, nullable=False)

    meta_title = db.Column(db.String(180))
    meta_description = db.Column(db.String(300))

    def __repr__(self):
        return f"<Service {self.slug}>"
