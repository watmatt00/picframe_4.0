"""
Unit tests: a contributor upload that exactly matches a photo already in the album's
cloud folder is skipped (PL-129); different photos and failed listings still upload.
"""

import hashlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.dependencies import require_contributor
from src.api.routes import contributor
from src.utils.rclone import RcloneResult

PHOTO = b"\xff\xd8\xff\xe0 fake jpeg bytes"


@pytest.fixture
def upload(monkeypatch):
    """Contributor auth bypassed, one cloud source, rclone mocked. Returns (post, copies, listing)."""
    source = SimpleNamespace(id="fam", name="Family", enabled=True, rclone_remote="koofr:KFR_fam")
    monkeypatch.setattr(contributor.source_manager, "get_source", lambda sid: source if sid == "fam" else None)
    app.dependency_overrides[require_contributor] = lambda: SimpleNamespace(device_name="Phone", role="contributor")

    copies = []
    listing = {"files": []}

    async def fake_copyto(local, dest):
        copies.append(dest)
        return RcloneResult(success=True)

    async def fake_list(remote):
        return listing["files"]

    monkeypatch.setattr(contributor, "rclone_copyto", fake_copyto)
    monkeypatch.setattr(contributor, "rclone_list_md5", fake_list)

    def post(data=PHOTO):
        return TestClient(app).post(
            "/api/v1/contributor/upload/fam", files={"file": ("p.jpg", data, "image/jpeg")}
        )

    yield post, copies, listing
    app.dependency_overrides.clear()


def test_exact_copy_is_skipped(upload):
    post, copies, listing = upload
    listing["files"] = [("old.jpg", len(PHOTO), hashlib.md5(PHOTO).hexdigest())]
    r = post()
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] is True
    assert r.json()["file_name"] == "old.jpg"
    assert copies == []


def test_same_size_different_photo_uploads(upload):
    post, copies, listing = upload
    listing["files"] = [("old.jpg", len(PHOTO), "0" * 32)]
    r = post()
    assert r.json()["skipped"] is False
    assert len(copies) == 1


def test_listing_failure_still_uploads(upload):
    post, copies, listing = upload
    listing["files"] = None
    r = post()
    assert r.status_code == 200
    assert r.json()["skipped"] is False
    assert len(copies) == 1
