from app.models import (
    Project, ProjectImage, Course, CourseCategory, BlogPost, BlogCategory, Testimonial,
)
from tests.conftest import login


def _login_admin(client, admin_user):
    return login(client, "admin@example.com", "correcthorsebattery")


def _csrf_token(html: str) -> str:
    import re

    match = re.search(r'name="csrf_token".*?value="([^"]+)"', html)
    assert match, "expected a CSRF token in the rendered form"
    return match.group(1)


# =====================================================================
# Projects
# =====================================================================

def test_project_create_and_list(client, admin_user):
    _login_admin(client, admin_user)
    resp = client.post(
        "/admin/projects/new",
        data={
            "title": "New Dashboard",
            "short_description": "A dashboard for tracking things.",
            "status": "live",
            "display_order": 0,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    project = Project.query.filter_by(title="New Dashboard").first()
    assert project is not None
    assert project.slug == "new-dashboard"

    list_resp = client.get("/admin/projects")
    assert b"New Dashboard" in list_resp.data


def test_project_slug_uniqueness_on_collision(client, admin_user, db):
    _login_admin(client, admin_user)
    for _ in range(2):
        client.post(
            "/admin/projects/new",
            data={"title": "Duplicate Title", "short_description": "desc", "status": "live"},
            follow_redirects=True,
        )
    slugs = sorted(p.slug for p in Project.query.filter(Project.title == "Duplicate Title").all())
    assert slugs == ["duplicate-title", "duplicate-title-2"]


def test_project_edit_updates_fields(client, admin_user, db):
    _login_admin(client, admin_user)
    project = Project(title="Old Title", slug="old-title", short_description="old", status="live")
    db.session.add(project)
    db.session.commit()

    client.post(
        f"/admin/projects/{project.id}/edit",
        data={
            "title": "Updated Title",
            "slug": "old-title",
            "short_description": "updated description",
            "status": "live",
        },
        follow_redirects=True,
    )
    db.session.refresh(project)
    assert project.title == "Updated Title"
    assert project.short_description == "updated description"


def test_project_delete(client, admin_user, db):
    _login_admin(client, admin_user)
    project = Project(title="Delete Me", slug="delete-me", short_description="x", status="live")
    db.session.add(project)
    db.session.commit()
    project_id = project.id

    client.post(f"/admin/projects/{project_id}/delete", follow_redirects=True)
    from app.extensions import db
    assert db.session.get(Project, project_id) is None


def test_project_toggle_published(client, admin_user, db):
    _login_admin(client, admin_user)
    project = Project(title="Toggle Me", slug="toggle-me", short_description="x", published=False)
    db.session.add(project)
    db.session.commit()

    client.post(f"/admin/projects/{project.id}/toggle-published", follow_redirects=True)
    db.session.refresh(project)
    assert project.published is True


def test_project_crud_blocked_for_non_admin(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get("/admin/projects")
    assert resp.status_code == 403
    resp = client.post("/admin/projects/new", data={"title": "x", "short_description": "x"})
    assert resp.status_code == 403


def _make_project(db):
    project = Project(
        title="Gallery Project", slug="gallery-project",
        short_description="Has a gallery.", published=True,
    )
    db.session.add(project)
    db.session.commit()
    return project


def test_project_image_add_stores_url_and_alt_text(client, admin_user, db):
    """
    Regression: this route used to read

        project_image.project_id=project.id, image_url=image_url, alt_text=alt_text

    which Python parses as a chained assignment, not three keyword
    arguments, so every submission raised ValueError instead of saving
    the image.
    """
    _login_admin(client, admin_user)
    project = _make_project(db)

    resp = client.post(
        f"/admin/projects/{project.id}/images/add",
        data={"image_url": "/static/images/uploads/projects/gallery-1.webp",
              "alt_text": "The queue dashboard"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    images = ProjectImage.query.filter_by(project_id=project.id).all()
    assert len(images) == 1
    image = images[0]
    assert image.image_url == "/static/images/uploads/projects/gallery-1.webp"
    assert image.alt_text == "The queue dashboard"
    assert image.display_order == 0


def test_project_images_get_increasing_display_order(client, admin_user, db):
    _login_admin(client, admin_user)
    project = _make_project(db)

    for n in (1, 2, 3):
        client.post(
            f"/admin/projects/{project.id}/images/add",
            data={"image_url": f"/static/images/uploads/projects/g{n}.webp", "alt_text": f"Shot {n}"},
            follow_redirects=True,
        )

    orders = [i.display_order for i in ProjectImage.query.filter_by(project_id=project.id)
              .order_by(ProjectImage.display_order).all()]
    assert orders == [0, 1, 2]


def test_project_image_add_ignores_a_blank_url(client, admin_user, db):
    _login_admin(client, admin_user)
    project = _make_project(db)

    resp = client.post(
        f"/admin/projects/{project.id}/images/add",
        data={"image_url": "   ", "alt_text": "nothing"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert ProjectImage.query.filter_by(project_id=project.id).count() == 0


# =====================================================================
# Courses (sections + lessons)
# =====================================================================

def test_course_create(client, admin_user):
    _login_admin(client, admin_user)
    resp = client.post(
        "/admin/courses/new",
        data={
            "title": "New Course",
            "short_description": "Learn things.",
            "price": "10000",
            "currency": "NGN",
            "difficulty": "beginner",
            "category_id": 0,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    course = Course.query.filter_by(title="New Course").first()
    assert course is not None
    assert course.slug == "new-course"


def test_course_category_create(client, admin_user):
    _login_admin(client, admin_user)
    client.post("/admin/course-categories", data={"name": "Automation", "slug": ""}, follow_redirects=True)
    category = CourseCategory.query.filter_by(name="Automation").first()
    assert category is not None
    assert category.slug == "automation"


def test_add_section_and_lesson_to_course(client, admin_user, db):
    _login_admin(client, admin_user)
    course = Course(title="Curriculum Course", slug="curriculum-course", short_description="x", price=0)
    db.session.add(course)
    db.session.commit()

    client.post(
        f"/admin/courses/{course.id}/sections/add",
        data={"title": "Section One", "display_order": 0},
        follow_redirects=True,
    )
    db.session.refresh(course)
    assert len(course.sections) == 1
    section = course.sections[0]

    client.post(
        f"/admin/courses/{course.id}/sections/{section.id}/lessons/add",
        data={
            "title": "Lesson One", "slug": "", "duration_seconds": 0, "display_order": 0,
            "is_free_preview": "y",
        },
        follow_redirects=True,
    )
    db.session.refresh(section)
    assert len(section.lessons) == 1
    assert section.lessons[0].slug == "lesson-one"
    assert section.lessons[0].is_free_preview is True


def test_lesson_slug_unique_within_section(client, admin_user, db):
    _login_admin(client, admin_user)
    course = Course(title="Dup Lesson Course", slug="dup-lesson-course", short_description="x", price=0)
    db.session.add(course)
    db.session.commit()
    from app.models import CourseSection

    section = CourseSection(course_id=course.id, title="Section")
    db.session.add(section)
    db.session.commit()

    for _ in range(2):
        client.post(
            f"/admin/courses/{course.id}/sections/{section.id}/lessons/add",
            data={"title": "Same Title", "slug": "", "duration_seconds": 0, "display_order": 0},
            follow_redirects=True,
        )
    db.session.refresh(section)
    slugs = sorted(lesson.slug for lesson in section.lessons)
    assert slugs == ["same-title", "same-title-2"]


def test_delete_section_cascades_lessons(client, admin_user, db):
    _login_admin(client, admin_user)
    course = Course(title="Cascade Course", slug="cascade-course", short_description="x", price=0)
    db.session.add(course)
    db.session.commit()
    from app.models import CourseSection, Lesson

    section = CourseSection(course_id=course.id, title="Section")
    db.session.add(section)
    db.session.commit()
    lesson = Lesson(section_id=section.id, title="L1", slug="l1")
    db.session.add(lesson)
    db.session.commit()
    lesson_id = lesson.id

    client.post(
        f"/admin/courses/{course.id}/sections/{section.id}/delete", follow_redirects=True
    )
    from app.extensions import db
    assert db.session.get(Lesson, lesson_id) is None


def test_course_crud_blocked_for_non_admin(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get("/admin/courses")
    assert resp.status_code == 403


# =====================================================================
# Blog
# =====================================================================

def test_blog_post_create_with_tags(client, admin_user):
    _login_admin(client, admin_user)
    resp = client.post(
        "/admin/blog/new",
        data={
            "title": "How Flask Works",
            "body": "<p>Content here.</p>",
            "category_id": 0,
            "tags_csv": "flask, python, tutorials",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    post = BlogPost.query.filter_by(title="How Flask Works").first()
    assert post is not None
    assert {t.name for t in post.tags} == {"flask", "python", "tutorials"}


def test_blog_category_create(client, admin_user):
    _login_admin(client, admin_user)
    client.post("/admin/blog-categories", data={"name": "Tutorials", "slug": ""}, follow_redirects=True)
    assert BlogCategory.query.filter_by(name="Tutorials").first() is not None


def test_blog_publish_sets_published_at(client, admin_user, db):
    _login_admin(client, admin_user)
    post = BlogPost(title="Draft Post", slug="draft-post", body="content", published=False)
    db.session.add(post)
    db.session.commit()
    assert post.published_at is None

    client.post(
        f"/admin/blog/{post.id}/edit",
        data={
            "title": "Draft Post", "slug": "draft-post", "body": "content",
            "category_id": 0, "published": "y",
        },
        follow_redirects=True,
    )
    db.session.refresh(post)
    assert post.published is True
    assert post.published_at is not None


def test_blog_crud_blocked_for_non_admin(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get("/admin/blog")
    assert resp.status_code == 403


# =====================================================================
# Testimonials
# =====================================================================

def test_testimonial_create_and_approve_toggle(client, admin_user):
    _login_admin(client, admin_user)
    client.post(
        "/admin/testimonials/new",
        data={"author_name": "Jane Client", "quote": "Great work!", "display_order": 0},
        follow_redirects=True,
    )
    testimonial = Testimonial.query.filter_by(author_name="Jane Client").first()
    assert testimonial is not None
    assert testimonial.approved is False

    client.post(f"/admin/testimonials/{testimonial.id}/toggle-approved", follow_redirects=True)
    from app.extensions import db

    db.session.refresh(testimonial)
    assert testimonial.approved is True


def test_testimonial_crud_blocked_for_non_admin(client, user):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.get("/admin/testimonials")
    assert resp.status_code == 403
