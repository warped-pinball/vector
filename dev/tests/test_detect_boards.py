import pathlib
from unittest.mock import patch

import pytest

import sys
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))
import dev.detect_boards as detect_boards


class Result:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.returncode = 0


@patch("dev.detect_boards.subprocess.run")
def test_detect_boards(mock_run):
    def side_effect(cmd, capture_output, text, check):
        if cmd == ["mpremote", "connect", "list"]:
            return Result("/dev/ttyACM0\n/dev/ttyACM1\n")
        if cmd[:3] == ["mpremote", "connect", "/dev/ttyACM0"]:
            return Result("sys11\n")
        if cmd[:3] == ["mpremote", "connect", "/dev/ttyACM1"]:
            return Result("wpc\n")
        return Result("")

    mock_run.side_effect = side_effect

    mapping = detect_boards.detect_boards()
    assert mapping == {"sys11": ["/dev/ttyACM0"], "wpc": ["/dev/ttyACM1"]}
    assert mock_run.call_count == 3
