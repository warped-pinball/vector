"""Tests for the bench recovery ladder, with the hardware faked out.

The escalation order is the whole design - cheapest and least destructive
first, stopping the moment the board answers - so that is what these pin down,
along with the checksum gate on anything that gets flashed.
"""

from __future__ import annotations

import subprocess
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.modules.setdefault("serial", types.ModuleType("serial"))
if "usb_coms_demo" not in sys.modules:
    stub = types.ModuleType("usb_coms_demo")
    stub.UsbApiClient = object
    sys.modules["usb_coms_demo"] = stub

sys.path.insert(0, str(REPO_ROOT / "dev" / "hil"))

import bench  # noqa: E402
import recover  # noqa: E402


def args(**overrides):
    defaults = {"reflash": True, "no_power_cycle": False, "force_bootsel": False, "step_timeout": 30, "cache_dir": Path("/nonexistent")}
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.fixture()
def ladder(monkeypatch):
    """Record which recovery steps ran, and let a test choose which one works."""
    calls = []

    def step(name, works_at=None):
        def run(*_args, **_kwargs):
            calls.append(name)
            return True

        return run

    monkeypatch.setattr(recover, "drain", step("drain"))
    monkeypatch.setattr(recover, "usb_reset", step("usb_reset"))
    monkeypatch.setattr(recover, "power_cycle", step("power_cycle"))
    monkeypatch.setattr(recover, "reflash", step("reflash"))
    monkeypatch.setattr(recover, "SETTLE_SECONDS", 0)
    return calls


def recovers_after(monkeypatch, calls, step_count):
    """Make the board answer once `step_count` steps have run."""
    monkeypatch.setattr(recover, "responsive", lambda _port, timeout=None: len(calls) >= step_count)


def test_the_cheapest_step_that_works_ends_the_ladder(monkeypatch, ladder):
    recovers_after(monkeypatch, ladder, 1)

    method = recover.recover("/dev/ttyFAKE", "wpc", args())

    assert ladder == ["drain"]
    assert "drain" in method


def test_it_escalates_only_as_far_as_it_has_to(monkeypatch, ladder):
    recovers_after(monkeypatch, ladder, 3)

    method = recover.recover("/dev/ttyFAKE", "wpc", args())

    assert ladder == ["drain", "usb_reset", "power_cycle"]
    assert "power cycle" in method


def test_reflashing_is_the_last_resort_and_not_before(monkeypatch, ladder):
    recovers_after(monkeypatch, ladder, 4)

    method = recover.recover("/dev/ttyFAKE", "wpc", args())

    assert ladder == ["drain", "usb_reset", "power_cycle", "reflash"]
    assert "reflash" in method


def test_a_board_that_never_answers_reports_defeat(monkeypatch, ladder):
    monkeypatch.setattr(recover, "responsive", lambda _port, timeout=None: False)

    assert recover.recover("/dev/ttyFAKE", "wpc", args()) is None
    assert ladder == ["drain", "usb_reset", "power_cycle", "reflash"]


def test_no_reflash_leaves_the_firmware_alone(monkeypatch, ladder):
    monkeypatch.setattr(recover, "responsive", lambda _port, timeout=None: False)

    recover.recover("/dev/ttyFAKE", "wpc", args(reflash=False))

    assert "reflash" not in ladder


def test_reflash_is_skipped_when_the_target_is_unknown(monkeypatch, ladder, capsys):
    # Flashing the wrong system's UF2 is worse than leaving the board dead.
    monkeypatch.setattr(recover, "responsive", lambda _port, timeout=None: False)

    recover.recover("/dev/ttyFAKE", None, args())

    assert "reflash" not in ladder
    assert "no target known" in capsys.readouterr().out


def test_a_failing_step_does_not_stop_the_ladder(monkeypatch, ladder):
    def explode(*_args, **_kwargs):
        ladder.append("usb_reset")
        raise OSError("ioctl went wrong")

    monkeypatch.setattr(recover, "usb_reset", explode)
    recovers_after(monkeypatch, ladder, 3)

    method = recover.recover("/dev/ttyFAKE", "wpc", args())

    assert ladder == ["drain", "usb_reset", "power_cycle"]
    assert method is not None


# --------------------------------------------------------------------------
# survey
# --------------------------------------------------------------------------


def fake_survey(monkeypatch, ports, dead_ports, chip_ids):
    monkeypatch.setattr(recover, "list_ports", lambda: ports)
    monkeypatch.setattr(recover, "responsive", lambda port, timeout=None: port not in dead_ports)

    def fake_mpremote(*call, timeout=None):
        port = call[1]
        return types.SimpleNamespace(returncode=0, stdout=chip_ids[port], stderr="")

    monkeypatch.setattr(recover, "mpremote", fake_mpremote)


def test_survey_deduces_the_dead_board_by_elimination(monkeypatch):
    """A wedged board cannot say what it is, but the others can say what it is not."""
    fake_survey(
        monkeypatch,
        ports=["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2"],
        dead_ports={"/dev/ttyACM1"},
        chip_ids={"/dev/ttyACM0": "aaa", "/dev/ttyACM2": "ccc"},
    )
    board_map = {"aaa": "sys11", "bbb": "wpc", "ccc": "data_east"}

    alive, dead, targets = recover.survey(board_map)

    assert alive == ["/dev/ttyACM0", "/dev/ttyACM2"]
    assert dead == ["/dev/ttyACM1"]
    assert targets == {"/dev/ttyACM1": "wpc"}


def test_survey_will_not_guess_when_two_boards_are_down(monkeypatch):
    fake_survey(
        monkeypatch,
        ports=["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2"],
        dead_ports={"/dev/ttyACM1", "/dev/ttyACM2"},
        chip_ids={"/dev/ttyACM0": "aaa"},
    )
    board_map = {"aaa": "sys11", "bbb": "wpc", "ccc": "data_east"}

    _alive, dead, targets = recover.survey(board_map)

    assert sorted(dead) == ["/dev/ttyACM1", "/dev/ttyACM2"]
    assert targets == {}


def test_survey_fails_when_nothing_is_attached(monkeypatch):
    monkeypatch.setattr(recover, "list_ports", lambda: [])

    with pytest.raises(bench.CheckFailure, match="no boards found"):
        recover.survey({})


def test_responsive_is_false_when_mpremote_times_out(monkeypatch):
    def times_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="mpremote", timeout=20)

    monkeypatch.setattr(recover, "mpremote", times_out)

    assert recover.responsive("/dev/ttyFAKE") is False


# --------------------------------------------------------------------------
# the UF2 gate
# --------------------------------------------------------------------------


def test_fetch_uf2_refuses_a_file_that_does_not_match_the_pin(tmp_path):
    filename, _digest = recover.TARGET_UF2["wpc"]
    (tmp_path / filename).write_bytes(b"not the firmware you are looking for")

    with pytest.raises(bench.CheckFailure, match="refusing to flash it"):
        recover.fetch_uf2("wpc", tmp_path)

    # And it does not leave the bad file behind to be picked up next time.
    assert not (tmp_path / filename).exists()


def test_fetch_uf2_accepts_the_pinned_file(tmp_path, monkeypatch):
    import hashlib

    payload = b"pretend UF2"
    filename, _digest = recover.TARGET_UF2["wpc"]
    monkeypatch.setitem(recover.TARGET_UF2, "wpc", (filename, hashlib.sha256(payload).hexdigest()))
    (tmp_path / filename).write_bytes(payload)

    assert recover.fetch_uf2("wpc", tmp_path) == tmp_path / filename


def test_fetch_uf2_rejects_a_target_it_has_no_firmware_for(tmp_path):
    with pytest.raises(bench.CheckFailure, match="no UF2 known"):
        recover.fetch_uf2("whitestar", tmp_path)


def test_every_target_uf2_pin_is_a_sha256():
    for target, (filename, digest) in recover.TARGET_UF2.items():
        assert filename.endswith(".uf2"), target
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef"), target


# --------------------------------------------------------------------------
# sysfs plumbing
# --------------------------------------------------------------------------


def test_usb_device_path_walks_up_to_the_device(tmp_path, monkeypatch):
    device = tmp_path / "sys" / "devices" / "usb1" / "1-1.4"
    interface = device / "1-1.4:1.0" / "tty" / "ttyACM1"
    interface.mkdir(parents=True)
    (device / "busnum").write_text("1\n")
    (device / "devnum").write_text("7\n")

    link = tmp_path / "sys" / "class" / "tty" / "ttyACM1" / "device"
    link.parent.mkdir(parents=True)
    link.symlink_to(device / "1-1.4:1.0")

    monkeypatch.setattr(recover, "Path", lambda p: link if str(p).endswith("/device") else Path(p))

    assert recover.usb_device_path("/dev/ttyACM1") == Path("/dev/bus/usb/001/007")


@pytest.mark.parametrize(
    "usb_path, expected",
    [
        ("1-1.4:1.0", ("1-1", "4")),
        ("1-1.2.3:1.0", ("1-1.2", "3")),
        ("2-3:1.0", ("2", "3")),
    ],
)
def test_hub_location_splits_the_usb_path(tmp_path, monkeypatch, usb_path, expected):
    device = tmp_path / usb_path
    device.mkdir(parents=True)
    (device / "busnum").write_text("1\n")

    link = tmp_path / "link"
    link.symlink_to(device)
    monkeypatch.setattr(recover, "Path", lambda p: link if str(p).endswith("/device") else Path(p))

    assert recover.hub_location("/dev/ttyACM1") == expected


def test_reflash_will_not_strand_a_board_in_bootsel_it_cannot_flash(monkeypatch, tmp_path, capsys):
    """The touch is a one-way door.

    A wedged board is at least still a serial device. Touching it into BOOTSEL
    with no way to write a UF2 turns it into a mass-storage device that only a
    replug gets out of - strictly worse than how it was found.
    """
    touched = []
    monkeypatch.setattr(recover, "bootsel_touch", lambda port: touched.append(port))
    monkeypatch.setattr(recover, "can_complete_a_reflash", lambda: (False, "no udisksctl"))

    assert recover.reflash("/dev/ttyFAKE", "wpc", tmp_path) is False
    assert touched == []
    assert "not touching the board into BOOTSEL" in capsys.readouterr().out


def test_reflash_verifies_the_uf2_before_the_point_of_no_return(monkeypatch, tmp_path):
    """Download and checksum first: a bad fetch must not cost us the board."""
    touched = []
    monkeypatch.setattr(recover, "bootsel_touch", lambda port: touched.append(port))
    monkeypatch.setattr(recover, "can_complete_a_reflash", lambda: (True, "udisksctl is available"))

    filename, _digest = recover.TARGET_UF2["wpc"]
    (tmp_path / filename).write_bytes(b"corrupted download")

    with pytest.raises(bench.CheckFailure, match="refusing to flash it"):
        recover.reflash("/dev/ttyFAKE", "wpc", tmp_path)
    assert touched == []


def test_force_bootsel_overrides_the_guard(monkeypatch, tmp_path):
    import hashlib

    payload = b"pretend UF2"
    filename, _digest = recover.TARGET_UF2["wpc"]
    monkeypatch.setitem(recover.TARGET_UF2, "wpc", (filename, hashlib.sha256(payload).hexdigest()))
    (tmp_path / filename).write_bytes(payload)

    touched = []
    monkeypatch.setattr(recover, "bootsel_touch", lambda port: touched.append(port))
    monkeypatch.setattr(recover, "can_complete_a_reflash", lambda: (False, "no udisksctl"))
    monkeypatch.setattr(recover, "find_bootloader_drive", lambda *a, **k: None)
    monkeypatch.setattr(recover, "mount_bootloader_drive", lambda *a, **k: None)

    assert recover.reflash("/dev/ttyFAKE", "wpc", tmp_path, force=True) is False
    assert touched == ["/dev/ttyFAKE"]
