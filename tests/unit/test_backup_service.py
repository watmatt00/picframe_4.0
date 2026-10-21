"""
Unit tests: Photo Backups on the dashboard's Backups tab (PL-164): per-album and
whole-frame backups (one archive with a manifest), the free-space check,
download, and deleting a backup by filename.
"""

import asyncio
import re
import shutil
import tarfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.dashboard import routes
from src.services import backup_service
from src.services import source_manager as sm
from src.services.source_manager import PhotoSource, SourceManager

LAN = ("192.168.1.50", 50000)


@pytest.fixture
def frame(tmp_path, monkeypatch):
    """Temp ~/Pictures with albums trip, trip_2 (prefix of trip) and empty_one (no folder yet)."""
    pictures = tmp_path / "Pictures"
    for sid in ("trip", "trip_2"):
        (pictures / sid).mkdir(parents=True)
        (pictures / sid / "a.jpg").write_bytes(b"x" * 100)
    backups = pictures / "backups"
    backups.mkdir()

    manager = SourceManager(tmp_path / "sources.yaml")
    manager._save_sources([
        PhotoSource(id=sid, name=sid.title(), local_path=str(pictures / sid), rclone_remote=f"kfr:KFR_{sid}")
        for sid in ("trip", "trip_2", "empty_one")
    ])
    monkeypatch.setattr(sm, "source_manager", manager)
    monkeypatch.setattr(routes, "source_manager", manager)
    monkeypatch.setattr(backup_service, "BACKUPS_DIR", backups)
    return SimpleNamespace(pictures=pictures, backups=backups, manager=manager)


def _no_space(monkeypatch):
    """Make the disk look full: only the 1 GB margin is free."""
    usage = shutil.disk_usage("/")._replace(free=backup_service.FREE_SPACE_MARGIN)
    monkeypatch.setattr(backup_service.shutil, "disk_usage", lambda path: usage)


def _frame_backup(frame):
    return asyncio.run(backup_service.create_frame_backup(frame.manager.list_sources(), "TK Frame", "1000000002343a2b"))


def test_frame_backup_is_one_file_with_manifest_first(frame):
    """Whole frame: one archive, manifest first, a folder per album that has one."""
    result = _frame_backup(frame)
    assert re.fullmatch(r"frame_tk-frame_\d{4}-\d{2}-\d{2}_\d{6}\.tar\.gz", result["filename"])
    assert result["albums"] == 2 and result["skipped"] == ["empty_one"]
    assert [p.name for p in frame.backups.iterdir()] == [result["filename"]]  # no temp files left
    with tarfile.open(frame.backups / result["filename"]) as tf:
        names = tf.getnames()
    assert names[0] == "manifest.yaml" and {"trip/a.jpg", "trip_2/a.jpg"} <= set(names)
    manifest = backup_service.read_frame_manifest(frame.backups / result["filename"])
    assert manifest["frame_name"] == "TK Frame"
    assert [(a["id"], a["cloud_folder"], a["photo_count"]) for a in manifest["albums"]] == [
        ("trip", "KFR_trip", 1), ("trip_2", "KFR_trip_2", 1)]


def test_frame_backup_not_enough_space_creates_nothing(frame, monkeypatch):
    """The whole set is checked first, so a full disk leaves no archive."""
    _no_space(monkeypatch)
    with pytest.raises(ValueError, match="Not enough free space"):
        _frame_backup(frame)
    assert list(frame.backups.iterdir()) == []


def test_album_called_frame_doesnt_pick_up_frame_backups(frame):
    """An album with id "frame" lists only its own backups, not frame_<name>_… ones."""
    _frame_backup(frame)
    (frame.backups / "frame_2026-10-21_091205.tar.gz").write_bytes(b"")
    assert [b["filename"] for b in backup_service.list_backups("frame")] == ["frame_2026-10-21_091205.tar.gz"]


def test_read_frame_manifest_ignores_album_backups(frame):
    """A plain album backup has no manifest."""
    created = asyncio.run(backup_service.create_backup("trip", str(frame.pictures / "trip")))
    assert backup_service.read_frame_manifest(frame.backups / created["filename"]) is None


def test_create_backup_not_enough_space(frame, monkeypatch):
    """A single album backup is refused on a full disk, and no file is left behind."""
    _no_space(monkeypatch)
    with pytest.raises(ValueError, match="Not enough free space"):
        asyncio.run(backup_service.create_backup("trip", str(frame.pictures / "trip")))
    assert list(frame.backups.iterdir()) == []


def test_list_backups_ignores_album_with_longer_id(frame):
    """Album trip's list doesn't pick up trip_2's backups (both match "trip_*")."""
    (frame.backups / "trip_2026-10-21_091205.tar.gz").write_bytes(b"")
    (frame.backups / "trip_2_2026-10-21_091205.tar.gz").write_bytes(b"")
    assert [b["filename"] for b in backup_service.list_backups("trip")] == ["trip_2026-10-21_091205.tar.gz"]
    with pytest.raises(ValueError, match="does not belong"):
        backup_service.delete_backup("trip", "trip_2_2026-10-21_091205.tar.gz")


@pytest.mark.parametrize("name", ["../x_2026-10-21_091205.tar.gz", "x.tar.gz", "Trip_2026-10-21_091205.tar.gz"])
def test_delete_backup_file_rejects_bad_names(frame, name):
    """Only <id>_<timestamp>.tar.gz names inside the backups folder can be deleted."""
    with pytest.raises(ValueError, match="Invalid backup filename"):
        backup_service.delete_backup_file(name)


def test_delete_backup_file_removes_deleted_albums_backup(frame):
    """A backup whose album is gone can still be deleted by filename."""
    f = frame.backups / "old_party_2026-10-01_120000.tar.gz"
    f.write_bytes(b"")
    backup_service.delete_backup_file(f.name)
    assert not f.exists()
    with pytest.raises(FileNotFoundError):
        backup_service.delete_backup_file(f.name)


def test_routes_whole_frame(frame):
    """Backups tab routes: create the frame backup, list all (deleted albums marked), download, delete by name."""
    client = TestClient(app, client=LAN)
    (frame.backups / "old_party_2026-10-01_120000.tar.gz").write_bytes(b"")

    r = client.post("/api/tools/backup/all/create").json()
    assert r["ok"] and r["albums"] == 2 and r["skipped"] == ["empty_one"]
    assert r["path"] == str(frame.backups / r["filename"])

    listed = client.get("/api/tools/backup/all").json()
    assert listed["ok"]
    kinds = {b["filename"]: b for b in listed["backups"]}
    assert kinds[r["filename"]]["kind"] == "frame" and kinds[r["filename"]]["album_count"] == 2
    old = kinds["old_party_2026-10-01_120000.tar.gz"]
    assert old["kind"] == "album" and not old["album_exists"] and old["path"].endswith("/backups/" + old["filename"])

    dl = client.get(f"/api/tools/backup/download/{r['filename']}")
    assert dl.status_code == 200 and dl.content == (frame.backups / r["filename"]).read_bytes()
    assert "attachment" in dl.headers["content-disposition"]
    assert client.get("/api/tools/backup/download/nope_2026-10-01_120000.tar.gz").status_code == 404
    assert client.get("/api/tools/backup/download/..%2Fsources.yaml").status_code in (400, 404)

    r = client.post("/api/tools/backup/delete", json={"filename": "old_party_2026-10-01_120000.tar.gz"}).json()
    assert r == {"ok": True}
    r = client.post("/api/tools/backup/delete", json={"filename": "../etc_2026-10-01_120000.tar.gz"}).json()
    assert not r["ok"]


def test_route_create_all_reports_no_space(frame, monkeypatch):
    """A full disk comes back as an error message, not a 500."""
    _no_space(monkeypatch)
    r = TestClient(app, client=LAN).post("/api/tools/backup/all/create").json()
    assert not r["ok"] and "Not enough free space" in r["error"]
