from flask import Blueprint, render_template, abort, request

from app.models import BlogPost

bp = Blueprint("blog", __name__)

PER_PAGE = 9


@bp.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    pagination = (
        BlogPost.query.filter_by(published=True)
        .order_by(BlogPost.published_at.desc())
        .paginate(page=page, per_page=PER_PAGE, error_out=False)
    )
    return render_template("blog/index.html", pagination=pagination, posts=pagination.items)


@bp.route("/<slug>")
def detail(slug):
    post = BlogPost.query.filter_by(slug=slug, published=True).first()
    if not post:
        abort(404)
    related = (
        BlogPost.query.filter(
            BlogPost.category_id == post.category_id, BlogPost.id != post.id, BlogPost.published.is_(True)
        )
        .limit(3)
        .all()
    )
    return render_template("blog/detail.html", post=post, related=related)
