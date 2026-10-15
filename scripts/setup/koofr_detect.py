"""
PicFrame Setup - Koofr configuration detection.

Derives whether cloud sync is configured from the frame user's own config
files, so a stale koofr_configured flag in state.yaml can be corrected (PL-063).
Reads files only; never runs rclone.
"""

import configparser
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _has_koofr_user(home: Path) -> bool:
    """Return True if ~/.picframe/config.yaml has sync.koofr_user set."""
    path = home / ".picframe" / "config.yaml"
    if not path.exists():
        return False
    with open(path) as f:
        config = yaml.safe_load(f) or {}
    return bool(str((config.get("sync") or {}).get("koofr_user") or "").strip())


def _has_koofr_remote(home: Path) -> bool:
    """Return True if the user's rclone.conf defines a remote of type koofr."""
    path = home / ".config" / "rclone" / "rclone.conf"
    if not path.exists():
        return False
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path)
    return any(
        parser.get(section, "type", fallback="").strip().lower() == "koofr"
        for section in parser.sections()
    )


def _has_source_remote(home: Path) -> bool:
    """Return True if any enabled source in ~/.picframe/sources.yaml has a cloud remote."""
    path = home / ".picframe" / "sources.yaml"
    if not path.exists():
        return False
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return any(
        source.get("enabled") and str(source.get("rclone_remote") or "").strip()
        for source in data.get("sources") or []
    )


def is_koofr_configured(home: Path) -> bool:
    """
    Return True if cloud sync is configured for the frame user.

    Same signals as the dashboard's _is_koofr_configured(): Koofr credentials
    saved in config.yaml, a Koofr remote in rclone.conf, or an enabled source
    with a cloud remote. An unreadable file counts as "not configured".

    Args:
        home: The frame user's home directory.
    """
    for check in (_has_koofr_user, _has_koofr_remote, _has_source_remote):
        try:
            if check(home):
                return True
        except (OSError, yaml.YAMLError, configparser.Error) as e:
            logger.warning(f"Koofr detection: {check.__name__} failed: {e}")
    return False
