"""
Unit tests for scripts/setup/koofr_detect.py (PL-063).
"""

import sys
from pathlib import Path

SETUP_DIR = Path(__file__).resolve().parents[2] / "scripts" / "setup"
sys.path.insert(0, str(SETUP_DIR))

from koofr_detect import is_koofr_configured  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class TestIsKoofrConfigured:
    """Each signal on its own is enough; none means not configured."""

    def test_empty_home(self, tmp_path):
        assert is_koofr_configured(tmp_path) is False

    def test_koofr_user_in_config(self, tmp_path):
        _write(tmp_path / ".picframe" / "config.yaml", "sync:\n  koofr_user: a@b.com\n")
        assert is_koofr_configured(tmp_path) is True

    def test_blank_koofr_user_ignored(self, tmp_path):
        _write(tmp_path / ".picframe" / "config.yaml", "sync:\n  koofr_user: '  '\n")
        assert is_koofr_configured(tmp_path) is False

    def test_koofr_remote_in_rclone_conf(self, tmp_path):
        _write(
            tmp_path / ".config" / "rclone" / "rclone.conf",
            "[kfr_tkframe]\ntype = koofr\nuser = a@b.com\npassword = x%y\n",
        )
        assert is_koofr_configured(tmp_path) is True

    def test_other_remote_type_ignored(self, tmp_path):
        _write(tmp_path / ".config" / "rclone" / "rclone.conf", "[gd]\ntype = drive\n")
        assert is_koofr_configured(tmp_path) is False

    def test_enabled_source_with_remote(self, tmp_path):
        _write(
            tmp_path / ".picframe" / "sources.yaml",
            "sources:\n  - id: a\n    enabled: true\n    rclone_remote: kfr:KFR_a\n",
        )
        assert is_koofr_configured(tmp_path) is True

    def test_disabled_or_local_sources_ignored(self, tmp_path):
        _write(
            tmp_path / ".picframe" / "sources.yaml",
            "sources:\n"
            "  - id: a\n    enabled: false\n    rclone_remote: kfr:KFR_a\n"
            "  - id: b\n    enabled: true\n    rclone_remote: ''\n",
        )
        assert is_koofr_configured(tmp_path) is False

    def test_corrupt_file_does_not_raise(self, tmp_path):
        _write(tmp_path / ".picframe" / "config.yaml", "sync: [unclosed\n")
        _write(tmp_path / ".config" / "rclone" / "rclone.conf", "[kfr]\ntype = koofr\n")
        assert is_koofr_configured(tmp_path) is True
