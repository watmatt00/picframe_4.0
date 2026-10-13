"""
Unit tests: PATCH /folders/{id} renames a source's display name only; the id,
local folder and cloud folder stay the same.
"""

from datetime import datetime, timezone

import pytest
from filelock import FileLock
from fastapi.testclient import TestClient

from src.api.app import app
from src.auth import jwt_handler
from src.auth.models import Device
from src.services import source_manager as sm
from src.services.source_manager import PhotoSource, SourceManager
from src.storage.devices import device_storage


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Temp sources file with one source, plus admin and contributor tokens."""
    manager = SourceManager(tmp_path / "sources.yaml")
    manager._save_sources([PhotoSource(
        id="kfr_frame", name="Kfr Frame", local_path=str(tmp_path / "kfr_frame"),
        rclone_remote="kfr:KFR_frame",
    )])
    monkeypatch.setattr(sm, "source_manager", manager)
    monkeypatch.setattr("src.api.routes.folders.source_manager", manager)
    monkeypatch.setattr(device_storage, "_path", tmp_path / "devices.json")
    monkeypatch.setattr(device_storage, "_lock", FileLock(tmp_path / "devices.lock"))
    monkeypatch.setattr(jwt_handler, "SECRET_PATH", tmp_path / "jwt_secret")

    headers = {}
    for device_id, role in (("admin1", "admin"), ("con1", "contributor")):
        device_storage.add_device(Device(
            id=device_id, name=device_id, role=role, paired_at=datetime.now(timezone.utc),
        ))
        token = jwt_handler.create_token(
            device_id=device_id, device_name=device_id, role=role, frame_id="test-frame",
        )
        headers[role] = {"Authorization": f"Bearer {token}"}
    return TestClient(app), manager, headers


def test_rename_changes_name_only(setup):
    client, manager, headers = setup
    r = client.patch("/api/v1/folders/kfr_frame", json={"name": "  Family 2026  "},
                     headers=headers["admin"])
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Family 2026"
    source = manager.get_source("kfr_frame")
    assert source.name == "Family 2026"
    assert source.id == "kfr_frame"
    assert source.rclone_remote == "kfr:KFR_frame"
    assert source.local_path.endswith("kfr_frame")


@pytest.mark.parametrize("name", ["", "   ", "a\nb", "x" * 51])
def test_rename_rejects_bad_names(setup, name):
    client, manager, headers = setup
    r = client.patch("/api/v1/folders/kfr_frame", json={"name": name}, headers=headers["admin"])
    assert r.status_code == 422
    assert manager.get_source("kfr_frame").name == "Kfr Frame"


def test_rename_unknown_source_is_404(setup):
    client, _, headers = setup
    r = client.patch("/api/v1/folders/nope", json={"name": "X"}, headers=headers["admin"])
    assert r.status_code == 404


def test_rename_needs_admin(setup):
    client, manager, headers = setup
    r = client.patch("/api/v1/folders/kfr_frame", json={"name": "X"},
                     headers=headers["contributor"])
    assert r.status_code == 403
    assert manager.get_source("kfr_frame").name == "Kfr Frame"
