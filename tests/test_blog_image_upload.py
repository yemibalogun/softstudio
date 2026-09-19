"""Blog featured-image uploads: validation, sanitising, storage and cleanup."""
import io
import os
import re

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import BlogPost
from app.uploads import (
    ImageUploadError,
    delete_uploaded_image,
    is_uploaded_image,
    process_image,
)
from tests.conftest import login

UPLOAD_URL = re.compile(r"^/static/images/uploads/blog/[0-9a-f]{32}\.(jpg|png|webp)$")


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------

def _image_bytes(fmt="PNG", size=(64, 40), mode="RGB", **save_kwargs) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, (0, 87, 255) if mode == "RGB" else 128).save(buf, fmt, **save_kwargs)
    return buf.getvalue()


def _jpeg_with_gps_exif() -> bytes:
    image = Image.new("RGB", (80, 60), (10, 20, 30))
    exif = Image.Exif()
    exif[0x010F] = "SnoopCam"             # Make
    exif[0x0112] = 6                      # Orientation: rotate 90 CW
    gps = exif.get_ifd(0x8825)
    gps[2] = (6.0, 27.0, 0.0)             # GPSLatitude (Lagos-ish)
    gps[1] = "N"
    buf = io.BytesIO()
    image.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _upload(data: bytes, filename: str) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=filename)


@pytest.fixture()
def upload_dir(app, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    return tmp_path


def _login_admin(client):
    return login(client, "admin@example.com", "correcthorsebattery")


def _blog_form(**overrides):
    data = {"title": "Post With Image", "body": "Body text.", "category_id": 0}
    data.update(overrides)
    return data


def _stored_files(upload_dir):
    folder = upload_dir / "blog"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


# ---------------------------------------------------------------------
# process_image: what gets accepted and what comes out
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "fmt,name,ext",
    [("PNG", "a.png", "png"), ("JPEG", "a.jpg", "jpg"), ("WEBP", "a.webp", "webp")],
)
def test_accepts_supported_formats(app, fmt, name, ext):
    result = process_image(_upload(_image_bytes(fmt), name))
    assert result.extension == ext
    assert Image.open(io.BytesIO(result.data)).format == fmt


def test_strips_exif_and_applies_orientation(app):
    result = process_image(_upload(_jpeg_with_gps_exif(), "holiday.jpeg"))
    cleaned = Image.open(io.BytesIO(result.data))
    assert not cleaned.getexif(), "EXIF (incl. GPS and camera make) must be removed"
    assert b"SnoopCam" not in result.data
    # Orientation 6 was baked into the pixels: 80x60 becomes 60x80.
    assert cleaned.size == (60, 80)


def test_polyglot_payload_is_destroyed(app):
    payload = b"<script>alert(document.cookie)</script><?php system($_GET['c']); ?>"
    result = process_image(_upload(_image_bytes("PNG") + payload, "innocent.png"))
    assert b"<script>" not in result.data
    assert b"<?php" not in result.data


def test_extension_comes_from_content_not_filename(app):
    # Real PNG bytes named .jpg: accepted, but stored as what it really is.
    result = process_image(_upload(_image_bytes("PNG"), "photo.jpg"))
    assert result.extension == "png"


def test_large_images_are_scaled_down(app):
    result = process_image(_upload(_image_bytes("JPEG", size=(4000, 1000)), "wide.jpg"))
    assert max(result.width, result.height) == 2400


@pytest.mark.parametrize(
    "data,filename",
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "logo.svg"),
        (b"<html><script>alert(1)</script></html>", "fake.png"),
        (b"MZ\x90\x00\x03\x00\x00\x00", "setup.exe"),
        (b"GIF89a" + b"\x00" * 20, "anim.gif"),
        (_image_bytes("PNG"), "noextension"),
        (_image_bytes("PNG")[:40], "truncated.png"),
    ],
    ids=["svg", "html-as-png", "exe", "gif", "no-extension", "truncated"],
)
def test_rejects_unsafe_or_invalid_files(app, data, filename):
    with pytest.raises(ImageUploadError):
        process_image(_upload(data, filename))


def test_rejects_empty_file(app):
    with pytest.raises(ImageUploadError, match="empty"):
        process_image(_upload(b"", "empty.png"))


def test_rejects_oversized_file(app):
    app.config["IMAGE_UPLOAD_MAX_BYTES"] = 1024
    big = _image_bytes("PNG", size=(400, 400), mode="RGB", compress_level=0)
    assert len(big) > 1024
    with pytest.raises(ImageUploadError, match="MB or smaller"):
        process_image(_upload(big, "big.png"))


def test_rejects_decompression_bomb_dimensions(app):
    # A tiny file that declares a huge canvas is refused before decoding.
    with pytest.raises(ImageUploadError, match="px"):
        process_image(_upload(_image_bytes("PNG", size=(10_001, 1), mode="L"), "bomb.png"))


# ---------------------------------------------------------------------
# delete_uploaded_image never touches files it did not create
# ---------------------------------------------------------------------

def test_delete_ignores_foreign_and_traversal_urls(app, upload_dir):
    victim = upload_dir / "keep.txt"
    victim.write_text("important")
    for url in [
        "https://example.com/static/images/uploads/blog/0123456789abcdef0123456789abcdef.png",
        "/static/images/uploads/blog/../keep.txt",
        "/static/images/uploads/../../keep.txt",
        "/static/css/tailwind.css",
        None,
        "",
    ]:
        delete_uploaded_image(url)
    assert victim.exists()
    assert not is_uploaded_image("/static/images/uploads/blog/../../x.png")


# ---------------------------------------------------------------------
# End to end through the admin blog form
# ---------------------------------------------------------------------

def test_admin_uploads_featured_image(client, admin_user, upload_dir):
    _login_admin(client)
    resp = client.post(
        "/admin/blog/new",
        data=_blog_form(featured_image_file=(io.BytesIO(_jpeg_with_gps_exif()), "cover.jpg"), published="y"),
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    post = BlogPost.query.filter_by(title="Post With Image").one()
    assert UPLOAD_URL.match(post.featured_image)
    stored = upload_dir / "blog" / post.featured_image.rsplit("/", 1)[1]
    assert stored.exists()
    assert not Image.open(stored).getexif()
    assert b"cover" not in os.fsencode(stored.name), "the uploader's filename must never be used"

    page = client.get(f"/blog/{post.slug}")
    assert post.featured_image.encode() in page.data


def test_invalid_upload_shows_error_and_saves_nothing(client, admin_user, upload_dir):
    _login_admin(client)
    resp = client.post(
        "/admin/blog/new",
        data=_blog_form(featured_image_file=(io.BytesIO(b"<script>alert(1)</script>"), "x.png")),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert b"not a valid JPG, PNG or WebP image" in resp.data
    assert BlogPost.query.filter_by(title="Post With Image").first() is None
    assert _stored_files(upload_dir) == []


def test_svg_upload_is_rejected(client, admin_user, upload_dir):
    _login_admin(client)
    svg = b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"
    resp = client.post(
        "/admin/blog/new",
        data=_blog_form(featured_image_file=(io.BytesIO(svg), "logo.svg")),
        content_type="multipart/form-data",
    )
    assert b"Upload a JPG, PNG or WebP image." in resp.data
    assert _stored_files(upload_dir) == []


def test_replacing_and_removing_image_cleans_up_files(client, admin_user, upload_dir):
    _login_admin(client)
    client.post(
        "/admin/blog/new",
        data=_blog_form(featured_image_file=(io.BytesIO(_image_bytes("PNG")), "one.png")),
        content_type="multipart/form-data",
    )
    post = BlogPost.query.filter_by(title="Post With Image").one()
    first = post.featured_image

    # Replace: the new file is stored and the old one removed.
    client.post(
        f"/admin/blog/{post.id}/edit",
        data=_blog_form(slug=post.slug, featured_image=first,
                        featured_image_file=(io.BytesIO(_image_bytes("WEBP")), "two.webp")),
        content_type="multipart/form-data",
    )
    post = db.session.get(BlogPost, post.id)
    assert post.featured_image != first and post.featured_image.endswith(".webp")
    assert _stored_files(upload_dir) == [post.featured_image.rsplit("/", 1)[1]]

    # Remove: the field is cleared and the file deleted.
    client.post(
        f"/admin/blog/{post.id}/edit",
        data=_blog_form(slug=post.slug, featured_image=post.featured_image, remove_featured_image="y"),
        content_type="multipart/form-data",
    )
    post = db.session.get(BlogPost, post.id)
    assert post.featured_image is None
    assert _stored_files(upload_dir) == []


def test_deleting_post_removes_its_image(client, admin_user, upload_dir):
    _login_admin(client)
    client.post(
        "/admin/blog/new",
        data=_blog_form(featured_image_file=(io.BytesIO(_image_bytes("PNG")), "one.png")),
        content_type="multipart/form-data",
    )
    post = BlogPost.query.filter_by(title="Post With Image").one()
    assert len(_stored_files(upload_dir)) == 1

    client.post(f"/admin/blog/{post.id}/delete")
    assert _stored_files(upload_dir) == []


def test_editing_without_new_file_keeps_uploaded_image(client, admin_user, upload_dir):
    _login_admin(client)
    client.post(
        "/admin/blog/new",
        data=_blog_form(featured_image_file=(io.BytesIO(_image_bytes("PNG")), "one.png")),
        content_type="multipart/form-data",
    )
    post = BlogPost.query.filter_by(title="Post With Image").one()
    image = post.featured_image

    # The edit form round-trips the stored site-relative path in the URL field.
    client.post(
        f"/admin/blog/{post.id}/edit",
        data=_blog_form(slug=post.slug, title="Renamed", featured_image=image),
        content_type="multipart/form-data",
    )
    post = db.session.get(BlogPost, post.id)
    assert post.title == "Renamed"
    assert post.featured_image == image
    assert len(_stored_files(upload_dir)) == 1


@pytest.mark.parametrize("url,ok", [
    ("https://images.example.com/cover.jpg", True),
    ("javascript:alert(1)", False),
    ("/static/images/uploads/blog/../../../etc/passwd", False),
    ("//evil.example.com/x.png", False),
])
def test_image_url_field_validation(client, admin_user, upload_dir, url, ok):
    _login_admin(client)
    client.post("/admin/blog/new", data=_blog_form(featured_image=url), content_type="multipart/form-data")
    post = BlogPost.query.filter_by(title="Post With Image").first()
    assert (post is not None) is ok
    if ok:
        assert post.featured_image == url


def test_upload_requires_admin(client, user, upload_dir):
    login(client, "student@example.com", "correcthorsebattery")
    resp = client.post(
        "/admin/blog/new",
        data=_blog_form(featured_image_file=(io.BytesIO(_image_bytes("PNG")), "one.png")),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403
    assert _stored_files(upload_dir) == []
