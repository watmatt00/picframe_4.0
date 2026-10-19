"""
Unit tests: recovering albums (PL-147 follow-up) from an unused cloud folder,
a backup, or an uploaded .zip / .tar.gz. rclone is mocked.
"""

import asyncio
import io
import tarfile
import zipfile
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.services import backup_service, recovery_service
from src.services import source_manager as sm
from src.services.source_manager import PhotoSource, SourceManager
from src.services.sync_service import sync_service
from src.utils.rclone import RcloneResult

LAN = ("192.168.1.50", 50000)


@pytest.fixture
def frame(tmp_path, monkeypatch):
    """Temp ~/Pictures with album "trip" (cloud folder KFR_trip); rclone calls recorded."""
    pictures = tmp_path / "Pictures"
    (pictures / "trip").mkdir(parents=True)
    (pictures / "trip" / "a.jpg").write_bytes(b"old")
    backups = pictures / "backups"
    backups.mkdir()

    manager = SourceManager(tmp_path / "sources.yaml")
    manager._save_sources([
        PhotoSource(id="trip", name="Trip", local_path=str(pictures / "trip"), rclone_remote="kfr:KFR_trip"),
    ])

    def create_source(name, rclone_remote=None):
        sid = name.lower().replace(" ", "_")
        src = PhotoSource(id=sid, name=name, local_path=str(pictures / sid),
                          rclone_remote=rclone_remote or f"kfr:KFR_{sid}")
        (pictures / sid).mkdir(exist_ok=True)
        manager._save_sources(manager.list_sources() + [src])
        return src

    monkeypatch.setattr(manager, "create_source", create_source)
    monkeypatch.setattr(sm, "source_manager", manager)
    monkeypatch.setattr(backup_service, "BACKUPS_DIR", backups)

    calls = SimpleNamespace(copies=[], in_album_at_copy=[], syncs=[], copy_ok=True)

    async def fake_copy(local_dir, remote):
        calls.copies.append((sorted(p.name for p in local_dir.iterdir()), remote))
        album = pictures / remote.split("KFR_", 1)[1]
        calls.in_album_at_copy.append(sorted(p.name for p in album.iterdir()) if album.exists() else [])
        return RcloneResult(success=calls.copy_ok, error=None if calls.copy_ok else "network down")

    async def fake_dirs(remote):
        return ["KFR_trip", "KFR_old_party", "KFR_kids", "Documents"]

    async def fake_count(remote):
        return {"kfr:KFR_old_party": 12, "kfr:KFR_kids": 3}.get(remote, 0)

    async def fake_sync(source_id, local_path, remote):
        calls.syncs.append((source_id, remote))

    monkeypatch.setattr(recovery_service, "rclone_copy_dir", fake_copy)
    monkeypatch.setattr(recovery_service, "rclone_list_dirs", fake_dirs)
    monkeypatch.setattr(recovery_service, "rclone_count", fake_count)
    monkeypatch.setattr(recovery_service, "find_koofr_remote", lambda: "kfr")
    monkeypatch.setattr(sync_service, "sync_source", fake_sync)
    monkeypatch.setattr(sync_service, "_is_syncing", False)
    monkeypatch.setattr(sync_service, "_current_source", None)
    return SimpleNamespace(pictures=pictures, backups=backups, manager=manager, calls=calls)


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _tar(files: dict[str, bytes], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        if symlink:
            link = tarfile.TarInfo(symlink)
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            tf.addfile(link)
    return buf.getvalue()


def _upload(data: bytes, **params):
    return TestClient(app, client=LAN).post("/api/albums/upload-archive", params=params, content=data)


# --- Cloud folders -----------------------------------------------------------

def test_lists_only_unused_kfr_folders(frame):
    r = TestClient(app, client=LAN).get("/api/albums/recoverable")
    data = r.json()
    assert data["ok"] and data["cloud_error"] is None
    assert data["cloud"] == [
        {"folder": "KFR_kids", "photo_count": 3, "suggested_name": "kids"},
        {"folder": "KFR_old_party", "photo_count": 12, "suggested_name": "old party"},
    ]


def test_recover_from_cloud_points_album_at_folder_and_syncs(frame):
    r = TestClient(app, client=LAN).post("/api/albums/recover-cloud", json={"folder": "KFR_old_party", "name": "Party"})
    data = r.json()
    assert data["ok"], data
    assert data["cloud_folder"] == "kfr:KFR_old_party" and data["sync_started"] is True
    assert frame.manager.get_source("party").rclone_remote == "kfr:KFR_old_party"
    assert frame.calls.syncs == [("party", "kfr:KFR_old_party")]


@pytest.mark.parametrize("folder", ["KFR_trip", "Documents", "KFR_../x", "KFR_missing"])
def test_recover_refuses_used_or_invalid_folders(frame, folder):
    r = TestClient(app, client=LAN).post("/api/albums/recover-cloud", json={"folder": folder, "name": "X"})
    assert r.json()["ok"] is False


def test_cloud_unavailable_still_lists_backups(frame, monkeypatch):
    monkeypatch.setattr(recovery_service, "find_koofr_remote", lambda: None)
    (frame.backups / "trip_2026-10-01_120000.tar.gz").write_bytes(_tar({"trip/b.jpg": b"b"}))
    data = TestClient(app, client=LAN).get("/api/albums/recoverable").json()
    assert data["cloud"] == [] and "No cloud storage" in data["cloud_error"]
    assert data["backups"][0]["album_id"] == "trip" and data["backups"][0]["album_exists"] is True


# --- Backups ----------------------------------------------------------------

def test_restore_backup_of_deleted_album_into_new_album(frame):
    (frame.backups / "gone_2026-10-01_120000.tar.gz").write_bytes(_tar({"gone/x.jpg": b"x", "gone/y.png": b"y"}))
    backups = recovery_service.list_all_backups()
    assert backups[0]["album_id"] == "gone" and backups[0]["album_exists"] is False

    r = TestClient(app, client=LAN).post("/api/albums/restore-backup", json={
        "filename": "gone_2026-10-01_120000.tar.gz", "new_name": "Gone",
    })
    data = r.json()
    assert data["ok"], data
    assert data["restored"] == 2 and data["uploaded_to_cloud"] is True
    assert sorted(p.name for p in (frame.pictures / "gone").iterdir()) == ["x.jpg", "y.png"]
    assert frame.calls.copies == [(["x.jpg", "y.png"], "kfr:KFR_gone")]


def test_restore_into_existing_album_renames_clashes(frame):
    (frame.backups / "trip_2026-10-01_120000.tar.gz").write_bytes(_tar({"trip/a.jpg": b"new", "trip/b.jpg": b"b"}))
    data = TestClient(app, client=LAN).post("/api/albums/restore-backup", json={
        "filename": "trip_2026-10-01_120000.tar.gz", "target_id": "trip",
    }).json()
    assert data["ok"] and data["renamed"] == 1
    assert (frame.pictures / "trip" / "a.jpg").read_bytes() == b"old"
    assert (frame.pictures / "trip" / "a_1.jpg").read_bytes() == b"new"


def test_restore_backup_bad_filename(frame):
    data = TestClient(app, client=LAN).post("/api/albums/restore-backup", json={
        "filename": "../../etc/passwd", "target_id": "trip",
    }).json()
    assert data == {"ok": False, "error": "Invalid backup filename: ../../etc/passwd"}


# --- Upload --------------------------------------------------------------------

def test_upload_zip_into_existing_album(frame):
    data = _upload(_zip({"Photos/2024/c.JPG": b"c", "d.mov": b"d", "notes.txt": b"n",
                         "__MACOSX/Photos/._c.JPG": b"m", ".DS_Store": b"s"}), target_id="trip").json()
    assert data["ok"], data
    assert data["restored"] == 2 and data["skipped"] == 3
    assert sorted(p.name for p in (frame.pictures / "trip").iterdir()) == ["a.jpg", "c.JPG", "d.mov"]


def test_zip_slip_names_are_flattened(frame):
    data = _upload(_zip({"../../evil.jpg": b"e", "/abs/path/f.jpg": b"f"}), target_id="trip").json()
    assert data["ok"]
    assert not (frame.pictures.parent / "evil.jpg").exists()
    assert {"evil.jpg", "f.jpg"} <= {p.name for p in (frame.pictures / "trip").iterdir()}


def test_tar_symlink_member_skipped(frame):
    data = _upload(_tar({"g.jpg": b"g"}, symlink="link.jpg"), target_id="trip").json()
    assert data["ok"] and data["restored"] == 1 and data["skipped"] == 1
    assert not (frame.pictures / "trip" / "link.jpg").exists()


def test_upload_into_new_album(frame):
    data = _upload(_zip({"h.jpg": b"h"}), new_name="Holiday").json()
    assert data["ok"] and data["album"] == "holiday"
    assert (frame.pictures / "holiday" / "h.jpg").exists()


def test_not_an_archive(frame):
    data = _upload(b"just some text", target_id="trip").json()
    assert data == {"ok": False, "error": "That isn't a .zip or .tar.gz file."}
    assert not list(frame.backups.glob(".incoming-*"))


def test_zip_bomb_refused_before_extracting(frame, monkeypatch):
    monkeypatch.setattr(recovery_service, "MAX_TOTAL_BYTES", 10)
    data = _upload(_zip({"big.jpg": b"x" * 100}), target_id="trip").json()
    assert data["ok"] is False and data["error"].startswith("Not enough space")
    assert not (frame.pictures / "trip" / "big.jpg").exists()
    assert not list(frame.backups.glob(".staging-*")) and not list(frame.backups.glob(".incoming-*"))


def test_no_photos_in_archive(frame):
    data = _upload(_zip({"readme.txt": b"r"}), target_id="trip").json()
    assert data == {"ok": False, "error": "No photos or videos found in this archive."}


# --- Ordering and safety -------------------------------------------------------

def test_cloud_copy_happens_before_files_reach_album(frame):
    _upload(_zip({"k.jpg": b"k"}), target_id="trip")
    assert frame.calls.copies == [(["k.jpg"], "kfr:KFR_trip")]
    assert frame.calls.in_album_at_copy == [["a.jpg"]]  # k.jpg not in the album yet
    assert (frame.pictures / "trip" / "k.jpg").exists()


def test_cloud_copy_failure_leaves_album_untouched(frame):
    frame.calls.copy_ok = False
    data = _upload(_zip({"k.jpg": b"k"}), target_id="trip").json()
    assert data["ok"] is False and "Nothing was added" in data["error"]
    assert sorted(p.name for p in (frame.pictures / "trip").iterdir()) == ["a.jpg"]
    assert not list(frame.backups.glob(".staging-*"))


def test_refused_while_album_syncs(frame, monkeypatch):
    monkeypatch.setattr(sync_service, "_is_syncing", True)
    monkeypatch.setattr(sync_service, "_current_source", "trip")
    data = _upload(_zip({"k.jpg": b"k"}), target_id="trip").json()
    assert data["ok"] is False and "syncing" in data["error"]


def test_restores_run_one_at_a_time(frame):
    (frame.backups / "trip_2026-10-01_120000.tar.gz").write_bytes(_tar({"m.jpg": b"m"}))
    (frame.backups / "trip_2026-10-02_120000.tar.gz").write_bytes(_tar({"n.jpg": b"n"}))
    active, peak = 0, 0
    original = recovery_service.rclone_copy_dir

    async def slow_copy(local_dir, remote):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return await original(local_dir, remote)

    recovery_service.rclone_copy_dir = slow_copy
    try:
        async def both():
            await asyncio.gather(
                recovery_service.restore_backup("trip_2026-10-01_120000.tar.gz", "trip", None),
                recovery_service.restore_backup("trip_2026-10-02_120000.tar.gz", "trip", None),
            )
        asyncio.run(both())
    finally:
        recovery_service.rclone_copy_dir = original
    assert peak == 1
    assert {"m.jpg", "n.jpg"} <= {p.name for p in (frame.pictures / "trip").iterdir()}


def test_recovery_routes_are_lan_only(frame):
    client = TestClient(app, client=("8.8.8.8", 5000))
    assert client.get("/api/albums/recoverable").status_code == 403
    assert client.post("/api/albums/upload-archive", content=b"x").status_code == 403
