"""
The JSWM Abbreviator privacy page is the URL on the app's Google Play
listing. Google checks that it names the app and matches the app's Data
safety answers, so these tests pin both.
"""
import re


def _text(client, url):
    resp = client.get(url)
    assert resp.status_code == 200, url
    return re.sub(r"\s+", " ", resp.data.decode())


def test_the_app_privacy_page_names_the_app_and_says_nothing_is_collected(client, app):
    page = _text(client, "/privacy/jswm-abbreviator")
    assert "<title>JSWM Abbreviator Privacy Policy" in page
    for phrase in ("does not collect, store on any server, share or sell",
                   "does not request permission to use the internet",
                   "read on your device only",
                   "Your original document is never changed",
                   "The app does not read the clipboard"):
        assert phrase in page, phrase
    assert f"mailto:{app.config['ADMIN_EMAIL']}" in page
    # Points back to the website policy rather than repeating it.
    assert 'href="/privacy"' in page


def test_the_app_privacy_page_answers_with_a_trailing_slash(client):
    resp = client.get("/privacy/jswm-abbreviator/")
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/privacy/jswm-abbreviator"


def test_the_app_privacy_page_is_in_the_sitemap(client):
    assert "/privacy/jswm-abbreviator</loc>" in client.get("/sitemap.xml").data.decode()
