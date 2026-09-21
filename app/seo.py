"""
Absolute URLs for things that leave the page: social cards, canonical
links, sitemap entries, share links.

The base always comes from the configured SITE_URL, never from the request's
Host header, so a forged Host cannot rewrite the canonical URL of a page and
the same code produces production URLs behind nginx/gunicorn and localhost
URLs in development.
"""
from urllib.parse import urlsplit

from flask import current_app


def site_base_url() -> str:
    """The configured public base URL, without a trailing slash."""
    return (current_app.config.get("SITE_URL") or "").rstrip("/")


def absolute_url(target: str | None) -> str | None:
    """
    Make `target` absolute against SITE_URL.

    Already-absolute URLs (http/https, protocol-relative) pass through
    untouched; a site-relative path gets the configured base prepended.
    Returns None for empty input so callers can fall back to a default
    rather than emitting an empty meta tag.
    """
    if not target:
        return None
    value = target.strip()
    if not value:
        return None
    if value.startswith("//"):
        return value
    if urlsplit(value).scheme:
        return value
    return f"{site_base_url()}/{value.lstrip('/')}"


def default_social_image_url() -> str:
    """The site-wide social card, used when a page has no image of its own."""
    return f"{site_base_url()}/static/images/brand/og-default.png"
