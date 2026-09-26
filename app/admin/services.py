import bleach

from app.extensions import db
from app.admin.forms import slugify

# NOTE: blog post bodies moved to Markdown - they are rendered and
# sanitized at display time by app/blog/render.py, not here. This
# allowlist / sanitize_html() is kept for any other admin-authored HTML
# field that may need it.
ALLOWED_HTML_TAGS = [
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "code",
    "strong", "em", "a", "img", "br", "hr",
]
ALLOWED_HTML_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title"],
}


def sanitize_html(value: str) -> str:
    """Strip any tag/attribute not in the allowlist from admin-authored HTML."""
    if not value:
        return value
    return bleach.clean(
        value, tags=ALLOWED_HTML_TAGS, attributes=ALLOWED_HTML_ATTRS, strip=True
    )


def unique_slug(model, base_value: str, current_id: int | None = None) -> str:
    """
    Generate a unique slug for `model` from `base_value`, appending
    -2, -3, ... on collision. Excludes the row being edited (current_id)
    so saving an unchanged slug doesn't false-collide with itself.
    """
    base = slugify(base_value) or "item"
    slug = base
    counter = 2
    while True:
        query = model.query.filter_by(slug=slug)
        if current_id is not None:
            query = query.filter(model.id != current_id)
        if not query.first():
            return slug
        slug = f"{base}-{counter}"
        counter += 1


def parse_csv_names(value: str) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def get_or_create_by_name(model, name: str, extra_defaults=None):
    """Return an existing named/slugged record or create a new one."""
    name = name.strip()

    if not name:
        raise ValueError("Name cannot be empty.")

    slug = slugify(name)

    # Check the slug as well as the name because the database enforces
    # uniqueness on the slug. This prevents duplicate-key errors when
    # two differently formatted names generate the same slug.
    instance = model.query.filter(
        db.or_(
            model.name == name,
            model.slug == slug,
        )
    ).first()

    if instance:
        return instance

    kwargs = {"name": name, "slug": slug}

    if extra_defaults:
        kwargs.update(extra_defaults)

    instance = model(**kwargs)
    db.session.add(instance)
    db.session.flush()

    return instance


def get_or_create_all_by_name(model, names) -> list:
    """
    Resolve a list of names to records, with no repeats.

    Two names in one list can resolve to the same record, because
    get_or_create_by_name matches on slug as well as name: "Flask" and
    "flask" are one tag. The association tables for tags and technologies
    have a composite primary key over (parent_id, child_id), so assigning
    the same record twice fails on insert. Order is kept, so the first
    spelling a user typed is the one that decides position.
    """
    resolved: dict[str, object] = {}
    for name in names:
        instance = get_or_create_by_name(model, name)
        resolved.setdefault(instance.slug, instance)
    return list(resolved.values())
