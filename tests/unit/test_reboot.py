"""
Unit tests: Reboot Frame (PL-142) — admin only, a clear 503 when the polkit
rule isn't installed, and `systemctl reboot` runs after the delay (mocked).
"""

import asyncio
from datetime import datetime, timezone

import pytest
from filelock import FileLock
from fastapi.testclient import TestClient

from src.api.app import app
from src.auth import jwt_handler
from src.auth.models import Device
from src.services import power_service
from src.storage.devices import device_storage

LAN = ("192.168.1.50", 50000)


@pytest.fixture
def frame(tmp_path, monkeypatch):
    """Tokens for an admin and a contributor; polkit rule installed; reboots recorded, not run."""
    rule = tmp_path / "50-picframe.rules"
    rule.write_text('action.id === "org.freedesktop.login1.reboot"')
    monkeypatch.setattr(power_service, "POLKIT_RULE", rule)
    scheduled = []
    monkeypatch.setattr(power_service, "schedule_reboot", lambda who, ip=None: scheduled.append(who))

    monkeypatch.setattr(device_storage, "_path", tmp_path / "devices.json")
    monkeypatch.setattr(device_storage, "_lock", FileLock(tmp_path / "devices.lock"))
    monkeypatch.setattr(jwt_handler, "SECRET_PATH", tmp_path / "jwt_secret")
    headers = {}
    for device_id, role in (("admin1", "admin"), ("con1", "contributor")):
        device_storage.add_device(Device(id=device_id, name=f"{role} phone", role=role, paired_at=datetime.now(timezone.utc)))
        token = jwt_handler.create_token(device_id=device_id, device_name=f"{role} phone", role=role, frame_id="f")
        headers[role] = {"Authorization": f"Bearer {token}"}
    return rule, scheduled, headers


def test_admin_can_reboot(frame):
    _, scheduled, headers = frame
    r = TestClient(app).post("/api/v1/system/reboot", headers=headers["admin"])
    assert r.status_code == 202
    assert r.json()["rebooting"] is True
    assert scheduled == ["admin phone"]


def test_contributor_cannot_reboot(frame):
    _, scheduled, headers = frame
    r = TestClient(app).post("/api/v1/system/reboot", headers=headers["contributor"])
    assert r.status_code == 403
    assert scheduled == []


def test_no_token_cannot_reboot(frame):
    _, scheduled, _ = frame
    assert TestClient(app).post("/api/v1/system/reboot").status_code == 401
    assert scheduled == []


def test_not_set_up_is_503_with_message(frame):
    rule, scheduled, headers = frame
    rule.unlink()
    r = TestClient(app).post("/api/v1/system/reboot", headers=headers["admin"])
    assert r.status_code == 503
    assert r.json()["detail"] == power_service.NOT_SET_UP_MESSAGE
    assert scheduled == []


def test_dashboard_reboot(frame):
    rule, scheduled, _ = frame
    client = TestClient(app, client=LAN)
    assert client.post("/system/reboot").json()["ok"] is True
    assert scheduled == ["dashboard"]
    rule.write_text("no reboot here")
    assert client.post("/system/reboot").json() == {"ok": False, "error": power_service.NOT_SET_UP_MESSAGE}


def test_dashboard_reboot_is_lan_only(frame):
    _, scheduled, _ = frame
    assert TestClient(app, client=("8.8.8.8", 5000)).post("/system/reboot").status_code == 403
    assert scheduled == []


def test_reboot_runs_systemctl_after_delay(monkeypatch):
    calls = []

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return FakeProc()

    monkeypatch.setattr(power_service, "REBOOT_DELAY_SECONDS", 0)
    monkeypatch.setattr(power_service.asyncio, "create_subprocess_exec", fake_exec)

    async def run():
        power_service.schedule_reboot("test")
        assert calls == []  # not before the delay
        await asyncio.gather(*power_service._pending)

    asyncio.run(run())
    assert calls == [("systemctl", "reboot")]
