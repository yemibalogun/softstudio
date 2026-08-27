from flask import Blueprint, render_template

from app.models import Project, Course, Service, Testimonial

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    featured_projects = (
        Project.query.filter_by(published=True, featured=True)
        .order_by(Project.display_order)
        .limit(6)
        .all()
    )
    featured_courses = (
        Course.query.filter_by(published=True, featured=True)
        .limit(6)
        .all()
    )
    services = Service.query.filter_by(published=True).order_by(Service.display_order).all()
    testimonials = (
        Testimonial.query.filter_by(approved=True, featured=True)
        .order_by(Testimonial.display_order)
        .all()
    )
    return render_template(
        "home/index.html",
        projects=featured_projects,
        courses=featured_courses,
        services=services,
        testimonials=testimonials,
    )


@bp.route("/about")
def about():
    return render_template("home/about.html")


@bp.route("/robots.txt")
def robots():
    from flask import Response, current_app
    lines = [
        "User-agent: *",
        "Disallow: /dashboard/",
        "Disallow: /account/",
        "Disallow: /admin/",
        "Disallow: /payments/",
        f"Sitemap: {current_app.config['SITE_URL']}/sitemap.xml",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    from flask import Response, current_app, url_for

    urls = [
        url_for("main.index"),
        url_for("projects.index"),
        url_for("courses.index"),
        url_for("services.index"),
        url_for("blog.index"),
        url_for("main.about"),
        url_for("contact.index"),
        url_for("legal.privacy"),
        url_for("legal.cookies"),
        url_for("legal.terms"),
        url_for("legal.refunds"),
    ]
    xml_items = "".join(
        f"<url><loc>{current_app.config['SITE_URL']}{u}</loc></url>" for u in urls
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>' \
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml_items}</urlset>'
    return Response(xml, mimetype="application/xml")
