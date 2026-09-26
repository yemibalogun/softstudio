"""
Creating tags and technologies by name tolerates names that collide.

`blog_tags.slug` is unique but `blog_tags.name` is not, so looking a record
up by name alone is not enough: "Flask" and "flask " are different names
that slugify to the same slug. Matching on name only meant the second one
was inserted, the unique index rejected it, and saving the post failed with
an IntegrityError - which is what produced a 502 when posting a blog on
2026-09-23.
"""
import pytest

from app.admin.services import get_or_create_by_name
from app.models import BlogPost, BlogTag, Technology
from tests.conftest import login


def _login_admin(client, admin_user):
    return login(client, "admin@example.com", "correcthorsebattery")


# ---------------------------------------------------------------------
# get_or_create_by_name
# ---------------------------------------------------------------------

def test_the_same_name_returns_the_same_record(db):
    first = get_or_create_by_name(BlogTag, "Flask")
    db.session.commit()
    again = get_or_create_by_name(BlogTag, "Flask")
    assert again.id == first.id
    assert BlogTag.query.count() == 1


@pytest.mark.parametrize("second", ["flask", "FLASK", "  Flask  ", "flask"])
def test_names_that_share_a_slug_reuse_the_existing_record(db, second):
    """The regression: each of these used to hit the unique slug index."""
    first = get_or_create_by_name(BlogTag, "Flask")
    db.session.commit()

    found = get_or_create_by_name(BlogTag, second)
    db.session.commit()

    assert found.id == first.id
    assert BlogTag.query.count() == 1


def test_surrounding_whitespace_is_not_stored(db):
    tag = get_or_create_by_name(BlogTag, "  Web Development  ")
    db.session.commit()
    assert tag.name == "Web Development"
    assert tag.slug == "web-development"


def test_a_blank_name_is_rejected(db):
    for blank in ["", "   ", "\t"]:
        with pytest.raises(ValueError):
            get_or_create_by_name(BlogTag, blank)


def test_distinct_names_still_create_distinct_records(db):
    get_or_create_by_name(BlogTag, "Flask")
    get_or_create_by_name(BlogTag, "Django")
    db.session.commit()
    assert BlogTag.query.count() == 2


def test_extra_defaults_are_applied_on_creation(db):
    tech = get_or_create_by_name(Technology, "Postgres", extra_defaults={"icon": "postgres.svg"})
    db.session.commit()
    assert tech.icon == "postgres.svg"


# ---------------------------------------------------------------------
# Through the admin form - the path that actually broke
# ---------------------------------------------------------------------

def test_posting_a_blog_with_colliding_tags_succeeds(client, admin_user, db):
    """
    Regression for the 502 on 2026-09-23: "Flask" and "flask" in one tag
    list slugify identically, and the insert used to violate the unique
    index on blog_tags.slug while saving the post.
    """
    _login_admin(client, admin_user)

    resp = client.post(
        "/admin/blog/new",
        data={
            "title": "Shipping Flask",
            "body": "<p>Content.</p>",
            "category_id": 0,
            "tags_csv": "Flask, flask,  FLASK , python",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    post = BlogPost.query.filter_by(title="Shipping Flask").first()
    assert post is not None, "the post was not saved"
    slugs = sorted(t.slug for t in post.tags)
    assert slugs == ["flask", "python"], f"expected the colliding tags to merge, got {slugs}"
    assert BlogTag.query.filter_by(slug="flask").count() == 1


def test_saving_a_project_with_colliding_technologies_succeeds(client, admin_user, db):
    """
    Same defect class on the project form: project_technologies also has a
    composite primary key, so a repeated technology fails on insert.
    """
    _login_admin(client, admin_user)

    resp = client.post(
        "/admin/projects/new",
        data={
            "title": "Queue Manager",
            "short_description": "Replaced a paper ticket system.",
            "status": "live",
            "display_order": 0,
            "technologies_csv": "Flask, flask, PostgreSQL,  postgresql ",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    from app.models import Project
    project = Project.query.filter_by(title="Queue Manager").first()
    assert project is not None, "the project was not saved"
    assert sorted(t.slug for t in project.technologies) == ["flask", "postgresql"]
