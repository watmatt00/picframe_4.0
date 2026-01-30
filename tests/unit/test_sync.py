"""
Unit tests for sync service.
"""

import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path

from src.utils.rclone import (
    _validate_remote,
    _validate_path,
    _is_safe_flag,
    _parse_transferred,
)


class TestRcloneValidation:
    """Tests for rclone input validation."""

    def test_valid_remote_formats(self):
        """Valid remote formats should pass."""
        assert _validate_remote("koofr:folder") is True
        assert _validate_remote("gdrive:Photos") is True
        assert _validate_remote("remote_name:path/to/folder") is True
        assert _validate_remote("/local/path") is True

    def test_invalid_remote_formats(self):
        """Invalid remote formats should fail."""
        assert _validate_remote("no-colon") is False
        assert _validate_remote("") is False
        assert _validate_remote("inva!id:path") is False

    def test_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        assert _validate_path("/home/pi/Pictures") is True
        assert _validate_path("/home/pi/../etc") is False
        assert _validate_path("../relative") is False

    def test_safe_flags(self):
        """Safe flags should pass, dangerous should not."""
        assert _is_safe_flag("--verbose") is True
        assert _is_safe_flag("-v") is True
        assert _is_safe_flag("--stats=1s") is True

        assert _is_safe_flag("--config=/etc/rclone.conf") is False
        assert _is_safe_flag("--delete-before") is False

    def test_parse_transferred(self):
        """Should parse transferred count from rclone output."""
        output = "Transferred: 5 / 5, 100%, 1.2 MBytes/s"
        assert _parse_transferred(output) == 5

        output_none = "Some other output"
        assert _parse_transferred(output_none) == 0
