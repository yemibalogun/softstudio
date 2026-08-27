from app.extensions import db
from app.models import TimestampMixin

blog_post_tags = db.Table(
    "blog_post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("blog_posts.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("blog_tags.id", ondelete="CASCADE"), primary_key=True),
)


class BlogCategory(db.Model):
    __tablename__ = "blog_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)

    posts = db.relationship("BlogPost", back_populates="category")


class BlogTag(db.Model):
    __tablename__ = "blog_tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)


class BlogPost(db.Model, TimestampMixin):
    __tablename__ = "blog_posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)

    excerpt = db.Column(db.String(400))
    body = db.Column(db.Text, nullable=False)
    featured_image = db.Column(db.String(512))

    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    author = db.relationship("User")

    category_id = db.Column(db.Integer, db.ForeignKey("blog_categories.id"))
    category = db.relationship("BlogCategory", back_populates="posts")
    tags = db.relationship("BlogTag", secondary=blog_post_tags, backref="posts")

    published = db.Column(db.Boolean, default=False, nullable=False)
    published_at = db.Column(db.DateTime(timezone=True))

    meta_title = db.Column(db.String(180))
    meta_description = db.Column(db.String(300))
    og_image = db.Column(db.String(512))

    def __repr__(self):
        return f"<BlogPost {self.slug}>"
