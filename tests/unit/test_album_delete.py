"""
Unit tests: deleting an album (PL-147) removes it and its photos on the frame,
keeps the cloud folder and backups, refuses the album that's showing or syncing,
and never deletes outside ~/Pictures/<album>.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from filelock import FileLock
from fastapi.testclient import TestClient

from src.api.app import app
from src.auth import jwt_handler
from src.auth.models import Device
from src.services import album_service, frame_registry
from src.services import source_manager as sm
from src.services.source_manager import PhotoSource, SourceManager
from src.services.sync_service import sync_service
from src.storage.devices import device_storage
from src.utils import thumbnails

LAN = ("192.168.1.50", 50000)


@pytest.fixture
def frame(tmp_path, monkeypatch):
    """Temp ~/Pictures with a showing album and an inactive one, plus tokens."""
    pictures = tmp_path / "Pictures"
    for name in ("showing", "trip", "spotlight", "backups"):
        (pictures / name).mkdir(parents=True)
    for i in range(3):
        (pictures / "trip" / f"p{i}.jpg").write_bytes(b"x")
    (pictures / "backups" / "trip_backup.tar.gz").write_bytes(b"x")

    # Frame registry in tmp, following this manager's changes
    monkeypatch.setattr(frame_registry, "LOCAL_PATH", tmp_path / "frame_albums.yaml")
    monkeypatch.setattr(frame_registry, "LEGACY_DELETED_PATH", tmp_path / "deleted_albums.yaml")
    monkeypatch.setattr(frame_registry, "board_serial", lambda: "1000000002343a2b")
    manager = SourceManager(tmp_path / "sources.yaml")
    manager.add_listener(frame_registry.note_change)
    manager._save_sources([
        PhotoSource(id="showing", name="Showing", local_path=str(pictures / "showing"), rclone_remote="kfr:KFR_showing"),
        PhotoSource(id="trip", name="Trip", local_path=str(pictures / "trip"), rclone_remote="kfr:KFR_trip"),
    ])
    monkeypatch.setattr(sm, "source_manager", manager)
    monkeypatch.setattr(album_service, "PICTURES_DIR", pictures)
    monkeypatch.setattr(album_service, "get_settings",
                        lambda: SimpleNamespace(display=SimpleNamespace(current_source="showing")))
    monkeypatch.setattr(thumbnails, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    (tmp_path / "thumbs").mkdir()
    (tmp_path / "thumbs" / "trip_p0.jpg_1.jpg").write_bytes(b"x")
    (tmp_path / "thumbs" / "dash_trip_p0.jpg_1.jpg").write_bytes(b"x")
    (tmp_path / "thumbs" / "showing_a.jpg_1.jpg").write_bytes(b"x")
    monkeypatch.setattr(sync_service, "_is_syncing", False)
    monkeypatch.setattr(sync_service, "_current_source", None)

    monkeypatch.setattr(device_storage, "_path", tmp_path / "devices.json")
    monkeypatch.setattr(device_storage, "_lock", FileLock(tmp_path / "devices.lock"))
    monkeypatch.setattr(jwt_handler, "SECRET_PATH", tmp_path / "jwt_secret")
    headers = {}
    for device_id, role in (("admin1", "admin"), ("con1", "contributor")):
        device_storage.add_device(Device(id=device_id, name=device_id, role=role, paired_at=datetime.now(timezone.utc)))
        token = jwt_handler.create_token(device_id=device_id, device_name=device_id, role=role, frame_id="f")
        headers[role] = {"Authorization": f"Bearer {token}"}
    return SimpleNamespace(pictures=pictures, manager=manager, headers=headers, thumbs=tmp_path / "thumbs")


def test_delete_removes_album_and_photos(frame):
    r = TestClient(app).delete("/api/v1/folders/trip", headers=frame.headers["admin"])
    assert r.status_code == 200, r.text
    assert r.json() == {
        "deleted": "trip", "name": "Trip", "photos_removed": 3, "local_folder_removed": True,
        "cloud_folder": "kfr:KFR_trip", "error": None,
    }
    assert frame.manager.get_source("trip") is None
    assert not (frame.pictures / "trip").exists()
    assert (frame.pictures / "backups" / "trip_backup.tar.gz").exists()
    assert sorted(p.name for p in frame.thumbs.iterdir()) == ["showing_a.jpg_1.jpg"]


def test_delete_is_recorded_for_recovery(frame):
    TestClient(app).delete("/api/v1/folders/trip", headers=frame.headers["admin"])
    albums = {a["folder"]: a for a in frame_registry.local_doc()["albums"]}
    assert albums["KFR_trip"]["status"] == "deleted" and albums["KFR_trip"]["name"] == "Trip"
    assert albums["KFR_showing"]["status"] == "active"
    assert (frame_registry.LOCAL_PATH.stat().st_mode & 0o777) == 0o600


def test_showing_album_is_refused(frame):
    r = TestClient(app).delete("/api/v1/folders/showing", headers=frame.headers["admin"])
    assert r.status_code == 409
    assert r.json()["detail"] == "This album is showing on the frame. Show another album first, then delete it."
    assert frame.manager.get_source("showing") is not None
    assert (frame.pictures / "showing").exists()


def test_syncing_album_is_refused(frame, monkeypatch):
    monkeypatch.setattr(sync_service, "_is_syncing", True)
    monkeypatch.setattr(sync_service, "_current_source", "trip")
    r = TestClient(app).delete("/api/v1/folders/trip", headers=frame.headers["admin"])
    assert r.status_code == 409
    assert "syncing" in r.json()["detail"]
    assert (frame.pictures / "trip").exists()


def test_unknown_album_is_404(frame):
    r = TestClient(app).delete("/api/v1/folders/nope", headers=frame.headers["admin"])
    assert r.status_code == 404


def test_contributor_cannot_delete(frame):
    r = TestClient(app).delete("/api/v1/folders/trip", headers=frame.headers["contributor"])
    assert r.status_code == 403
    assert (frame.pictures / "trip").exists()


@pytest.mark.parametrize("local_path", ["{p}/spotlight", "{p}/backups", "{p}", "{p}/../outside", "{p}/trip/sub"])
def test_unsafe_folders_are_kept(frame, local_path):
    target = local_path.format(p=frame.pictures)
    from pathlib import Path
    Path(target).mkdir(parents=True, exist_ok=True)
    frame.manager._save_sources(frame.manager.list_sources() + [
        PhotoSource(id="odd", name="Odd", local_path=target),
    ])
    r = TestClient(app).delete("/api/v1/folders/odd", headers=frame.headers["admin"])
    assert r.status_code == 200
    assert r.json()["local_folder_removed"] is False
    assert Path(target).exists()
    assert frame.manager.get_source("odd") is None


def test_folder_shared_with_another_album_is_kept(frame):
    frame.manager._save_sources(frame.manager.list_sources() + [
        PhotoSource(id="trip_copy", name="Trip copy", local_path=str(frame.pictures / "trip")),
    ])
    r = TestClient(app).delete("/api/v1/folders/trip_copy", headers=frame.headers["admin"])
    assert r.json()["local_folder_removed"] is False
    assert (frame.pictures / "trip" / "p0.jpg").exists()


def test_rmtree_failure_is_reported(frame, monkeypatch):
    def boom(path):
        raise OSError("Permission denied")
    monkeypatch.setattr(album_service.shutil, "rmtree", boom)
    r = TestClient(app).delete("/api/v1/folders/trip", headers=frame.headers["admin"])
    assert r.status_code == 200
    body = r.json()
    assert body["local_folder_removed"] is False and body["photos_removed"] == 0
    assert body["error"].startswith("The album was removed, but its photos couldn't be deleted")


def test_dashboard_delete(frame):
    client = TestClient(app, client=LAN)
    r = client.post("/api/sources/delete", json={"source_id": "showing"})
    assert r.json() == {"ok": False, "error": "This album is showing on the frame. Show another album first, then delete it."}
    r = client.post("/api/sources/delete", json={"source_id": "trip"})
    assert r.json()["ok"] is True and r.json()["photos_removed"] == 3
    assert not (frame.pictures / "trip").exists()
