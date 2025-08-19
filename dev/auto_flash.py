#!/usr/bin/env python3
"""Build firmware once per hardware and flash all boards in parallel."""

import json
import subprocess
import sys
from typing import Dict, List


def build_for_hardware(hardware: str) -> str:
    """Build firmware for *hardware* and return the build directory."""
    build_dir = f"build/{hardware}"
    subprocess.check_call(
        [
            "python",
            "dev/build.py",
            "--build-dir",
            build_dir,
            "--source-dir",
            "src",
            "--target_hardware",
            hardware,
        ]
    )
    return build_dir


def flash_port(build_dir: str, port: str) -> subprocess.Popen:
    """Flash the firmware in *build_dir* to *port* asynchronously."""
    return subprocess.Popen(
        [
            "python",
            "dev/flash.py",
            build_dir,
            "--port",
            port,
        ]
    )


def build_and_flash(mapping: Dict[str, List[str]]) -> int:
    """Build once per hardware then flash all ports in parallel.

    Returns the first non-zero flash return code, or ``0`` on success.
    """
    build_dirs: Dict[str, str] = {}
    for hardware in mapping:
        build_dirs[hardware] = build_for_hardware(hardware)

    processes: List[subprocess.Popen] = []
    for hardware, ports in mapping.items():
        build_dir = build_dirs[hardware]
        for port in ports:
            processes.append(flash_port(build_dir, port))

    exit_code = 0
    for proc in processes:
        rc = proc.wait()
        if rc != 0 and exit_code == 0:
            exit_code = rc
    return exit_code


def main(argv: List[str]) -> int:
    mapping = json.loads(argv[1]) if len(argv) > 1 else {}
    return build_and_flash(mapping)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
