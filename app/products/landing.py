"""
Light markup for the focused landing layout (templates/products/landing.html).

The admin types plain text into the headline and bullet fields. Two marks are
understood, and nothing else is:

    *words*     -> the blue gradient highlight   (<span class="g">)
    **words**   -> bold                           (<b>)

Line breaks in the headline become <br>. The text is HTML-escaped before the
marks are applied, so anything typed into these fields can only ever produce
those two tags - never markup of its own.
"""
import re

from markupsafe import Markup, escape

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HIGHLIGHT = re.compile(r"\*(.+?)\*")


def landing_markup(text: str | None) -> Markup:
    if not text:
        return Markup("")
    out = str(escape(text.strip()))
    out = _BOLD.sub(r"<b>\1</b>", out)          # before *x*, which would eat the inner pair
    out = _HIGHLIGHT.sub(r'<span class="g">\1</span>', out)
    out = re.sub(r"\r?\n", "<br>", out)
    return Markup(out)


def landing_points(text: str | None) -> list[Markup]:
    """One bullet per non-empty line, each with the same marks applied."""
    return [landing_markup(line) for line in (text or "").splitlines() if line.strip()]


def initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p[:1].isalpha()]
    return "".join(p[0].upper() for p in parts[:2]) or "·"
