"""
Markdown -> safe HTML for blog post bodies.

Posts are authored and stored as Markdown (BlogPost.body). This module
renders that to HTML at display time - fenced code blocks get real
syntax highlighting via Pygments (class-based; the matching CSS lives in
tailwind.input.css under `.highlight`) - then runs the result through a
strict bleach allowlist so a post body can never inject script/style/etc.,
even though Markdown passes raw HTML through untouched.
"""
from __future__ import annotations

import re

import markdown
from markupsafe import Markup

# codehilite always emits `<pre><span></span>` at the start and a stray
# newline before `</code></pre>`; both render as blank lines in the block.
_CODEHILITE_LEAD = re.compile(r"(<div class=\"highlight\"><pre>)<span></span>")
_CODEHILITE_TRAIL = re.compile(r"\n(</code></pre></div>)")

# Structural tags Markdown can emit, plus the span/div Pygments wraps
# highlighted tokens in, plus basic tables.
_ALLOWED_TAGS = {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "blockquote", "pre", "code", "span", "div",
    "strong", "em", "del", "sub", "sup",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
}

# `class` is what carries Pygments token colours and the codehilite wrapper;
# scope it to the elements that legitimately use it.
_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "span": ["class"],
    "div": ["class"],
    "pre": ["class"],
    "code": ["class"],
    "th": ["align"],
    "td": ["align"],
}

_MD_EXTENSIONS = ["fenced_code", "codehilite", "tables", "sane_lists"]
_MD_EXTENSION_CONFIGS = {
    "codehilite": {
        "css_class": "highlight",
        "guess_lang": False,   # unlabeled fences stay plain, not mis-coloured
        "linenums": False,
    },
}


def render_markdown(text: str | None) -> Markup:
    """Render a Markdown string to sanitized, display-ready HTML."""
    if not text:
        return Markup("")

    html = markdown.markdown(
        text,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
        output_format="html",
    )
    html = _CODEHILITE_LEAD.sub(r"\1", html)
    html = _CODEHILITE_TRAIL.sub(r"\1", html)

    import bleach

    clean = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        strip=True,
    )
    return Markup(clean)
