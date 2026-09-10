from app.blog.render import render_markdown


def test_paragraphs_are_split():
    html = str(render_markdown("First paragraph.\n\nSecond paragraph."))
    assert "<p>First paragraph.</p>" in html
    assert "<p>Second paragraph.</p>" in html


def test_fenced_code_block_is_highlighted():
    md = "Intro.\n\n```python\ndef hi():\n    return 1\n```\n"
    html = str(render_markdown(md))
    assert 'class="highlight"' in html
    # Pygments token spans (keyword etc.) prove real highlighting ran.
    assert 'class="k"' in html or 'class="nf"' in html
    assert "def" in html


def test_unlabeled_fence_still_renders_as_code_not_prose():
    html = str(render_markdown("```\nplain text block\n```"))
    assert 'class="highlight"' in html
    assert "plain text block" in html


def test_inline_code_preserved():
    html = str(render_markdown("Use the `ProxyFix` middleware."))
    assert "<code>ProxyFix</code>" in html


def test_raw_html_script_is_stripped():
    html = str(render_markdown("Hello\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>"))
    assert "<script>" not in html
    assert "onerror" not in html


def test_links_and_images_survive_sanitizer():
    html = str(render_markdown("[docs](https://example.com) and ![a diagram](/x.png)"))
    assert '<a href="https://example.com">docs</a>' in html
    assert 'src="/x.png"' in html and 'alt="a diagram"' in html


def test_none_and_empty():
    assert str(render_markdown(None)) == ""
    assert str(render_markdown("")) == ""


def test_blog_detail_renders_markdown_body(client, db):
    from app.models import BlogPost
    from datetime import datetime, timezone

    post = BlogPost(
        title="Rendering Test",
        slug="rendering-test",
        excerpt="x",
        body="## Heading\n\nA paragraph.\n\n```python\nx = 1\n```",
        published=True,
        published_at=datetime.now(timezone.utc),
    )
    db.session.add(post)
    db.session.commit()

    resp = client.get("/blog/rendering-test")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<h2" in body and "Heading" in body
    assert "<p>A paragraph.</p>" in body
    assert 'class="highlight"' in body
