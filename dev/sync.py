#!/usr/bin/env python3
"""Build firmware and flash boards using Python."""

import argparse
import json
import subprocess
import sys
import time
from typing import Optional

from auto_flash import build_and_flash, build_for_hardware
from detect_boards import detect_boards, list_pico_ports

REPL_ATTEMPTS = 10
REPL_DELAY = 1


def flash_single(system: str, port: Optional[str], write_config: Optional[str]) -> int:
    """Build *system* firmware and flash a single board."""
    build_dir = build_for_hardware(system)
    cmd = ["python", "dev/flash.py", build_dir]
    if port:
        cmd.extend(["--port", port])
    if write_config is not None:
        if write_config == "__DEFAULT__":
            cmd.append("--write-config")
        else:
            cmd.extend(["--write-config", write_config])
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
        return build_and_flash(mapping, write_config=args.write_config)

    port = args.port
    if port is None:
        ports = list_pico_ports()
        if not ports:
            print("No boards detected.")
            return 1
        if len(ports) == 1:
            port = ports[0]
            print(f"Using detected port: {port}")
        else:
            print("Available ports:")
            for i, p in enumerate(ports, 1):
                print(f"  {i}) {p}")
            try:
                choice = input("Select a port [1]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                return 1
            try:
                idx = int(choice) - 1 if choice else 0
            except ValueError:
                print("Invalid selection.")
                return 1
            if idx < 0 or idx >= len(ports):
                print("Invalid selection.")
                return 1
            port = ports[idx]

    rc = flash_single(args.system, port, args.write_config)
    if rc == 0:
        open_repl(port)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
