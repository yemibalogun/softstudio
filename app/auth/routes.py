from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter, oauth
from app.auth.forms import RegisterForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from app.auth import services
from app import emails

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("learning.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        if services.find_user_by_email(form.email.data):
            flash("An account with this email already exists.", "error")
            return render_template("auth/register.html", form=form)

        user = services.create_local_user(form.email.data, form.full_name.data, form.password.data)
        verify_token = services.generate_token(user.email, salt="email-verify")
        emails.send_welcome_email(user)
        emails.send_verification_email(user, verify_token)
        flash("Account created. Please check your email to verify your address.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("learning.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = services.find_user_by_email(form.email.data)
        if user and user.is_active and user.check_password(form.password.data):
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            login_user(user, remember=form.remember_me.data)
            next_url = request.args.get("next")
            return redirect(next_url or url_for("learning.dashboard"))
        flash("Invalid email or password.", "error")

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("6 per hour")
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = services.find_user_by_email(form.email.data)
        if user:
            reset_token = services.generate_token(user.email, salt="password-reset")
            emails.send_password_reset_email(user, reset_token)
        # Always show the same message to avoid leaking account existence.
        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def reset_password(token):
    email = services.verify_token(token, salt="password-reset", max_age_seconds=3600)
    if not email:
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = services.find_user_by_email(email)
        if user:
            user.set_password(form.password.data)
            db.session.commit()
            flash("Your password has been updated. Please log in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form, token=token)


@bp.route("/verify-email/<token>")
def verify_email(token):
    email = services.verify_token(token, salt="email-verify", max_age_seconds=86400)
    if not email:
        flash("That verification link is invalid or has expired.", "error")
        return redirect(url_for("main.index"))
    user = services.find_user_by_email(email)
    if user and not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Your email has been verified.", "success")
    return redirect(url_for("auth.login"))


# --- OAuth -----------------------------------------------------------

@bp.route("/oauth/<provider>")
def oauth_login(provider):
    if provider not in ("google", "github"):
        return redirect(url_for("auth.login"))
    redirect_uri = url_for("auth.oauth_callback", provider=provider, _external=True)
    client = oauth.create_client(provider)
    return client.authorize_redirect(redirect_uri)


@bp.route("/oauth/<provider>/callback")
def oauth_callback(provider):
    if provider not in ("google", "github"):
        return redirect(url_for("auth.login"))

    client = oauth.create_client(provider)
    token = client.authorize_access_token()  # authlib validates `state` internally

    if provider == "google":
        userinfo = token.get("userinfo") or client.userinfo()
        provider_user_id = userinfo["sub"]
        email = userinfo.get("email")
        full_name = userinfo.get("name", "")
        avatar_url = userinfo.get("picture")
    else:  # github
        profile = client.get("user").json()
        provider_user_id = str(profile["id"])
        full_name = profile.get("name") or profile.get("login", "")
        avatar_url = profile.get("avatar_url")
        email = profile.get("email")
        if not email:
            emails = client.get("user/emails").json()
            primary = next((e for e in emails if e.get("primary")), None)
            email = primary["email"] if primary else None

    try:
        user = services.resolve_oauth_login(provider, provider_user_id, email, full_name, avatar_url)
    except services.AccountLinkingRequired as exc:
        flash(
            "An account already exists with this email. Please log in with your "
            "password first, then link this provider from your security settings.",
            "info",
        )
        return redirect(url_for("auth.login", prefill_email=exc.existing_user.email))

    login_user(user)
    return redirect(url_for("learning.dashboard"))
