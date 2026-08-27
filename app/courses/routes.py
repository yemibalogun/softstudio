from flask import Blueprint, render_template, abort
from flask_login import current_user

from app.models import Course, CourseCategory, Enrollment

bp = Blueprint("courses", __name__)


@bp.route("/")
def index():
    courses = Course.query.filter_by(published=True).all()
    categories = CourseCategory.query.all()
    return render_template("courses/index.html", courses=courses, categories=categories)


@bp.route("/category/<slug>")
def category(slug):
    category = CourseCategory.query.filter_by(slug=slug).first()
    if not category:
        abort(404)
    courses = Course.query.filter_by(published=True, category_id=category.id).all()
    return render_template("courses/category.html", category=category, courses=courses)


@bp.route("/<slug>")
def detail(slug):
    course = Course.query.filter_by(slug=slug, published=True).first()
    if not course:
        abort(404)

    is_enrolled = False
    if current_user.is_authenticated:
        enrollment = Enrollment.query.filter_by(
            user_id=current_user.id, course_id=course.id, status="active"
        ).first()
        is_enrolled = enrollment is not None

    return render_template("courses/detail.html", course=course, is_enrolled=is_enrolled)
