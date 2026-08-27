from flask import Blueprint, render_template, abort

from app.models import Project

bp = Blueprint("projects", __name__)


@bp.route("/")
def index():
    projects = Project.query.filter_by(published=True).order_by(Project.display_order).all()
    return render_template("projects/index.html", projects=projects)


@bp.route("/<slug>")
def detail(slug):
    project = Project.query.filter_by(slug=slug, published=True).first()
    if not project:
        abort(404)
    related_services = []  # populate via category -> service mapping once seeded
    return render_template("projects/detail.html", project=project, related_services=related_services)
