"""Tests for the parts of the HIL flash + health check harness that do not
need a board - currently just the job-summary rendering.

Everything else in flash_and_check.py talks to real serial hardware, which is
out of reach here.
"""

from __future__ import annotations

import ast
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
    assert "| `/dev/ttyACM0` | wpc | FAIL |" in rendered
    assert "| `/dev/ttyACM1` | sys11 | ok |" in rendered
    assert "- /dev/ttyACM0 (wpc): could not reset /dev/ttyACM0 before the health check: timed out" in rendered
    assert "board said: nothing" in rendered


def test_write_step_summary_reports_missing_boards(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    fac.write_step_summary([], failures=[], missing=["data_east"])

    rendered = summary.read_text()
    assert "| - | data_east | ABSENT |" in rendered


def test_write_step_summary_is_a_no_op_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    fac.write_step_summary([{"port": "/dev/ttyACM0", "target": "wpc"}], failures=[], missing=[])


def test_classic_ap_button_pin_uses_a_pull_up():
    source = (REPO_ROOT / "src" / "classic" / "main.py").read_text()
    module = ast.parse(source)

    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SW_pin" for target in node.targets):
            call = node.value
            assert isinstance(call, ast.Call)
            assert len(call.args) >= 3
            pull = call.args[2]
            assert isinstance(pull, ast.Attribute)
            assert pull.attr == "PULL_UP"
            assert isinstance(pull.value, ast.Attribute)
            assert pull.value.attr == "Pin"
            assert isinstance(pull.value.value, ast.Name)
            assert pull.value.value.id == "machine"
            break
    else:
        pytest.fail("SW_pin assignment not found in src/classic/main.py")


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
