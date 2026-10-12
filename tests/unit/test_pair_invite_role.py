"""
Unit tests: the Manager (admin) app can't pair with a contributor invite code, and the
invite isn't used up when it tries; the Contributor app still can.
"""

import pytest
from filelock import FileLock
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.routes import pairing
from src.auth import jwt_handler
from src.storage.devices import device_storage
from src.storage.invites import InviteStorage


@pytest.fixture
def invites(tmp_path, monkeypatch):
    """Fresh invite and device storage, admin pairing codes always invalid."""
    store = InviteStorage(tmp_path / "invites.json")
    monkeypatch.setattr(pairing, "invite_storage", store)
    monkeypatch.setattr(pairing, "verify_pairing_code", lambda code: False)
    monkeypatch.setattr(device_storage, "_path", tmp_path / "devices.json")
    monkeypatch.setattr(device_storage, "_lock", FileLock(tmp_path / "devices.lock"))
    monkeypatch.setattr(jwt_handler, "SECRET_PATH", tmp_path / "jwt_secret")
    return store


def _pair(code, role):
    return TestClient(app).post("/api/v1/pair", json={
        "code": code, "device_name": "Test Phone", "requested_role": role,
    })


def test_manager_refuses_invite_without_claiming(invites):
    invite = invites.create_invite()
    r = _pair(invite.code, "admin")
    assert r.status_code == 403
    assert "Contributor app" in r.json()["detail"]
    assert invites.is_valid_invite(invite.code)  # still usable


def test_manager_unknown_code_is_401(invites):
    assert _pair("NOPE-000", "admin").status_code == 401


def test_contributor_app_claims_invite(invites):
    invite = invites.create_invite()
    r = _pair(invite.code, "contributor")
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "contributor"
    assert not invites.is_valid_invite(invite.code)  # single-use
