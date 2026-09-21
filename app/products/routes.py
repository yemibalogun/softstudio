import re

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.models import Product, WaitlistSubscriber
from app.products.forms import WaitlistForm
from app.seo import absolute_url, default_social_image_url, site_base_url

bp = Blueprint("products", __name__)

# Slugs this app generates (admin/services.py:unique_slug -> slugify).
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG_LENGTH = 180

# Attribution labels are free text from a URL, so they are normalized to a
# short, predictable token before being stored or shown in the admin.
_SOURCE_CLEAN_RE = re.compile(r"[^a-z0-9_.-]+")


def _clean_attribution(value: str | None, max_length: int = 60) -> str | None:
    if not value:
        return None
    cleaned = _SOURCE_CLEAN_RE.sub("-", value.strip().lower()).strip("-")
    return cleaned[:max_length] or None


def _referrer_host() -> str | None:
    referrer = request.referrer or ""
    if not referrer:
        return None
    from urllib.parse import urlsplit

    host = urlsplit(referrer).hostname or ""
    if not host or host == urlsplit(site_base_url()).hostname:
        return None  # our own pages are not a traffic source
    return _clean_attribution(host.removeprefix("www."))


def _attribution(form: WaitlistForm | None = None) -> dict[str, str | None]:
    """
    Where this visitor came from. Reads the form's carried-through values
    first, then the current query string, then the referring site, and
    finally falls back to "direct". Never required.
    """
    def pick(field: str) -> str | None:
        from_form = getattr(form, field).data if form is not None else None
        return _clean_attribution(from_form or request.args.get(field), max_length=120)

    source = pick("utm_source") or _referrer_host() or "direct"
    return {
        "source": source[:60],
        "utm_medium": pick("utm_medium"),
        "utm_campaign": pick("utm_campaign"),
        "utm_content": pick("utm_content"),
    }


def _form_defaults() -> dict[str, str | None]:
    """
    Prefill the form's hidden campaign fields, so parameters from a share
    link survive the POST. The model calls it `source`; the form field is
    `utm_source`.
    """
    attribution = _attribution()
    return {
        "utm_source": attribution["source"],
        "utm_medium": attribution["utm_medium"],
        "utm_campaign": attribution["utm_campaign"],
        "utm_content": attribution["utm_content"],
    }


def _published_product_or_404(slug: str) -> Product:
    if not slug or len(slug) > MAX_SLUG_LENGTH or not SLUG_RE.match(slug):
        abort(404)
    product = Product.query.filter_by(slug=slug, published=True).first()
    if product is None:
        abort(404)
    return product


def _render_detail(product: Product, form: WaitlistForm, joined: bool = False, status: int = 200):
    """One place that builds the public URLs every product page needs."""
    product_url = f"{site_base_url()}{url_for('products.detail', slug=product.slug)}"
    product_image_url = absolute_url(product.social_image) or default_social_image_url()
    html = render_template(
        "products/detail.html",
        product=product,
        form=form,
        joined=joined,
        product_url=product_url,
        product_image_url=product_image_url,
    )
    return html, status


@bp.route("/")
def index():
    products = (
        Product.query.filter_by(published=True)
        .order_by(Product.display_order, Product.created_at.desc())
        .all()
    )
    return render_template("products/index.html", products=products)


@bp.route("/<slug>")
def detail(slug):
    product = _published_product_or_404(slug)
    form = WaitlistForm(data=_form_defaults())
    joined = request.args.get("joined") == "1"
    return _render_detail(product, form, joined=joined)


@bp.route("/<slug>/waitlist", methods=["POST"])
@limiter.limit("10 per hour")
def waitlist(slug):
    product = _published_product_or_404(slug)
    if not product.waitlist_enabled:
        abort(404)

    form = WaitlistForm()
    if not form.validate_on_submit():
        return _render_detail(product, form, status=400)

    if form.website.data:
        # Honeypot tripped: behave exactly like success, store nothing.
        return redirect(url_for("products.detail", slug=product.slug, joined=1) + "#waitlist")

    email = (form.email.data or "").strip().lower()
    attribution = _attribution(form)

    subscriber = WaitlistSubscriber(
        product_id=product.id,
        email=email,
        name=(form.name.data or "").strip() or None,
        ip_address=request.remote_addr,
        **attribution,
    )
    db.session.add(subscriber)
    try:
        db.session.commit()
    except IntegrityError:
        # Already on this product's list (unique product_id+email). Joining
        # twice is not an error for the visitor, and re-reporting it would
        # leak whether an address is registered.
        db.session.rollback()

    return redirect(url_for("products.detail", slug=product.slug, joined=1) + "#waitlist")
