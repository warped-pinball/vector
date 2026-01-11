#!/usr/bin/env python3
"""Build firmware and flash boards using Python."""

import argparse
import json
import os
import sys
import time
from typing import Optional

from auto_flash import build_and_flash, build_for_hardware
from detect_boards import detect_board_type, detect_boards

from common import open_repl, run_python_script

REPL_ATTEMPTS = 10
REPL_DELAY = 1


def flash_single(system: str, port: Optional[str], write_config: Optional[str]) -> int:
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
    if write_config is not None:
        if write_config == "__DEFAULT__":
            args.append("--write-config")
        else:
            args.extend(["--write-config", write_config])
    return run_python_script("dev/flash.py", args, wait=True)


def open_repl_wrapper(port: Optional[str]) -> None:
    """Attempt to open an mpremote REPL, retrying briefly."""
    print("Opening REPL...")
    open_repl(connect=port, attempts=REPL_ATTEMPTS, delay=REPL_DELAY)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build and flash Vector firmware")
    parser.add_argument("system", nargs="?", default="auto", help="Target system or 'auto'")
    parser.add_argument("port", nargs="?", help="Serial port for manual flashing")
    parser.add_argument(
        "--write-config",
        nargs="?",
        const="__DEFAULT__",
        metavar="PATH",
        help=("Pass through to flash.py: wipe config on Pico and write configuration from PATH. " "If provided with no PATH, uses the default config for the selected build_dir."),
    )
    args = parser.parse_args(argv[1:])

    if args.system == "auto":
        mapping = detect_boards()
        if not mapping:
            print("No boards detected. Aborting.")
            return 1
        print("Boards detected:", json.dumps(mapping))
        rc = build_and_flash(mapping, write_config=args.write_config)
    else:
        rc = flash_single(args.system, args.port, args.write_config)

    if rc != 0:
        print("Flashing failed: ", rc)
        return rc

    print("Flash complete.")

    # delay briefly to allow the board to reset
    time.sleep(0.5)

    open_repl_wrapper(args.port)

    return


if __name__ == "__main__":
    sys.exit(main(sys.argv))
