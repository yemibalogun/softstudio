from app.extensions import db
from app.models import TimestampMixin

# Many-to-many join table between Project and Technology.
project_technologies = db.Table(
    "project_technologies",
    db.Column(
        "project_id", db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    db.Column(
        "technology_id", db.Integer, db.ForeignKey("technologies.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Technology(db.Model):
    __tablename__ = "technologies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False, index=True)
    icon = db.Column(db.String(120))  # e.g. icon identifier or svg filename

    def __repr__(self):
        return f"<Technology {self.name}>"


class Project(db.Model, TimestampMixin):
    __tablename__ = "projects"

    STATUS_CHOICES = ("draft", "in_progress", "live", "archived")

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)

    short_description = db.Column(db.String(280), nullable=False)
    description = db.Column(db.Text)
    problem = db.Column(db.Text)
    solution = db.Column(db.Text)
    results = db.Column(db.Text)

    category = db.Column(db.String(80), index=True)
    status = db.Column(db.String(20), default="live", nullable=False)
    featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    published = db.Column(db.Boolean, default=False, nullable=False, index=True)

    thumbnail = db.Column(db.String(512))
    hero_image = db.Column(db.String(512))
    demo_video = db.Column(db.String(512))

    live_url = db.Column(db.String(512))
    github_url = db.Column(db.String(512))
    documentation_url = db.Column(db.String(512))

    # SEO overrides (fall back to sensible defaults if blank)
    meta_title = db.Column(db.String(180))
    meta_description = db.Column(db.String(300))
    og_image = db.Column(db.String(512))

    display_order = db.Column(db.Integer, default=0, nullable=False)

    images = db.relationship(
        "ProjectImage", back_populates="project", cascade="all, delete-orphan",
        order_by="ProjectImage.display_order",
    )
    technologies = db.relationship(
        "Technology", secondary=project_technologies, backref="projects"
    )

    def __repr__(self):
        return f"<Project {self.slug}>"


class ProjectImage(db.Model, TimestampMixin):
    __tablename__ = "project_images"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    image_url = db.Column(db.String(512), nullable=False)
    alt_text = db.Column(db.String(255))
    caption = db.Column(db.String(255))
    display_order = db.Column(db.Integer, default=0, nullable=False)

    project = db.relationship("Project", back_populates="images")
