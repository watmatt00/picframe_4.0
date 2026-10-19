"""
Unit tests: demo mode (PL-015) — reusable reviewer pairing codes, 14-day expiry,
revoke on end, the demo.allowed gate, and the exact errors the app shows.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from filelock import FileLock
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.routes import pairing
from src.auth import jwt_handler
from src.auth.models import Device
from src.config import settings as settings_mod
from src.config.manager import config_manager
from src.services import demo_service
from src.storage.devices import device_storage

EXPIRED = "This demo code has expired. Contact the frame owner for a new code."
INVITE = "This is an invite code. Use the PicFrame Contributor app to pair with it."
INVALID = "Invalid or expired pairing code"
LAN = ("192.168.1.50", 50000)
PUBLIC = ("8.8.8.8", 50000)


@pytest.fixture
def frame(tmp_path, monkeypatch):
    """Isolated config, devices and JWT secret; demo.allowed true; normal codes never valid."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"demo": {"allowed": True}}))

    monkeypatch.setattr(config_manager, "_path", config_path)
    monkeypatch.setattr(config_manager, "_lock", FileLock(tmp_path / "config.lock"))
    monkeypatch.setattr(settings_mod, "CONFIG_FILE", config_path)
    original_from_yaml = settings_mod.Settings.from_yaml.__func__
    monkeypatch.setattr(
        settings_mod.Settings, "from_yaml",
        classmethod(lambda cls, path=config_path: original_from_yaml(cls, path)),
    )
    monkeypatch.setattr(device_storage, "_path", tmp_path / "devices.json")
    monkeypatch.setattr(device_storage, "_lock", FileLock(tmp_path / "devices.lock"))
    monkeypatch.setattr(jwt_handler, "SECRET_PATH", tmp_path / "jwt_secret")
    monkeypatch.setattr(pairing, "verify_pairing_code", lambda code: False)
    settings_mod.reload_settings()
    yield config_path
    settings_mod.get_settings.cache_clear()


def _pair(code, role):
    return TestClient(app).post("/api/v1/pair", json={
        "code": code, "device_name": "Reviewer iPhone", "requested_role": role,
    })


def _add_owner_phone():
    device_storage.add_device(Device(
        id="owner", name="Owner Phone", role="admin", paired_at=datetime.now(timezone.utc),
    ))


# --- Pairing with live codes ------------------------------------------------

def test_admin_code_is_reusable(frame):
    codes = demo_service.enable_demo()
    for _ in range(6):  # past MAX_ATTEMPTS and MAX_CODES_PER_HOUR
        r = _pair(codes["admin_code"], "admin")
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "admin"
    devices = device_storage.list_devices()
    assert len(devices) == 6 and all(d.demo for d in devices)


def test_admin_code_in_contributor_app_gives_contributor(frame):
    codes = demo_service.enable_demo()
    r = _pair(codes["admin_code"], "contributor")
    assert r.status_code == 200
    assert r.json()["role"] == "contributor"


def test_contributor_code_in_contributor_app(frame):
    codes = demo_service.enable_demo()
    for _ in range(3):
        r = _pair(codes["contributor_code"], "contributor")
        assert r.status_code == 200
        assert r.json()["role"] == "contributor"


def test_contributor_code_in_manager_app_is_refused(frame):
    codes = demo_service.enable_demo()
    r = _pair(codes["contributor_code"], "admin")
    assert r.status_code == 403
    assert r.json()["detail"] == INVITE
    assert device_storage.list_devices() == []


def test_codes_are_case_insensitive(frame):
    codes = demo_service.enable_demo()
    r = _pair("  " + codes["admin_code"].lower() + " ", "admin")
    assert r.status_code == 200


def test_wrong_code_is_401_invalid(frame):
    demo_service.enable_demo()
    r = _pair("ZZZ-999", "admin")
    assert r.status_code == 401
    assert r.json()["detail"] == INVALID


# --- Ended / replaced codes -------------------------------------------------

def test_code_after_turning_off_says_expired(frame):
    codes = demo_service.enable_demo()
    demo_service.disable_demo()
    for code in (codes["admin_code"], codes["contributor_code"]):
        r = _pair(code, "contributor")
        assert r.status_code == 401
        assert r.json()["detail"] == EXPIRED


def test_code_after_14_days_says_expired_and_revokes(frame):
    _add_owner_phone()
    start = datetime.now(timezone.utc) - timedelta(days=14, minutes=1)
    codes = demo_service.enable_demo(now=start)
    device_storage.add_device(Device(id="rev", name="Reviewer", role="admin", paired_at=start, demo=True))

    r = _pair(codes["admin_code"], "admin")
    assert r.status_code == 401
    assert r.json()["detail"] == EXPIRED
    assert [d.id for d in device_storage.list_devices()] == ["owner"]
    assert settings_mod.get_settings().demo.enabled is False


def test_old_code_after_regenerate_says_expired(frame):
    old = demo_service.enable_demo()
    new = demo_service.regenerate_demo_codes()
    assert new["admin_code"] != old["admin_code"]
    r = _pair(old["admin_code"], "admin")
    assert r.status_code == 401
    assert r.json()["detail"] == EXPIRED
    assert _pair(new["admin_code"], "admin").status_code == 200


# --- demo.allowed gate ------------------------------------------------------

def test_not_allowed_blocks_enable_and_regenerate(frame):
    frame.write_text(yaml.safe_dump({"demo": {"allowed": False}}))
    settings_mod.reload_settings()
    with pytest.raises(demo_service.DemoNotAllowedError):
        demo_service.enable_demo()
    with pytest.raises(demo_service.DemoNotAllowedError):
        demo_service.regenerate_demo_codes()


def test_not_allowed_hand_enabled_codes_do_nothing(frame):
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    frame.write_text(yaml.safe_dump({"demo": {
        "allowed": False, "enabled": True, "admin_code": "ABC-123",
        "contributor_code": "XYZ-789", "expires_at": future,
    }}))
    settings_mod.reload_settings()
    r = _pair("ABC-123", "admin")
    assert r.status_code == 401
    assert r.json()["detail"] == INVALID  # don't reveal it was ever a demo code
    assert settings_mod.get_settings().demo.enabled is False


def test_invalid_stored_code_never_matches(frame):
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    frame.write_text(yaml.safe_dump({"demo": {
        "allowed": True, "enabled": True, "admin_code": "", "contributor_code": "bad",
        "expires_at": future,
    }}))
    settings_mod.reload_settings()
    assert _pair("", "admin").status_code == 401
    assert _pair("BAD", "contributor").status_code == 401


# --- Lifecycle ---------------------------------------------------------------

def test_enable_keeps_codes_across_off_and_on(frame):
    first = demo_service.enable_demo()
    demo_service.disable_demo()
    second = demo_service.enable_demo()
    assert first["admin_code"] == second["admin_code"]
    assert first["contributor_code"] == second["contributor_code"]
    assert first["admin_code"] != first["contributor_code"]


def test_enable_sets_14_days(frame):
    now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    status = demo_service.enable_demo(now=now)
    assert status["expires_at"] == (now + timedelta(days=14)).isoformat()
    assert status["days_left"] == 14


def test_regenerate_restarts_clock_and_keeps_paired_phones(frame):
    start = datetime.now(timezone.utc) - timedelta(days=10)
    codes = demo_service.enable_demo(now=start)
    device_storage.add_device(Device(id="rev", name="Reviewer", role="admin", paired_at=start, demo=True))
    status = demo_service.regenerate_demo_codes()
    assert status["days_left"] == 14
    assert status["admin_code"] != codes["admin_code"]
    assert device_storage.count_demo_devices() == 1


def test_disable_revokes_only_demo_devices(frame):
    _add_owner_phone()
    codes = demo_service.enable_demo()
    _pair(codes["admin_code"], "admin")
    _pair(codes["contributor_code"], "contributor")
    assert demo_service.disable_demo() == 2
    assert [d.id for d in device_storage.list_devices()] == ["owner"]


def test_revoked_demo_phone_gets_401_on_next_call(frame):
    codes = demo_service.enable_demo()
    token = _pair(codes["admin_code"], "admin").json()["token"]
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/devices", headers=headers).status_code == 200
    demo_service.disable_demo()
    r = client.get("/api/v1/devices", headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"] == "Device has been revoked"


def test_expiry_revokes_on_next_api_call(frame):
    _add_owner_phone()
    codes = demo_service.enable_demo()
    token = _pair(codes["admin_code"], "admin").json()["token"]
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    config_manager.update({"demo": {"expires_at": past}})
    settings_mod.reload_settings()
    r = TestClient(app).get("/api/v1/devices", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert [d.id for d in device_storage.list_devices()] == ["owner"]


def test_config_written_owner_only(frame):
    demo_service.enable_demo()
    assert frame.stat().st_mode & 0o777 == 0o600


# --- Dashboard routes --------------------------------------------------------

def test_dashboard_toggle_and_regenerate(frame):
    client = TestClient(app, client=LAN)
    r = client.post("/api/settings/demo", json={"enabled": True})
    assert r.status_code == 200 and r.json()["ok"]
    code = r.json()["demo"]["admin_code"]
    r = client.post("/api/settings/demo/regenerate")
    assert r.json()["ok"] and r.json()["demo"]["admin_code"] != code
    r = client.post("/api/settings/demo", json={"enabled": False})
    assert r.json()["ok"] and r.json()["demo"]["enabled"] is False


def test_dashboard_routes_refused_when_not_allowed(frame):
    frame.write_text(yaml.safe_dump({"demo": {"allowed": False}}))
    settings_mod.reload_settings()
    client = TestClient(app, client=LAN)
    for r in (client.post("/api/settings/demo", json={"enabled": True}),
              client.post("/api/settings/demo/regenerate")):
        assert r.status_code == 403
        assert "not allowed" in r.json()["error"]


def test_dashboard_demo_routes_are_lan_only(frame):
    client = TestClient(app, client=PUBLIC)
    assert client.post("/api/settings/demo", json={"enabled": True}).status_code == 403
    assert client.post("/api/settings/demo/regenerate").status_code == 403
    assert settings_mod.get_settings().demo.enabled is False


def test_dashboard_page_shows_banner_and_card(frame):
    codes = demo_service.enable_demo()
    html = TestClient(app, client=LAN).get("/").text
    assert "DEMO MODE ON" in html and "14 days left" in html
    assert codes["admin_code"] in html and codes["contributor_code"] in html


def test_dashboard_page_hides_card_when_not_allowed(frame):
    frame.write_text(yaml.safe_dump({"demo": {"allowed": False}}))
    settings_mod.reload_settings()
    html = TestClient(app, client=LAN).get("/").text
    assert "Demo Mode Card" not in html
    assert 'id="demo-banner" class="demo-banner" style="display:none;"' in html


def test_status_hides_codes_when_not_allowed(frame):
    frame.write_text(yaml.safe_dump({"demo": {"allowed": False, "admin_code": "ABC-123"}}))
    settings_mod.reload_settings()
    assert demo_service.demo_status()["admin_code"] == ""


def test_dashboard_page_shows_qr_for_both_codes(frame, monkeypatch):
    from src.dashboard import routes as dashboard_routes
    config_manager.update({"frame": {"funnel_url": "https://tkframe.example.ts.net", "name": "Test Frame"}})
    settings_mod.reload_settings()
    payloads = []
    real = dashboard_routes.generate_qr_data_url
    monkeypatch.setattr(dashboard_routes, "generate_qr_data_url",
                        lambda **kw: payloads.append(kw) or real(**kw))
    codes = demo_service.enable_demo()
    html = TestClient(app, client=LAN).get("/").text
    for key in ("admin", "contributor"):
        assert re.search(rf'<img src="data:image/png;base64,[^"]+" alt="[^"]+" id="demo-{key}-qr">', html)
    assert 'download="picframe-demo-manager-qr.png"' in html
    assert {p["code"] for p in payloads} == {codes["admin_code"], codes["contributor_code"]}
    assert all(p["url"] == "https://tkframe.example.ts.net" for p in payloads)


def test_dashboard_page_no_qr_when_demo_off(frame):
    demo_service.enable_demo()
    demo_service.disable_demo()
    html = TestClient(app, client=LAN).get("/").text
    assert "demo-admin-qr" not in html
