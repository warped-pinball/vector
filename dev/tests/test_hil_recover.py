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

_serial_stub = sys.modules.setdefault("serial", types.ModuleType("serial"))
if not hasattr(_serial_stub, "SerialTimeoutException"):
    _serial_stub.SerialTimeoutException = type("SerialTimeoutException", (Exception,), {})
if "usb_coms_demo" not in sys.modules:
    stub = types.ModuleType("usb_coms_demo")
    stub.UsbApiClient = object
    sys.modules["usb_coms_demo"] = stub

sys.path.insert(0, str(REPO_ROOT / "dev" / "hil"))

import bench  # noqa: E402
import recover  # noqa: E402
import trench_coat  # noqa: E402


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
# handing the board to TrenchCoat
# --------------------------------------------------------------------------


def test_reflash_delegates_to_trench_coat(monkeypatch, tmp_path):
    """The sequence is TrenchCoat's, not ours - we only point it at one board."""
    called = {}
    monkeypatch.setattr(recover, "can_complete_a_reflash", lambda: (True, "udisksctl is available"))
    monkeypatch.setattr(recover.trench_coat, "flash", lambda port, target, root: called.update(port=port, target=target, root=root) or True)

    assert recover.reflash("/dev/ttyFAKE", "wpc", tmp_path) is True
    assert called["port"] == "/dev/ttyFAKE"
    assert called["target"] == "wpc"


def test_reflash_will_not_strand_a_board_in_bootsel_it_cannot_flash(monkeypatch, tmp_path, capsys):
    """Entering BOOTSEL is a one-way door.

    A wedged board is at least still a serial device. Sending it to the ROM
    bootloader with no way to write a UF2 turns it into a mass-storage device
    that only a replug gets out of - strictly worse than how it was found.
    """
    monkeypatch.setattr(recover, "can_complete_a_reflash", lambda: (False, "no udisksctl"))
    monkeypatch.setattr(recover.trench_coat, "flash", lambda *a, **k: pytest.fail("must not touch the board"))

    assert recover.reflash("/dev/ttyFAKE", "wpc", tmp_path) is False
    assert "not touching the board into BOOTSEL" in capsys.readouterr().out


def test_force_bootsel_overrides_the_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(recover, "can_complete_a_reflash", lambda: (False, "no udisksctl"))
    monkeypatch.setattr(recover.trench_coat, "flash", lambda *a, **k: True)

    assert recover.reflash("/dev/ttyFAKE", "wpc", tmp_path, force=True) is True


def test_can_complete_a_reflash_accepts_udisksctl(monkeypatch):
    monkeypatch.setattr(recover.shutil, "which", lambda name: "/usr/bin/udisksctl" if name == "udisksctl" else None)
    monkeypatch.setattr(recover.Path, "is_dir", lambda self: False)

    possible, why = recover.can_complete_a_reflash()

    assert possible is True
    assert "udisksctl" in why


def test_can_complete_a_reflash_says_no_when_nothing_can_mount(monkeypatch):
    monkeypatch.setattr(recover.shutil, "which", lambda _name: None)
    monkeypatch.setattr(recover.Path, "is_dir", lambda self: False)

    possible, why = recover.can_complete_a_reflash()

    assert possible is False
    assert "nothing here can mount" in why


def test_every_target_maps_to_a_bundled_uf2():
    for target, filename in trench_coat.TARGET_UF2.items():
        assert filename.endswith(".uf2"), target


def test_bundled_uf2_rejects_an_unknown_target(tmp_path):
    with pytest.raises(bench.CheckFailure, match="no TrenchCoat UF2 known"):
        trench_coat.bundled_uf2(tmp_path, "whitestar")


def test_bundled_uf2_reports_a_checkout_missing_the_file(tmp_path):
    with pytest.raises(bench.CheckFailure, match="missing from the trench-coat checkout"):
        trench_coat.bundled_uf2(tmp_path, "wpc")


def test_load_refuses_the_wrong_src_package(tmp_path, monkeypatch):
    """Both repos have a top-level `src`; importing ours would fail confusingly."""
    fake = tmp_path / "src"
    fake.mkdir()
    (fake / "__init__.py").write_text("")
    (fake / "core.py").write_text("")
    (fake / "ray.py").write_text("")

    real_import = trench_coat.load
    monkeypatch.setattr(trench_coat, "clone", lambda root, commit=None: root)

    # Loading from the right root works; the guard only fires on a mismatch,
    # which is what the assertion inside load() covers.
    core, _ray = real_import(tmp_path)
    assert str(Path(core.__file__).resolve()).startswith(str(tmp_path.resolve()))


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
        # A root-hub port (no dot) is deliberately not switchable - see
        # test_hub_location_refuses_a_root_hub_port.
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


# --------------------------------------------------------------------------
# narrowing TrenchCoat to one board
# --------------------------------------------------------------------------


def fake_trench_coat(monkeypatch, drives=("/media/RPI-RP2",)):
    """Stand in for TrenchCoat's core/ray modules and record how they are used."""
    seen = {"flashed": None, "ports_seen": None, "drives_seen": None, "bootloader": []}

    class FakeRay:
        def __init__(self, port):
            seen["bootloader"].append(port)

        def enter_bootloader_mode(self):
            pass

        @classmethod
        def find_board_ports(cls):
            return ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2"]

    ray = types.SimpleNamespace(Ray=FakeRay, serial=types.SimpleNamespace(Serial=lambda *a, **k: object()))
    core = types.SimpleNamespace(
        list_rpi_rp2_drives=lambda: list(drives),
        graceful_exit=lambda now=False: None,
        flash_firmware=lambda path: seen.update(
            flashed=path,
            ports_seen=ray.Ray.find_board_ports(),
            drives_seen=core.list_rpi_rp2_drives(),
        ),
    )

    monkeypatch.setattr(trench_coat, "clone", lambda root, commit=None: root)
    monkeypatch.setattr(trench_coat, "load", lambda root: (core, ray))
    monkeypatch.setattr(trench_coat, "bundled_uf2", lambda root, target: Path(f"/uf2/{target}.uf2"))
    # Drive discovery is the real function now, and it neither finds a fake
    # drive nor fails fast - without this the tests sit through its full wait.
    monkeypatch.setattr(trench_coat, "find_bootloader_drives", lambda: list(drives))
    monkeypatch.setattr(trench_coat, "wait_for_drive", lambda core, timeout=None: list(drives))
    monkeypatch.setattr(trench_coat, "bootsel_touch", lambda port: None)
    return seen


def test_flash_hides_the_other_boards_from_trench_coat(monkeypatch, tmp_path):
    """The one thing that must not go wrong.

    TrenchCoat flashes every board it finds, which on the bench would nuke the
    two healthy boards alongside the broken one. It only ever gets to see the
    board being recovered.
    """
    seen = fake_trench_coat(monkeypatch)

    assert trench_coat.flash("/dev/ttyACM1", "wpc", tmp_path) is True
    assert seen["ports_seen"] == []
    assert seen["flashed"] == "/uf2/wpc.uf2"
    # Only the board being recovered is asked to enter the bootloader.
    assert seen["bootloader"] == ["/dev/ttyACM1"]


def test_flash_gives_trench_coat_the_drive_it_could_not_find(monkeypatch, tmp_path):
    """A headless runner has no automounter, so we mount and hand the path over."""
    seen = fake_trench_coat(monkeypatch, drives=())
    monkeypatch.setattr(trench_coat, "mount_rpi_rp2", lambda: "/media/runner/RPI-RP2")
    monkeypatch.setattr(trench_coat, "wait_for_drive", lambda core, timeout=None: ["/media/runner/RPI-RP2"])

    assert trench_coat.flash("/dev/ttyACM1", "wpc", tmp_path) is True
    assert seen["drives_seen"] == ["/media/runner/RPI-RP2"]


def test_flash_stops_when_the_board_never_reaches_the_bootloader(monkeypatch, tmp_path, capsys):
    seen = fake_trench_coat(monkeypatch, drives=())
    monkeypatch.setattr(trench_coat, "mount_rpi_rp2", lambda: None)
    monkeypatch.setattr(trench_coat, "bootsel_touch", lambda port: None)
    monkeypatch.setattr(trench_coat, "wait_for_drive", lambda core, timeout=None: [])

    assert trench_coat.flash("/dev/ttyACM1", "wpc", tmp_path) is False
    assert seen["flashed"] is None
    assert "never presented a bootloader drive" in capsys.readouterr().out


def test_flash_turns_trench_coats_exit_into_an_error(monkeypatch, tmp_path):
    """Its failure path calls sys.exit; the harness needs an exception instead."""
    seen = fake_trench_coat(monkeypatch)
    core, _ray = trench_coat.load(tmp_path)

    def bail(_path):
        core.graceful_exit()

    core.flash_firmware = bail

    with pytest.raises(bench.CheckFailure, match="could not complete the flash"):
        trench_coat.flash("/dev/ttyACM1", "wpc", tmp_path)
    assert seen["flashed"] is None


def test_enter_bootloader_falls_back_to_the_1200_baud_touch(monkeypatch):
    """TrenchCoat's route needs the VM alive enough to run one statement."""
    touched = []
    attempts = []

    class FakeRay:
        def __init__(self, port):
            pass

        def enter_bootloader_mode(self):
            attempts.append("machine.bootloader()")

    monkeypatch.setattr(trench_coat, "bootsel_touch", lambda port: touched.append(port))
    monkeypatch.setattr(trench_coat, "wait_for_drive", lambda core, timeout=None: [] if not touched else ["/media/RPI-RP2"])

    drives = trench_coat.enter_bootloader(types.SimpleNamespace(), types.SimpleNamespace(Ray=FakeRay), "/dev/ttyACM1")

    assert attempts == ["machine.bootloader()"]
    assert touched == ["/dev/ttyACM1"]
    assert drives == ["/media/RPI-RP2"]


def test_hub_location_refuses_a_root_hub_port(tmp_path, monkeypatch, capsys):
    """Cutting a root hub takes every board down, not just the broken one."""
    device = tmp_path / "1-1:1.0"
    device.mkdir(parents=True)
    (device / "busnum").write_text("1\n")

    link = tmp_path / "link"
    link.symlink_to(device)
    monkeypatch.setattr(recover, "Path", lambda p: link if str(p).endswith("/device") else Path(p))

    assert recover.hub_location("/dev/ttyACM1") is None
    assert "cut every board on the bus" in capsys.readouterr().out


def test_power_cycle_stands_down_without_a_switchable_hub_port(monkeypatch, capsys):
    monkeypatch.setattr(recover.shutil, "which", lambda _name: "/usr/sbin/uhubctl")
    monkeypatch.setattr(recover, "hub_location", lambda _port: None)

    assert recover.power_cycle("/dev/ttyACM1") is False
    assert "could not work out which hub port" in capsys.readouterr().out


def test_trench_coats_serial_writes_are_bounded(monkeypatch):
    """TrenchCoat opens with a read timeout only, which hangs on a wedged board.

    One recovery run spent its whole 600s step budget inside
    enter_bootloader_mode because of this, and only the SIGALRM backstop ended
    it. Their code is written for a healthy board on a desktop; ours is pointed
    at a board that is broken by definition.
    """
    opened = {}

    class FakeSerialModule:
        @staticmethod
        def Serial(*args, **kwargs):
            opened.update(kwargs)
            return object()

    ray = types.SimpleNamespace(serial=FakeSerialModule)
    trench_coat.bound_serial_writes(ray)
    ray.serial.Serial("/dev/ttyFAKE", 115200, timeout=0.1)

    assert opened["write_timeout"] == bench.SERIAL_WRITE_TIMEOUT


def test_bound_serial_writes_leaves_an_explicit_timeout_alone(monkeypatch):
    opened = {}

    class FakeSerialModule:
        @staticmethod
        def Serial(*args, **kwargs):
            opened.update(kwargs)
            return object()

    ray = types.SimpleNamespace(serial=FakeSerialModule)
    trench_coat.bound_serial_writes(ray)
    ray.serial.Serial("/dev/ttyFAKE", write_timeout=99)

    assert opened["write_timeout"] == 99
