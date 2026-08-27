from app.extensions import db
from app.admin.forms import slugify


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
    instance = model.query.filter_by(name=name).first()
    if instance:
        return instance
    kwargs = {"name": name, "slug": slugify(name)}
    if extra_defaults:
        kwargs.update(extra_defaults)
    instance = model(**kwargs)
    db.session.add(instance)
    db.session.flush()
    return instance
