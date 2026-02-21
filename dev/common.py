#!/usr/bin/env python3
"""Common utilities for dev scripts: subprocess helpers and mpremote wrappers."""

from __future__ import annotations

import subprocess
import sys
from typing import Iterable, List, Optional, Sequence


def run_python_script(
    script: str,
    args: Optional[Sequence[str]] = None,
    *,
    quiet: bool = False,
    wait: bool = True,
    check: bool = True,
    **popen_kwargs,
):
    """Run a Python script using the current interpreter (sys.executable).

    Returns a CompletedProcess when wait=True, else a Popen process.
    """
    cmd: List[str] = [sys.executable, script]
    if args:
        cmd.extend(args)
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.STDOUT if quiet else None
    if wait:
        return subprocess.run(cmd, check=check, stdout=stdout, stderr=stderr, **popen_kwargs)
    else:
        return subprocess.Popen(cmd, stdout=stdout, stderr=stderr, **popen_kwargs)


def _mpremote_base_args(connect: Optional[str]) -> List[str]:
    # Use the current interpreter to run mpremote as a module for cross-platform reliability
    args: List[str] = [sys.executable, "-m", "mpremote"]
    if connect:
        args.extend(["connect", connect])
    return args


def mpremote_run(
    *mp_args: str,
    connect: Optional[str] = None,
    quiet: bool = False,
    check: bool = False,
    text: bool = True,
    capture_output: bool = False,
    **run_kwargs,
) -> subprocess.CompletedProcess:
    """Run an mpremote command and return CompletedProcess.

    Example: mpremote_run("fs", "cp", "-r", ".", ":", connect=port)
    """
    cmd = _mpremote_base_args(connect) + list(mp_args)
    if capture_output:
        return subprocess.run(cmd, check=check, text=text, capture_output=True, **run_kwargs)
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.STDOUT if quiet else None
    return subprocess.run(cmd, check=check, text=text, stdout=stdout, stderr=stderr, **run_kwargs)


def mpremote_exec(
    code: str,
    *,
    connect: Optional[str] = None,
    no_follow: bool = False,
    quiet: bool = False,
    check: bool = False,
    capture_output: bool = False,
    **run_kwargs,
) -> subprocess.CompletedProcess:
    """Execute Python code on the device via mpremote exec."""
    args: List[str] = ["exec"]
    if no_follow:
        args.append("--no-follow")
    args.append(code)
    return mpremote_run(*args, connect=connect, quiet=quiet, check=check, capture_output=capture_output, **run_kwargs)


def list_mpremote_devs(timeout: float = 5.0) -> List[str]:
    """Return a list of serial ports reported by `mpremote devs`."""
    try:
        result = mpremote_run("devs", capture_output=True, check=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []

    ports: List[str] = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            ports.append(line.split()[0])
    return ports


def autodetect_pico_port(timeout: float = 5.0) -> Optional[str]:
    """Return the first available Pico port via mpremote, or None."""
    ports = list_mpremote_devs(timeout=timeout)
    return ports[0] if ports else None


def open_repl(connect: Optional[str] = None, attempts: int = 10, delay: float = 1.0) -> None:
    """Try to open an mpremote REPL, retrying a few times."""
    cmd = _mpremote_base_args(connect)
    for _ in range(attempts):
        if subprocess.call(cmd) == 0:
            break
        try:
            import time as _time
            _time.sleep(delay)
        except Exception:
            pass
