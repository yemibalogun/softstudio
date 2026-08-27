from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user, logout_user

from app.extensions import db
from app.models import UserSession
from app import emails

bp = Blueprint("account", __name__)


@bp.route("/profile")
@login_required
def profile():
    return render_template("account/profile.html")


@bp.route("/security")
@login_required
def security():
    return render_template("account/security.html")


@bp.route("/sessions")
@login_required
def sessions():
    active_sessions = (
        UserSession.query.filter_by(user_id=current_user.id, revoked_at=None)
        .order_by(UserSession.last_active_at.desc())
        .all()
    )
    return render_template("account/sessions.html", sessions=active_sessions)


@bp.route("/sessions/<int:session_id>/revoke", methods=["POST"])
@login_required
def revoke_session(session_id):
    target = UserSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    target.revoked_at = datetime.now(timezone.utc)
    db.session.commit()

    emails.send_security_notification(
        current_user, "Session revoked",
        detail=f"A session ({target.user_agent or 'unknown device'}) was revoked from your account.",
    )

    # If the user revoked their own current session, log them out immediately.
    current_token = request.cookies.get("session_token")
    if current_token and target.session_token == current_token:
        logout_user()
        flash("You've been logged out of that session.", "info")
        return redirect(url_for("auth.login"))

    flash("Session revoked.", "success")
    return redirect(url_for("account.sessions"))


@bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("account.security"))
    if len(new_password) < 10:
        flash("New password must be at least 10 characters.", "error")
        return redirect(url_for("account.security"))
    if new_password != confirm_password:
        flash("New passwords do not match.", "error")
        return redirect(url_for("account.security"))

    current_user.set_password(new_password)
    db.session.commit()

    # Invalidate other active sessions on password change.
    UserSession.query.filter_by(user_id=current_user.id, revoked_at=None).update(
        {"revoked_at": datetime.now(timezone.utc)}
    )
    db.session.commit()

    emails.send_security_notification(
        current_user, "Password changed",
        detail="Your password was just changed. All other active sessions have been signed out.",
    )

    flash("Password updated. Please log in again.", "success")
    logout_user()
    return redirect(url_for("auth.login"))
