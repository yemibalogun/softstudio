"""
Short-lived public hosting for the studio's own reels, used by the reel autoposter.

Instagram's API (with Instagram Login) only publishes a Reel from a public URL; it
will not take the file itself. The autoposter uploads each reel here, gives
Instagram the link, and deletes the file as soon as Instagram has fetched it.

- Off unless REEL_HOST_TOKEN is set: with no token every route here is a 404.
- Upload and delete need that token as a bearer token (constant-time compare).
- Only MP4 is accepted (ISO-BMFF "ftyp" box at byte 4), capped at
  REEL_HOST_MAX_BYTES. The edge nginx allows 10 MB, so the cap stays under it.
- Stored in the protected volume, never under /static, under a random 32-hex
  name. The uploader's filename is never used, so a link can't be guessed.
- Anything older than REEL_HOST_TTL_HOURS is removed on every upload, so a crash
  between upload and delete can't leave a file online for long.
"""
import hmac
import os
import re
import secrets
import time

from flask import Blueprint, abort, current_app, jsonify, request, send_file, url_for

from app.extensions import csrf, limiter

bp = Blueprint("reels", __name__)
csrf.exempt(bp)  # machine-to-machine; authenticated by the bearer token instead

_NAME_RE = re.compile(r"^[0-9a-f]{32}$")


def _enabled() -> bool:
    return bool(current_app.config.get("REEL_HOST_TOKEN"))


def _folder() -> str:
    folder = os.path.join(current_app.config["PROTECTED_UPLOADS_DIR"], "reels")
    os.makedirs(folder, exist_ok=True)
    return folder


def _require_token() -> None:
    if not _enabled():
        abort(404)
    expected = f"Bearer {current_app.config['REEL_HOST_TOKEN']}".encode()
    if not hmac.compare_digest(request.headers.get("Authorization", "").encode(), expected):
        abort(403)


def _prune(folder: str) -> None:
    cutoff = time.time() - current_app.config["REEL_HOST_TTL_HOURS"] * 3600
    for entry in os.scandir(folder):
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                os.remove(entry.path)
        except OSError:
            pass


@bp.post("/internal/reels")
@limiter.limit("30 per hour")
def upload():
    _require_token()
    request.max_content_length = current_app.config["REEL_HOST_MAX_BYTES"]
    data = request.get_data(cache=False)  # 413 above the cap
    if len(data) < 12 or data[4:8] != b"ftyp":
        abort(400)

    folder = _folder()
    _prune(folder)
    name = secrets.token_hex(16)
    partial = os.path.join(folder, f"{name}.part")
    with open(partial, "wb") as fh:
        fh.write(data)
    os.replace(partial, os.path.join(folder, f"{name}.mp4"))
    return jsonify(name=name, url=url_for("reels.serve", name=name, _external=True)), 201


@bp.get("/r/<name>.mp4")
@limiter.exempt
def serve(name: str):
    if not _enabled() or not _NAME_RE.match(name):
        abort(404)
    path = os.path.join(_folder(), f"{name}.mp4")
    if not os.path.isfile(path):
        abort(404)
    response = send_file(path, mimetype="video/mp4", conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@bp.delete("/internal/reels/<name>")
def delete(name: str):
    _require_token()
    if not _NAME_RE.match(name):
        abort(404)
    try:
        os.remove(os.path.join(_folder(), f"{name}.mp4"))
    except FileNotFoundError:
        pass
    return "", 204
