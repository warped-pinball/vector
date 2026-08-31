"""Tests for the parts of the HIL flash + health check harness that do not
need a board - currently just the job-summary rendering.

Everything else in flash_and_check.py talks to real serial hardware, which is
out of reach here.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

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
