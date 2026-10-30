"""
The /reels page, and the endpoint the reel autoposter reports to.

The page shows each Instagram post as a card. The video stays on Instagram:
pressing play swaps the card for Instagram's own embedded player, so nothing
from Instagram loads - and Instagram sets no cookies - for a visitor who never
presses play. Only this page's Content-Security-Policy admits Instagram frames.
"""
import base64
import binascii
import io
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, jsonify, make_response, render_template, request
from werkzeug.datastructures import FileStorage

from app.extensions import csrf, db, limiter
from app.models import InstagramPost
from app.models.instagram import parse_instagram_url
from app.reels.routes import _require_token
from app.uploads import ImageUploadError, process_image, store_image

bp = Blueprint("instagram", __name__)

INSTAGRAM_FRAMES = "frame-src https://www.instagram.com;"
MAX_COVER_BYTES = 5 * 1024 * 1024


@bp.route("/reels")
def index():
    from app import CONTENT_SECURITY_POLICY

    posts = (
        InstagramPost.query.filter_by(published=True)
        .order_by(
            InstagramPost.display_order,
            InstagramPost.posted_at.desc().nullslast(),
            InstagramPost.created_at.desc(),
        )
        .all()
    )
    response = make_response(render_template(
        "instagram/index.html",
        posts=posts,
        profile_url=current_app.config["INSTAGRAM_PROFILE_URL"],
        handle=current_app.config["INSTAGRAM_HANDLE"],
    ))
    # Set here, before the site-wide after_request hook, which only fills in
    # a policy when the response has none.
    response.headers["Content-Security-Policy"] = f"{CONTENT_SECURITY_POLICY} {INSTAGRAM_FRAMES}"
    return response


def _decode_cover(encoded: str | None):
    """A base64 JPEG/PNG/WebP from the autoposter, validated like any upload."""
    if not encoded:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ImageUploadError("cover is not valid base64")
    if len(raw) > MAX_COVER_BYTES:
        raise ImageUploadError("cover is too large")
    return process_image(FileStorage(stream=io.BytesIO(raw), filename="cover.jpg"))


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@bp.post("/internal/instagram-posts")
@csrf.exempt
@limiter.limit("60 per hour")
def report():
    """
    The reel autoposter reports a published post here (same bearer token as
    the reel host). Idempotent per post: reporting again fills in anything
    still missing, and never overwrites what an admin has edited.
    """
    _require_token()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    parsed = parse_instagram_url(payload.get("permalink"))
    if parsed is None:
        return jsonify(error="permalink is not an Instagram post link"), 400
    kind, shortcode = parsed

    post = InstagramPost.query.filter_by(shortcode=shortcode).first()
    created = post is None
    if created:
        post = InstagramPost(shortcode=shortcode, kind=kind, source=InstagramPost.SOURCE_AUTOPOSTER)
        db.session.add(post)

    title = (payload.get("title") or "").strip()[:160]
    caption = (payload.get("caption") or "").strip()
    post.title = post.title or title or None
    post.caption = post.caption or caption or None
    post.posted_at = post.posted_at or _parse_time(payload.get("posted_at"))

    cover_status = "unchanged"
    if not post.cover_image and payload.get("cover_jpeg_b64"):
        try:
            post.cover_image = store_image(_decode_cover(payload["cover_jpeg_b64"]), "reels")
            cover_status = "stored"
        except ImageUploadError as exc:
            # Keep the post; a card without a cover still plays.
            current_app.logger.warning("instagram cover rejected for %s: %s", shortcode, exc)
            cover_status = "rejected"

    db.session.commit()
    return jsonify(shortcode=shortcode, created=created, cover=cover_status), 201 if created else 200
