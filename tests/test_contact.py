from app.models import ProjectInquiry


def test_valid_inquiry_is_stored(client):
    resp = client.post(
        "/contact/",
        data={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "project_type": "web_app",
            "project_description": "Need a dashboard for tracking inventory.",
            "website": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    inquiry = ProjectInquiry.query.filter_by(email="jane@example.com").first()
    assert inquiry is not None
    assert inquiry.name == "Jane Doe"


def test_invalid_inquiry_missing_required_fields(client):
    resp = client.post(
        "/contact/",
        data={"name": "", "email": "not-an-email", "website": ""},
    )
    assert resp.status_code == 200  # re-renders form with errors
    assert ProjectInquiry.query.count() == 0


def test_honeypot_field_blocks_storage(client):
    resp = client.post(
        "/contact/",
        data={
            "name": "Bot",
            "email": "bot@spam.com",
            "project_type": "web_app",
            "project_description": "spam content",
            "website": "http://spam-link.example.com",  # honeypot triggered
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Bot receives what looks like a normal success response...
    assert ProjectInquiry.query.count() == 0  # ...but nothing is persisted.


def test_html_is_stripped_from_free_text_fields(client):
    client.post(
        "/contact/",
        data={
            "name": "Jane Doe",
            "email": "jane2@example.com",
            "project_type": "web_app",
            "project_description": "<script>alert(1)</script>Need automation.",
            "website": "",
        },
        follow_redirects=True,
    )
    inquiry = ProjectInquiry.query.filter_by(email="jane2@example.com").first()
    assert inquiry is not None
    assert "<script>" not in inquiry.project_description
