"""
Business logic for authentication, kept out of route handlers so it can
be unit tested independently of Flask request context where possible.
"""
from datetime import datetime, timezone

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app

from app.extensions import db
from app.models.user import User, Role
from app.models.oauth import OAuthIdentity


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_token(email: str, salt: str) -> str:
    return _serializer().dumps(email, salt=salt)


def verify_token(token: str, salt: str, max_age_seconds: int = 3600) -> str | None:
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


def get_or_create_default_role(name: str = "student") -> Role:
    role = Role.query.filter_by(name=name).first()
    if not role:
        role = Role(name=name, description=f"Default {name} role")
        db.session.add(role)
        db.session.flush()
    return role


def create_local_user(email: str, full_name: str, password: str) -> User:
    role = get_or_create_default_role("student")
    user = User(email=email.lower().strip(), full_name=full_name.strip(), role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def find_user_by_email(email: str) -> User | None:
    return User.query.filter_by(email=email.lower().strip()).first()


class AccountLinkingRequired(Exception):
    """
    Raised when an OAuth login matches an existing local account by
    email but that account is not yet linked to this provider. The
    caller must present an explicit confirmation step (e.g. "log in
    with your password to link Google") rather than auto-linking,
    to prevent account-takeover via a spoofed/unverified email claim.
    """

    def __init__(self, existing_user: User):
        self.existing_user = existing_user
        super().__init__("Account linking confirmation required")


def resolve_oauth_login(
    provider: str, provider_user_id: str, email: str | None, full_name: str, avatar_url: str | None
) -> User:
    """
    Resolve an OAuth callback into a local User.

    `email` MUST be an address the provider has itself verified the user
    controls (the caller is responsible for that — see oauth_callback).

    1. If this exact (provider, provider_user_id) is already linked, log
       that user in directly.
    2. Else, if a *verified* local account shares this email, do NOT
       silently link — raise AccountLinkingRequired so the caller can
       force an explicit confirmation (re-auth with password) before
       attaching the identity to somebody else's account.
    3. Else, if an *unverified* local account shares this email, nobody
       ever proved they own that inbox — the person completing this
       OAuth flow just did, so adopt that account: link the identity,
       mark it verified, and drop any password a pre-registration set.
    4. Else, create a brand-new account + identity.
    """
    identity = OAuthIdentity.query.filter_by(
        provider=provider, provider_user_id=provider_user_id
    ).first()
    if identity:
        identity.email = email or identity.email
        db.session.commit()
        return identity.user

    if email:
        existing = find_user_by_email(email)
        if existing is not None:
            if existing.email_verified:
                raise AccountLinkingRequired(existing)

            # Unverified local account — adopt it rather than colliding on
            # the unique email index by trying to INSERT a duplicate.
            existing.email_verified = True
            existing.email_verified_at = datetime.now(timezone.utc)
            existing.password_hash = None  # neutralise any pre-set password
            if avatar_url and not existing.avatar_url:
                existing.avatar_url = avatar_url
            if full_name and not existing.full_name:
                existing.full_name = full_name
            db.session.add(
                OAuthIdentity(
                    user_id=existing.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                )
            )
            db.session.commit()
            return existing

    role = get_or_create_default_role("student")
    user = User(
        email=(email or f"{provider}_{provider_user_id}@no-email.local").lower(),
        full_name=full_name or "New User",
        avatar_url=avatar_url,
        role=role,
        email_verified=bool(email),
        email_verified_at=datetime.now(timezone.utc) if email else None,
    )
    db.session.add(user)
    db.session.flush()

    db.session.add(
        OAuthIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
        )
    )
    db.session.commit()
    return user


def link_oauth_identity(user: User, provider: str, provider_user_id: str, email: str | None) -> None:
    """Explicitly link a provider identity to an already-authenticated user."""
    existing = OAuthIdentity.query.filter_by(provider=provider, provider_user_id=provider_user_id).first()
    if existing:
        raise ValueError("This provider account is already linked to another user.")
    db.session.add(
        OAuthIdentity(user_id=user.id, provider=provider, provider_user_id=provider_user_id, email=email)
    )
    db.session.commit()
