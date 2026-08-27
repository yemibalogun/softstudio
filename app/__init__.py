import os

from flask import Flask, render_template, request

from app.config import config_map
from app.extensions import db, migrate, login_manager, csrf, mail, oauth, limiter


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)

    config_obj = config_map.get(config_name, config_map["default"])
    app.config.from_object(config_obj() if config_name == "production" else config_obj)

    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    _register_context_processors(app)
    _register_cli(app)

    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    oauth.init_app(app)
    limiter.init_app(app)

    from app.models.user import User

    @login_manager.user_loader
    def load_user(public_id: str):
        return User.query.filter_by(public_id=public_id, is_active=True).first()

    # OAuth provider registration (Google, GitHub). Structured so
    # additional providers can be added without touching route logic.
    if app.config.get("GOOGLE_CLIENT_ID"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    if app.config.get("GITHUB_CLIENT_ID"):
        oauth.register(
            name="github",
            client_id=app.config["GITHUB_CLIENT_ID"],
            client_secret=app.config["GITHUB_CLIENT_SECRET"],
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )


def _register_blueprints(app: Flask) -> None:
    from app.main.routes import bp as main_bp
    from app.auth.routes import bp as auth_bp
    from app.account.routes import bp as account_bp
    from app.projects.routes import bp as projects_bp
    from app.courses.routes import bp as courses_bp
    from app.learning.routes import bp as learning_bp
    from app.services.routes import bp as services_bp
    from app.contact.routes import bp as contact_bp
    from app.blog.routes import bp as blog_bp
    from app.payments.routes import bp as payments_bp
    from app.admin.routes import bp as admin_bp
    from app.legal.routes import bp as legal_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(account_bp, url_prefix="/account")
    app.register_blueprint(projects_bp, url_prefix="/projects")
    app.register_blueprint(courses_bp, url_prefix="/courses")
    app.register_blueprint(learning_bp, url_prefix="/dashboard")
    app.register_blueprint(services_bp, url_prefix="/services")
    app.register_blueprint(contact_bp, url_prefix="/contact")
    app.register_blueprint(blog_bp, url_prefix="/blog")
    app.register_blueprint(payments_bp, url_prefix="/payments")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(legal_bp)


def _register_error_handlers(app: Flask) -> None:
    handlers = {
        400: "errors/400.html",
        403: "errors/403.html",
        404: "errors/404.html",
        429: "errors/429.html",
        500: "errors/500.html",
    }

    def make_handler(status_code: int, template: str):
        def handler(err):
            if status_code == 500:
                app.logger.exception("Unhandled server error: %s", err)
            return render_template(template), status_code
        return handler

    for status_code, template in handlers.items():
        app.register_error_handler(status_code, make_handler(status_code, template))


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if app.config.get("PREFERRED_URL_SCHEME") == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        # CSP kept permissive-but-scoped; tighten per-page via nonce if
        # third-party embeds (payment SDKs, video players) are added.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "frame-ancestors 'none';",
        )
        return response


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        return {
            "site_name": app.config["SITE_NAME"],
            "site_url": app.config["SITE_URL"],
            "current_path": request.path,
        }


def _register_cli(app: Flask) -> None:
    from app.cli import register_cli_commands
    register_cli_commands(app)
