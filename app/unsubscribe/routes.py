"""
/unsubscribe/<token>: withdraw marketing email consent.

Opening the link only shows a confirm button; the POST unsubscribes. Mail
scanners open every link in a message, and a GET that unsubscribed would
take people off the list without their asking. Mail apps' own one-click
"Unsubscribe" (RFC 8058 List-Unsubscribe-Post) sends that POST directly.
The token is the authentication, so the POST is CSRF-exempt: a one-click
request arrives with no session at all.
"""
from flask import Blueprint, abort, make_response, render_template

from app.consent import email_from_token, unsubscribe
from app.extensions import csrf, limiter

bp = Blueprint("consent", __name__)


def _page(email: str, done: bool, status: int = 200):
    response = make_response(render_template("consent/unsubscribe.html", email=email, done=done), status)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.get("/unsubscribe/<token>", endpoint="unsubscribe")   # what emails link to
def unsubscribe_page(token):
    email = email_from_token(token)
    if email is None:
        abort(404)
    return _page(email, done=False)


@bp.post("/unsubscribe/<token>")
@csrf.exempt
@limiter.limit("30 per hour")
def unsubscribe_confirm(token):
    email = email_from_token(token)
    if email is None:
        abort(404)
    unsubscribe(email)
    return _page(email, done=True)
