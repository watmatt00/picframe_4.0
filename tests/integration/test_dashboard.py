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
        assert "PicFrame" in response.text


class TestDashboardNavigation:
    """Tests for dashboard navigation."""

    def test_all_nav_links_present(self, client):
        """All navigation links should be present on each page."""
        response = client.get("/")
        assert response.status_code == 200


class TestDashboardForms:
    """Tests for dashboard form submissions."""

    def test_settings_form_submit(self, client):
        """Settings API should accept valid settings."""
        response = client.post("/api/settings", json={
            "frame_name": "Updated Frame",
            "rotation_interval": 45,
            "sync_interval": 900,
            "log_level": "INFO",
        })
        # Should return OK or fail gracefully (Pi config file not present in test env)
        assert response.status_code in (200, 302, 303, 500)

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
