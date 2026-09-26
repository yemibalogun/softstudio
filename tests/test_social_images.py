"""
Every page carries a social card image, and it is the image uploaded for
that piece of content.

The rule across the site: the uploaded image wins, the "Social image URL"
field is only a fallback, values are always absolute (Facebook, WhatsApp,
LinkedIn and X ignore relative paths), and a page with no image of its own
falls back to the site's default card rather than an empty tag.
"""
import re

import pytest

from app.models import BlogPost, Course, CourseCategory, Product, Project

UPLOAD = "/static/images/uploads/blog/0123456789abcdef0123456789abcdef.jpg"


def _meta(html, attr, value):
    pattern = (
        rf'<meta[^>]*{attr}="{re.escape(value)}"[^>]*content="([^"]*)"'
        rf'|<meta[^>]*content="([^"]*)"[^>]*{attr}="{re.escape(value)}"'
    )
    match = re.search(pattern, html)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def og(html):
    return _meta(html, "property", "og:image")


def twitter(html):
    return _meta(html, "name", "twitter:image")


@pytest.fixture()
def post(db):
    item = BlogPost(
        title="Just automate it", slug="just-automate-it", excerpt="How.",
        body="Body.", featured_image=UPLOAD, published=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


# ---------------------------------------------------------------------
# Blog: the featured image uploaded with the post
# ---------------------------------------------------------------------

def test_blog_post_shares_its_uploaded_image(client, app, post):
    html = client.get(f"/blog/{post.slug}").data.decode()
    expected = app.config["SITE_URL"].rstrip("/") + UPLOAD
    assert og(html) == expected
    assert twitter(html) == expected, "the meta image must match the social image"


def test_uploaded_image_wins_over_the_social_url_field(client, app, db, post):
    """The field is a fallback: filling it must not hide the uploaded image."""
    post.og_image = "https://jaybalostudio.com/blog/just-automate-it/og-image.jpg"
    db.session.commit()

    html = client.get(f"/blog/{post.slug}").data.decode()
    assert og(html) == app.config["SITE_URL"].rstrip("/") + UPLOAD


def test_social_url_field_is_used_when_nothing_was_uploaded(client, db, post):
    post.featured_image = None
    post.og_image = "https://cdn.example.com/card.png"
    db.session.commit()

    assert og(client.get(f"/blog/{post.slug}").data.decode()) == "https://cdn.example.com/card.png"


def test_post_without_any_image_falls_back_to_the_site_card(client, app, db, post):
    post.featured_image = None
    db.session.commit()

    image = og(client.get(f"/blog/{post.slug}").data.decode())
    assert image.startswith(app.config["SITE_URL"].rstrip("/"))
    assert image.endswith("og-default.png")


# ---------------------------------------------------------------------
# The same rule on the other content types
# ---------------------------------------------------------------------

def test_project_shares_its_uploaded_image(client, app, db):
    project = Project(
        title="Clinic queue manager", slug="clinic-queue-manager",
        short_description="Replaced a paper ticket system.",
        thumbnail="/static/images/uploads/projects/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.webp",
        published=True,
    )
    db.session.add(project)
    db.session.commit()

    html = client.get(f"/projects/{project.slug}").data.decode()
    assert og(html) == app.config["SITE_URL"].rstrip("/") + project.thumbnail


def test_course_shares_its_uploaded_thumbnail(client, app, db):
    category = CourseCategory(name="Flask", slug="flask")
    db.session.add(category)
    db.session.flush()
    course = Course(
        title="Flask in production", slug="flask-in-production",
        short_description="Ship it.", description="Long.", price=1000, currency="NGN",
        difficulty="intermediate", published=True, category_id=category.id,
        thumbnail="/static/images/uploads/courses/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.webp",
    )
    db.session.add(course)
    db.session.commit()

    html = client.get(f"/courses/{course.slug}").data.decode()
    assert og(html) == app.config["SITE_URL"].rstrip("/") + course.thumbnail


def test_product_shares_its_uploaded_image(client, app, db):
    product = Product(
        title="Flask Production MCP", slug="flask-production-mcp",
        short_description="Ship Flask apps without guesswork.",
        image="/static/images/uploads/products/cccccccccccccccccccccccccccccccc.webp",
        og_image="https://cdn.example.com/other.png",
        published=True,
    )
    db.session.add(product)
    db.session.commit()

    html = client.get(f"/products/{product.slug}").data.decode()
    assert og(html) == app.config["SITE_URL"].rstrip("/") + product.image


# ---------------------------------------------------------------------
# Pages with no content image of their own still carry a card
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    ["/", "/about", "/blog/", "/projects/", "/services/", "/courses/", "/contact/"],
)
def test_every_page_has_an_absolute_social_image(client, app, path):
    html = client.get(path).data.decode()
    image = og(html)
    assert image, f"{path} has no og:image"
    assert image.startswith(("http://", "https://")), f"{path} og:image is not absolute: {image}"
    assert twitter(html) == image
