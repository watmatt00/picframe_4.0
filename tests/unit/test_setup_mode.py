"""
Unit tests for WiFi setup mode (scripts/setup): watchdog boot/retry logic,
shared WiFi config writer, and BLE adapter preparation.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SETUP_DIR = Path(__file__).resolve().parents[2] / "scripts" / "setup"
sys.path.insert(0, str(SETUP_DIR))

import watchdog  # noqa: E402
import wifi_config  # noqa: E402

# ble_setup imports bless (Pi-only BLE stack) at module level — stub it
sys.modules.setdefault("bless", MagicMock())
import ble_setup  # noqa: E402

# ── wifi_config ──────────────────────────────────────────────────────────────

class TestWriteWifiCredentials:
    """NetworkManager profile creation shared by portal and BLE."""

    def test_wpa_profile_is_hidden_with_psk(self):
        """Secured network: profile marked hidden and carries the PSK."""
        with patch.object(wifi_config.subprocess, "run") as run:
            wifi_config.write_wifi_credentials("7Oaks", "secretpass")

        assert run.call_args_list[0].args[0] == ["nmcli", "con", "delete", "picframe-wifi"]
        add_cmd = run.call_args_list[1].args[0]
        assert add_cmd[:3] == ["nmcli", "con", "add"]
        assert add_cmd[add_cmd.index("ssid") + 1] == "7Oaks"
        assert add_cmd[add_cmd.index("802-11-wireless.hidden") + 1] == "yes"
        assert add_cmd[add_cmd.index("wifi-sec.psk") + 1] == "secretpass"
        assert run.call_args_list[1].kwargs["check"] is True

    def test_open_network_has_no_security(self):
        """Open network: no wifi-sec settings."""
        with patch.object(wifi_config.subprocess, "run") as run:
            wifi_config.write_wifi_credentials("Guest", "")

        add_cmd = run.call_args_list[1].args[0]
        assert not any(arg.startswith("wifi-sec") for arg in add_cmd)
        assert "802-11-wireless.hidden" in add_cmd

    def test_nmcli_failure_propagates(self):
        """A failed profile creation must raise so callers can report it."""
        def fake_run(cmd, **kwargs):
            if cmd[2] == "add":
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(wifi_config.subprocess, "run", side_effect=fake_run):
            with pytest.raises(subprocess.CalledProcessError):
                wifi_config.write_wifi_credentials("7Oaks", "secretpass")


# ── watchdog ─────────────────────────────────────────────────────────────────

@pytest.fixture
def no_sleep():
    """Make polling loops instant."""
    with patch.object(watchdog.time, "sleep"):
        yield


class TestWaitForWifi:
    """Grace-period polling."""

    def test_returns_true_once_associated(self, no_sleep):
        with patch.object(watchdog, "is_wifi_associated", side_effect=[False, False, True]):
            assert watchdog.wait_for_wifi(60) is True

    def test_returns_false_after_timeout(self, no_sleep):
        with patch.object(watchdog, "is_wifi_associated", return_value=False):
            assert watchdog.wait_for_wifi(0) is False


class TestDisplayControl:
    """Display is controlled through the configured frame user, not a hardcoded one."""

    def test_stop_display_targets_frame_user(self, no_sleep):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            out = "running" if "is-system-running" in cmd else ""
            return subprocess.CompletedProcess(cmd, 0, out, "")

        with patch.object(watchdog, "FRAME_USER", "pi"), \
                patch.object(watchdog.subprocess, "run", side_effect=fake_run):
            watchdog.stop_display()

        assert ["systemctl", "--user", "-M", "pi@", "stop", "picframe"] in calls

    def test_stop_display_waits_for_user_manager(self, no_sleep):
        states = iter(["starting", "starting", "running"])
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            out = next(states) if "is-system-running" in cmd else ""
            return subprocess.CompletedProcess(cmd, 0, out, "")

        with patch.object(watchdog.subprocess, "run", side_effect=fake_run):
            watchdog.stop_display()

        assert sum("is-system-running" in c for c in calls) == 3
        assert calls[-1][-2:] == ["stop", "picframe"]


@pytest.fixture
def boot_env():
    """Patch everything main() touches; yields the mocks."""
    sm = MagicMock()
    with patch.object(watchdog, "state_manager", sm), \
            patch.object(watchdog, "_restore_issue"), \
            patch.object(watchdog, "generate_setup_image"), \
            patch.object(watchdog, "restore_no_pictures"), \
            patch.object(watchdog, "start_setup_mode") as start_setup, \
            patch.object(watchdog, "run_monitoring_loop") as loop, \
            patch.object(watchdog, "wait_for_wifi") as wait, \
            patch.object(watchdog, "is_wifi_associated", return_value=True):
        yield {"sm": sm, "start_setup": start_setup, "loop": loop, "wait": wait}


def _state(reason, needs_setup=True, provisioned=True):
    return {
        "provisioned": provisioned,
        "needs_setup": needs_setup,
        "setup_mode_reason": reason,
        "frame_name": "tkframe",
        "koofr_configured": True,
    }


class TestBootDecision:
    """A stale outage flag must not force setup mode when home WiFi works."""

    def test_stale_outage_flag_cleared_when_wifi_returns(self, boot_env):
        boot_env["sm"].read.return_value = _state("extended_outage")
        boot_env["wait"].return_value = True

        watchdog.main()

        boot_env["sm"].clear_needs_setup.assert_called_once()
        boot_env["start_setup"].assert_not_called()
        boot_env["loop"].assert_called_once_with()

    def test_outage_flag_enters_setup_when_wifi_absent(self, boot_env):
        boot_env["sm"].read.return_value = _state("extended_outage")
        boot_env["wait"].return_value = False

        watchdog.main()

        boot_env["start_setup"].assert_called_once()
        boot_env["loop"].assert_called_once_with(in_setup_mode=True, retry_home_wifi=True)

    def test_manual_setup_not_bypassed_by_wifi(self, boot_env):
        boot_env["sm"].read.return_value = _state("manual")

        watchdog.main()

        boot_env["wait"].assert_not_called()
        boot_env["start_setup"].assert_called_once()
        boot_env["loop"].assert_called_once_with(in_setup_mode=True, retry_home_wifi=False)

    def test_unprovisioned_always_enters_setup(self, boot_env):
        boot_env["sm"].read.return_value = _state(None, needs_setup=False, provisioned=False)

        watchdog.main()

        boot_env["wait"].assert_not_called()
        boot_env["start_setup"].assert_called_once()


class TestLeaveSetupMode:
    """Periodic retry out of outage-triggered setup mode."""

    def test_leaves_setup_when_wifi_back(self):
        sm = MagicMock()
        with patch.object(watchdog, "state_manager", sm), \
                patch.object(watchdog, "stop_setup_mode") as stop_setup, \
                patch.object(watchdog, "wait_for_wifi", return_value=True), \
                patch.object(watchdog, "_restore_issue"), \
                patch.object(watchdog, "start_display") as start_display, \
                patch.object(watchdog, "start_setup_mode") as start_setup:
            assert watchdog.try_leave_setup_mode() is True

        stop_setup.assert_called_once()
        sm.clear_needs_setup.assert_called_once()
        start_display.assert_called_once()
        start_setup.assert_not_called()

    def test_reenters_setup_when_wifi_still_down(self):
        sm = MagicMock()
        with patch.object(watchdog, "state_manager", sm), \
                patch.object(watchdog, "stop_setup_mode"), \
                patch.object(watchdog, "wait_for_wifi", return_value=False), \
                patch.object(watchdog, "start_display") as start_display, \
                patch.object(watchdog, "start_setup_mode") as start_setup:
            assert watchdog.try_leave_setup_mode() is False

        sm.clear_needs_setup.assert_not_called()
        start_display.assert_not_called()
        start_setup.assert_called_once()


# ── ble_setup ────────────────────────────────────────────────────────────────

def _fake_rfkill(root: Path, name: str, rtype: str, soft: str) -> Path:
    entry = root / name
    entry.mkdir()
    (entry / "type").write_text(f"{rtype}\n")
    (entry / "name").write_text(f"{name}-dev\n")
    (entry / "soft").write_text(f"{soft}\n")
    return entry


class TestEnsureBluetoothReady:
    """Soft-blocked Bluetooth is unblocked and the adapter powered on."""

    def test_unblocks_only_bluetooth_and_powers_on(self, tmp_path):
        bt = _fake_rfkill(tmp_path, "rfkill0", "bluetooth", "1")
        wlan = _fake_rfkill(tmp_path, "rfkill1", "wlan", "1")
        ok = subprocess.CompletedProcess([], 0, "Changing power on succeeded\n", "")

        with patch.object(ble_setup, "RFKILL_SYSFS", tmp_path), \
                patch.object(ble_setup.subprocess, "run", return_value=ok) as run:
            ble_setup.ensure_bluetooth_ready()

        assert (bt / "soft").read_text() == "0"
        assert (wlan / "soft").read_text().strip() == "1"
        run.assert_called_once()
        assert run.call_args.args[0] == ["bluetoothctl", "power", "on"]

    def test_power_on_retries_then_gives_up(self, tmp_path):
        fail = subprocess.CompletedProcess([], 1, "", "No default controller available")

        with patch.object(ble_setup, "RFKILL_SYSFS", tmp_path), \
                patch.object(ble_setup.time, "sleep"), \
                patch.object(ble_setup.subprocess, "run", return_value=fail) as run:
            ble_setup.ensure_bluetooth_ready()  # must not raise

        assert run.call_count == 5
