from flask import Blueprint, render_template

bp = Blueprint("legal", __name__)


@bp.route("/privacy")
def privacy():
    return render_template("legal/privacy.html")


@bp.route("/privacy/jswm-abbreviator")
def privacy_jswm_abbreviator():
    # Linked from the app's Google Play store listing; keep this URL stable.
    return render_template("legal/privacy_jswm_abbreviator.html")


@bp.route("/cookies")
def cookies():
    return render_template("legal/cookies.html")


@bp.route("/terms")
def terms():
    return render_template("legal/terms.html")


@bp.route("/refunds")
def refunds():
    return render_template("legal/refund.html")
