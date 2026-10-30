"""
Instagram posts shown on the /reels page.

Nothing from Instagram is copied here except the post's address (its
shortcode) and the words around it: the video itself plays from Instagram,
in their embed, and only after a visitor asks for it. A post arrives either
from the reel autoposter, which reports each reel once it is published, or
from an admin pasting its link.
"""
import re

from app.extensions import db
from app.models import TimestampMixin

# instagram.com/reel/<code>/, /reels/<code>/, /p/<code>/, /tv/<code>/, with or
# without www, an account name before the kind, or a query string after.
_URL_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:[A-Za-z0-9_.]{1,30}/)?"
    r"(reels?|p|tv)/([A-Za-z0-9_-]{5,40})/?(?:[?#].*)?$",
    re.I,
)
SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,40}$")
_HASHTAG_RE = re.compile(r"(?:^|\s)[#@][\w.]+")


def parse_instagram_url(url: str | None) -> tuple[str, str] | None:
    """("reel" | "post", shortcode) for an Instagram post link, else None."""
    match = _URL_RE.match((url or "").strip())
    if not match:
        return None
    kind = "post" if match.group(1).lower() == "p" else "reel"
    return kind, match.group(2)   # shortcodes are case-sensitive: keep as given


class InstagramPost(db.Model, TimestampMixin):
    __tablename__ = "instagram_posts"

    KIND_REEL = "reel"
    KIND_POST = "post"
    SOURCE_ADMIN = "admin"
    SOURCE_AUTOPOSTER = "autoposter"

    id = db.Column(db.Integer, primary_key=True)
    shortcode = db.Column(db.String(40), unique=True, nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False, default=KIND_REEL)

    title = db.Column(db.String(160))
    caption = db.Column(db.Text)
    # Site-relative path of a cover uploaded through app/uploads.py. Optional:
    # without one the card shows a branded placeholder.
    cover_image = db.Column(db.String(512))

    posted_at = db.Column(db.DateTime(timezone=True))
    published = db.Column(db.Boolean, default=True, nullable=False, index=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    source = db.Column(db.String(20), nullable=False, default=SOURCE_ADMIN)

    @property
    def _segment(self) -> str:
        return "p" if self.kind == self.KIND_POST else "reel"

    @property
    def permalink(self) -> str:
        return f"https://www.instagram.com/{self._segment}/{self.shortcode}/"

    @property
    def embed_url(self) -> str:
        return f"https://www.instagram.com/{self._segment}/{self.shortcode}/embed/"

    @property
    def heading(self) -> str:
        """The title, or the caption's first line without its hashtags."""
        if self.title:
            return self.title
        for line in (self.caption or "").splitlines():
            line = _HASHTAG_RE.sub("", line).strip()
            if line:
                return line if len(line) <= 90 else line[:87].rstrip() + "…"
        return "Watch on Instagram"

    def __repr__(self):
        return f"<InstagramPost {self.shortcode}>"
