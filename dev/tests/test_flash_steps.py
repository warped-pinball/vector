"""Tests for dev/flash.py's mpremote step runner.

The flashing itself needs a board; what is testable here is the thing that
broke the bench - an mpremote step with no timeout of its own, blocking
forever on a board that stopped answering. HIL run 59 spent its entire 900s
budget inside one `fs cp` and ended with a half-flashed board that could not
report its chip id, plus an orphaned mpremote still holding the port.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dev"))

import flash  # noqa: E402


def test_run_step_returns_none_when_a_step_hangs(monkeypatch):
    def hang(*_args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="mpremote", timeout=kwargs["timeout"])

    monkeypatch.setattr(flash.subprocess, "run", hang)

    assert flash.run_step(["mpremote", "connect", "/dev/ttyFAKE", "exec", "pass"]) is None


def test_run_step_passes_a_timeout_to_every_step(monkeypatch):
    seen = {}

    def record(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(flash.subprocess, "run", record)
    flash.run_step(["mpremote", "connect", "/dev/ttyFAKE", "exec", "pass"])

    assert seen["timeout"] == flash.STEP_TIMEOUT
    # shell=True would leave the timeout killing the shell and mpremote behind
    # it, still holding the port for the next job to trip over.
    assert "shell" not in seen


def test_step_failed_covers_both_a_hang_and_a_non_zero_exit():
    assert flash.step_failed(None) is True
    assert flash.step_failed(subprocess.CompletedProcess([], 1)) is True
    assert flash.step_failed(subprocess.CompletedProcess([], 0)) is False


def test_the_copy_gets_a_longer_budget_than_an_exec_step():
    """A full filesystem copy is genuinely slow; an exec is not."""
    assert flash.COPY_TIMEOUT > flash.STEP_TIMEOUT
