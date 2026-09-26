"""
Environment-specific application configuration.

All secrets/config come from environment variables. Never hard-code
credentials here. See .env.example for the full list of variables.
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def _bool_env(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _db_url(key: str, default: str) -> str:
    """
    The database URL with the driver we actually ship named explicitly.

    A bare "postgresql://" URL leaves the driver up to SQLAlchemy's
    default, and that default changed: 2.0 picks psycopg2, 2.1 picks
    psycopg 3. requirements.txt ships psycopg2-binary, so an unpinned
    install of 2.1 would import a driver that is not there. Naming the
    driver keeps the URL meaning the same thing across versions, whatever
    DATABASE_URL a deployment sets. "postgres://" is also normalised,
    since SQLAlchemy dropped that alias.
    """
    url = os.environ.get(key, default)
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


class BaseConfig:
    """Shared configuration across all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")

    SQLALCHEMY_DATABASE_URI = _db_url(
        "DATABASE_URL", "postgresql://softstudio:softstudio@db:5432/softstudio"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Site identity
    SITE_NAME = os.environ.get("SITE_NAME", "Jaybalo Studio")
    SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")

    # Sessions / cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # overridden to True in ProductionConfig
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # CSRF (Flask-WTF)
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_STRICT = False  # overridden to True in ProductionConfig

    # OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")

    # Mail
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = _bool_env("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _bool_env("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@example.com")

    # Payments (provider-agnostic; see app/payments/services.py)
    PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "flutterwave")
    PAYMENT_SECRET_KEY = os.environ.get("PAYMENT_SECRET_KEY")
    PAYMENT_PUBLIC_KEY = os.environ.get("PAYMENT_PUBLIC_KEY")
    PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET")
    DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "NGN")

    # Uploads
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB, whole request (Flask returns 413 above this)
    # Public images written by app/uploads.py, served at /static/images/uploads/.
    # In Docker this directory is a named volume shared with nginx.
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(basedir, "app", "static", "images", "uploads")
    )
    IMAGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per image
    # No SVG: it is XML that can carry script and would be served from our origin.
    # Reference only; the enforced allowlist is app/uploads.py ALLOWED_EXTENSIONS.
    UPLOAD_ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}
    UPLOAD_ALLOWED_RESOURCE_EXT = {"pdf", "zip"}

    # Rate limiting (Flask-Limiter storage backend)
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Cookie consent
    COOKIE_CONSENT_NAME = "cookie_consent"
    COOKIE_CONSENT_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _db_url(
        "DATABASE_URL", "postgresql://softstudio:softstudio@localhost:5432/softstudio_dev"
    )
    WTF_CSRF_SSL_STRICT = False


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _db_url(
        "TEST_DATABASE_URL", "postgresql://softstudio:softstudio@localhost:5432/softstudio_test"
    )
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    MAIL_SUPPRESS_SEND = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_SSL_STRICT = True
    PREFERRED_URL_SCHEME = "https"

    def __init__(self):
        # Fail fast if critical secrets are missing in production.
        required = ["SECRET_KEY", "DATABASE_URL"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"Missing required production environment variables: {', '.join(missing)}"
            )


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
