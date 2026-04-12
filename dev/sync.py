#!/usr/bin/env python3
"""Build firmware and flash boards using Python."""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import List, Optional

from auto_flash import build_and_flash, build_for_hardware
from detect_boards import detect_boards, list_pico_ports

REPL_ATTEMPTS = 10
REPL_DELAY = 1

HARDWARE_TARGETS_DIR = os.path.join(os.path.dirname(__file__), "..", "src")


def list_hardware_targets() -> List[str]:
    """Return available hardware targets discovered from the src/ directory."""
    try:
        entries = sorted(os.listdir(HARDWARE_TARGETS_DIR))
    except OSError:
        return []
    return [e for e in entries if e != "common" and os.path.isdir(os.path.join(HARDWARE_TARGETS_DIR, e))]


def interactive_select(label: str, options: List[str]) -> Optional[str]:
    """Prompt the user to interactively pick from *options*.

    Auto-selects when there is exactly one option.  Returns ``None`` on
    empty lists, invalid input, or if the user cancels.
    """
    if not options:
        return None
    if len(options) == 1:
        print(f"Using {label}: {options[0]}")
        return options[0]
    print(f"Available {label}s:")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    try:
        choice = input(f"Select a {label} [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return None
    try:
        idx = int(choice) - 1 if choice else 0
    except ValueError:
        print("Invalid selection.")
        return None
    if idx < 0 or idx >= len(options):
        print("Invalid selection.")
        return None
    return options[idx]


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
    parser.add_argument("system", nargs="?", default=None, help="Target system or 'auto'")
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

    system = args.system
    if system is None:
        targets = list_hardware_targets()
        if not targets:
            print("No hardware targets found.")
            return 1
        system = interactive_select("target", targets)
        if system is None:
            return 1

    port = args.port
    if port is None:
        ports = list_pico_ports()
        if len(ports) == 1:
            port = ports[0]
            print(f"Using detected port: {port}")
        elif len(ports) > 1:
            port = interactive_select("port", ports)
            if port is None:
                return 1

    rc = flash_single(system, port, args.write_config)
    if rc == 0:
        open_repl(port)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
