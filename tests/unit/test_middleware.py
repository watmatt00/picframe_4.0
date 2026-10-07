"""
Unit tests for the deny-by-default LAN-only middleware.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.middleware import is_local_ip, is_public_path

LAN = ("192.168.1.50", 50000)
TAILSCALE = ("100.100.168.66", 50000)
LOOPBACK = ("127.0.0.1", 50000)
PUBLIC = ("64.98.52.132", 50000)

# Routes that must never be reachable from the public internet
LAN_ONLY_ROUTES = [
    ("GET", "/"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("GET", "/static/js/dashboard.js"),
    ("GET", "/api/updates/settings"),
    ("POST", "/api/updates/check"),
    ("POST", "/api/updates/apply"),
    ("POST", "/api/updates/schedule"),
    ("POST", "/sync"),
    ("POST", "/services/picframe/restart"),
    ("POST", "/api/settings"),
    ("POST", "/api/sources/delete"),
    ("POST", "/dashboard/koofr-setup"),
    ("GET", "/api/tools/backup/x/list"),
    ("GET", "/debug/token"),
    ("GET", "/no-such-route"),
]


class TestIsLocalIp:
    """Tests for is_local_ip()."""

    @pytest.mark.parametrize("ip", [
        "192.168.102.210", "10.0.0.5", "172.16.0.1", "172.31.255.254",
        "127.0.0.1", "100.64.0.1", "100.127.255.254", "::1", "fd7a:115c:a1e0::3932:a843",
    ])
    def test_local(self, ip):
        """LAN, loopback and Tailscale addresses are local."""
        assert is_local_ip(ip)

    @pytest.mark.parametrize("ip", [
        "64.98.52.132", "8.8.8.8", "172.32.0.1", "100.1.2.3", "100.128.0.1",
        "", "testclient", "192.168.1.1, 8.8.8.8",
    ])
    def test_not_local(self, ip):
        """Public, out-of-range, empty and malformed addresses are not local."""
        assert not is_local_ip(ip)


class TestIsPublicPath:
    """Tests for is_public_path()."""

    @pytest.mark.parametrize("path", ["/health", "/version", "/api/v1/status", "/api/v1/pair"])
    def test_public(self, path):
        """App API, health and version are public."""
        assert is_public_path(path)

    @pytest.mark.parametrize("path", ["/", "/api/v1", "/api/updates/apply", "/healthz", "/version/x", "/docs"])
    def test_not_public(self, path):
        """Everything else is not public."""
        assert not is_public_path(path)


class TestPublicClient:
    """Requests from a public internet address (Funnel)."""

    @pytest.fixture
    def client(self):
        """Test client connecting from a public address."""
        return TestClient(app, client=PUBLIC)

    @pytest.mark.parametrize("method,path", LAN_ONLY_ROUTES)
    def test_lan_only_routes_blocked(self, client, method, path):
        """Dashboard and other non-API routes return 403."""
        response = client.request(method, path)
        assert response.status_code == 403

    def test_spoofed_forwarded_for_blocked(self, client):
        """A LAN address in X-Forwarded-For does not grant access."""
        response = client.get("/", headers={"X-Forwarded-For": "192.168.1.1"})
        assert response.status_code == 403

    def test_403_does_not_echo_client_ip(self, client):
        """The 403 body does not include the caller's address."""
        response = client.get("/")
        assert "client_ip" not in response.json()

    @pytest.mark.parametrize("path", ["/health", "/version"])
    def test_health_and_version_allowed(self, client, path):
        """Health and version stay public."""
        assert client.get(path).status_code == 200

    @pytest.mark.parametrize("method,path", [
        ("GET", "/api/v1/status"),
        ("GET", "/api/v1/updates/settings"),
        ("POST", "/api/v1/updates/check"),
        ("POST", "/api/v1/updates/apply"),
        ("POST", "/api/v1/updates/schedule"),
    ])
    def test_api_v1_reaches_jwt_auth(self, client, method, path):
        """App API passes the middleware and is rejected by JWT auth instead."""
        response = client.request(method, path)
        assert response.status_code == 401


class TestLocalClients:
    """Requests from LAN, Tailscale and loopback addresses."""

    @pytest.mark.parametrize("address", [LAN, TAILSCALE, LOOPBACK])
    def test_dashboard_allowed(self, address):
        """Dashboard home page loads for local clients."""
        client = TestClient(app, client=address)
        assert client.get("/").status_code == 200

    def test_debug_token_removed(self):
        """The debug token endpoint no longer exists (PL-002)."""
        client = TestClient(app, client=LAN)
        assert client.get("/debug/token").status_code == 404
