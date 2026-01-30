"""
Unit tests for authentication module.
"""

import pytest
from datetime import datetime, timezone

from src.auth.jwt_handler import create_token, verify_token
from src.auth.pairing import generate_pairing_code, verify_pairing_code, invalidate_all_codes


class TestJWTHandler:
    """Tests for JWT token handling."""

    def test_create_token_returns_string(self):
        """Token creation should return a JWT string."""
        token = create_token(
            device_id="test-device",
            device_name="Test Device",
            role="admin",
            frame_id="test-frame",
        )
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts separated by dots
        assert len(token.split(".")) == 3

    def test_verify_valid_token(self):
        """Valid tokens should verify successfully."""
        token = create_token(
            device_id="test-device",
            device_name="Test Device",
            role="admin",
            frame_id="test-frame",
        )

        claims = verify_token(token)
        assert claims is not None
        assert claims.device_id == "test-device"
        assert claims.device_name == "Test Device"
        assert claims.role == "admin"
        assert claims.frame_id == "test-frame"

    def test_verify_invalid_token(self):
        """Invalid tokens should return None."""
        claims = verify_token("invalid.token.here")
        assert claims is None

    def test_verify_tampered_token(self):
        """Tampered tokens should fail verification."""
        token = create_token(
            device_id="test-device",
            device_name="Test Device",
            role="admin",
            frame_id="test-frame",
        )

        # Tamper with the payload
        parts = token.split(".")
        parts[1] = parts[1][:-5] + "XXXXX"
        tampered = ".".join(parts)

        claims = verify_token(tampered)
        assert claims is None


class TestPairingCode:
    """Tests for pairing code management."""

    def setup_method(self):
        """Clean up before each test."""
        invalidate_all_codes()

    def test_generate_code_format(self):
        """Generated codes should have correct format."""
        code = generate_pairing_code()
        assert code is not None
        # Format: ABC-XYZ
        assert len(code.code) == 7
        assert code.code[3] == "-"
        assert code.code[:3].isalnum()
        assert code.code[4:].isalnum()

    def test_verify_valid_code(self):
        """Valid codes should verify successfully."""
        code = generate_pairing_code()
        assert code is not None

        result = verify_pairing_code(code.code)
        assert result is True

    def test_code_single_use(self):
        """Codes should only work once."""
        code = generate_pairing_code()
        assert code is not None

        # First verification succeeds
        result1 = verify_pairing_code(code.code)
        assert result1 is True

        # Second verification fails
        result2 = verify_pairing_code(code.code)
        assert result2 is False

    def test_verify_invalid_code(self):
        """Invalid codes should fail verification."""
        result = verify_pairing_code("XXX-YYY")
        assert result is False

    def test_code_case_insensitive(self):
        """Code verification should be case-insensitive."""
        code = generate_pairing_code()
        assert code is not None

        # Should work with lowercase
        result = verify_pairing_code(code.code.lower())
        assert result is True
