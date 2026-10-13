"""
Unit tests: DELETE /devices/me removes the calling device (any role), refuses the
last admin, and the removed device's token stops working.
"""

from datetime import datetime, timezone

import pytest
from filelock import FileLock
from fastapi.testclient import TestClient

from src.api.app import app
from src.auth import jwt_handler
from src.auth.models import Device
from src.storage.devices import device_storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Fresh device storage and JWT secret."""
    monkeypatch.setattr(device_storage, "_path", tmp_path / "devices.json")
    monkeypatch.setattr(device_storage, "_lock", FileLock(tmp_path / "devices.lock"))
    monkeypatch.setattr(jwt_handler, "SECRET_PATH", tmp_path / "jwt_secret")
    return TestClient(app)


def _device(device_id: str, role: str) -> dict:
    """Add a device and return auth headers for it."""
    device_storage.add_device(Device(
        id=device_id, name=f"{device_id} phone", role=role,
        paired_at=datetime.now(timezone.utc),
    ))
    token = jwt_handler.create_token(
        device_id=device_id, device_name=f"{device_id} phone", role=role, frame_id="test-frame",
    )
    return {"Authorization": f"Bearer {token}"}


def test_contributor_unpairs_self(client):
    _device("admin1", "admin")
    headers = _device("con1", "contributor")
    r = client.delete("/api/v1/devices/me", headers=headers)
    assert r.status_code == 204, r.text
    assert device_storage.get_device("con1") is None
    assert device_storage.get_device("admin1") is not None
    # Token no longer works
    assert client.delete("/api/v1/devices/me", headers=headers).status_code == 401


def test_last_admin_cannot_unpair_self(client):
    headers = _device("admin1", "admin")
    r = client.delete("/api/v1/devices/me", headers=headers)
    assert r.status_code == 400
    assert device_storage.get_device("admin1") is not None


def test_second_admin_unpairs_self(client):
    _device("admin1", "admin")
    headers = _device("admin2", "admin")
    assert client.delete("/api/v1/devices/me", headers=headers).status_code == 204
    assert device_storage.get_device("admin2") is None


def test_me_needs_auth(client):
    assert client.delete("/api/v1/devices/me").status_code == 401
