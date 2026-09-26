from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    ProjectInquiry, Purchase, Enrollment, Course, Project, ProjectImage, Technology,
    Service, CourseCategory, CourseSection, Lesson, BlogPost, BlogCategory, BlogTag,
    Testimonial, Product, WaitlistSubscriber,
)
from app.admin.forms import (
    ProjectForm, ServiceForm, CourseForm, CourseCategoryForm, CourseSectionForm, LessonForm,
    BlogPostForm, BlogCategoryForm, TestimonialForm, ProductForm, slugify,
)
from app.admin.services import unique_slug, parse_csv_names, get_or_create_by_name
from app.uploads import delete_uploaded_image, store_image

bp = Blueprint("admin", __name__)


def admin_required(view):
    """
    Role-based authorization for every admin route. Checked server-side
    on each request — never inferred from a hidden frontend button.
    """
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/")
@admin_required
def dashboard():
    stats = {
        "new_inquiries": ProjectInquiry.query.filter_by(status="new").count(),
        "active_enrollments": Enrollment.query.filter_by(status="active").count(),
        "completed_purchases": Purchase.query.filter_by(status="completed").count(),
        "published_projects": Project.query.filter_by(published=True).count(),
        "published_courses": Course.query.filter_by(published=True).count(),
    }
    return render_template("admin/dashboard.html", stats=stats)


@bp.route("/inquiries")
@admin_required
def inquiries():
    items = ProjectInquiry.query.order_by(ProjectInquiry.created_at.desc()).all()
    return render_template("admin/inquiries.html", inquiries=items)


@bp.route("/payments")
@admin_required
def payments():
    items = Purchase.query.order_by(Purchase.created_at.desc()).all()
    return render_template("admin/payments.html", purchases=items)


# =====================================================================
# Projects
# =====================================================================

@bp.route("/projects")
@admin_required
def projects_list():
    items = Project.query.order_by(Project.display_order, Project.created_at.desc()).all()
    return render_template("admin/projects_list.html", projects=items)


@bp.route("/projects/new", methods=["GET", "POST"])
@admin_required
def project_create():
    form = ProjectForm()
    if form.validate_on_submit():
        project = Project()
        project.title = form.title.data
        _apply_project_form(project, form, is_new=True)
        db.session.add(project)
        db.session.commit()
        flash("Project created.", "success")
        return redirect(url_for("admin.projects_list"))
    return render_template("admin/project_form.html", form=form, project=None)


@bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@admin_required
def project_edit(project_id):
    project = Project.query.get_or_404(project_id)
    form = ProjectForm(obj=project)
    if request.method == "GET":
        form.technologies_csv.data = ", ".join(t.name for t in project.technologies)

    if form.validate_on_submit():
        _apply_project_form(project, form, is_new=False)
        db.session.commit()
        flash("Project updated.", "success")
        return redirect(url_for("admin.projects_list"))
    return render_template("admin/project_form.html", form=form, project=project)


def _apply_project_form(project: Project, form: ProjectForm, is_new: bool) -> None:
    project.title = form.title.data
    base_slug = form.slug.data or form.title.data or ""
    project.slug = unique_slug(Project, base_slug, current_id=project.id if not is_new else None)
    project.short_description = form.short_description.data
    project.description = form.description.data
    project.problem = form.problem.data
    project.solution = form.solution.data
    project.results = form.results.data
    project.category = form.category.data
    project.status = form.status.data
    project.featured = form.featured.data
    project.published = form.published.data
    project.thumbnail = form.thumbnail.data
    project.hero_image = form.hero_image.data
    project.demo_video = form.demo_video.data
    project.live_url = form.live_url.data
    project.github_url = form.github_url.data
    project.documentation_url = form.documentation_url.data
    project.display_order = form.display_order.data or 0
    project.meta_title = form.meta_title.data
    project.meta_description = form.meta_description.data
    project.og_image = form.og_image.data

    names = parse_csv_names(form.technologies_csv.data or "")
    technologies = [get_or_create_by_name(Technology, name) for name in names]
    project.technologies.clear()
    project.technologies.extend(technologies)


@bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@admin_required
def project_delete(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash("Project deleted.", "info")
    return redirect(url_for("admin.projects_list"))


@bp.route("/projects/<int:project_id>/toggle-published", methods=["POST"])
@admin_required
def project_toggle_published(project_id):
    project = Project.query.get_or_404(project_id)
    project.published = not project.published
    db.session.commit()
    return redirect(url_for("admin.projects_list"))


@bp.route("/projects/<int:project_id>/toggle-featured", methods=["POST"])
@admin_required
def project_toggle_featured(project_id):
    project = Project.query.get_or_404(project_id)
    project.featured = not project.featured
    db.session.commit()
    return redirect(url_for("admin.projects_list"))


@bp.route("/projects/<int:project_id>/images/add", methods=["POST"])
@admin_required
def project_image_add(project_id):
    project = Project.query.get_or_404(project_id)
    image_url = request.form.get("image_url", "").strip()
    alt_text = request.form.get("alt_text", "").strip()
    if image_url:
        project_image = ProjectImage()
        project_image.project_id = project.id
        project_image.image_url = image_url
        project_image.alt_text = alt_text
        project_image.display_order = len(project.images)
        db.session.add(project_image)
        db.session.commit()
        flash("Image added.", "success")
    return redirect(url_for("admin.project_edit", project_id=project.id))


@bp.route("/projects/<int:project_id>/images/<int:image_id>/delete", methods=["POST"])
@admin_required
def project_image_delete(project_id, image_id):
    image = ProjectImage.query.filter_by(id=image_id, project_id=project_id).first_or_404()
    db.session.delete(image)
    db.session.commit()
    return redirect(url_for("admin.project_edit", project_id=project_id))


# =====================================================================
# Products
# =====================================================================

@bp.route("/products")
@admin_required
def products_list():
    items = Product.query.order_by(Product.display_order, Product.created_at.desc()).all()
    return render_template("admin/products_list.html", products=items)


@bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_create():
    form = ProductForm()
    if form.validate_on_submit():
        product = Product()
        _apply_product_form(product, form, is_new=True)
        db.session.add(product)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_uploaded_image(product.image)  # don't orphan the new file
            raise
        flash("Product created.", "success")
        return redirect(url_for("admin.products_list"))
    return render_template("admin/product_form.html", form=form, product=None)


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)
    previous_image = product.image

    if form.validate_on_submit():
        _apply_product_form(product, form, is_new=False)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            if product.image != previous_image:
                delete_uploaded_image(product.image)
            raise
        # Only after the new value is safely stored: drop a replaced upload.
        if previous_image != product.image:
            delete_uploaded_image(previous_image)
        flash("Product updated.", "success")
        return redirect(url_for("admin.products_list"))
    return render_template("admin/product_form.html", form=form, product=product)


def _apply_product_form(product: Product, form: ProductForm, is_new: bool) -> None:
    product.title = form.title.data
    base_slug: str = form.slug.data or form.title.data or ""
    product.slug = unique_slug(Product, base_slug, current_id=product.id if not is_new else None)
    product.short_description = form.short_description.data
    product.description = form.description.data

    # Image: a new upload wins, then "remove", then the URL field.
    if form.processed_image is not None:
        product.image = store_image(form.processed_image, "products")
    elif form.remove_image.data:
        product.image = None
    else:
        product.image = form.image.data or None

    product.published = form.published.data
    product.waitlist_enabled = form.waitlist_enabled.data
    product.featured = form.featured.data
    product.display_order = form.display_order.data or 0
    product.cta_label = form.cta_label.data or None
    product.cta_url = form.cta_url.data or None
    product.meta_title = form.meta_title.data
    product.meta_description = form.meta_description.data
    product.og_image = form.og_image.data


@bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    image = product.image
    db.session.delete(product)  # waitlist rows cascade
    db.session.commit()
    delete_uploaded_image(image)
    flash("Product deleted.", "info")
    return redirect(url_for("admin.products_list"))


@bp.route("/products/<int:product_id>/toggle-published", methods=["POST"])
@admin_required
def product_toggle_published(product_id):
    product = Product.query.get_or_404(product_id)
    product.published = not product.published
    db.session.commit()
    return redirect(url_for("admin.products_list"))


@bp.route("/products/<int:product_id>/toggle-waitlist", methods=["POST"])
@admin_required
def product_toggle_waitlist(product_id):
    product = Product.query.get_or_404(product_id)
    product.waitlist_enabled = not product.waitlist_enabled
    db.session.commit()
    return redirect(url_for("admin.products_list"))


@bp.route("/products/<int:product_id>/waitlist")
@admin_required
def product_waitlist(product_id):
    """Subscriber list for one product. Admin-only: emails are never public."""
    product = Product.query.get_or_404(product_id)
    subscribers = (
        WaitlistSubscriber.query.filter_by(product_id=product.id)
        .order_by(WaitlistSubscriber.created_at.desc())
        .all()
    )
    by_source: dict[str, int] = {}
    for sub in subscribers:
        by_source[sub.source or "direct"] = by_source.get(sub.source or "direct", 0) + 1
    return render_template(
        "admin/product_waitlist.html",
        product=product,
        subscribers=subscribers,
        by_source=sorted(by_source.items(), key=lambda kv: -kv[1]),
    )


# =====================================================================
# Services
# =====================================================================

@bp.route("/services")
@admin_required
def services_list():
    items = Service.query.order_by(Service.display_order).all()
    return render_template("admin/services_list.html", services=items)


@bp.route("/services/new", methods=["GET", "POST"])
@admin_required
def service_create():
    form = ServiceForm()
    if form.validate_on_submit():
        service = Service()
        service.title = form.title.data
        _apply_service_form(service, form, is_new=True)
        db.session.add(service)
        db.session.commit()
        flash("Service created.", "success")
        return redirect(url_for("admin.services_list"))
    return render_template("admin/service_form.html", form=form, service=None)


@bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
@admin_required
def service_edit(service_id):
    service = Service.query.get_or_404(service_id)
    form = ServiceForm(obj=service)
    if request.method == "GET":
        form.process_steps.data = service.process
    if form.validate_on_submit():
        _apply_service_form(service, form, is_new=False)
        db.session.commit()
        flash("Service updated.", "success")
        return redirect(url_for("admin.services_list"))
    return render_template("admin/service_form.html", form=form, service=service)


def _apply_service_form(service: Service, form: ServiceForm, is_new: bool) -> None:
    service.title = form.title.data
    base_slug = str(form.slug.data or form.title.data or "")
    service.slug = unique_slug(Service, base_slug, current_id=service.id if not is_new else None)
    service.summary = form.summary.data
    service.description = form.description.data
    service.problems_solved = form.problems_solved.data
    service.process = form.process_steps.data
    service.technologies = form.technologies.data
    service.expected_outcomes = form.expected_outcomes.data
    service.display_order = form.display_order.data or 0
    service.published = form.published.data


@bp.route("/services/<int:service_id>/delete", methods=["POST"])
@admin_required
def service_delete(service_id):
    service = Service.query.get_or_404(service_id)
    db.session.delete(service)
    db.session.commit()
    flash("Service deleted.", "info")
    return redirect(url_for("admin.services_list"))


# =====================================================================
# Courses (+ categories, sections, lessons)
# =====================================================================

@bp.route("/courses")
@admin_required
def courses_list():
    items = Course.query.order_by(Course.created_at.desc()).all()
    return render_template("admin/courses_list.html", courses=items)


def _course_form_with_categories() -> CourseForm:
    form = CourseForm()
    form.category_id.choices = [(0, "— None —")] + [
        (c.id, c.name) for c in CourseCategory.query.order_by(CourseCategory.name).all()
    ]
    return form


@bp.route("/courses/new", methods=["GET", "POST"])
@admin_required
def course_create():
    form = _course_form_with_categories()
    if form.validate_on_submit():
        course = Course()
        course.title = form.title.data
        _apply_course_form(course, form, is_new=True)
        db.session.add(course)
        db.session.commit()
        flash("Course created. Now add sections and lessons.", "success")
        return redirect(url_for("admin.course_edit", course_id=course.id))
    return render_template("admin/course_form.html", form=form, course=None)


@bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@admin_required
def course_edit(course_id):
    course = Course.query.get_or_404(course_id)
    form = _course_form_with_categories()
    if request.method == "GET":
        form = CourseForm(obj=course)
        form.category_id.choices = [(0, "— None —")] + [
            (c.id, c.name) for c in CourseCategory.query.order_by(CourseCategory.name).all()
        ]
        form.category_id.data = course.category_id or 0

    if form.validate_on_submit():
        _apply_course_form(course, form, is_new=False)
        db.session.commit()
        flash("Course updated.", "success")
        return redirect(url_for("admin.course_edit", course_id=course.id))

    section_form = CourseSectionForm()
    lesson_form = LessonForm()
    return render_template(
        "admin/course_form.html", form=form, course=course,
        section_form=section_form, lesson_form=lesson_form,
    )


def _apply_course_form(course: Course, form: CourseForm, is_new: bool) -> None:
    course.title = form.title.data
    course.slug = unique_slug(
        Course, form.slug.data or form.title.data or "", current_id=course.id if not is_new else None
    )
    course.short_description = form.short_description.data
    course.description = form.description.data
    course.thumbnail = form.thumbnail.data
    course.promo_video_url = form.promo_video_url.data
    course.price = form.price.data
    course.discount_price = form.discount_price.data
    course.currency = form.currency.data
    course.difficulty = form.difficulty.data
    course.category_id = form.category_id.data or None
    course.learning_objectives = form.learning_objectives.data
    course.requirements = form.requirements.data
    course.target_audience = form.target_audience.data
    course.published = form.published.data
    course.featured = form.featured.data
    course.meta_title = form.meta_title.data
    course.meta_description = form.meta_description.data
    course.og_image = form.og_image.data


@bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@admin_required
def course_delete(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash("Course deleted.", "info")
    return redirect(url_for("admin.courses_list"))


@bp.route("/courses/<int:course_id>/toggle-published", methods=["POST"])
@admin_required
def course_toggle_published(course_id):
    course = Course.query.get_or_404(course_id)
    course.published = not course.published
    db.session.commit()
    return redirect(url_for("admin.courses_list"))


@bp.route("/course-categories", methods=["GET", "POST"])
@admin_required
def course_categories():
    form = CourseCategoryForm()
    if form.validate_on_submit():
        category = CourseCategory()
        category.name = form.name.data
        base_slug = form.slug.data or form.name.data or ""
        category.slug = unique_slug(CourseCategory, base_slug)
        category.description = form.description.data

        db.session.add(category)
        db.session.commit()
        flash("Category created.", "success")
        return redirect(url_for("admin.course_categories"))
    categories = CourseCategory.query.order_by(CourseCategory.name).all()
    return render_template("admin/course_categories.html", form=form, categories=categories)


# --- Sections ---------------------------------------------------------

@bp.route("/courses/<int:course_id>/sections/add", methods=["POST"])
@admin_required
def section_add(course_id):
    course = Course.query.get_or_404(course_id)
    form = CourseSectionForm()
    if form.validate_on_submit():
        course_section = CourseSection()
        course_section.course_id = course.id
        course_section.title = form.title.data
        course_section.display_order = form.display_order.data or len(course.sections)

        db.session.add(course_section)

        db.session.commit()
        flash("Section added.", "success")
    else:
        flash("Could not add section — please check the form.", "error")
    return redirect(url_for("admin.course_edit", course_id=course.id))


@bp.route("/courses/<int:course_id>/sections/<int:section_id>/delete", methods=["POST"])
@admin_required
def section_delete(course_id, section_id):
    section = CourseSection.query.filter_by(id=section_id, course_id=course_id).first_or_404()
    db.session.delete(section)
    db.session.commit()
    flash("Section deleted.", "info")
    return redirect(url_for("admin.course_edit", course_id=course_id))


# --- Lessons ------------------------------------------------------------

@bp.route("/courses/<int:course_id>/sections/<int:section_id>/lessons/add", methods=["POST"])
@admin_required
def lesson_add(course_id, section_id):
    section = CourseSection.query.filter_by(id=section_id, course_id=course_id).first_or_404()
    form = LessonForm()
    if form.validate_on_submit():
        slug_source = (form.slug.data or form.title.data or "")
        slug = slugify(slug_source)
        # Ensure slug is unique within this section.
        existing_slugs = {lesson.slug for lesson in section.lessons}
        base_slug, counter = slug, 2
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1

        lesson = Lesson()
        lesson.section_id = section.id
        lesson.title = form.title.data
        lesson.slug = slug
        lesson.description = form.description.data
        lesson.video_url = form.video_url.data
        lesson.duration_seconds = form.duration_seconds.data or 0
        lesson.display_order = form.display_order.data or len(section.lessons)
        lesson.is_free_preview = form.is_free_preview.data
        lesson.published = form.published.data

        db.session.add(lesson)

        db.session.commit()
        flash("Lesson added.", "success")
    else:
        flash("Could not add lesson — please check the form.", "error")
    return redirect(url_for("admin.course_edit", course_id=course_id))


@bp.route("/courses/<int:course_id>/lessons/<int:lesson_id>/delete", methods=["POST"])
@admin_required
def lesson_delete(course_id, lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    if lesson.section.course_id != course_id:
        abort(404)
    db.session.delete(lesson)
    db.session.commit()
    flash("Lesson deleted.", "info")
    return redirect(url_for("admin.course_edit", course_id=course_id))


# =====================================================================
# Blog
# =====================================================================

@bp.route("/blog")
@admin_required
def blog_list():
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template("admin/blog_list.html", posts=posts)


def _blog_form_with_categories() -> BlogPostForm:
    form = BlogPostForm()
    form.category_id.choices = [(0, "— None —")] + [
        (c.id, c.name) for c in BlogCategory.query.order_by(BlogCategory.name).all()
    ]
    return form


@bp.route("/blog/new", methods=["GET", "POST"])
@admin_required
def blog_create():
    form = _blog_form_with_categories()
    if form.validate_on_submit():
        post = BlogPost()
        post.title = form.title.data
        post.author_id = current_user.id

        _apply_blog_form(post, form, is_new=True)
        db.session.add(post)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_uploaded_image(post.featured_image)  # don't orphan the new file
            raise
        flash("Blog post created.", "success")
        return redirect(url_for("admin.blog_list"))
    return render_template("admin/blog_form.html", form=form, post=None)


@bp.route("/blog/<int:post_id>/edit", methods=["GET", "POST"])
@admin_required
def blog_edit(post_id):
    post = BlogPost.query.get_or_404(post_id)
    if request.method == "GET":
        form = BlogPostForm(obj=post)
        form.category_id.choices = [(0, "— None —")] + [
            (c.id, c.name) for c in BlogCategory.query.order_by(BlogCategory.name).all()
        ]
        form.category_id.data = post.category_id or 0
        form.tags_csv.data = ", ".join(t.name for t in post.tags)
    else:
        form = _blog_form_with_categories()

    if form.validate_on_submit():
        previous_image = post.featured_image
        _apply_blog_form(post, form, is_new=False)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            if post.featured_image != previous_image:
                delete_uploaded_image(post.featured_image)
            raise
        # Only after the new value is safely stored: drop a replaced upload.
        if previous_image != post.featured_image:
            delete_uploaded_image(previous_image)
        flash("Blog post updated.", "success")
        return redirect(url_for("admin.blog_list"))
    return render_template("admin/blog_form.html", form=form, post=post)


def _apply_blog_form(post: BlogPost, form: BlogPostForm, is_new: bool) -> None:
    from datetime import datetime, timezone

    post.title = form.title.data
    # ensure a str is passed to unique_slug (form fields may be None)
    base_slug: str = form.slug.data or form.title.data or ""
    post.slug = unique_slug(BlogPost, base_slug, current_id=post.id if not is_new else None)
    post.excerpt = form.excerpt.data
    # Stored as raw Markdown; rendered + sanitized at display time by the
    # `markdown` Jinja filter (app/blog/render.py).
    post.body = form.body.data

    # Featured image: a new upload wins, then "remove", then the URL field.
    # The upload was already validated and re-encoded during form validation.
    if form.processed_image is not None:
        post.featured_image = store_image(form.processed_image, "blog")
    elif form.remove_featured_image.data:
        post.featured_image = None
    else:
        post.featured_image = form.featured_image.data or None

    post.category_id = form.category_id.data or None

    was_published = post.published
    post.published = form.published.data
    if post.published and not was_published:
        post.published_at = datetime.now(timezone.utc)

    post.meta_title = form.meta_title.data
    post.meta_description = form.meta_description.data
    post.og_image = form.og_image.data

    # ensure a str is passed to parse_csv_names (WTForms field may be None)
    names = parse_csv_names(form.tags_csv.data or "")
    # SQLAlchemy relationship attributes are typed as RelationshipProperty, so cast
    # the assigned list to Any to satisfy static type checkers while preserving runtime behavior.
    from typing import Any, cast

    post.tags = cast(Any, [get_or_create_by_name(BlogTag, name) for name in names])


@bp.route("/blog/<int:post_id>/delete", methods=["POST"])
@admin_required
def blog_delete(post_id):
    post = BlogPost.query.get_or_404(post_id)
    image = post.featured_image
    db.session.delete(post)
    db.session.commit()
    delete_uploaded_image(image)
    flash("Blog post deleted.", "info")
    return redirect(url_for("admin.blog_list"))


@bp.route("/blog-categories", methods=["GET", "POST"])
@admin_required
def blog_categories():
    form = BlogCategoryForm()
    if form.validate_on_submit():
        blog_category = BlogCategory()
        blog_category.name = form.name.data
        blog_category.slug = unique_slug(BlogCategory, form.slug.data or form.name.data or "")
        db.session.add(blog_category)

        db.session.commit()
        flash("Category created.", "success")
        return redirect(url_for("admin.blog_categories"))
    categories = BlogCategory.query.order_by(BlogCategory.name).all()
    return render_template("admin/blog_categories.html", form=form, categories=categories)


# =====================================================================
# Testimonials
# =====================================================================

@bp.route("/testimonials")
@admin_required
def testimonials_list():
    items = Testimonial.query.order_by(Testimonial.display_order).all()
    return render_template("admin/testimonials_list.html", testimonials=items)


@bp.route("/testimonials/new", methods=["GET", "POST"])
@admin_required
def testimonial_create():
    form = TestimonialForm()
    if form.validate_on_submit():
        testimonial = Testimonial()
        _apply_testimonial_form(testimonial, form)
        db.session.add(testimonial)
        db.session.commit()
        flash("Testimonial created.", "success")
        return redirect(url_for("admin.testimonials_list"))
    return render_template("admin/testimonial_form.html", form=form, testimonial=None)


@bp.route("/testimonials/<int:testimonial_id>/edit", methods=["GET", "POST"])
@admin_required
def testimonial_edit(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    form = TestimonialForm(obj=testimonial)
    if form.validate_on_submit():
        _apply_testimonial_form(testimonial, form)
        db.session.commit()
        flash("Testimonial updated.", "success")
        return redirect(url_for("admin.testimonials_list"))
    return render_template("admin/testimonial_form.html", form=form, testimonial=testimonial)


def _apply_testimonial_form(testimonial: Testimonial, form: TestimonialForm) -> None:
    testimonial.author_name = form.author_name.data
    testimonial.author_title = form.author_title.data
    testimonial.author_avatar = form.author_avatar.data
    testimonial.quote = form.quote.data
    testimonial.rating = form.rating.data
    testimonial.approved = form.approved.data
    testimonial.featured = form.featured.data
    testimonial.display_order = form.display_order.data or 0


@bp.route("/testimonials/<int:testimonial_id>/delete", methods=["POST"])
@admin_required
def testimonial_delete(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    db.session.delete(testimonial)
    db.session.commit()
    flash("Testimonial deleted.", "info")
    return redirect(url_for("admin.testimonials_list"))


@bp.route("/testimonials/<int:testimonial_id>/toggle-approved", methods=["POST"])
@admin_required
def testimonial_toggle_approved(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    testimonial.approved = not testimonial.approved
    db.session.commit()
    return redirect(url_for("admin.testimonials_list"))
