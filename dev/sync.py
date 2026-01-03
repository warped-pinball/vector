#!/usr/bin/env python3
"""Build firmware and flash boards using Python."""

import argparse
import os
import json
import subprocess
import sys
import time
from typing import Optional

from auto_flash import build_and_flash, build_for_hardware
from detect_boards import detect_boards, detect_board_type
from common import run_python_script, open_repl

REPL_ATTEMPTS = 10
REPL_DELAY = 1


def flash_single(system: str, port: Optional[str]) -> int:
    """Build *system* firmware and flash a single board."""
    hardware = system
    # If system is 'dev' or not a valid hardware folder under src, try to auto-detect
    if hardware == "dev" or not os.path.isdir(os.path.join("src", hardware)):
        detected: Optional[str] = None
        if port:
            detected = detect_board_type(port)  # type: ignore[assignment]
        if not detected:
            mapping = detect_boards()
            if len(mapping) == 1:
                detected = next(iter(mapping.keys()))
        if detected and os.path.isdir(os.path.join("src", detected)):
            hardware = detected
    build_dir = build_for_hardware(hardware)
    args = [build_dir]
    if port:
        args.extend(["--port", port])
    result = run_python_script("dev/flash.py", args, wait=True)
    return result.returncode


def open_repl_wrapper(port: Optional[str]) -> None:
    """Attempt to open an mpremote REPL, retrying briefly."""
    open_repl(connect=port, attempts=REPL_ATTEMPTS, delay=REPL_DELAY)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build and flash Vector firmware")
    parser.add_argument("system", nargs="?", default="auto", help="Target system or 'auto'")
    parser.add_argument("port", nargs="?", help="Serial port for manual flashing")
    args = parser.parse_args(argv[1:])

    if args.system == "auto":
        mapping = detect_boards()
        if not mapping:
            print("No boards detected. Aborting.")
            return 1
        print("Boards detected:", json.dumps(mapping))
        return build_and_flash(mapping)

    rc = flash_single(args.system, args.port)
    if rc == 0:
        open_repl_wrapper(args.port)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
