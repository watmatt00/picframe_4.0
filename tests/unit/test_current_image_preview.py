"""
Unit tests: dashboard preview of the photo on the frame (PL-174). The name comes
from Pi3D's Content-Disposition; the image is our own thumbnail, so HEIC works.
"""

import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from src.dashboard import routes
from src.utils import thumbnails


@pytest.mark.parametrize("header, expected", [
    ("inline; filename=\"a.jpg\"; filename*=utf-8''a.jpg", "a.jpg"),
    ("inline; filename=\"x.heic\"; filename*=utf-8''caf%C3%A9%20pic.heic", "café pic.heic"),
    ('inline; filename="only plain.jpg"', "only plain.jpg"),
    ("", None),
])
def test_filename_from_disposition(header, expected):
    assert routes._filename_from_disposition(header) == expected


@pytest.fixture
def albums(tmp_path, monkeypatch):
    """Two albums, 'trip' showing; both hold a photo called same.jpg."""
    for name in ("trip", "home"):
        (tmp_path / name).mkdir()
        Image.new("RGB", (1200, 900), "blue").save(tmp_path / name / "same.jpg")
    Image.new("RGB", (900, 1200), "red").save(tmp_path / "home" / "only_home.jpg")
    sources = [SimpleNamespace(id=n, local_path=str(tmp_path / n)) for n in ("home", "trip")]
    monkeypatch.setattr(routes, "source_manager", SimpleNamespace(list_sources=lambda: sources))
    monkeypatch.setattr(routes, "get_settings",
                        lambda: SimpleNamespace(display=SimpleNamespace(current_source="trip")))
    monkeypatch.setattr(thumbnails, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    return tmp_path


def _client():
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_find_prefers_showing_album(albums):
    assert routes._find_current_photo("same.jpg") == ("trip", albums / "trip" / "same.jpg")
    assert routes._find_current_photo("only_home.jpg") == ("home", albums / "home" / "only_home.jpg")


@pytest.mark.parametrize("name", [None, "", "missing.jpg", "../trip/same.jpg", "a/b.jpg"])
def test_find_rejects_missing_or_traversal(albums, name):
    assert routes._find_current_photo(name) is None


def test_preview_serves_our_thumbnail(albums):
    client = _client()
    resp = client.get("/current-image", params={"filename": "only_home.jpg"})
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(resp.content)).size == (420, 560)
    assert list((albums / "thumbs").glob("preview_home_only_home.jpg_*.jpg"))


def test_preview_503_when_pi3d_down(albums, monkeypatch):
    """Not in an album and Pi3D unreachable: 503, not an empty 200/404."""
    monkeypatch.setattr(routes, "PI3D_URL", "http://127.0.0.1:9")
    client = _client()
    assert client.get("/current-image", params={"filename": "nowhere.jpg"}).status_code == 503
    assert client.get("/current-image/info").json() == {"filename": None}


def test_evict_drops_preview_size(albums):
    client = _client()
    client.get("/current-image", params={"filename": "only_home.jpg"})
    thumbnails.evict("home", "only_home.jpg")
    assert not list((albums / "thumbs").glob("preview_*"))
