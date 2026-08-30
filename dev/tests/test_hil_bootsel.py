"""Tests for the states the bench harness has to survive without a serial port.

A board in BOOTSEL, a board the map has never seen, and a bench that is a board
short are the three ways a run can be worthless while looking fine, and all
three are hardware-free to pin down: sysfs is a directory, the job summary is a
file, and flashing is a subprocess.
"""

from __future__ import annotations

import sys
import time
import types
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
import trench_coat  # noqa: E402


def usb_tree(tmp_path, devices):
    """Build a fake /sys/bus/usb/devices holding `devices` = {name: (vid, pid, serial)}."""
    root = tmp_path / "usb"
    root.mkdir()
    for name, fields in devices.items():
        entry = root / name
        entry.mkdir()
        if fields is None:  # an interface, which has no ids at all
            continue
        vid, pid, serial = fields
        (entry / "idVendor").write_text(vid + "\n")
        (entry / "idProduct").write_text(pid + "\n")
        if serial is not None:
            (entry / "serial").write_text(serial + "\n")
    return root


# --------------------------------------------------------------------------
# finding a board that has no serial port
# --------------------------------------------------------------------------


def test_bootsel_boards_finds_rp2_bootloaders(monkeypatch, tmp_path):
    root = usb_tree(
        tmp_path,
        {
            "1-1": ("2e8a", "0003", "E661A4D4179A5B2F"),  # RP2040 in BOOTSEL
            "1-2": ("2e8a", "000f", "df13a50c13958980"),  # RP2350 in BOOTSEL
            "1-3": ("2e8a", "0005", "e66141040380b42e"),  # running MicroPython
            "1-4": ("1d6b", "0002", None),  # a hub
            "1-1:1.0": None,  # an interface
        },
    )
    monkeypatch.setattr(bench, "USB_DEVICES", root)

    found = bench.bootsel_boards()

    assert [b["chip_id"] for b in found] == ["e661a4d4179a5b2f", "df13a50c13958980"]
    assert [b["processor"] for b in found] == ["RP2040", "RP2350"]
    # The id is the same one the map is keyed by, so a board is identifiable
    # here even though nothing can be asked of it.
    assert all(b["port"] is None and b["bootsel"] and not b["responsive"] for b in found)


def test_bootsel_boards_is_empty_without_sysfs(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "USB_DEVICES", tmp_path / "nothing here")
    assert bench.bootsel_boards() == []


def test_an_empty_bench_is_told_apart_from_one_in_the_bootloader(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "bootsel_boards", lambda: [])
    monkeypatch.setattr(bench, "USB_DEVICES", tmp_path / "nothing")
    assert "nothing in the ROM bootloader either" in bench.no_boards_message()

    monkeypatch.setattr(bench, "bootsel_boards", lambda: [{"chip_id": "e66141040380b42e"}])
    message = bench.no_boards_message()
    assert "e66141040380b42e" in message
    assert "recover.py" in message
    assert "check the USB hub and power" not in message


def test_inventory_lists_bootsel_boards_alongside_the_others(monkeypatch, capsys):
    monkeypatch.setattr(bench, "list_ports", lambda: ["/dev/ttyACM0"])
    monkeypatch.setattr(bench, "probe", lambda port: {"port": port, "chip_id": "aaaa", "system": "wpc", "version": "1.7", "responsive": True})
    monkeypatch.setattr(bench, "bootsel_boards", lambda: [{"chip_id": "bbbb", "processor": "RP2040"}])

    boards = bench.inventory()
    printed = capsys.readouterr().out

    # Only the usable board is returned, but the other one is not silent.
    assert [b["port"] for b in boards] == ["/dev/ttyACM0"]
    assert "bbbb" in printed and "BOOTSEL" in printed
    assert "::warning::" in printed


def test_inventory_explains_a_bench_that_is_entirely_in_the_bootloader(monkeypatch):
    monkeypatch.setattr(bench, "list_ports", lambda: [])
    monkeypatch.setattr(bench, "bootsel_boards", lambda: [{"chip_id": "bbbb", "processor": "RP2040"}])

    with pytest.raises(bench.CheckFailure, match="ROM bootloader"):
        bench.inventory()


# --------------------------------------------------------------------------
# a board the map does not know
# --------------------------------------------------------------------------


@pytest.fixture()
def job_summary(monkeypatch, tmp_path):
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    return path


def test_an_unknown_board_puts_its_id_and_the_fix_in_the_job_summary(job_summary):
    boards = [
        {"port": "/dev/ttyACM0", "chip_id": "aaaa"},
        {"port": None, "chip_id": "cccc"},
    ]
    board_map = {"aaaa": "wpc"}

    message = bench.report_unknown_boards([boards[1]], boards, board_map)
    written = job_summary.read_text()

    assert "cccc" in message
    # The id, the line to set, and where to set it - the whole remedy, on the
    # page somebody reads when a run goes red.
    assert "cccc" in written
    assert "VECTOR_HIL_BOARD_MAP=aaaa=wpc,cccc=<target>" in written
    assert "actions-runner/.env" in written
    # A board already mapped keeps its target in the suggested line.
    assert "aaaa=<target>" not in written


def test_resolve_targets_reports_the_board_it_cannot_place(job_summary):
    boards = [
        {"port": "/dev/ttyACM0", "chip_id": "aaaa", "system": "wpc", "responsive": True},
        {"port": "/dev/ttyACM1", "chip_id": "cccc", "system": None, "responsive": True},
    ]

    with pytest.raises(bench.CheckFailure, match="does not cover"):
        bench.resolve_targets(boards, {"aaaa": "wpc"})

    assert "cccc" in job_summary.read_text()


def test_the_instructions_name_the_valid_targets(job_summary):
    text = bench.board_map_instructions([{"port": None, "chip_id": "cccc"}], {})
    for target in bench.DEFAULT_GAMENAME:
        assert target in text


# --------------------------------------------------------------------------
# a bench that is a board short
# --------------------------------------------------------------------------


def boards_for(*targets):
    return [{"port": f"/dev/ttyACM{i}", "target": target} for i, target in enumerate(targets)]


def test_a_missing_system_fails_the_run(job_summary, monkeypatch):
    monkeypatch.delenv("VECTOR_HIL_REQUIRED_TARGETS", raising=False)

    missing = bench.check_bench_complete(boards_for("wpc", "sys11"))

    assert missing == ["data_east"]
    written = job_summary.read_text()
    assert "Incomplete bench" in written
    assert "data_east" in written


def test_a_complete_bench_says_nothing_to_the_summary(job_summary, monkeypatch):
    monkeypatch.delenv("VECTOR_HIL_REQUIRED_TARGETS", raising=False)

    assert bench.check_bench_complete(boards_for("wpc", "sys11", "data_east")) == []
    assert not job_summary.exists()


def test_a_bench_that_really_has_lost_a_board_can_say_so(job_summary, monkeypatch):
    monkeypatch.setenv("VECTOR_HIL_REQUIRED_TARGETS", "wpc,sys11")
    assert bench.check_bench_complete(boards_for("wpc", "sys11")) == []


def test_the_check_can_be_turned_off_entirely(job_summary, monkeypatch):
    monkeypatch.setenv("VECTOR_HIL_REQUIRED_TARGETS", "")
    assert bench.check_bench_complete([]) == []


# --------------------------------------------------------------------------
# flashing every board at once
# --------------------------------------------------------------------------


def test_boards_are_flashed_in_parallel(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "write_bench_config", lambda target, workdir: tmp_path / f"{target}.json")

    def slow_flash(target, port, build_dir, config_path):
        time.sleep(0.3)

    monkeypatch.setattr(bench, "flash", slow_flash)
    boards = boards_for("wpc", "sys11", "data_east")

    started = time.monotonic()
    assert bench.flash_boards(boards, tmp_path) == {}
    elapsed = time.monotonic() - started

    # Three 0.3s flashes, one after another, would be 0.9s.
    assert elapsed < 0.6


def test_one_board_failing_to_flash_does_not_take_the_others_with_it(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "write_bench_config", lambda target, workdir: tmp_path / f"{target}.json")

    def flash(target, port, build_dir, config_path):
        if target == "sys11":
            raise bench.CheckFailure("flash failed for sys11: no space left")

    monkeypatch.setattr(bench, "flash", flash)
    boards = boards_for("wpc", "sys11", "data_east")

    errors = bench.flash_boards(boards, tmp_path)

    # Attributed to the right board, which is the whole risk of doing this
    # concurrently.
    assert list(errors) == ["/dev/ttyACM1"]
    assert "no space left" in errors["/dev/ttyACM1"]


def test_an_unexpected_error_is_reported_rather_than_escaping(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "write_bench_config", lambda target, workdir: tmp_path / f"{target}.json")

    def flash(target, port, build_dir, config_path):
        raise RuntimeError("the venv moved")

    monkeypatch.setattr(bench, "flash", flash)

    errors = bench.flash_boards(boards_for("wpc"), tmp_path)

    assert "RuntimeError: the venv moved" in errors["/dev/ttyACM0"]


# --------------------------------------------------------------------------
# putting firmware back on a board in the bootloader
# --------------------------------------------------------------------------


def test_the_drive_is_found_through_the_devices_own_sysfs_path(tmp_path):
    device = tmp_path / "1-1"
    block = device / "1-1:1.0" / "host0" / "target0:0:0" / "0:0:0:0" / "block" / "sda"
    block.mkdir(parents=True)

    assert trench_coat.block_device(device) == Path("/dev/sda")


def test_no_drive_yet_is_not_an_error(tmp_path):
    device = tmp_path / "1-1"
    device.mkdir()
    assert trench_coat.block_device(device) is None


def test_an_already_mounted_drive_is_not_mounted_again(monkeypatch):
    monkeypatch.setattr(trench_coat, "mount_point", lambda device: "/media/runner/RPI-RP2")
    monkeypatch.setattr(trench_coat.subprocess, "run", lambda *a, **k: pytest.fail("udisksctl must not be called for a drive that is already mounted"))

    assert trench_coat.mount("/dev/sda") == "/media/runner/RPI-RP2"


def test_mount_point_reads_proc_mounts(monkeypatch, tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("proc /proc proc rw 0 0\n/dev/sdb /media/runner/RPI-RP2 vfat rw 0 0\n")
    real_read = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: real_read(mounts) if str(self) == "/proc/mounts" else real_read(self, *a, **k))

    assert trench_coat.mount_point("/dev/sdb") == "/media/runner/RPI-RP2"
    assert trench_coat.mount_point("/dev/sdc") is None


@pytest.fixture()
def rescue(monkeypatch):
    """Fake out everything below rescue_bootsel and record what it flashed."""
    flashed = []
    monkeypatch.setattr(trench_coat, "clone", lambda root, commit=None: Path("/trench-coat"))
    monkeypatch.setattr(trench_coat, "flash_bootsel", lambda chip_id, target, root: flashed.append((chip_id, target)) or "/dev/ttyACM9")
    return flashed


def test_a_board_in_the_bootloader_is_flashed_with_its_own_targets_firmware(monkeypatch, rescue, tmp_path):
    monkeypatch.setattr(bench, "bootsel_boards", lambda: [{"chip_id": "aaaa", "processor": "RP2040"}, {"chip_id": "bbbb", "processor": "RP2040"}])

    assert trench_coat.rescue_bootsel({"aaaa": "wpc", "bbbb": "data_east"}, tmp_path) == 2
    assert rescue == [("aaaa", "wpc"), ("bbbb", "data_east")]


def test_an_unmapped_board_is_reported_and_left_alone(monkeypatch, rescue, tmp_path, job_summary):
    monkeypatch.setattr(bench, "bootsel_boards", lambda: [{"chip_id": "aaaa", "processor": "RP2040"}, {"chip_id": "cccc", "processor": "RP2350"}])

    # Guessing which system's firmware to write would be a good way to flash
    # WPC firmware onto the Data East board.
    assert trench_coat.rescue_bootsel({"aaaa": "wpc"}, tmp_path) == 1
    assert rescue == [("aaaa", "wpc")]
    assert "cccc" in job_summary.read_text()


def test_nothing_in_the_bootloader_costs_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "bootsel_boards", lambda: [])
    monkeypatch.setattr(trench_coat, "clone", lambda *a, **k: pytest.fail("must not clone trench-coat with nothing to rescue"))

    assert trench_coat.rescue_bootsel({"aaaa": "wpc"}, tmp_path) == 0


def test_one_boards_rescue_failing_does_not_stop_the_next(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "bootsel_boards", lambda: [{"chip_id": "aaaa", "processor": "RP2040"}, {"chip_id": "bbbb", "processor": "RP2040"}])
    monkeypatch.setattr(trench_coat, "clone", lambda root, commit=None: Path("/trench-coat"))
    tried = []

    def flash_bootsel(chip_id, target, root):
        tried.append(chip_id)
        if chip_id == "aaaa":
            raise bench.CheckFailure("no drive ever appeared")
        return "/dev/ttyACM1"

    monkeypatch.setattr(trench_coat, "flash_bootsel", flash_bootsel)

    assert trench_coat.rescue_bootsel({"aaaa": "wpc", "bbbb": "sys11"}, tmp_path) == 1
    assert tried == ["aaaa", "bbbb"]


def test_the_wipe_comes_before_the_firmware(monkeypatch, tmp_path):
    """nuke.uf2 first is the whole difference between a recovery and an upgrade."""
    root = tmp_path / "trench-coat"
    (root / "uf2").mkdir(parents=True)
    (root / "uf2" / "nuke.uf2").write_text("nuke")
    (root / "uf2" / trench_coat.TARGET_UF2["wpc"]).write_text("firmware")

    copied = []
    monkeypatch.setattr(trench_coat, "copy_uf2", lambda uf2, device, drive: copied.append(uf2.name))
    monkeypatch.setattr(trench_coat, "bootsel_drive", lambda chip_id, timeout=None: ("/dev/sda", "/media/RPI-RP2"))
    monkeypatch.setattr(trench_coat, "wait_for_bootsel", lambda chip_id, present, timeout=None: True)
    monkeypatch.setattr(trench_coat, "BOOTSEL_SETTLE", 0)
    ports = iter([[], [], ["/dev/ttyACM0"]])
    monkeypatch.setattr(trench_coat, "serial_ports", lambda: next(ports, ["/dev/ttyACM0"]))

    assert trench_coat.flash_bootsel("aaaa", "wpc", root) == "/dev/ttyACM0"
    assert copied == ["nuke.uf2", trench_coat.TARGET_UF2["wpc"]]


def test_a_board_that_never_presents_a_drive_is_not_flashed(monkeypatch, tmp_path):
    root = tmp_path / "trench-coat"
    (root / "uf2").mkdir(parents=True)
    (root / "uf2" / "nuke.uf2").write_text("nuke")
    (root / "uf2" / trench_coat.TARGET_UF2["wpc"]).write_text("firmware")

    monkeypatch.setattr(trench_coat, "copy_uf2", lambda *a: pytest.fail("nothing to copy to"))
    monkeypatch.setattr(trench_coat, "bootsel_drive", lambda chip_id, timeout=None: (None, None))
    monkeypatch.setattr(trench_coat, "serial_ports", lambda: [])

    assert trench_coat.flash_bootsel("aaaa", "wpc", root) is None


def test_trench_coat_is_shown_the_recovered_board_and_no_other(monkeypatch, tmp_path):
    """The port filter has to do two opposite things at two moments.

    Before the flash it must hide every board, so TrenchCoat resets none of
    them; after it, it must show the recovered one, or its own wait for the
    board to restart can never be satisfied.
    """
    seen = {}

    class FakeRay:
        def __init__(self, port):
            seen.setdefault("bootloader", []).append(port)

        def enter_bootloader_mode(self):
            pass

        @classmethod
        def find_board_ports(cls):
            return []

    ray = types.SimpleNamespace(Ray=FakeRay, serial=types.SimpleNamespace(Serial=lambda *a, **k: object()))
    core = types.SimpleNamespace(
        list_rpi_rp2_drives=lambda: ["/media/RPI-RP2"],
        graceful_exit=lambda now=False: None,
        flash_firmware=lambda path: seen.update(during=ray.Ray.find_board_ports()),
    )
    monkeypatch.setattr(trench_coat, "clone", lambda root, commit=None: root)
    monkeypatch.setattr(trench_coat, "load", lambda root: (core, ray))
    monkeypatch.setattr(trench_coat, "bundled_uf2", lambda root, target: Path("/uf2/wpc.uf2"))
    monkeypatch.setattr(trench_coat, "find_bootloader_drives", lambda: ["/media/RPI-RP2"])
    monkeypatch.setattr(trench_coat, "wait_for_drive", lambda core, timeout=None: ["/media/RPI-RP2"])

    # The two healthy boards are on ACM0 and ACM2; the board being recovered is
    # a drive right now and comes back on a number it did not have before.
    monkeypatch.setattr(trench_coat, "serial_ports", lambda: ["/dev/ttyACM0", "/dev/ttyACM2"])
    assert trench_coat.flash("/dev/ttyACM1", "wpc", tmp_path) is True
    assert seen["during"] == []
    assert seen["bootloader"] == ["/dev/ttyACM1"]

    hidden = ray.Ray.find_board_ports
    monkeypatch.setattr(trench_coat, "serial_ports", lambda: ["/dev/ttyACM0", "/dev/ttyACM2", "/dev/ttyACM3"])
    assert hidden() == ["/dev/ttyACM3"]


def test_the_same_finding_reaches_the_summary_once(job_summary, monkeypatch):
    """Three stages, one summary page, one problem."""
    monkeypatch.delenv("VECTOR_HIL_REQUIRED_TARGETS", raising=False)
    boards = boards_for("wpc", "sys11")

    for _stage in range(3):
        assert bench.check_bench_complete(boards) == ["data_east"]

    assert job_summary.read_text().count("### Incomplete bench") == 1


def test_a_different_finding_still_gets_through(job_summary):
    boards = [{"port": None, "chip_id": "cccc"}, {"port": None, "chip_id": "dddd"}]

    bench.report_unknown_boards([boards[0]], boards, {})
    bench.report_unknown_boards([boards[1]], boards, {})

    written = job_summary.read_text()
    assert "cccc" in written and "dddd" in written


# --------------------------------------------------------------------------
# an empty bench has to explain itself
# --------------------------------------------------------------------------


def test_an_empty_bench_prints_the_usb_bus(monkeypatch, tmp_path):
    """ "no boards found" and "lsusb shows them" is a contradiction the log must settle."""
    root = usb_tree(
        tmp_path,
        {
            "usb1": ("1d6b", "0002", "0000:01:00.0"),
            "1-1": ("2109", "3431", None),
            "1-1.1": ("2e8a", "0005", "e661a4d4179a5b2f"),  # a mode we do not handle
            "1-1.1:1.0": None,
        },
    )
    monkeypatch.setattr(bench, "USB_DEVICES", root)

    message = bench.no_boards_message()

    assert "2e8a:0005" in message
    assert "2109:3431" in message
    # The recognised ids are named, so the reader can see what the mismatch is.
    assert "2e8a:0003" in message
    # Interfaces carry no ids and are not devices.
    assert "1-1.1:1.0" not in message


def test_an_empty_sysfs_says_so_rather_than_blaming_the_boards(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "USB_DEVICES", tmp_path / "nothing")
    assert "Nothing at all is on the USB bus" in bench.no_boards_message()
