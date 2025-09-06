#!/usr/bin/env python3
"""Utilities for discovering connected Vector boards and their hardware types."""

import json
import subprocess
from typing import Dict, List

from common import list_mpremote_devs, mpremote_exec


def list_pico_ports(timeout: float = 5.0) -> List[str]:
    """Return a list of serial ports with connected Pico boards using mpremote.

    A timeout is used to prevent hanging if mpremote fails to respond.
    """
    # Delegate to common helper which already handles timeouts and parsing
    return list_mpremote_devs(timeout=timeout)


def detect_board_type(port: str, timeout: float = 5.0) -> str | None:
    """Detect the board type for a given port by querying systemConfig.

    Returns the board name, or ``None`` if detection fails or times out.
    """
    try:
        result = mpremote_exec(
            "import systemConfig;print(systemConfig.vectorSystem)",
            connect=port,
            capture_output=True,
            check=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def detect_boards() -> Dict[str, List[str]]:
    """Detect all connected boards and group them by board type."""
    mapping: Dict[str, List[str]] = {}
    for port in list_pico_ports():
        board = detect_board_type(port)
        if board:
            mapping.setdefault(board, []).append(port)
    return mapping


if __name__ == "__main__":
    print(json.dumps(detect_boards()))
