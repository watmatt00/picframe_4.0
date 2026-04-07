"""
Unit tests for sync service.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime, timezone

from src.utils.rclone import (
    _validate_remote,
    _validate_path,
    _is_safe_flag,
    _parse_transferred,
    count_local_files,
    RcloneResult,
)
from src.services.sync_service import SyncService, SyncResult


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
        """Should parse transferred count from rclone --stats-one-line -v output.

        Each transferred file appears as '<name>: Copied (new)' or
        '<name>: Copied (replaced existing)' — count those lines.
        """
        output = (
            "2024/01/01 12:00:00 INFO  : photo1.jpg: Copied (new)\n"
            "2024/01/01 12:00:01 INFO  : photo2.jpg: Copied (replaced existing)\n"
            "2024/01/01 12:00:02 INFO  : photo3.jpg: Copied (new)\n"
            "Transferred: 3 / 3, 100%, 1.2 MBytes/s\n"
        )
        assert _parse_transferred(output) == 3

        output_none = "Some other output"
        assert _parse_transferred(output_none) == 0


class TestCountLocalFiles:
    """Tests for counting local files."""

    def test_count_files_in_directory(self, tmp_path):
        """Should count files in a directory."""
        (tmp_path / "file1.jpg").touch()
        (tmp_path / "file2.jpg").touch()
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.jpg").touch()

        assert count_local_files(tmp_path) == 3

    def test_count_empty_directory(self, tmp_path):
        """Should return 0 for empty directory."""
        assert count_local_files(tmp_path) == 0

    def test_count_nonexistent_directory(self, tmp_path):
        """Should return 0 for nonexistent directory."""
        assert count_local_files(tmp_path / "nonexistent") == 0


class TestSyncService:
    """Tests for the SyncService class."""

    @pytest.fixture
    def service(self):
        """Create a fresh SyncService."""
        return SyncService()

    @pytest.mark.asyncio
    async def test_sync_success(self, service, tmp_path):
        """Should complete sync successfully."""
        mock_result = RcloneResult(
            success=True,
            files_transferred=5,
            files_deleted=0,
            output="Transferred: 5 / 5",
        )

        with patch("src.services.sync_service.rclone_sync", return_value=mock_result):
            result = await service.sync_source(
                source_id="test",
                local_path=tmp_path,
                rclone_remote="koofr:test",
            )

        assert result.success is True
        assert result.files_transferred == 5
        assert result.source_id == "test"
        assert service._is_syncing is False

    @pytest.mark.asyncio
    async def test_sync_failure(self, service, tmp_path):
        """Should handle sync failure."""
        mock_result = RcloneResult(
            success=False,
            error="Connection failed",
        )

        with patch("src.services.sync_service.rclone_sync", return_value=mock_result):
            result = await service.sync_source(
                source_id="test",
                local_path=tmp_path,
                rclone_remote="koofr:test",
            )

        assert result.success is False
        assert result.error == "Connection failed"
        assert service._is_syncing is False

    @pytest.mark.asyncio
    async def test_concurrent_sync_blocked(self, service, tmp_path):
        """Should block concurrent syncs."""
        service._is_syncing = True
        service._current_source = "other"

        with pytest.raises(RuntimeError, match="Sync already in progress"):
            await service.sync_source(
                source_id="test",
                local_path=tmp_path,
                rclone_remote="koofr:test",
            )
