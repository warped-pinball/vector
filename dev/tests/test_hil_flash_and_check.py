"""Tests for the parts of the HIL flash + health check harness that do not
need a board - currently just the job-summary rendering.

Everything else in flash_and_check.py talks to real serial hardware, which is
out of reach here.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# bench.py imports pyserial (which ships with mpremote) and dev/usb_coms_demo.
# Neither is needed for the pure helpers under test and neither is guaranteed to
# be installed wherever these tests run, so stand them in before the import.
_serial_stub = sys.modules.setdefault("serial", types.ModuleType("serial"))
if not hasattr(_serial_stub, "SerialTimeoutException"):
    _serial_stub.SerialTimeoutException = type("SerialTimeoutException", (Exception,), {})
if "usb_coms_demo" not in sys.modules:
    stub = types.ModuleType("usb_coms_demo")
    stub.UsbApiClient = object
    sys.modules["usb_coms_demo"] = stub

sys.path.insert(0, str(REPO_ROOT / "dev" / "hil"))

import bench  # noqa: E402
import flash_and_check as fac  # noqa: E402


def test_write_step_summary_renders_a_table_and_the_failures(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    boards = [
        {"port": "/dev/ttyACM0", "target": "wpc"},
        {"port": "/dev/ttyACM1", "target": "sys11"},
    ]
    failures = ["/dev/ttyACM0 (wpc): could not reset /dev/ttyACM0 before the health check: timed out\n      board said: nothing"]

    fac.write_step_summary(boards, failures, missing=[])

    rendered = summary.read_text()
    assert "| `/dev/ttyACM0` | wpc | `-` | FAIL |" in rendered
    assert "| `/dev/ttyACM1` | sys11 | `-` | ok |" in rendered
    assert "- /dev/ttyACM0 (wpc): could not reset /dev/ttyACM0 before the health check: timed out" in rendered
    assert "board said: nothing" in rendered


def test_write_step_summary_reports_missing_boards(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    fac.write_step_summary([], failures=[], missing=["data_east"])

    rendered = summary.read_text()
    assert "| - | data_east | - | ABSENT |" in rendered


def test_write_step_summary_is_a_no_op_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    fac.write_step_summary([{"port": "/dev/ttyACM0", "target": "wpc"}], failures=[], missing=[])


# --------------------------------------------------------------------------
# the post-flash reset race
# --------------------------------------------------------------------------
#
# dev/flash.py ends by resetting the board, so a board is already booting when
# flash_boards returns. The health check resets again to own the boot it
# watches, and when those two land on top of each other the board wedges: run
# 60 flashed sys11 successfully, tried to reset it 90ms later, and failed the
# whole bench run on a board that was fine.


def test_wait_out_post_flash_boot_waits_for_a_board_flashed_moments_ago(monkeypatch):
    slept = []
    monkeypatch.setattr(bench.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(bench, "wait_for_port", lambda port, **kw: None)
    monkeypatch.setattr(bench.time, "monotonic", lambda: 1000.0)

    bench.wait_out_post_flash_boot("/dev/ttyFAKE", flashed_at=999.9, grace=35)

    # Flashed a tenth of a second ago, so very nearly the whole grace period.
    assert slept and 34 < slept[0] <= 35


def test_wait_out_post_flash_boot_does_not_wait_for_a_board_that_already_booted(monkeypatch):
    slept = []
    monkeypatch.setattr(bench.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(bench, "wait_for_port", lambda port, **kw: None)
    monkeypatch.setattr(bench.time, "monotonic", lambda: 1000.0)

    # Boards are flashed in parallel and checked one at a time, so every board
    # but the last has already finished booting by the time its turn comes.
    bench.wait_out_post_flash_boot("/dev/ttyFAKE", flashed_at=900.0, grace=35)

    assert slept == []


def test_wait_for_port_returns_once_the_board_comes_back(monkeypatch):
    """A board is off the bus for a second or two across a reset."""
    appearances = iter([False, False, True])
    monkeypatch.setattr(bench.os.path, "exists", lambda _port: next(appearances))
    monkeypatch.setattr(bench.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(bench, "open_serial", lambda port: types.SimpleNamespace(close=lambda: None))

    bench.wait_for_port("/dev/ttyFAKE", timeout=30)


def test_wait_for_port_gives_up_with_a_reason(monkeypatch):
    monkeypatch.setattr(bench.os.path, "exists", lambda _port: False)
    monkeypatch.setattr(bench.time, "sleep", lambda _seconds: None)
    clock = iter([0, 1, 2, 3, 99])
    monkeypatch.setattr(bench.time, "monotonic", lambda: next(clock))

    with pytest.raises(bench.CheckFailure, match="did not come back"):
        bench.wait_for_port("/dev/ttyFAKE", timeout=5)


def test_reset_board_reports_a_reason_mpremote_put_on_stdout(monkeypatch):
    """The empty-message failure that made run 60 impossible to read.

    mpremote puts connection errors on stdout, so reading only stderr produced
    "could not reset /dev/ttyACM0 before the health check:" and nothing else.
    """
    monkeypatch.setattr(
        bench,
        "mpremote",
        lambda *a, **kw: types.SimpleNamespace(returncode=1, stdout="failed to access /dev/ttyFAKE", stderr=""),
    )

    with pytest.raises(bench.CheckFailure, match="failed to access /dev/ttyFAKE"):
        bench.reset_board("/dev/ttyFAKE")


def test_reset_board_never_raises_an_empty_reason(monkeypatch):
    monkeypatch.setattr(bench, "mpremote", lambda *a, **kw: types.SimpleNamespace(returncode=2, stdout="", stderr=""))

    with pytest.raises(bench.CheckFailure, match="without saying why"):
        bench.reset_board("/dev/ttyFAKE")


# --------------------------------------------------------------------------
# machine id
# --------------------------------------------------------------------------
#
# The one API value that is not pure shared code: origin.get_machine_id() is
# common to every target, but crc32 and machine.unique_id() come from whichever
# MicroPython image the board runs, and the bench runs a different image per
# system. These tests cover the recomputation and the ways a board can be wrong
# about its own identity; the hardware answers the rest.


class FakeClient:
    """A board that answers the routes check_machine_id asks for.

    Each route holds a list of successive answers so a board can be made to
    change its mind between two calls, which is one of the failures under test.
    """

    def __init__(self, answers):
        self.answers = {route: list(bodies) for route, bodies in answers.items()}
        self.ser = None
        self.asked = []

    def send_and_receive(self, route, payload=None, timeout=None):
        self.asked.append(route)
        bodies = self.answers.get(route)
        if bodies is None:
            return {"status": 404, "body": None}
        body = bodies.pop(0) if len(bodies) > 1 else bodies[0]
        return {"status": 200, "body": body}


CHIP_ID = "e6614c311b8a2f39"
GAMENAME = "GenericDE_"


def board_reporting(machine_id, chip_id=CHIP_ID, gamename=GAMENAME, target="data_east"):
    ids = machine_id if isinstance(machine_id, list) else [machine_id]
    return {
        "port": "/dev/ttyACM0",
        "target": target,
        "chip_id": chip_id,
        "client": FakeClient(
            {
                "/api/machine_id": [{"machine_id": value} for value in ids],
                "/api/game/active_config": [{"active_config": gamename}],
            }
        ),
    }


def test_expected_machine_id_mirrors_the_firmware():
    """Recomputed exactly as origin.get_machine_id() does (origin.py:50-56)."""
    import binascii

    message = (CHIP_ID + GAMENAME).encode()
    reference = (binascii.crc32(message) & 0xFFFFFFFF).to_bytes(4, "big").hex()

    assert fac.expected_machine_id(CHIP_ID, GAMENAME) == reference
    assert len(fac.expected_machine_id(CHIP_ID, GAMENAME)) == fac.MACHINE_ID_DIGITS


def test_expected_machine_id_depends_on_both_inputs():
    """A board with the right chip and the wrong config is a different machine."""
    assert fac.expected_machine_id(CHIP_ID, GAMENAME) != fac.expected_machine_id(CHIP_ID, "Generic_WPC")
    assert fac.expected_machine_id(CHIP_ID, GAMENAME) != fac.expected_machine_id("e6614c311b8a2f38", GAMENAME)


def test_check_machine_id_accepts_the_id_the_inputs_imply():
    board = board_reporting(fac.expected_machine_id(CHIP_ID, GAMENAME))

    assert fac.check_machine_id(board) == board["machine_id"]
    assert board["machine_id"] == fac.expected_machine_id(CHIP_ID, GAMENAME)


def test_check_machine_id_rejects_a_missing_id():
    """A route that answers 200 with nothing in it - the shape a target whose
    image cannot run get_machine_id() would produce."""
    board = board_reporting("deadbeef")
    board["client"].answers["/api/machine_id"] = [{}]

    with pytest.raises(bench.CheckFailure, match="expected an object with a machine_id"):
        fac.check_machine_id(board)


def test_check_machine_id_rejects_a_value_that_is_not_an_id():
    for value in (None, "", 12345):
        board = board_reporting(value)
        with pytest.raises(bench.CheckFailure, match="not an id|not 8 lowercase hex"):
            fac.check_machine_id(board)


def test_check_machine_id_rejects_a_wrong_shape():
    board = board_reporting("1a2b3c4d5e6f")

    with pytest.raises(bench.CheckFailure, match="not 8 lowercase hex digits"):
        fac.check_machine_id(board)


def test_check_machine_id_rejects_the_empty_input_placeholder():
    board = board_reporting("00000000")

    with pytest.raises(bench.CheckFailure, match="not an identity"):
        fac.check_machine_id(board)


def test_check_machine_id_rejects_an_id_that_changes_between_calls():
    board = board_reporting([fac.expected_machine_id(CHIP_ID, GAMENAME), "12345678"])

    with pytest.raises(bench.CheckFailure, match="not stable"):
        fac.check_machine_id(board)


def test_check_machine_id_rejects_an_id_not_derived_from_this_boards_inputs():
    """The failure this check exists for: a plausible-looking id that no
    combination of this board's unique id and its configured game produces."""
    board = board_reporting("a1b2c3d4")

    with pytest.raises(bench.CheckFailure, match="crc32\\(unique_id \\+ gamename\\)"):
        fac.check_machine_id(board)


def test_check_machine_id_shape_checks_a_board_with_no_chip_id(capsys):
    """A board that never reported a chip id cannot be checked against its
    inputs, but the rest of the check still applies."""
    board = board_reporting("a1b2c3d4", chip_id=None)

    assert fac.check_machine_id(board) == "a1b2c3d4"
    assert "::warning::" in capsys.readouterr().out


def test_check_machine_ids_distinct_passes_when_every_board_differs():
    boards = [
        {"port": "/dev/ttyACM0", "target": "wpc", "machine_id": "aaaaaaaa"},
        {"port": "/dev/ttyACM1", "target": "data_east", "machine_id": "bbbbbbbb"},
    ]

    assert fac.check_machine_ids_distinct(boards) == []


def test_check_machine_ids_distinct_reports_a_collision():
    """Two boards with one identity: Origin would file both machines' games
    under a single machine."""
    boards = [
        {"port": "/dev/ttyACM0", "target": "wpc", "machine_id": "aaaaaaaa"},
        {"port": "/dev/ttyACM1", "target": "data_east", "machine_id": "aaaaaaaa"},
    ]

    failures = fac.check_machine_ids_distinct(boards)

    assert len(failures) == 1
    assert "/dev/ttyACM0 (wpc)" in failures[0]
    assert "/dev/ttyACM1 (data_east)" in failures[0]


def test_check_machine_ids_distinct_ignores_boards_that_never_answered():
    boards = [{"port": "/dev/ttyACM0", "target": "wpc"}, {"port": "/dev/ttyACM1", "target": "sys11"}]

    assert fac.check_machine_ids_distinct(boards) == []


def test_check_machine_id_explains_a_handler_that_raised_on_the_board(monkeypatch):
    """The failure a MicroPython image without binascii.crc32 would produce.

    origin.py imports crc32 at module scope, so this is really any exception
    inside the handler: the USB bridge sends nothing and the client times out.
    Without the board's own console line, the run reports "no response within
    timeout period", which says nothing about which board or why.
    """
    board = board_reporting("deadbeef")

    def raise_timeout(route, payload=None, timeout=None):
        raise TimeoutError("No response received within timeout period.")

    board["client"].send_and_receive = raise_timeout
    monkeypatch.setattr(fac, "_drain_serial", lambda _ser, **kw: "\n      board said: USB REQ: error processing request: no module named 'binascii.crc32'")

    with pytest.raises(bench.CheckFailure) as failure:
        fac.check_machine_id(board)

    assert "never answered" in str(failure.value)
    assert "binascii.crc32" in str(failure.value)
