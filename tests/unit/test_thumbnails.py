"""
Unit tests for the shared thumbnail helper: disk cache, EXIF rotation, eviction
of old versions and of both sizes (app and dashboard).
"""

import asyncio
import io
import os

import pytest
from PIL import Image

from src.utils import thumbnails


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Point the cache at tmp_path."""
    monkeypatch.setattr(thumbnails, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    return tmp_path / "thumbs"


def _jpeg(path, size=(1200, 600), orientation=None):
    img = Image.new("RGB", size, "red")
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    img.save(path, format="JPEG", exif=exif.tobytes())


def _thumb(path, name, prefix=""):
    return asyncio.run(thumbnails.get_thumbnail(path, "src", name, (256, 256), 75, prefix))


def test_generates_and_caches(tmp_path, cache):
    photo = tmp_path / "a b.jpg"
    _jpeg(photo)
    data = _thumb(photo, "a b.jpg")
    assert Image.open(io.BytesIO(data)).size == (256, 128)
    assert len(list(cache.glob("src_a b.jpg_*.jpg"))) == 1
    assert _thumb(photo, "a b.jpg") == data


def test_applies_exif_orientation(tmp_path, cache):
    photo = tmp_path / "rot.jpg"
    _jpeg(photo, orientation=6)  # rotate 90°: landscape pixels shown as portrait
    data = _thumb(photo, "rot.jpg")
    assert Image.open(io.BytesIO(data)).size == (128, 256)


def test_new_version_replaces_old(tmp_path, cache):
    photo = tmp_path / "p.jpg"
    _jpeg(photo)
    _thumb(photo, "p.jpg")
    st = photo.stat()
    os.utime(photo, (st.st_atime, st.st_mtime + 10))
    _thumb(photo, "p.jpg")
    assert len(list(cache.glob("src_p.jpg_*.jpg"))) == 1


def test_evict_removes_both_sizes(tmp_path, cache):
    photo = tmp_path / "Mom [1].jpg"
    _jpeg(photo)
    _thumb(photo, "Mom [1].jpg")
    _thumb(photo, "Mom [1].jpg", prefix="dash_")
    assert len(list(cache.iterdir())) == 2
    thumbnails.evict("src", "Mom [1].jpg")
    assert list(cache.iterdir()) == []
