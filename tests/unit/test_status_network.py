"""
Unit test for the network block in GET /api/v1/status (used by the app's connection info).
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api.app import app
from src.api.dependencies import require_admin
from src.api.routes import status


def test_status_includes_network(monkeypatch):
    async def fake_service(name):
        return status.ServiceStatus(name=name, display_name=name, active=True, status="running", can_restart=True)

    async def fake_counts(source):
        return 3, 3

    monkeypatch.setattr(status, "_get_service_status", fake_service)
    monkeypatch.setattr(status, "get_current_source", lambda: ("heic", None))
    monkeypatch.setattr(status, "get_photo_counts", fake_counts)
    monkeypatch.setattr(status, "get_last_sync_time", lambda: None)
    monkeypatch.setattr(status, "get_disk_capacity", lambda path: {
        "total_gb": 1.0, "used_gb": 0.5, "available_gb": 0.5, "percent_used": 50.0,
        "total_bytes": 1, "used_bytes": 1, "free_bytes": 1,
    })
    monkeypatch.setattr(status, "get_lan_ip", lambda: "192.168.102.210")
    monkeypatch.setattr(status, "get_tailscale_ip", lambda: "100.100.168.66")
    monkeypatch.setattr(status, "get_settings", lambda: SimpleNamespace(frame=SimpleNamespace(
        id="f1", name="tkframe", funnel_url="https://tkframe.whale-ayu.ts.net")))
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    try:
        r = TestClient(app).get("/api/v1/status")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert r.status_code == 200, r.text
    assert r.json()["network"] == {
        "lan_ip": "192.168.102.210",
        "tailscale_ip": "100.100.168.66",
        "funnel_url": "https://tkframe.whale-ayu.ts.net",
    }
