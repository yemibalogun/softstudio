"""
Centralized extension instances.

Extensions are instantiated here (unbound) and initialized against the
app inside the application factory (app/__init__.py). This avoids
circular imports between models, blueprints, and the factory.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()
oauth = OAuth()
limiter = Limiter(key_func=get_remote_address)

login_manager.login_view = "auth.login"  # type: ignore[assignment]
login_manager.login_message = "Please log in to access this page."  # type: ignore[assignment]
login_manager.login_message_category = "info"  # type: ignore[assignment]
