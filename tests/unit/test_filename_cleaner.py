"""
Unit tests for the Filename Cleaner's stem rules (photo_tools_service).
"""

from src.services import photo_tools_service as svc


def test_special_chars_replaced(tmp_path):
    (tmp_path / "Mom & Dad + #1.jpg").write_bytes(b"x")
    fix = svc._proposed_filename("Mom & Dad + #1.jpg", tmp_path)
    assert fix is not None
    assert fix.proposed == "Mom_Dad_1.jpg"
    assert "special_chars" in fix.reasons


def test_only_special_chars_falls_back_to_date(tmp_path, monkeypatch):
    (tmp_path / "&&&.jpg").write_bytes(b"x")
    monkeypatch.setattr(svc, "_date_stem_from_file", lambda p: ("20261012_120000", True))
    fix = svc._proposed_filename("&&&.jpg", tmp_path)
    assert fix is not None
    assert fix.proposed == "20261012_120000.jpg"
    assert fix.needs_review is True


def test_app_upload_name_untouched(tmp_path):
    # Names the iOS app gives uploads must not be flagged (stem is exactly 20 chars)
    (tmp_path / "20261012_113108_5f7b.jpg").write_bytes(b"x")
    assert svc._proposed_filename("20261012_113108_5f7b.jpg", tmp_path) is None
