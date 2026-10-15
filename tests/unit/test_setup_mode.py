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


class TestMissingStateFile:
    """A recreated state.yaml must not force the portal when WiFi works (PL-064)."""

    def test_missing_state_with_wifi_marks_provisioned(self, boot_env):
        boot_env["sm"]._path.exists.return_value = False
        boot_env["sm"].read.return_value = _state(None, needs_setup=False, provisioned=False)
        boot_env["wait"].return_value = True

        watchdog.main()

        boot_env["sm"].set.assert_any_call("provisioned", True)
        boot_env["start_setup"].assert_not_called()
        boot_env["loop"].assert_called_once_with()

    def test_missing_state_without_wifi_enters_setup(self, boot_env):
        boot_env["sm"]._path.exists.return_value = False
        boot_env["sm"].read.return_value = _state(None, needs_setup=False, provisioned=False)
        boot_env["wait"].return_value = False

        watchdog.main()

        boot_env["sm"].mark_needs_setup.assert_called_once_with("unprovisioned")
        boot_env["start_setup"].assert_called_once()


class TestKoofrFlagAtBoot:
    """A stale koofr_configured=false must not bring back the setup image (PL-063)."""

    def test_stale_flag_corrected_when_koofr_configured(self, boot_env):
        state = _state(None, needs_setup=False)
        state["koofr_configured"] = False
        boot_env["sm"].read.return_value = state

        with patch.object(watchdog, "is_koofr_configured", return_value=True):
            watchdog.main()

        boot_env["sm"].set.assert_any_call("koofr_configured", True)
        watchdog.generate_setup_image.assert_not_called()
        watchdog.restore_no_pictures.assert_called_once()

    def test_setup_image_shown_when_koofr_not_configured(self, boot_env):
        state = _state(None, needs_setup=False)
        state["koofr_configured"] = False
        boot_env["sm"].read.return_value = state

        with patch.object(watchdog, "is_koofr_configured", return_value=False):
            watchdog.main()

        assert ("koofr_configured", True) not in [c.args for c in boot_env["sm"].set.call_args_list]
        watchdog.generate_setup_image.assert_called_once_with("tkframe")


class TestLeaveSetupMode:
    """Periodic retry out of outage-triggered setup mode."""

    def test_leaves_setup_when_wifi_back(self):
        sm = MagicMock()
        with patch.object(watchdog, "state_manager", sm), \
                patch.object(watchdog, "stop_setup_mode") as stop_setup, \
                patch.object(watchdog, "_reconnect_home_wifi"), \
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
                patch.object(watchdog, "_reconnect_home_wifi"), \
                patch.object(watchdog, "wait_for_wifi", return_value=False), \
                patch.object(watchdog, "start_display") as start_display, \
                patch.object(watchdog, "start_setup_mode") as start_setup:
            assert watchdog.try_leave_setup_mode() is False

        sm.clear_needs_setup.assert_not_called()
        start_display.assert_not_called()
        start_setup.assert_called_once()

    def test_reconnect_runs_between_stop_and_wait(self):
        """NetworkManager must be told to reconnect before waiting for WiFi (PL-138)."""
        order = MagicMock()
        with patch.object(watchdog, "state_manager", MagicMock()), \
                patch.object(watchdog, "stop_setup_mode", order.stop), \
                patch.object(watchdog, "_reconnect_home_wifi", order.reenable), \
                patch.object(watchdog, "wait_for_wifi", order.wait), \
                patch.object(watchdog, "_restore_issue"), \
                patch.object(watchdog, "start_display"):
            order.wait.return_value = True
            watchdog.try_leave_setup_mode()

        assert [c[0] for c in order.mock_calls] == ["stop", "reenable", "wait"]


class TestReconnectHomeWifi:
    """Handing wlan0 back to NetworkManager after the AP stops (PL-138)."""

    @staticmethod
    def _fake_nm(states):
        """subprocess.run stand-in: GENERAL.STATE returns the given states in turn."""
        states = iter(states)
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["nmcli", "-g", "GENERAL.STATE"]:
                return subprocess.CompletedProcess(cmd, 0, next(states) + "\n", "")
            if "list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "7Oaks\nNeighbor\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        return run, calls

    def test_waits_for_device_then_scans_then_connects(self, no_sleep):
        run, calls = self._fake_nm(["20 (unavailable)", "20 (unavailable)", "30 (disconnected)"])
        with patch.object(watchdog.subprocess, "run", side_effect=run):
            watchdog._reconnect_home_wifi()

        assert calls[0] == ["nmcli", "device", "set", "wlan0", "autoconnect", "yes"]
        assert sum(c[:3] == ["nmcli", "-g", "GENERAL.STATE"] for c in calls) == 3
        assert calls[-2] == ["nmcli", "-g", "SSID", "device", "wifi", "list", "ifname", "wlan0", "--rescan", "yes"]
        assert calls[-1] == ["nmcli", "--wait", "20", "device", "connect", "wlan0"]

    def test_connected_state_counts_as_ready(self, no_sleep):
        """"100 (connected)" must not be read as 10."""
        run, calls = self._fake_nm(["100 (connected)"])
        with patch.object(watchdog.subprocess, "run", side_effect=run):
            watchdog._reconnect_home_wifi()

        assert sum(c[:3] == ["nmcli", "-g", "GENERAL.STATE"] for c in calls) == 1

    def test_gives_up_waiting_and_still_connects(self, no_sleep):
        clock = iter(range(0, 1000, 5))
        run, calls = self._fake_nm(["20 (unavailable)"] * 50)
        with patch.object(watchdog.subprocess, "run", side_effect=run), \
                patch.object(watchdog.time, "monotonic", side_effect=lambda: next(clock)):
            watchdog._reconnect_home_wifi()

        assert calls[-1] == ["nmcli", "--wait", "20", "device", "connect", "wlan0"]

    def test_failures_do_not_raise(self, no_sleep):
        with patch.object(watchdog.subprocess, "run", side_effect=subprocess.TimeoutExpired("nmcli", 30)), \
                patch.object(watchdog.time, "monotonic", side_effect=[0, 100, 100]):
            watchdog._reconnect_home_wifi()

    @pytest.mark.parametrize("state,code", [
        ("30 (disconnected)", 30), ("100 (connected)", 100), ("20 (unavailable)", 20), ("", 0), ("x", 0),
    ])
    def test_state_code(self, state, code):
        assert watchdog._nm_state_code(state) == code


class TestWifiDiagnostics:
    """Evidence copied to the watchdog log when leaving setup mode fails."""

    def test_logged_only_when_wifi_stays_down(self):
        with patch.object(watchdog, "state_manager", MagicMock()), \
                patch.object(watchdog, "stop_setup_mode"), \
                patch.object(watchdog, "_reconnect_home_wifi"), \
                patch.object(watchdog, "_restore_issue"), \
                patch.object(watchdog, "start_display"), \
                patch.object(watchdog, "start_setup_mode"), \
                patch.object(watchdog, "_log_wifi_diagnostics") as diag:
            with patch.object(watchdog, "wait_for_wifi", return_value=True):
                watchdog.try_leave_setup_mode()
            diag.assert_not_called()
            with patch.object(watchdog, "wait_for_wifi", return_value=False):
                watchdog.try_leave_setup_mode()
            diag.assert_called_once()

    def test_copies_command_output_to_log(self, caplog):
        def run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, f"out-of-{cmd[0]}\n", "")

        with patch.object(watchdog.subprocess, "run", side_effect=run), \
                caplog.at_level("INFO", logger=watchdog.logger.name):
            watchdog._log_wifi_diagnostics()

        assert "diag [nmcli] out-of-nmcli" in caplog.text
        assert "diag [iw] out-of-iw" in caplog.text
        assert "diag [journalctl] out-of-journalctl" in caplog.text


class TestSetupIssueText:
    """Console box shown in setup mode."""

    @pytest.fixture
    def issue(self, tmp_path):
        issue_path = tmp_path / "issue"
        issue_path.write_text("Debian GNU/Linux\n")
        with patch.object(watchdog, "ISSUE_PATH", issue_path), \
                patch.object(watchdog, "ISSUE_BACKUP_PATH", tmp_path / "issue.bak"), \
                patch.object(watchdog, "_get_hostapd_value", return_value="a1b2c3d4"), \
                patch.object(watchdog.subprocess, "run"):
            yield issue_path

    def test_outage_wording(self, issue):
        watchdog._write_setup_issue("tkframe", "extended_outage")
        text = issue.read_text()

        assert "PicFrame - No WiFi" in text
        assert "offline for over 10 min" in text
        assert "Photos resume automatically when WiFi is back" in text
        assert "checks every 15 minutes" in text
        assert "PicFrame-tkframe" in text
        assert "a1b2c3d4" in text
        assert "http://192.168.4.1" in text
        assert "WiFi Setup Mode" not in text

    @pytest.mark.parametrize("reason", ["unprovisioned", "manual", None])
    def test_other_reasons_keep_setup_wording(self, issue, reason):
        watchdog._write_setup_issue("tkframe", reason)
        text = issue.read_text()

        assert "WiFi Setup Mode" in text
        assert "No WiFi" not in text
        assert "PicFrame-tkframe" in text

    @pytest.mark.parametrize("reason", ["extended_outage", "unprovisioned"])
    def test_every_line_fits_the_box(self, issue, reason):
        watchdog._write_setup_issue("tkframe", reason)
        box = [line for line in issue.read_text().splitlines() if line]

        assert {len(line) for line in box} == {52}

    def test_start_setup_mode_passes_reason(self):
        sm = MagicMock()
        sm.read.return_value = {"frame_name": "tkframe", "setup_mode_reason": "extended_outage"}
        with patch.object(watchdog, "state_manager", sm), \
                patch.object(watchdog, "_update_hostapd_ssid"), \
                patch.object(watchdog, "Path"), \
                patch.object(watchdog.subprocess, "run"), \
                patch.object(watchdog, "stop_display"), \
                patch.object(watchdog, "_write_setup_issue") as write_issue:
            watchdog.start_setup_mode()

        write_issue.assert_called_once_with("tkframe", "extended_outage")


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
