"""
Unit tests for photo delete/rename (DELETE/PATCH /api/v1/sources/{id}/photos/{filename}).

Delete accepts any existing image name; rename keeps the strict name rule.
"""

from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.dependencies import require_admin
from src.api.routes import photos
from src.utils.rclone import RcloneResult

SPECIAL = "Mom & Dad + #1.jpg"


@pytest.fixture
def source_dir(tmp_path, monkeypatch):
    """A fake source on tmp_path, admin auth bypassed, rclone mocked out."""
    folder = tmp_path / "src"
    folder.mkdir()
    source = SimpleNamespace(id="test", local_path=str(folder), rclone_remote="koofr:test")
    monkeypatch.setattr(photos.source_manager, "get_source", lambda sid: source if sid == "test" else None)
    monkeypatch.setattr(photos.thumbnails, "THUMB_CACHE_DIR", tmp_path / "thumbs")

    calls = []

    async def fake_delete(remote, filename):
        calls.append(("delete", remote, filename))
        return RcloneResult(success=True, files_deleted=1)

    async def fake_move(remote, old, new):
        calls.append(("move", remote, old, new))
        return RcloneResult(success=True)

    monkeypatch.setattr(photos, "rclone_deletefile_raw", fake_delete)
    monkeypatch.setattr(photos, "rclone_movefile_raw", fake_move)
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    yield folder, calls
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def client():
    return TestClient(app)


def _url(filename: str) -> str:
    return f"/api/v1/sources/test/photos/{quote(filename, safe='')}"


def test_delete_special_name(client, source_dir):
    folder, calls = source_dir
    (folder / SPECIAL).write_bytes(b"x")
    r = client.delete(_url(SPECIAL))
    assert r.status_code == 200, r.text
    assert not (folder / SPECIAL).exists()
    assert calls == [("delete", "koofr:test", SPECIAL)]


@pytest.mark.parametrize("name", ["../x.jpg", "a/b.jpg", "x.txt", "missing.jpg"])
def test_delete_rejects_bad_names(client, source_dir, name):
    # An encoded "/" is decoded before routing, so slashes 404 instead of 400
    folder, calls = source_dir
    (folder / "x.txt").write_bytes(b"x")
    r = client.delete(_url(name))
    assert r.status_code in (400, 404), r.text
    assert calls == []


def test_rename_special_name_to_valid_name(client, source_dir):
    folder, calls = source_dir
    (folder / SPECIAL).write_bytes(b"x")
    r = client.patch(_url(SPECIAL), json={"new_filename": "Mom_Dad_1.jpg"})
    assert r.status_code == 200, r.text
    assert (folder / "Mom_Dad_1.jpg").exists() and not (folder / SPECIAL).exists()
    assert calls == [("move", "koofr:test", SPECIAL, "Mom_Dad_1.jpg")]


@pytest.mark.parametrize("name", ["../x.jpg", "x.txt", "missing.jpg"])
def test_rename_rejects_bad_current_names(client, source_dir, name):
    folder, calls = source_dir
    (folder / "x.txt").write_bytes(b"x")
    r = client.patch(_url(name), json={"new_filename": "fine.jpg"})
    assert r.status_code in (400, 404), r.text
    assert calls == []


def test_rename_to_special_name_rejected(client, source_dir):
    folder, calls = source_dir
    (folder / "ok.jpg").write_bytes(b"x")
    r = client.patch(_url("ok.jpg"), json={"new_filename": "a&b.jpg"})
    assert r.status_code == 400
    assert "letters, numbers" in r.json()["detail"]
    assert calls == []


def test_rename_normal(client, source_dir):
    folder, calls = source_dir
    (folder / "ok.jpg").write_bytes(b"x")
    r = client.patch(_url("ok.jpg"), json={"new_filename": "better name.jpg"})
    assert r.status_code == 200, r.text
    assert (folder / "better name.jpg").exists()
    assert calls == [("move", "koofr:test", "ok.jpg", "better name.jpg")]
