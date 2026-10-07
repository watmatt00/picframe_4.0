"""
Unit tests for scripts/pi/picframe-inspect, the read-only SSH command filter.
"""

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pi" / "picframe-inspect"


@pytest.fixture
def inspect_mod():
    """Load the extensionless script as a module."""
    loader = importlib.machinery.SourceFileLoader("picframe_inspect", str(SCRIPT))
    spec = importlib.util.spec_from_loader("picframe_inspect", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(inspect_mod, monkeypatch, command):
    """Run main() with SSH_ORIGINAL_COMMAND set; return the argv it would exec, or None if refused."""
    captured = {}

    def fake_exec(name, argv, env):
        captured["argv"] = argv
        captured["env"] = env
        raise SystemExit(0)

    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", command)
    monkeypatch.setattr(inspect_mod.os, "execvpe", fake_exec)
    with pytest.raises(SystemExit) as exc:
        inspect_mod.main()
    return captured.get("argv") if exc.value.code == 0 else None


@pytest.mark.parametrize("command", [
    "cat /home/pi/.picframe/logs/picframe.log",
    "tail -n 50 ~/.picframe/logs/security.log",
    "ls -la /home/pi",
    "grep -n ERROR /home/pi/.picframe/logs/picframe.log",
    "df -h",
    "free -m",
    "uptime",
    "hostname",
    "git -C ~/picframe_4.0 log --oneline -5",
    "git -C /home/pi/picframe_4.0 status",
    "git -C /home/pi/picframe_4.0 remote -v",
    "git -C /home/pi/picframe_4.0 branch --show-current",
    "git -C /home/pi/picframe_4.0 diff HEAD~1 --stat",
    "systemctl --user status picframe-api.service",
    "systemctl --user is-active picframe.service",
    "systemctl --user list-timers",
    "journalctl --user -u picframe-api.service -n 50",
    "tailscale status",
    "tailscale funnel status",
    "ss -ltn",
    "ps aux",
])
def test_allowed(inspect_mod, monkeypatch, command):
    """Read-only commands are passed to exec."""
    assert run(inspect_mod, monkeypatch, command) is not None


@pytest.mark.parametrize("command", [
    "",
    "bash",
    "sh -c id",
    "python3 -c 'print(1)'",
    "rm -rf /tmp/x",
    "touch /tmp/x",
    "cp a b",
    "nano file",
    "/bin/cat /etc/hostname",
    "cat x; id",
    "cat x && id",
    "cat x | sh",
    "cat x > /tmp/y",
    "cat $(id)",
    "cat `id`",
    "git -C /home/pi/picframe_4.0 pull",
    "git -C /home/pi/picframe_4.0 commit -am x",
    "git -C /home/pi/picframe_4.0 push",
    "git -C /home/pi/picframe_4.0 checkout main",
    "git -C /home/pi/picframe_4.0 reset --hard",
    "git -C /home/pi/picframe_4.0 branch evil",
    "git -C /home/pi/picframe_4.0 branch -D dev",
    "git -C /home/pi/picframe_4.0 remote add x y",
    "git -c core.pager=id log",
    "git -C /home/pi/picframe_4.0 diff --output=/tmp/x",
    "git -C /home/pi/picframe_4.0 log -p --ext-diff",
    "systemctl --user restart picframe-api.service",
    "systemctl --user stop picframe.service",
    "systemctl --user edit picframe.service",
    "journalctl --vacuum-time=1s",
    "journalctl --rotate",
    "journalctl --cursor-file=/tmp/x",
    "tailscale funnel 8000",
    "tailscale down",
    "tailscale serve reset",
    "ss -K dst 1.2.3.4",
    "hostname evil",
    "date -s 2020-01-01",
    "find / -delete",
    "curl http://127.0.0.1:8000/api/updates/apply -X POST",
])
def test_refused(inspect_mod, monkeypatch, command):
    """Anything that could change state, chain commands or start a shell is refused."""
    assert run(inspect_mod, monkeypatch, command) is None


def test_tilde_expanded(inspect_mod, monkeypatch):
    """~/ is expanded to HOME since no shell does it."""
    argv = run(inspect_mod, monkeypatch, "ls ~/picframe_4.0")
    assert argv[1].endswith("/picframe_4.0") and not argv[1].startswith("~")


def test_pager_disabled(inspect_mod, monkeypatch):
    """journalctl/systemctl get --no-pager so no pager (and its shell escape) can start."""
    argv = run(inspect_mod, monkeypatch, "journalctl --user -n 5")
    assert "--no-pager" in argv
