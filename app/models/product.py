from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import TimestampMixin, utcnow


class Product(db.Model, TimestampMixin):
    """
    A shareable product landing page: its own public URL, its own social
    card, and an optional waitlist.

    Deliberately separate from Project (portfolio case studies) and Course
    (paid, enrollable content): a product is a thing being launched, and
    giving it its own table keeps one canonical URL per piece of content.
    Field names follow the conventions already used by Project/BlogPost
    (`published`, `slug`, `meta_*`, `og_image`) so the admin, slug helper
    and SEO blocks all work unchanged.
    """

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)

    short_description = db.Column(db.String(280), nullable=False)
    description = db.Column(db.Text)

    # Site-relative path (uploads) or an absolute URL; made absolute for
    # social cards by app/seo.py:absolute_url.
    image = db.Column(db.String(512))

    published = db.Column(db.Boolean, default=False, nullable=False, index=True)
    waitlist_enabled = db.Column(db.Boolean, default=False, nullable=False)
    featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    # Optional call-to-action for products that are already available.
    cta_label = db.Column(db.String(80))
    cta_url = db.Column(db.String(512))

    # SEO overrides (fall back to title/short_description/image when blank)
    meta_title = db.Column(db.String(180))
    meta_description = db.Column(db.String(300))
    og_image = db.Column(db.String(512))

    # Gated download (app/downloads.py). The file sits in the protected
    # store under a random name; visitors only reach it through an emailed
    # link after leaving their name and email.
    download_file = db.Column(db.String(255))          # downloads/<hex>.<ext>
    download_filename = db.Column(db.String(255))      # name the browser saves
    download_size = db.Column(db.BigInteger)
    download_sha256 = db.Column(db.String(64))
    download_version = db.Column(db.String(40))
    download_updated_at = db.Column(db.DateTime(timezone=True))
    download_enabled = db.Column(db.Boolean, default=False, nullable=False)

    # Optional focused landing layout (templates/products/landing.html) for
    # ad and DM traffic: one offer, one form, no site navigation. Used in
    # place of the normal product page only while a download is offered.
    landing_page = db.Column(db.Boolean, default=False, nullable=False)
    landing_headline = db.Column(db.String(200))     # *highlight*, line breaks
    landing_points = db.Column(db.Text)              # one per line, **bold**
    landing_button_label = db.Column(db.String(80))

    download_requests = db.relationship(
        "DownloadRequest",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="DownloadRequest.created_at.desc()",
    )

    subscribers = db.relationship(
        "WaitlistSubscriber",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="WaitlistSubscriber.created_at.desc()",
    )

    @property
    def social_image(self) -> str | None:
        """
        The image a social card should use, before it is made absolute.

        The uploaded product image wins, as it does everywhere on the site;
        og_image is only for pages that have no image of their own.
        """
        return self.image or self.og_image or None

    @property
    def subscriber_count(self) -> int:
        return len(self.subscribers)

    @property
    def download_ready(self) -> bool:
        """A file is attached and switched on. Publishing is checked separately."""
        return bool(self.download_enabled and self.download_file)

    @property
    def download_offered(self) -> bool:
        """
        What the public pages go by: attached, switched on, and actually on
        disk. A missing file hides the download rather than showing a form
        whose links could never work. Publishing is checked separately.
        """
        from app.downloads import download_exists
        return self.download_ready and download_exists(self.download_file)

    @property
    def download_platform(self) -> str | None:
        from app.downloads import platform_for
        return platform_for(self.download_filename)

    @property
    def shows_landing_page(self) -> bool:
        """The landing layout needs a live download: it is a page with one form."""
        return bool(self.landing_page) and self.download_offered

    @property
    def download_kind(self) -> str | None:
        """Badge label: "Windows" for an installer, "PDF" for a document."""
        from app.downloads import kind_for
        return kind_for(self.download_filename)

    @property
    def download_request_count(self) -> int:
        return len(self.download_requests)

    def __repr__(self):
        return f"<Product {self.slug}>"


class WaitlistSubscriber(db.Model, TimestampMixin):
    """
    One email on one product's waitlist.

    Uniqueness is enforced by the database, not only by the route, so a
    double-submit or a race cannot create two rows for the same person.
    """

    __tablename__ = "waitlist_subscribers"
    __table_args__ = (
        db.UniqueConstraint("product_id", "email", name="uq_waitlist_product_email"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    email = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(120))

    # Attribution: where the visitor came from. Optional — a signup is never
    # rejected for missing or malformed campaign parameters.
    source = db.Column(db.String(60), index=True)
    utm_medium = db.Column(db.String(60))
    utm_campaign = db.Column(db.String(120))
    utm_content = db.Column(db.String(120))

    ip_address = db.Column(db.String(64))

    product = db.relationship("Product", back_populates="subscribers")

    def __repr__(self):
        return f"<WaitlistSubscriber {self.email} -> {self.product_id}>"


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes even for timezone=True columns."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class DownloadRequest(db.Model, TimestampMixin):
    """
    Someone who left their details to download a product, and the link they
    were sent.

    One row per person per product: asking again sends a fresh link to the
    same row rather than adding a duplicate lead. The link is a random token
    of which only the SHA-256 is kept (app/downloads.py), so a copy of this
    table cannot be turned into working download links.
    """

    __tablename__ = "download_requests"
    __table_args__ = (
        db.UniqueConstraint("product_id", "email", name="uq_download_product_email"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)

    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    link_sent_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    link_uses = db.Column(db.Integer, default=0, nullable=False)      # on the current link
    email_delivered = db.Column(db.Boolean, default=False, nullable=False)

    request_count = db.Column(db.Integer, default=1, nullable=False)
    download_count = db.Column(db.Integer, default=0, nullable=False)  # across all links
    first_downloaded_at = db.Column(db.DateTime(timezone=True))
    last_downloaded_at = db.Column(db.DateTime(timezone=True))

    # Attribution, same shape as WaitlistSubscriber.
    source = db.Column(db.String(60), index=True)
    utm_medium = db.Column(db.String(60))
    utm_campaign = db.Column(db.String(120))
    utm_content = db.Column(db.String(120))

    ip_address = db.Column(db.String(64))

    product = db.relationship("Product", back_populates="download_requests")

    def link_expires_at(self, max_age_seconds: int) -> datetime:
        sent = _as_utc(self.link_sent_at) or utcnow()
        return sent + timedelta(seconds=max_age_seconds)

    def link_expired(self, max_age_seconds: int, now: datetime | None = None) -> bool:
        return (now or utcnow()) >= self.link_expires_at(max_age_seconds)

    def sent_within(self, seconds: int, now: datetime | None = None) -> bool:
        sent = _as_utc(self.link_sent_at)
        return sent is not None and (now or utcnow()) - sent < timedelta(seconds=seconds)

    def __repr__(self):
        return f"<DownloadRequest {self.email} -> {self.product_id}>"
