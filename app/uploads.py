"""
Secure image uploads for admin-authored content (blog featured images).

Every upload is treated as hostile, even from an admin account:

1. Extension allowlist - JPG, PNG or WebP only. SVG is refused outright
   because it is XML that can carry script, and it would be served from
   this site's own origin.
2. Size limit - read at most IMAGE_UPLOAD_MAX_BYTES + 1 bytes, so an
   oversized file is rejected without buffering all of it.
3. Signature check - the first bytes must be a real JPEG/PNG/WebP header.
   The browser-supplied filename and Content-Type are never trusted.
4. Full decode with Pillow, with pixel and side-length caps that stop
   decompression bombs before any pixel data is decoded.
5. Re-encode from decoded pixels. Only pixels survive: EXIF (including GPS
   location), comments, text chunks and anything appended to the file
   (polyglot payloads) are dropped. Very large images are scaled down.
6. Stored under a random name with an extension derived from the decoded
   format, in a dedicated folder. The uploader's filename is never used.
"""
from __future__ import annotations

import io
import os
import re
import uuid
from dataclasses import dataclass

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

# Decoded format -> stored extension. Only these are ever written.
_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

# Extensions accepted on the uploaded filename (a first, cheap gate).
ALLOWED_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})

# Magic numbers for the formats above.
_SIGNATURES = (
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
)

MAX_SIDE = 10_000           # px, either dimension
MAX_PIXELS = 40_000_000     # px, width * height (a 40 MP image)
RESIZE_TO = 2400            # px, longest side kept after re-encoding

# Public URLs this module produces: /static/images/uploads/<subdir>/<32 hex>.<ext>
_UPLOAD_URL_RE = re.compile(
    r"^/static/images/uploads/(?P<subdir>[a-z]+)/(?P<name>[0-9a-f]{32}\.(?:jpg|png|webp))$"
)


class ImageUploadError(ValueError):
    """The upload was rejected. The message is safe to show to the user."""


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    extension: str
    width: int
    height: int


def _sniff_format(head: bytes) -> str | None:
    for signature, fmt in _SIGNATURES:
        if head.startswith(signature):
            return fmt
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    return None


def _max_bytes() -> int:
    return int(current_app.config.get("IMAGE_UPLOAD_MAX_BYTES", 5 * 1024 * 1024))


def process_image(file_storage) -> ProcessedImage:
    """
    Validate an uploaded image and return a clean, re-encoded copy.

    Raises ImageUploadError with a user-facing message on any problem.
    Nothing is written to disk here.
    """
    filename = (getattr(file_storage, "filename", "") or "").strip()
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ImageUploadError("Upload a JPG, PNG or WebP image.")

    limit = _max_bytes()
    data = file_storage.stream.read(limit + 1)
    if not data:
        raise ImageUploadError("The file is empty.")
    if len(data) > limit:
        raise ImageUploadError(f"Images must be {limit // (1024 * 1024)} MB or smaller.")

    sniffed = _sniff_format(data[:16])
    if sniffed is None:
        raise ImageUploadError("That file is not a valid JPG, PNG or WebP image.")

    try:
        # Header only: size and format are known before any pixels decode.
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != sniffed or probe.format not in _FORMATS:
                raise ImageUploadError("That file is not a valid JPG, PNG or WebP image.")
            width, height = probe.size
            too_big = width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PIXELS
            if width < 1 or height < 1 or too_big:
                raise ImageUploadError(
                    f"Images must be at most {MAX_SIDE:,} px on each side "
                    f"and {MAX_PIXELS // 1_000_000} megapixels."
                )
            probe.verify()  # structural check (checksums, truncation)

        # verify() leaves the image unusable, so reopen to decode for real.
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            fmt = image.format
            image = ImageOps.exif_transpose(image)  # bake in camera rotation before EXIF is dropped
            image.thumbnail((RESIZE_TO, RESIZE_TO), Image.Resampling.LANCZOS)
            clean = _reencode(image, fmt)
            out_width, out_height = image.size
    except ImageUploadError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        current_app.logger.info("Rejected image upload %r: %s", filename, exc)
        raise ImageUploadError("That file is not a valid JPG, PNG or WebP image.") from None

    return ProcessedImage(data=clean, extension=_FORMATS[fmt], width=out_width, height=out_height)


def _reencode(image: Image.Image, fmt: str) -> bytes:
    """Write fresh pixels only. No exif / icc / text chunks are passed through."""
    # Some writers (PNG) copy metadata such as the ICC profile from
    # image.info by default. Keep only palette transparency.
    image.info = {k: v for k, v in image.info.items() if k == "transparency"}
    out = io.BytesIO()
    if fmt == "JPEG":
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    elif fmt == "PNG":
        if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            image = image.convert("RGBA")
        image.save(out, "PNG", optimize=True)
    else:  # WEBP
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.mode else "RGB")
        image.save(out, "WEBP", quality=86, method=4)
    return out.getvalue()


def _upload_root() -> str:
    return current_app.config["UPLOAD_FOLDER"]


def store_image(image: ProcessedImage, subdir: str) -> str:
    """Write a processed image under a random name. Returns its public URL."""
    if not re.fullmatch(r"[a-z]+", subdir):
        raise ValueError("subdir must be lowercase letters only")

    directory = os.path.join(_upload_root(), subdir)
    os.makedirs(directory, exist_ok=True)

    name = f"{uuid.uuid4().hex}.{image.extension}"
    final_path = os.path.join(directory, name)
    temp_path = final_path + ".part"
    with open(temp_path, "xb") as handle:  # "x": never overwrite an existing file
        handle.write(image.data)
    os.replace(temp_path, final_path)

    return f"/static/images/uploads/{subdir}/{name}"


def is_uploaded_image(url: str | None) -> bool:
    return bool(url and _UPLOAD_URL_RE.match(url))


def delete_uploaded_image(url: str | None) -> None:
    """
    Remove a file previously written by store_image(). URLs that did not come
    from this module (external links, anything with path tricks) are ignored,
    so this can never delete an arbitrary file.
    """
    match = _UPLOAD_URL_RE.match(url or "")
    if not match:
        return
    path = os.path.join(_upload_root(), match["subdir"], match["name"])
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        current_app.logger.warning("Could not delete uploaded image %s", path, exc_info=True)
