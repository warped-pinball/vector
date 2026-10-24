#!/usr/bin/env python3
"""Build firmware and flash boards using Python."""

import argparse
import json
import subprocess
import sys
import time
from typing import Optional

from auto_flash import build_and_flash, build_for_hardware
from detect_boards import detect_boards

REPL_ATTEMPTS = 10
REPL_DELAY = 1


def flash_single(system: str, port: Optional[str]) -> int:
    """Build *system* firmware and flash a single board."""
    build_dir = build_for_hardware(system)
    cmd = ["python", "dev/flash.py", build_dir]
    if port:
        cmd.extend(["--port", port])
    return subprocess.call(cmd)


def open_repl(port: Optional[str]) -> None:
    """Attempt to open an mpremote REPL, retrying briefly."""
    cmd = ["mpremote"]
    if port:
        cmd.extend(["connect", port])
    for _ in range(REPL_ATTEMPTS):
        if subprocess.call(cmd) == 0:
            break
        time.sleep(REPL_DELAY)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build and flash Vector firmware")
    parser.add_argument("system", nargs="?", default="dev", help="Target system or 'auto'")
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
        open_repl(args.port)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
