import os
import time

import pytest

TOKEN = "test-reel-token"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
AUTH = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "video/mp4"}


@pytest.fixture()
def reels(app, tmp_path):
    app.config["PROTECTED_UPLOADS_DIR"] = str(tmp_path / "protected")
    app.config["REEL_HOST_TOKEN"] = TOKEN
    return tmp_path / "protected" / "reels"


def test_everything_is_a_404_when_no_token_is_configured(app, client):
    app.config["REEL_HOST_TOKEN"] = None
    assert client.post("/internal/reels", data=MP4, headers=AUTH).status_code == 404
    assert client.get("/r/" + "a" * 32 + ".mp4").status_code == 404


def test_upload_needs_the_token(client, reels):
    assert client.post("/internal/reels", data=MP4).status_code == 403
    bad = {**AUTH, "Authorization": "Bearer wrong"}
    assert client.post("/internal/reels", data=MP4, headers=bad).status_code == 403


def test_an_uploaded_reel_is_served_then_deleted(client, reels):
    r = client.post("/internal/reels", data=MP4, headers=AUTH)
    assert r.status_code == 201
    name = r.get_json()["name"]
    assert r.get_json()["url"].endswith(f"/r/{name}.mp4")
    assert len(name) == 32 and os.listdir(reels) == [f"{name}.mp4"]

    served = client.get(f"/r/{name}.mp4")
    assert served.status_code == 200
    assert served.mimetype == "video/mp4"
    assert served.data == MP4
    served.close()  # release the file handle (Windows won't delete an open file)

    assert client.delete(f"/internal/reels/{name}", headers=AUTH).status_code == 204
    assert client.get(f"/r/{name}.mp4").status_code == 404


def test_delete_needs_the_token(client, reels):
    name = client.post("/internal/reels", data=MP4, headers=AUTH).get_json()["name"]
    assert client.delete(f"/internal/reels/{name}").status_code == 403
    assert client.get(f"/r/{name}.mp4").status_code == 200


def test_range_requests_are_supported(client, reels):
    name = client.post("/internal/reels", data=MP4, headers=AUTH).get_json()["name"]
    part = client.get(f"/r/{name}.mp4", headers={"Range": "bytes=0-9"})
    assert part.status_code == 206
    assert part.data == MP4[:10]


def test_files_that_are_not_mp4_are_rejected(client, reels):
    assert client.post("/internal/reels", data=b"<html>not a video</html>", headers=AUTH).status_code == 400
    assert client.post("/internal/reels", data=b"", headers=AUTH).status_code == 400


def test_the_size_cap_is_enforced(app, client, reels):
    app.config["REEL_HOST_MAX_BYTES"] = 50
    assert client.post("/internal/reels", data=MP4, headers=AUTH).status_code == 413


def test_names_that_were_not_generated_here_are_refused(client, reels):
    assert client.get("/r/../../etc/passwd.mp4").status_code == 404
    assert client.get("/r/NOTHEX" + "0" * 26 + ".mp4").status_code == 404
    assert client.delete("/internal/reels/..%2Fsecret", headers=AUTH).status_code == 404


def test_old_files_are_pruned_on_upload(app, client, reels):
    first = client.post("/internal/reels", data=MP4, headers=AUTH).get_json()["name"]
    old = time.time() - (app.config["REEL_HOST_TTL_HOURS"] + 1) * 3600
    os.utime(reels / f"{first}.mp4", (old, old))
    second = client.post("/internal/reels", data=MP4, headers=AUTH).get_json()["name"]
    assert os.listdir(reels) == [f"{second}.mp4"]
