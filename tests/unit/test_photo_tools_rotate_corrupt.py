"""
Unit tests: Tools tab Rotate Photos (PL-126) and Corrupt Photo Finder (PL-127).
Real images made with Pillow; rclone is mocked.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api.app import app
from src.services import photo_tools_service as svc
from src.services.source_manager import PhotoSource, SourceManager
from src.utils.rclone import RcloneResult

LAN = ("192.168.1.50", 50000)


@pytest.fixture
def album(tmp_path, monkeypatch):
    """Album "trip" in tmp with a cloud folder; rclone uploads and deletes are recorded."""
    folder = tmp_path / "trip"
    folder.mkdir()
    manager = SourceManager(tmp_path / "sources.yaml")
    manager._save_sources([PhotoSource(id="trip", name="Trip", local_path=str(folder), rclone_remote="kfr:KFR_trip")])
    monkeypatch.setattr(svc, "source_manager", manager)
    calls = SimpleNamespace(uploads=[], deletes=[], ok=True)

    async def fake_copyto(local_file, remote_dest):
        calls.uploads.append((remote_dest, Image.open(local_file).size))
        return RcloneResult(success=calls.ok, error=None if calls.ok else "network down")

    async def fake_delete(remote, filename):
        calls.deletes.append((remote, filename))
        return RcloneResult(success=True)

    monkeypatch.setattr("src.utils.rclone.rclone_copyto", fake_copyto)
    monkeypatch.setattr(svc, "rclone_deletefile_raw", fake_delete)
    monkeypatch.setattr(svc.thumbnails, "evict", lambda *a: None)
    return SimpleNamespace(folder=folder, calls=calls)


def _jpeg(path, size=(40, 20), orientation=None):
    img = Image.new("RGB", size, (200, 30, 30))
    exif = img.getexif()
    if orientation:
        exif[274] = orientation
    img.save(path, "JPEG", exif=exif.tobytes())


# --- Corrupt finder -------------------------------------------------------------

def test_scan_corrupt_finds_empty_truncated_and_fake(album):
    _jpeg(album.folder / "good.jpg")
    (album.folder / "empty.jpg").write_bytes(b"")
    good = (album.folder / "good.jpg").read_bytes()
    (album.folder / "cut.jpg").write_bytes(good[: len(good) // 2])
    (album.folder / "notes.jpg").write_bytes(b"this is not a photo")
    (album.folder / "readme.txt").write_text("ignored")

    result = svc.scan_corrupt("trip")
    found = {f.filename: f.error for f in result.files}
    assert set(found) == {"empty.jpg", "cut.jpg", "notes.jpg"}
    assert found["empty.jpg"] == "Empty file (0 bytes)"
    assert result.total_files_scanned == 4


def test_apply_corrupt_deletes_cloud_first_and_refuses_non_photos(album):
    (album.folder / "empty.jpg").write_bytes(b"")
    (album.folder / "keep.txt").write_text("x")
    result = asyncio.run(svc.apply_corrupt("trip", ["empty.jpg", "keep.txt", "../outside.jpg"]))
    assert result.succeeded == ["empty.jpg"]
    assert {f["filename"] for f in result.failed} == {"keep.txt", "../outside.jpg"}
    assert album.calls.deletes == [("kfr:KFR_trip", "empty.jpg")]
    assert not (album.folder / "empty.jpg").exists() and (album.folder / "keep.txt").exists()


# --- Rotate ------------------------------------------------------------------------

def test_rotate_right_turns_pixels_and_uploads_first(album):
    _jpeg(album.folder / "wide.jpg", size=(40, 20))
    result = asyncio.run(svc.rotate_photos("trip", [svc.RotateItem(filename="wide.jpg", rotate="right")]))
    assert result.succeeded == ["wide.jpg"]
    assert album.calls.uploads == [("kfr:KFR_trip/wide.jpg", (20, 40))]
    with Image.open(album.folder / "wide.jpg") as img:
        assert img.size == (20, 40)
    assert [p.name for p in album.folder.iterdir()] == ["wide.jpg"]  # no temp file left


def test_rotate_auto_applies_exif_orientation_and_resets_tag(album):
    _jpeg(album.folder / "phone.jpg", size=(40, 20), orientation=6)  # 6 = shown turned 90° clockwise
    asyncio.run(svc.rotate_photos("trip", [svc.RotateItem(filename="phone.jpg", rotate="auto")]))
    with Image.open(album.folder / "phone.jpg") as img:
        assert img.size == (20, 40)
        assert img.getexif().get(274) == 1


def test_rotate_relative_to_how_it_looks(album):
    """'left' on a photo with orientation 6 (looks portrait) gives the landscape it really is."""
    _jpeg(album.folder / "phone.jpg", size=(40, 20), orientation=6)
    asyncio.run(svc.rotate_photos("trip", [svc.RotateItem(filename="phone.jpg", rotate="left")]))
    with Image.open(album.folder / "phone.jpg") as img:
        assert img.size == (40, 20)
        assert img.getexif().get(274) == 1


def test_rotate_cloud_failure_leaves_photo_unchanged(album):
    _jpeg(album.folder / "wide.jpg", size=(40, 20))
    before = (album.folder / "wide.jpg").read_bytes()
    album.calls.ok = False
    result = asyncio.run(svc.rotate_photos("trip", [svc.RotateItem(filename="wide.jpg", rotate="180")]))
    assert result.succeeded == [] and "Cloud upload failed" in result.failed[0]["error"]
    assert (album.folder / "wide.jpg").read_bytes() == before
    assert [p.name for p in album.folder.iterdir()] == ["wide.jpg"]


def test_rotate_rejects_bad_input(album):
    _jpeg(album.folder / "a.jpg")
    (album.folder / "clip.mov").write_bytes(b"x")
    result = asyncio.run(svc.rotate_photos("trip", [
        svc.RotateItem(filename="a.jpg", rotate="sideways"),
        svc.RotateItem(filename="clip.mov", rotate="right"),
        svc.RotateItem(filename="../x.jpg", rotate="right"),
    ]))
    assert result.succeeded == [] and len(result.failed) == 3


def test_dashboard_routes(album):
    _jpeg(album.folder / "wide.jpg")
    (album.folder / "empty.jpg").write_bytes(b"")
    client = TestClient(app, client=LAN)
    scan = client.get("/api/tools/trip/scan/corrupt").json()
    assert scan["ok"] and [f["filename"] for f in scan["files"]] == ["empty.jpg"]
    rot = client.post("/api/tools/trip/rotate", json={"items": [{"filename": "wide.jpg", "rotate": "left"}]}).json()
    assert rot["ok"] and rot["succeeded"] == ["wide.jpg"]
    assert client.post("/api/tools/trip/rotate", json={"items": []}).json()["ok"] is False
    dele = client.post("/api/tools/trip/apply/corrupt", json={"to_delete": ["empty.jpg"]}).json()
    assert dele["ok"] and dele["succeeded"] == ["empty.jpg"]
