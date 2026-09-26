from app.extensions import db
from app.models import TimestampMixin


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
