#!/usr/bin/env python3
"""Utilities for discovering connected Vector boards and their hardware types."""

import json
import subprocess
from typing import Dict, List


def list_pico_ports(timeout: float = 5.0) -> List[str]:
    """Return a list of serial ports with connected Pico boards using mpremote.

    A timeout is used to prevent hanging if mpremote fails to respond.
    """
    try:
        result = subprocess.run(
            ["mpremote", "devs"],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    ports: List[str] = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            ports.append(line.split()[0])
    return ports


def detect_board_type(port: str, timeout: float = 5.0) -> str | None:
    """Detect the board type for a given port by querying systemConfig.

    Returns the board name, or ``None`` if detection fails or times out.
    """
    try:
        result = subprocess.run(
            [
                "mpremote",
                "connect",
                port,
                "exec",
                "import systemConfig;print(systemConfig.vectorSystem)",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def detect_boards() -> Dict[str, List[str]]:
    """Detect all connected boards and group them by board type."""
    mapping: Dict[str, List[str]] = {}
    print("Automatically detecting boards...", end="", flush=True)
    for port in list_pico_ports():
        board = detect_board_type(port)
        if board:
            print(".", end="", flush=True)
            mapping.setdefault(board, []).append(port)
    print("OK!")
    return mapping


if __name__ == "__main__":
    print(json.dumps(detect_boards()))
