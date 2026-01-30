"""
Integration tests for the pairing flow.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.auth.pairing import generate_pairing_code, invalidate_all_codes


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_codes():
    """Clean up pairing codes before and after each test."""
    invalidate_all_codes()
    yield
    invalidate_all_codes()


class TestPairingFlow:
    """End-to-end pairing flow tests."""

    def test_pairing_code_generation(self):
        """Should generate valid pairing codes."""
        code = generate_pairing_code()
        assert code is not None
        assert len(code.code) == 7
        assert "-" in code.code

    def test_pairing_code_expiry(self):
        """Pairing codes should have expiry."""
        code = generate_pairing_code()
        assert code is not None
        assert code.expires_at > code.created_at

    def test_rate_limiting(self):
        """Should rate limit code generation."""
        # Generate 3 codes (the limit)
        for _ in range(3):
            code = generate_pairing_code()
            assert code is not None

        # 4th should be rate limited
        code = generate_pairing_code()
        assert code is None


class TestQRCodeGeneration:
    """Tests for QR code generation."""

    def test_generate_qr_code(self):
        """Should generate valid QR code data."""
        from src.utils.qr_generator import generate_pairing_qr, parse_qr_data

        qr_base64 = generate_pairing_qr(
            url="https://frame.example.ts.net",
            code="ABC-XYZ",
            frame_name="Test Frame",
        )

        assert qr_base64 is not None
        assert len(qr_base64) > 0

    def test_parse_qr_data(self):
        """Should parse QR code data correctly."""
        from src.utils.qr_generator import parse_qr_data

        data = '{"url":"https://frame.example.ts.net","code":"ABC-XYZ","name":"Test Frame"}'
        parsed = parse_qr_data(data)

        assert parsed is not None
        assert parsed["url"] == "https://frame.example.ts.net"
        assert parsed["code"] == "ABC-XYZ"
        assert parsed["name"] == "Test Frame"

    def test_parse_invalid_qr_data(self):
        """Should handle invalid QR data gracefully."""
        from src.utils.qr_generator import parse_qr_data

        assert parse_qr_data("not json") is None
        assert parse_qr_data('{"missing":"fields"}') is None
