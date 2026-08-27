from app.extensions import db
from app.models import TimestampMixin


class Testimonial(db.Model, TimestampMixin):
    __tablename__ = "testimonials"

    id = db.Column(db.Integer, primary_key=True)

    author_name = db.Column(db.String(120), nullable=False)
    author_title = db.Column(db.String(160))  # e.g. "CTO, Acme Inc."
    author_avatar = db.Column(db.String(512))

    quote = db.Column(db.Text, nullable=False)
    rating = db.Column(db.SmallInteger)  # optional 1-5

    related_project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))
    related_course_id = db.Column(db.Integer, db.ForeignKey("courses.id"))

    approved = db.Column(db.Boolean, default=False, nullable=False)
    featured = db.Column(db.Boolean, default=False, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    related_project = db.relationship("Project")
    related_course = db.relationship("Course")
