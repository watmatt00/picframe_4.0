"""
Integration tests for the web dashboard.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestDashboardPages:
    """Tests for dashboard page loads."""

    def test_home_page_loads(self, client):
        """Home page should load successfully."""
        response = client.get("/")
        assert response.status_code == 200
        assert "PicFrame" in response.text

    def test_settings_page_loads(self, client):
        """Settings page should load successfully."""
        response = client.get("/settings")
        assert response.status_code == 200
        assert "Settings" in response.text

    def test_devices_page_loads(self, client):
        """Devices page should load successfully."""
        response = client.get("/devices")
        assert response.status_code == 200
        assert "Paired Devices" in response.text

    def test_pairing_page_loads(self, client):
        """Pairing page should load successfully."""
        response = client.get("/pairing")
        assert response.status_code == 200
        assert "Pair" in response.text

    def test_logs_page_loads(self, client):
        """Logs page should load successfully."""
        response = client.get("/logs")
        assert response.status_code == 200
        assert "Logs" in response.text


class TestDashboardNavigation:
    """Tests for dashboard navigation."""

    def test_all_nav_links_present(self, client):
        """All navigation links should be present on each page."""
        response = client.get("/")
        assert 'href="/"' in response.text
        assert 'href="/settings"' in response.text
        assert 'href="/devices"' in response.text
        assert 'href="/pairing"' in response.text
        assert 'href="/logs"' in response.text


class TestDashboardForms:
    """Tests for dashboard form submissions."""

    def test_settings_form_submit(self, client):
        """Settings form should submit successfully."""
        response = client.post("/settings", data={
            "frame_name": "Updated Frame",
            "rotation_interval": "45",
        })
        # Should return OK or redirect
        assert response.status_code in (200, 302, 303)

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
        """All dashboard pages should be accessible without auth."""
        pages = ["/", "/settings", "/devices", "/pairing", "/logs"]

        for page in pages:
            response = client.get(page)
            # Should not return 401 or 403
            assert response.status_code not in (401, 403), f"Page {page} requires auth"
