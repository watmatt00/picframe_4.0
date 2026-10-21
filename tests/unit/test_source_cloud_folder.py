"""
Unit tests: a new album's cloud folder (PL-165). The Koofr account can be shared
by several frames, so a new album never reuses an existing KFR_* folder. rclone
is mocked.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from src.services import source_manager as sm
from src.services.source_manager import SourceManager, free_cloud_folder


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    """A SourceManager in tmp; rclone lists `state.dirs` (None = listing fails) and records mkdirs."""
    state = SimpleNamespace(dirs=["KFR_trip", "KFR_Home", "Documents"], mkdirs=[])
    monkeypatch.setattr(sm, "find_koofr_remote", lambda: "koofr")
    monkeypatch.setattr(sm.Path, "home", lambda: tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["rclone", "lsjson"]:
            if state.dirs is None:
                return subprocess.CompletedProcess(cmd, 1, "", "network down")
            return subprocess.CompletedProcess(cmd, 0, json.dumps([{"Name": d, "IsDir": True} for d in state.dirs]), "")
        if cmd[:2] == ["rclone", "mkdir"]:
            state.mkdirs.append(cmd[2])
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(sm.subprocess, "run", fake_run)
    return SimpleNamespace(manager=SourceManager(tmp_path / "sources.yaml"), state=state)


def test_new_album_gets_unused_folder(cloud):
    """No KFR_* folder with that name yet → KFR_<id>."""
    src = cloud.manager.create_source("Beach")
    assert src.rclone_remote == "koofr:KFR_beach"
    assert cloud.state.mkdirs == ["koofr:KFR_beach"]


def test_new_album_never_joins_existing_folder(cloud):
    """KFR_trip exists (another frame's, or this frame's deleted album) → KFR_trip_2."""
    assert cloud.manager.create_source("Trip").rclone_remote == "koofr:KFR_trip_2"
    assert "koofr:KFR_trip" not in cloud.state.mkdirs


def test_existing_folder_compared_case_insensitively(cloud):
    """Cloud folder KFR_Home blocks KFR_home too."""
    assert cloud.manager.create_source("Home").rclone_remote == "koofr:KFR_home_2"


def test_cloud_unreachable_sets_up_no_folder(cloud):
    """If the cloud can't be listed, the album has no cloud folder rather than maybe a shared one."""
    cloud.state.dirs = None
    src = cloud.manager.create_source("Beach")
    assert src.rclone_remote is None and cloud.state.mkdirs == []


def test_backfill_uses_same_rule(cloud):
    """Albums made before cloud storage was set up get an unused folder too."""
    cloud.state.dirs = None
    cloud.manager.create_source("Trip")
    cloud.state.dirs = ["KFR_trip"]
    assert cloud.manager.backfill_remotes() == ["trip"]
    assert cloud.manager.get_source("trip").rclone_remote == "koofr:KFR_trip_2"


def test_free_cloud_folder_counts_up():
    """_2, _3… until free; the chosen name is added to `taken`."""
    taken = {"KFR_a", "KFR_a_2"}
    assert free_cloud_folder("a", taken) == "KFR_a_3"
    assert free_cloud_folder("a", taken) == "KFR_a_4"
    assert free_cloud_folder("b c!", set()) == "KFR_b_c_"
