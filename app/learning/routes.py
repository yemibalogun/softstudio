from datetime import datetime, timezone
from typing import cast

from flask import Blueprint, render_template, abort, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Course, CourseSection, Lesson, Enrollment, LessonProgress

bp = Blueprint("learning", __name__)


def _user_can_access_lesson(user, lesson: Lesson) -> bool:
    """
    Authorization gate for paid lesson content.

    Request lesson -> authenticated? -> valid active enrollment? -> allow.
    Free-preview lessons remain accessible to any authenticated user
    (kept behind login, not fully public, to avoid unauthenticated
    scraping of course content while still honoring "free preview").
    """
    if lesson.is_free_preview:
        return True
    if not user or not user.is_authenticated:
        return False
    course = lesson.section.course
    enrollment = Enrollment.query.filter_by(
        user_id=user.id, course_id=course.id, status="active"
    ).first()
    return enrollment is not None


@bp.route("/")
@login_required
def dashboard():
    enrollments = (
        Enrollment.query.filter_by(user_id=current_user.id, status="active")
        .options(
            selectinload(Enrollment.course)
            .selectinload(Course.sections)
            .selectinload(CourseSection.lessons)
        )
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )

    # All of this user's completed lesson ids, fetched once rather than
    # re-querying (and, previously, mis-scoping) per enrollment below.
    completed_lesson_ids = {
        lesson_id
        for (lesson_id,) in LessonProgress.query.filter_by(
            user_id=current_user.id, completed=True
        ).with_entities(LessonProgress.lesson_id)
    }

    course_progress = []
    for enrollment in enrollments:
        course = enrollment.course
        lesson_ids = [lesson.id for section in course.sections for lesson in section.lessons]
        total = len(lesson_ids)
        completed = sum(1 for lesson_id in lesson_ids if lesson_id in completed_lesson_ids)
        percent = int((completed / total) * 100) if total else 0
        course_progress.append({"course": course, "percent": percent, "completed": completed, "total": total})

    return render_template("learning/dashboard.html", course_progress=course_progress)


@bp.route("/courses/<course_slug>")
@login_required
def course_overview(course_slug):
    course = Course.query.filter_by(slug=course_slug).first()
    if not course:
        abort(404)
    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id, course_id=course.id, status="active"
    ).first()
    if not enrollment:
        flash("You are not enrolled in this course yet.", "info")
        return redirect(url_for("courses.detail", slug=course_slug))
    return render_template("learning/course.html", course=course, enrollment=enrollment)


@bp.route("/courses/<course_slug>/lessons/<lesson_slug>")
@login_required
def lesson(course_slug, lesson_slug):
    course = Course.query.filter_by(slug=course_slug).first()
    if not course:
        abort(404)

    target_lesson = None
    for section in course.sections:
        for lesson_item in section.lessons:
            if lesson_item.slug == lesson_slug:
                target_lesson = lesson_item
                break
    if not target_lesson:
        abort(404)

    if not _user_can_access_lesson(current_user, target_lesson):
        flash("Enroll in this course to access this lesson.", "info")
        return redirect(url_for("courses.detail", slug=course_slug))

    progress = LessonProgress.query.filter_by(
        user_id=current_user.id, lesson_id=target_lesson.id
    ).first()

    return render_template(
        "learning/lesson.html", course=course, lesson=target_lesson, progress=progress
    )


@bp.route("/courses/<course_slug>/lessons/<lesson_slug>/complete", methods=["POST"])
@login_required
def mark_complete(course_slug, lesson_slug):
    course = Course.query.filter_by(slug=course_slug).first_or_404()
    target_lesson = None
    for section in course.sections:
        for lesson_item in section.lessons:
            if lesson_item.slug == lesson_slug:
                target_lesson = lesson_item
    if not target_lesson or not _user_can_access_lesson(current_user, target_lesson):
        abort(403)

    progress = LessonProgress.query.filter_by(
        user_id=current_user.id, lesson_id=target_lesson.id
    ).first()
    if not progress:
        progress = LessonProgress()
        progress.user_id = current_user.id
        progress.lesson_id = target_lesson.id

        db.session.add(progress)
    progress.completed = True
    progress.completed_at = datetime.now(timezone.utc)
    db.session.commit()

    return redirect(url_for("learning.lesson", course_slug=course_slug, lesson_slug=lesson_slug))


@bp.route("/courses/<course_slug>/lessons/<lesson_slug>/resources/<int:resource_id>")
@login_required
def download_resource(course_slug, lesson_slug, resource_id):
    """
    Serves a lesson resource only after the same authorization check
    used for the lesson itself — resource files must never be reachable
    via a guessable static URL.
    """
    from flask import send_from_directory, current_app
    from app.extensions import db
    from app.models import LessonResource

    resource = db.session.get(LessonResource, resource_id)
    if not resource:
        abort(404)
    lesson_obj = cast(Lesson, resource.lesson)
    if lesson_obj.section.course.slug != course_slug or lesson_obj.slug != lesson_slug:
        abort(404)
    if not _user_can_access_lesson(current_user, lesson_obj):
        abort(403)

    directory = current_app.config.get("PROTECTED_UPLOADS_DIR", "/data/protected")
    return send_from_directory(directory, resource.file_path, as_attachment=True)
