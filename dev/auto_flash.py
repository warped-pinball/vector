#!/usr/bin/env python3
"""Build firmware once per hardware and flash all boards in parallel."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List


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


def flash_port(build_dir: str, port: str, quiet: bool = False) -> subprocess.Popen:
    """Flash the firmware in *build_dir* to *port* asynchronously."""
    return subprocess.Popen(
        [
            "python",
            "dev/flash.py",
            build_dir,
            "--port",
            port,
        ],
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
    )


def build_and_flash(mapping: Dict[str, List[str]]) -> int:
    """Build once per hardware then flash all ports in parallel.

    Returns the first non-zero flash return code, or ``0`` on success.
    """
    total_ports = sum(len(ports) for ports in mapping.values())
    quiet = total_ports > 1

    build_dirs: Dict[str, str] = {}
    for hardware in mapping:
        build_dirs[hardware] = build_for_hardware(hardware, quiet)

    processes: List[subprocess.Popen] = []
    for hardware, ports in mapping.items():
        build_dir = build_dirs[hardware]
        for port in ports:
            processes.append(flash_port(build_dir, port, quiet))

    if not processes:
        return 0

    if quiet:
        total = len(processes)
        completed = 0
        exit_code = 0
        with ThreadPoolExecutor() as ex:
            future_map = {ex.submit(p.wait): p for p in processes}
            for future in as_completed(future_map):
                rc = future.result()
                completed += 1
                print(f"{completed} of {total} boards complete", flush=True)
                if rc != 0 and exit_code == 0:
                    exit_code = rc
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
