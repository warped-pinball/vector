#!/usr/bin/env python3
"""Utilities for discovering connected Vector boards and their hardware types."""

import json
import subprocess
from typing import Dict, List


def list_pico_ports() -> List[str]:
    """Return a list of serial ports with connected Pico boards using mpremote."""
    result = subprocess.run(
        ["mpremote", "connect", "list"],
        capture_output=True,
        text=True,
        check=True,
    )
    ports = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            ports.append(line.split()[0])
    return ports


def detect_board_type(port: str) -> str:
    """Detect the board type for a given port by querying systemConfig."""
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
    )
    return result.stdout.strip()


def detect_boards() -> Dict[str, List[str]]:
    """Detect all connected boards and group them by board type."""
    mapping: Dict[str, List[str]] = {}
    for port in list_pico_ports():
        board = detect_board_type(port)
        mapping.setdefault(board, []).append(port)
    return mapping


if __name__ == "__main__":
    print(json.dumps(detect_boards()))
