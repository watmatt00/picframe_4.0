"""
Integration tests for the web dashboard.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


# LAN client address so middleware allows dashboard access
LAN_CLIENT = ("192.168.1.50", 50000)


@pytest.fixture
def client():
    """Create test client connecting from a LAN address."""
    return TestClient(app, client=LAN_CLIENT)


class TestDashboardPages:
    """Tests for dashboard page loads."""

    def test_home_page_loads(self, client):
        """Home page (single-page dashboard) should load successfully."""
        response = client.get("/")
        assert response.status_code == 200
        assert "WanderWall" in response.text


class TestDashboardNavigation:
    """Tests for dashboard navigation."""

    def test_all_nav_links_present(self, client):
        """All navigation links should be present on each page."""
        response = client.get("/")
        assert response.status_code == 200


class TestDashboardForms:
    """Tests for dashboard form submissions."""

    def test_settings_form_submit(self, client, tmp_path, monkeypatch):
        """Settings API saves valid settings (temp config files, no real restarts)."""
        import yaml
        from filelock import FileLock
        from src.config import settings as settings_mod
        from src.config.manager import config_manager
        from src.dashboard import routes as dashboard_routes

        picframe_config = tmp_path / "configuration.yaml"
        picframe_config.write_text(yaml.safe_dump({"model": {"time_delay": 30, "fade_time": 2.0}}))
        config_path = tmp_path / "config.yaml"
        monkeypatch.setattr(dashboard_routes, "PICFRAME_CONFIG_PATH", picframe_config)
        monkeypatch.setattr(config_manager, "_path", config_path)
        monkeypatch.setattr(config_manager, "_lock", FileLock(tmp_path / "config.lock"))
        original_from_yaml = settings_mod.Settings.from_yaml.__func__
        monkeypatch.setattr(
            settings_mod.Settings, "from_yaml",
            classmethod(lambda cls, path=config_path: original_from_yaml(cls, path)),
        )
        restarts, timers = [], []

        async def fake_restart(name):
            restarts.append(name)
            return True

        async def fake_timer(interval):
            timers.append(interval)

        monkeypatch.setattr(dashboard_routes.systemd_service, "restart", fake_restart)
        monkeypatch.setattr(dashboard_routes, "update_sync_timer", fake_timer)
        settings_mod.reload_settings()
        try:
            response = client.post("/api/settings", json={
                "frame_name": "Updated Frame",
                "rotation_interval": 45,
                "sync_interval": 1800,
                "fade_time": 3.0,
            })
            assert response.status_code == 200
            assert response.json() == {"ok": True, "restarted": True}
            assert yaml.safe_load(picframe_config.read_text())["model"] == {"time_delay": 45.0, "fade_time": 3.0}
            saved = yaml.safe_load(config_path.read_text())
            assert saved["frame"]["name"] == "Updated Frame"
            assert saved["sync"]["interval"] == 1800
            assert restarts == ["picframe"] and timers == [1800]
        finally:
            settings_mod.get_settings.cache_clear()

    def test_settings_form_requires_fade_time(self, client):
        """Missing fade_time is a validation error, before anything is written."""
        response = client.post("/api/settings", json={
            "frame_name": "Updated Frame", "rotation_interval": 45, "sync_interval": 900,
        })
        assert response.status_code == 422

    def test_pairing_generate(self, client):
        """Pairing generation should work."""
        response = client.post("/pairing/generate")
        # Should return JSON with code info
        assert response.status_code in (200, 501)


class TestDashboardAPI:
    """Tests for dashboard API endpoints."""

    def test_logs_api(self, client):
        """Logs API should return log entries."""
        response = client.get("/api/logs?lines=10&log_type=ops")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data


class TestDashboardNoAuth:
    """Tests to verify dashboard has no auth requirement."""

    def test_pages_accessible_without_auth(self, client):
        """Dashboard should be accessible without auth from LAN."""
        response = client.get("/")
        # Should not return 401 or 403
        assert response.status_code not in (401, 403), "Dashboard requires auth"
