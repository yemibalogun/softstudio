from flask import Blueprint, render_template, abort

from app.models import Service

bp = Blueprint("services", __name__)


@bp.route("/")
def index():
    services = Service.query.filter_by(published=True).order_by(Service.display_order).all()
    return render_template("services/index.html", services=services)


@bp.route("/<slug>")
def detail(slug):
    service = Service.query.filter_by(slug=slug, published=True).first()
    if not service:
        abort(404)
    return render_template("services/detail.html", service=service)
