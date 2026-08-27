import re

from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, BooleanField, SelectField, DecimalField,
    IntegerField,
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange, URL


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


class ProjectForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    slug = StringField("Slug", validators=[Optional(), Length(max=180)])
    short_description = StringField("Short description", validators=[DataRequired(), Length(max=280)])
    description = TextAreaField("Description", validators=[Optional()])
    problem = TextAreaField("Problem", validators=[Optional()])
    solution = TextAreaField("Solution", validators=[Optional()])
    results = TextAreaField("Results", validators=[Optional()])

    category = StringField("Category", validators=[Optional(), Length(max=80)])
    status = SelectField(
        "Status",
        choices=[
            ("draft", "Draft"), ("in_progress", "In Progress"),
            ("live", "Live"), ("archived", "Archived"),
        ],
        default="live",
    )
    featured = BooleanField("Featured on homepage")
    published = BooleanField("Published")

    thumbnail = StringField("Thumbnail URL", validators=[Optional(), URL(), Length(max=512)])
    hero_image = StringField("Hero image URL", validators=[Optional(), URL(), Length(max=512)])
    demo_video = StringField("Demo video URL", validators=[Optional(), URL(), Length(max=512)])

    live_url = StringField("Live URL", validators=[Optional(), URL(), Length(max=512)])
    github_url = StringField("GitHub URL", validators=[Optional(), URL(), Length(max=512)])
    documentation_url = StringField("Documentation URL", validators=[Optional(), URL(), Length(max=512)])

    technologies_csv = StringField(
        "Technologies (comma-separated)", validators=[Optional(), Length(max=500)]
    )

    display_order = IntegerField("Display order", default=0, validators=[Optional()])

    meta_title = StringField("Meta title", validators=[Optional(), Length(max=180)])
    meta_description = StringField("Meta description", validators=[Optional(), Length(max=300)])
    og_image = StringField("OG image URL", validators=[Optional(), URL(), Length(max=512)])


class ServiceForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    slug = StringField("Slug", validators=[Optional(), Length(max=180)])
    summary = StringField("Summary", validators=[DataRequired(), Length(max=280)])
    description = TextAreaField("Description", validators=[Optional()])
    problems_solved = TextAreaField("Problems solved (one per line)", validators=[Optional()])
    process_steps = TextAreaField("Process (one per line)", validators=[Optional()])
    technologies = TextAreaField("Technologies (one per line)", validators=[Optional()])
    expected_outcomes = TextAreaField("Expected outcomes (one per line)", validators=[Optional()])
    display_order = IntegerField("Display order", default=0, validators=[Optional()])
    published = BooleanField("Published", default=True)


class CourseForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=180)])
    slug = StringField("Slug", validators=[Optional(), Length(max=200)])
    short_description = StringField("Short description", validators=[DataRequired(), Length(max=280)])
    description = TextAreaField("Description", validators=[Optional()])

    thumbnail = StringField("Thumbnail URL", validators=[Optional(), URL(), Length(max=512)])
    promo_video_url = StringField("Promo video URL", validators=[Optional(), URL(), Length(max=512)])

    price = DecimalField("Price", places=2, validators=[DataRequired(), NumberRange(min=0)])
    discount_price = DecimalField(
        "Discount price", places=2, validators=[Optional(), NumberRange(min=0)]
    )
    currency = SelectField(
        "Currency", choices=[("NGN", "NGN"), ("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP")], default="NGN"
    )

    difficulty = SelectField(
        "Difficulty",
        choices=[("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")],
        default="beginner",
    )

    category_id = SelectField("Category", coerce=int, validators=[Optional()])

    learning_objectives = TextAreaField("Learning objectives (one per line)", validators=[Optional()])
    requirements = TextAreaField("Requirements (one per line)", validators=[Optional()])
    target_audience = TextAreaField("Target audience (one per line)", validators=[Optional()])

    published = BooleanField("Published")
    featured = BooleanField("Featured on homepage")

    meta_title = StringField("Meta title", validators=[Optional(), Length(max=180)])
    meta_description = StringField("Meta description", validators=[Optional(), Length(max=300)])
    og_image = StringField("OG image URL", validators=[Optional(), URL(), Length(max=512)])


class CourseCategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    slug = StringField("Slug", validators=[Optional(), Length(max=140)])
    description = StringField("Description", validators=[Optional(), Length(max=300)])


class CourseSectionForm(FlaskForm):
    title = StringField("Section title", validators=[DataRequired(), Length(max=180)])
    display_order = IntegerField("Display order", default=0, validators=[Optional()])


class LessonForm(FlaskForm):
    title = StringField("Lesson title", validators=[DataRequired(), Length(max=180)])
    slug = StringField("Slug", validators=[Optional(), Length(max=200)])
    description = TextAreaField("Description", validators=[Optional()])
    video_url = StringField("Video URL / reference", validators=[Optional(), Length(max=512)])
    duration_seconds = IntegerField("Duration (seconds)", default=0, validators=[Optional()])
    display_order = IntegerField("Display order", default=0, validators=[Optional()])
    is_free_preview = BooleanField("Free preview")
    published = BooleanField("Published", default=True)


class BlogPostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    slug = StringField("Slug", validators=[Optional(), Length(max=220)])
    excerpt = StringField("Excerpt", validators=[Optional(), Length(max=400)])
    body = TextAreaField("Body (HTML)", validators=[DataRequired()])
    featured_image = StringField("Featured image URL", validators=[Optional(), URL(), Length(max=512)])
    category_id = SelectField("Category", coerce=int, validators=[Optional()])
    tags_csv = StringField("Tags (comma-separated)", validators=[Optional(), Length(max=300)])
    published = BooleanField("Published")

    meta_title = StringField("Meta title", validators=[Optional(), Length(max=180)])
    meta_description = StringField("Meta description", validators=[Optional(), Length(max=300)])
    og_image = StringField("OG image URL", validators=[Optional(), URL(), Length(max=512)])


class BlogCategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    slug = StringField("Slug", validators=[Optional(), Length(max=140)])


class TestimonialForm(FlaskForm):
    author_name = StringField("Author name", validators=[DataRequired(), Length(max=120)])
    author_title = StringField("Author title", validators=[Optional(), Length(max=160)])
    author_avatar = StringField("Author avatar URL", validators=[Optional(), URL(), Length(max=512)])
    quote = TextAreaField("Quote", validators=[DataRequired()])
    rating = IntegerField("Rating (1-5)", validators=[Optional(), NumberRange(min=1, max=5)])
    approved = BooleanField("Approved")
    featured = BooleanField("Featured on homepage")
    display_order = IntegerField("Display order", default=0, validators=[Optional()])
