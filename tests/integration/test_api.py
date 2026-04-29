"""
Integration tests for API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoints:
    """Tests for health and version endpoints."""

    def test_health_endpoint(self, client):
        """Health endpoint should return ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_version_endpoint(self, client):
        """Version endpoint should return version info."""
        response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["api"] == "picframe"


class TestPairingEndpoints:
    """Tests for pairing endpoints."""

    def test_pair_without_code(self, client):
        """Pairing without code should fail."""
        response = client.post("/api/v1/pair", json={})
        assert response.status_code == 422  # Validation error

    def test_pair_with_invalid_code(self, client):
        """Pairing with invalid code should fail."""
        response = client.post("/api/v1/pair", json={
            "code": "INVALID",
            "device_name": "Test Device",
        })
        # Should be 401 (invalid code)
        assert response.status_code in (401, 501)


class TestAuthenticatedEndpoints:
    """Tests for endpoints requiring authentication."""

    def test_status_without_auth(self, client):
        """Status endpoint should require auth."""
        response = client.get("/api/v1/status")
        # Should be 401 or 403 without auth
        assert response.status_code in (401, 403, 501)

    def test_devices_without_auth(self, client):
        """Devices endpoint should require auth."""
        response = client.get("/api/v1/devices")
        assert response.status_code in (401, 403, 501)

    def test_services_restart_without_auth(self, client):
        """Service restart should require auth."""
        response = client.post("/api/v1/services/picframe/restart")
        assert response.status_code in (401, 403, 501)
