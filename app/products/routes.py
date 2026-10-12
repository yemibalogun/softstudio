import re

from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.downloads import (
    format_size,
    hash_download_token,
    looks_like_token,
    new_download_token,
)
from app.emails import send_product_download_link
from app.extensions import db, limiter
from app.models import DownloadRequest, Product, WaitlistSubscriber, utcnow
from app.products.forms import DownloadConfirmForm, DownloadRequestForm, WaitlistForm
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


def _render_detail(
    product: Product,
    form: WaitlistForm | None = None,
    joined: bool = False,
    status: int = 200,
    download_form: DownloadRequestForm | None = None,
    download_state: str | None = None,
):
    """One place that builds the public URLs every product page needs."""
    product_url = f"{site_base_url()}{url_for('products.detail', slug=product.slug)}"
    product_image_url = absolute_url(product.social_image) or default_social_image_url()
    html = render_template(
        "products/detail.html",
        product=product,
        form=form or WaitlistForm(data=_form_defaults()),
        joined=joined,
        download_form=download_form or _download_form(data=_form_defaults()),
        download_state=download_state,
        download_offered=product.download_offered,
        download_size=format_size(product.download_size),
        download_valid_days=max(1, current_app.config["DOWNLOAD_LINK_MAX_AGE"] // 86400),
        product_url=product_url,
        product_image_url=product_image_url,
    )
    return html, status


def _download_form(**kwargs) -> DownloadRequestForm:
    """
    Prefixed, because the waitlist form can be on the same page: without it
    both would render inputs with id="email", and each label would point at
    the wrong field.
    """
    return DownloadRequestForm(prefix="download", **kwargs)


@bp.route("/")
def index():
    products = (
        Product.query.filter_by(published=True)
        .order_by(Product.display_order, Product.created_at.desc())
        .all()
    )
    return render_template("products/index.html", products=products)


# Outcomes of a download request, carried through the redirect.
_DOWNLOAD_STATES = {"sent", "failed"}


@bp.route("/<slug>")
def detail(slug):
    product = _published_product_or_404(slug)
    joined = request.args.get("joined") == "1"
    requested = request.args.get("requested")
    return _render_detail(
        product,
        joined=joined,
        download_state=requested if requested in _DOWNLOAD_STATES else None,
    )


@bp.route("/<slug>/waitlist", methods=["POST"])
@limiter.limit("10 per hour")
def waitlist(slug):
    product = _published_product_or_404(slug)
    if not product.waitlist_enabled:
        abort(404)

    form = WaitlistForm()
    if not form.validate_on_submit():
        return _render_detail(product, form=form, status=400)

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


# =====================================================================
# Gated downloads
#
#   POST /products/<slug>/download          name + email in, link emailed out
#   GET  /products/<slug>/download/<token>  the page the emailed link opens
#   POST /products/<slug>/download/<token>  its Download button: the file
#
# The file is only ever released by the POST. Outlook's Safe Links, Gmail
# and corporate filters open every link in a message to scan it; if the GET
# served the file, those scans would spend the visitor's downloads.
# =====================================================================

def _detail_anchor(product: Product, **params) -> str:
    return url_for("products.detail", slug=product.slug, **params) + "#download"


@bp.route("/<slug>/download", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def request_download(slug):
    product = _published_product_or_404(slug)
    if not product.download_offered:
        abort(404)
    if request.method == "GET":
        return redirect(_detail_anchor(product))

    form = _download_form()
    if not form.validate_on_submit():
        return _render_detail(product, download_form=form, status=400)

    sent = redirect(_detail_anchor(product, requested="sent"))
    if form.website.data:
        # Honeypot tripped: look exactly like success, store and send nothing.
        return sent

    email = form.email.data
    lead = DownloadRequest.query.filter_by(product_id=product.id, email=email).first()

    cooldown = current_app.config["DOWNLOAD_REQUEST_COOLDOWN"]
    if lead is not None and lead.email_delivered and lead.sent_within(cooldown):
        # A link went to this address moments ago. Answer as if sent: the
        # form must not become a way to flood someone else's inbox, and a
        # different reply would reveal that the address had asked before.
        return sent

    token, token_hash = new_download_token()
    if lead is None:
        lead = DownloadRequest(
            product_id=product.id,
            email=email,
            name=form.name.data,
            ip_address=request.remote_addr,
            **_attribution(form),
        )
        db.session.add(lead)
    else:
        # Asking again replaces the link (the old one stops working) and
        # keeps the original attribution: first touch is what brought them.
        lead.name = form.name.data
        lead.request_count = (lead.request_count or 0) + 1

    lead.token_hash = token_hash
    lead.link_sent_at = utcnow()
    lead.link_uses = 0
    lead.email_delivered = False
    try:
        db.session.commit()
    except IntegrityError:
        # A simultaneous submit for the same address created the row first;
        # that request is sending the email.
        db.session.rollback()
        return sent

    link = f"{site_base_url()}{url_for('products.download_page', slug=product.slug, token=token)}"
    lead.email_delivered = send_product_download_link(lead, product, link)
    db.session.commit()

    if not lead.email_delivered:
        return redirect(_detail_anchor(product, requested="failed"))
    return sent


def _resolve_link(product: Product, token: str) -> tuple[DownloadRequest | None, str]:
    """
    Check an emailed link. Returns the lead and one of:
    ok, unknown, unavailable, expired, used_up.
    """
    if not looks_like_token(token):
        return None, "unknown"
    lead = DownloadRequest.query.filter_by(token_hash=hash_download_token(token)).first()
    # A token only opens its own product: the slug in the URL must match.
    if lead is None or lead.product_id != product.id:
        return None, "unknown"
    if not product.download_offered:
        return lead, "unavailable"
    if lead.link_expired(current_app.config["DOWNLOAD_LINK_MAX_AGE"]):
        return lead, "expired"
    if lead.link_uses >= current_app.config["DOWNLOAD_LINK_MAX_USES"]:
        return lead, "used_up"
    return lead, "ok"


_LINK_STATUS = {"ok": 200, "unknown": 404, "unavailable": 404, "expired": 410, "used_up": 410}


def _private(response):
    """
    Headers for anything carrying a download token. no-referrer keeps the
    token out of the Referer sent to fonts and other third-party requests
    the page makes; no-store keeps it out of shared caches.
    """
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _render_link_page(product: Product, lead, state: str, form=None):
    max_uses = current_app.config["DOWNLOAD_LINK_MAX_USES"]
    html = render_template(
        "products/download.html",
        product=product,
        lead=lead,
        state=state,
        form=form or DownloadConfirmForm(),
        download_size=format_size(product.download_size),
        uses_left=max(0, max_uses - lead.link_uses) if lead else 0,
        expires_at=(
            lead.link_expires_at(current_app.config["DOWNLOAD_LINK_MAX_AGE"]) if lead else None
        ),
    )
    return _private(make_response(html, _LINK_STATUS[state]))


@bp.route("/<slug>/download/<token>", methods=["GET"])
def download_page(slug, token):
    product = _published_product_or_404(slug)
    lead, state = _resolve_link(product, token)
    return _render_link_page(product, lead, state)


@bp.route("/<slug>/download/<token>", methods=["POST"])
@limiter.limit("30 per hour")
def download_file(slug, token):
    product = _published_product_or_404(slug)
    form = DownloadConfirmForm()
    lead, state = _resolve_link(product, token)
    if state != "ok":
        return _render_link_page(product, lead, state)
    if not form.validate_on_submit():
        return _render_link_page(product, lead, state, form=form)

    # Count the use atomically: two clicks racing for the last use cannot
    # both get through, because the WHERE re-checks the limit in the update.
    now = utcnow()
    max_uses = current_app.config["DOWNLOAD_LINK_MAX_USES"]
    claimed = DownloadRequest.query.filter(
        DownloadRequest.id == lead.id, DownloadRequest.link_uses < max_uses
    ).update(
        {
            DownloadRequest.link_uses: DownloadRequest.link_uses + 1,
            DownloadRequest.download_count: DownloadRequest.download_count + 1,
            DownloadRequest.first_downloaded_at: func.coalesce(
                DownloadRequest.first_downloaded_at, now
            ),
            DownloadRequest.last_downloaded_at: now,
        },
        synchronize_session=False,
    )
    db.session.commit()
    if not claimed:
        db.session.refresh(lead)
        return _render_link_page(product, lead, "used_up")

    response = send_from_directory(
        current_app.config["PROTECTED_UPLOADS_DIR"],
        product.download_file,
        as_attachment=True,
        download_name=product.download_filename,
        mimetype="application/octet-stream",
        max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return _private(response)
