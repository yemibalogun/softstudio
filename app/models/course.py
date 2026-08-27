from app.extensions import db
from app.models import TimestampMixin


class CourseCategory(db.Model, TimestampMixin):
    __tablename__ = "course_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    description = db.Column(db.String(300))

    courses = db.relationship("Course", back_populates="category")

    def __repr__(self):
        return f"<CourseCategory {self.slug}>"


class Course(db.Model, TimestampMixin):
    __tablename__ = "courses"

    DIFFICULTY_CHOICES = ("beginner", "intermediate", "advanced")

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)

    short_description = db.Column(db.String(280), nullable=False)
    description = db.Column(db.Text)

    thumbnail = db.Column(db.String(512))
    promo_video_url = db.Column(db.String(512))

    price = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    discount_price = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(8), default="NGN", nullable=False)

    difficulty = db.Column(db.String(20), default="beginner", nullable=False)
    duration_minutes = db.Column(db.Integer, default=0)  # denormalized total, kept in sync on lesson save

    published = db.Column(db.Boolean, default=False, nullable=False)
    featured = db.Column(db.Boolean, default=False, nullable=False)

    # Stored as newline-delimited text; rendered as bullet lists.
    learning_objectives = db.Column(db.Text)
    requirements = db.Column(db.Text)
    target_audience = db.Column(db.Text)

    category_id = db.Column(db.Integer, db.ForeignKey("course_categories.id"))
    category = db.relationship("CourseCategory", back_populates="courses")

    meta_title = db.Column(db.String(180))
    meta_description = db.Column(db.String(300))
    og_image = db.Column(db.String(512))

    sections = db.relationship(
        "CourseSection", back_populates="course", cascade="all, delete-orphan",
        order_by="CourseSection.display_order",
    )
    enrollments = db.relationship(
        "Enrollment", back_populates="course", cascade="all, delete-orphan"
    )
    reviews = db.relationship(
        "CourseReview", back_populates="course", cascade="all, delete-orphan"
    )

    @property
    def effective_price(self):
        return self.discount_price if self.discount_price is not None else self.price

    @property
    def lesson_count(self) -> int:
        return sum(len(s.lessons) for s in self.sections)

    def __repr__(self):
        return f"<Course {self.slug}>"


class CourseSection(db.Model, TimestampMixin):
    __tablename__ = "course_sections"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)

    title = db.Column(db.String(180), nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    course = db.relationship("Course", back_populates="sections")
    lessons = db.relationship(
        "Lesson", back_populates="section", cascade="all, delete-orphan",
        order_by="Lesson.display_order",
    )


class Lesson(db.Model, TimestampMixin):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(
        db.Integer, db.ForeignKey("course_sections.id", ondelete="CASCADE"), nullable=False
    )

    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text)

    # Signed/protected video reference (provider-specific id or key),
    # never a directly public URL for paid content.
    video_url = db.Column(db.String(512))
    duration_seconds = db.Column(db.Integer, default=0)

    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_free_preview = db.Column(db.Boolean, default=False, nullable=False)
    published = db.Column(db.Boolean, default=True, nullable=False)

    section = db.relationship("CourseSection", back_populates="lessons")
    resources = db.relationship(
        "LessonResource", back_populates="lesson", cascade="all, delete-orphan"
    )
    progress_records = db.relationship(
        "LessonProgress", back_populates="lesson", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint("section_id", "slug", name="uq_lesson_section_slug"),
    )


class LessonResource(db.Model, TimestampMixin):
    __tablename__ = "lesson_resources"

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)

    title = db.Column(db.String(180), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)  # served via protected download route
    file_type = db.Column(db.String(20))  # pdf, zip, source, image, template
    file_size_bytes = db.Column(db.Integer)

    lesson = db.relationship("Lesson", back_populates="resources")


class CourseReview(db.Model, TimestampMixin):
    __tablename__ = "course_reviews"
    __table_args__ = (
        db.UniqueConstraint("user_id", "course_id", name="uq_review_per_user_course"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)

    rating = db.Column(db.SmallInteger, nullable=False)  # 1-5
    body = db.Column(db.Text)
    approved = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="course_reviews")
    course = db.relationship("Course", back_populates="reviews")
