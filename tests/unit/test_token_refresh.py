"""
Unit tests for token refresh (POST /api/v1/auth/refresh) and superseded-token rejection.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from filelock import FileLock

from src.api import dependencies
from src.api.app import app
from src.auth import jwt_handler
from src.auth.jwt_handler import create_token, verify_token
from src.auth.models import Device
from src.storage.devices import device_storage

DEVICE_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Keep device storage and the JWT secret out of the real home directory."""
    monkeypatch.setattr(device_storage, "_path", tmp_path / "devices.json")
    monkeypatch.setattr(device_storage, "_lock", FileLock(tmp_path / "devices.lock"))
    monkeypatch.setattr(jwt_handler, "SECRET_PATH", tmp_path / "jwt_secret")
    device_storage.add_device(Device(
        id=DEVICE_ID, name="Test Phone", role="admin", paired_at=datetime.now(timezone.utc),
    ))


@pytest.fixture
def client():
    """Test client connecting from a public address, like the app over Funnel."""
    return TestClient(app, client=("64.98.52.132", 50000))


def _token(**overrides) -> str:
    """Create a token for the test device."""
    args = {"device_id": DEVICE_ID, "device_name": "Test Phone", "role": "admin", "frame_id": "testframe"}
    args.update(overrides)
    return create_token(**args)


def _auth(token: str) -> dict:
    """Bearer header for a token."""
    return {"Authorization": f"Bearer {token}"}


class TestRefreshEndpoint:
    """Tests for POST /api/v1/auth/refresh."""

    def test_requires_token(self, client):
        """No token gets 401."""
        assert client.post("/api/v1/auth/refresh").status_code == 401

    def test_returns_new_90_day_token(self, client):
        """A valid token is swapped for a new, working 90-day token."""
        response = client.post("/api/v1/auth/refresh", headers=_auth(_token(expiry_days=365)))
        assert response.status_code == 200
        new_token = response.json()["token"]
        claims = verify_token(new_token)
        assert claims.device_id == DEVICE_ID
        assert claims.exp - claims.iat == timedelta(days=90)
        assert client.get("/api/v1/updates/settings", headers=_auth(new_token)).status_code != 401

    def test_records_token_not_before(self, client):
        """Refresh stores the new token's issue time on the device."""
        client.post("/api/v1/auth/refresh", headers=_auth(_token()))
        assert device_storage.get_device(DEVICE_ID).token_not_before is not None

    def test_role_comes_from_storage(self, client):
        """A token claiming admin for a contributor device is refreshed as contributor."""
        # Write directly: remove_device() refuses to remove the last admin
        device_storage._save([Device(
            id=DEVICE_ID, name="Test Phone", role="contributor", paired_at=datetime.now(timezone.utc),
        )])
        response = client.post("/api/v1/auth/refresh", headers=_auth(_token(role="admin")))
        assert verify_token(response.json()["token"]).role == "contributor"

    def test_revoked_device_cannot_refresh(self, client, monkeypatch):
        """A device removed from storage gets 401."""
        monkeypatch.setattr(device_storage, "get_device", lambda device_id: None)
        assert client.post("/api/v1/auth/refresh", headers=_auth(_token())).status_code == 401


class TestSupersededTokens:
    """Old tokens stop working once the grace period after a refresh ends."""

    def test_legacy_device_without_floor_accepted(self, client):
        """Devices paired before this change (no token_not_before) keep working."""
        assert device_storage.get_device(DEVICE_ID).token_not_before is None
        assert client.post("/api/v1/auth/refresh", headers=_auth(_token())).status_code == 200

    def test_old_token_works_during_grace(self, client):
        """Just after a refresh, the replaced token still works (in-flight requests)."""
        old = _backdated_token(hours=1)
        device_storage.set_token_not_before(DEVICE_ID, datetime.now(timezone.utc) - timedelta(seconds=30))
        assert client.post("/api/v1/auth/refresh", headers=_auth(old)).status_code == 200

    def test_old_token_rejected_after_grace(self, client):
        """Once the grace period is over, the replaced token gets 401."""
        old = _backdated_token(hours=1)
        device_storage.set_token_not_before(DEVICE_ID, datetime.now(timezone.utc) - timedelta(minutes=10))
        response = client.post("/api/v1/auth/refresh", headers=_auth(old))
        assert response.status_code == 401
        assert response.json()["detail"] == "Token has been replaced"

    def test_full_refresh_cycle(self, client):
        """New token works; old token is rejected once grace has passed."""
        old = _backdated_token(hours=1)
        new = client.post("/api/v1/auth/refresh", headers=_auth(old)).json()["token"]
        floor = device_storage.get_device(DEVICE_ID).token_not_before
        device_storage.set_token_not_before(DEVICE_ID, floor - dependencies.TOKEN_REFRESH_GRACE - timedelta(seconds=5))
        # Floor moved back past the grace window, but still after the old token's iat
        assert client.post("/api/v1/auth/refresh", headers=_auth(old)).status_code == 401
        assert client.post("/api/v1/auth/refresh", headers=_auth(new)).status_code == 200

    def test_token_issued_at_floor_not_superseded(self):
        """A token whose iat equals the floor is never superseded."""
        claims = verify_token(_token())
        assert not dependencies.is_superseded(claims, claims.iat)


def _backdated_token(hours: int) -> str:
    """Create a valid token for the test device issued `hours` ago."""
    now = datetime.now(timezone.utc)
    payload = {
        "device_id": DEVICE_ID, "device_name": "Test Phone", "role": "admin", "frame_id": "testframe",
        "iat": now - timedelta(hours=hours), "exp": now + timedelta(days=30),
    }
    return jwt.encode(payload, jwt_handler.get_or_create_secret(), algorithm="HS256")
