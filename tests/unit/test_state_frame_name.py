"""
Unit tests: a new state.yaml takes its frame_name from the hostname (PL-141),
so the setup hotspot is "WanderWall-<hostname>", not "WanderWall-wanderwall".
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "setup"))
import state_manager  # noqa: E402


@pytest.mark.parametrize("host, expected", [
    ("kframe", "kframe"),
    ("tkframe.local", "tkframe"),
    ("my frame!", "myframe"),
    ("a" * 40, "a" * 32),
    ("", "wanderwall"),
    ("...", "wanderwall"),
])
def test_default_frame_name(monkeypatch, host, expected):
    monkeypatch.setattr(state_manager.socket, "gethostname", lambda: host)
    assert state_manager.default_frame_name() == expected


def test_initialize_uses_hostname(tmp_path, monkeypatch):
    monkeypatch.setattr(state_manager.socket, "gethostname", lambda: "mnbframe")
    path = tmp_path / "state.yaml"
    state_manager.StateManager(path).initialize()
    assert yaml.safe_load(path.read_text())["frame_name"] == "mnbframe"


def test_initialize_keeps_existing_name(tmp_path, monkeypatch):
    monkeypatch.setattr(state_manager.socket, "gethostname", lambda: "mnbframe")
    path = tmp_path / "state.yaml"
    path.write_text(yaml.safe_dump({"frame_name": "Kitchen"}))
    state_manager.StateManager(path).initialize()
    assert yaml.safe_load(path.read_text())["frame_name"] == "Kitchen"
