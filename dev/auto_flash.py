#!/usr/bin/env python3
"""Build firmware once per hardware and flash all boards in parallel."""

import json
import subprocess
import sys
import time
from itertools import cycle
from typing import Dict, List, Optional


def build_for_hardware(hardware: str, quiet: bool = False) -> str:
    """Build firmware for *hardware* and return the build directory."""
    build_dir = f"build/{hardware}"
    subprocess.run(
        [
            "python",
            "dev/build.py",
            "--build-dir",
            build_dir,
            "--source-dir",
            "src",
            "--target_hardware",
            hardware,
        ],
        check=True,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
    )
    return build_dir


def flash_port(build_dir: str, port: str, quiet: bool = False, flash_args: Optional[List[str]] = None) -> subprocess.Popen:
    """Flash the firmware in *build_dir* to *port* asynchronously."""
    extra = flash_args or []
    return subprocess.Popen(
        [
            "python",
            "dev/flash.py",
            build_dir,
            "--port",
            port,
        ]
        + extra,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
    )


def build_and_flash(mapping: Dict[str, List[str]], write_config: Optional[str] = None) -> int:
    """Build once per hardware then flash all ports in parallel.

    Returns the first non-zero flash return code, or ``0`` on success.
    """
    total_ports = sum(len(ports) for ports in mapping.values())
    quiet = total_ports > 1

    build_dirs: Dict[str, str] = {}
    for hardware in mapping:
        build_dirs[hardware] = build_for_hardware(hardware, quiet)

    flash_args: List[str] = []
    if write_config is not None:
        if write_config == "__DEFAULT__":
            flash_args = ["--write-config"]
        else:
            flash_args = ["--write-config", write_config]

    processes: List[subprocess.Popen] = []
    for hardware, ports in mapping.items():
        build_dir = build_dirs[hardware]
        for port in ports:
            processes.append(flash_port(build_dir, port, quiet, flash_args=flash_args))

    if not processes:
        return 0

    if quiet:
        total = len(processes)
        completed = 0
        exit_code = 0
        remaining: List[subprocess.Popen] = processes[:]
        dots = cycle(["", ".", "..", "...", "..", "."])
        # initial progress line
        print(f"0 of {total} boards complete", end="", flush=True)
        while remaining:
            new_remaining: List[subprocess.Popen] = []
            for proc in remaining:
                rc = proc.poll()
                if rc is None:
                    new_remaining.append(proc)
                    continue
                completed += 1
                print(
                    f"\r{completed} of {total} boards complete   ",
                    end="",
                    flush=True,
                )
                if rc != 0 and exit_code == 0:
                    exit_code = rc
            if new_remaining:
                print(
                    f"\r{completed} of {total} boards complete{next(dots)}   ",
                    end="",
                    flush=True,
                )
                time.sleep(0.2)
            remaining = new_remaining
        print()  # finish line
        return exit_code

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
