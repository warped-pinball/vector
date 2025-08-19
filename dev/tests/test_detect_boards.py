from unittest.mock import patch

from .. import detect_boards


class Result:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.returncode = 0


@patch("dev.detect_boards.subprocess.run")
def test_detect_boards(mock_run):
    calls = []

    def side_effect(cmd, **kwargs):
        calls.append((cmd, kwargs.get("timeout")))
        if cmd == ["mpremote", "devs"]:
            return Result("/dev/ttyACM0\n/dev/ttyACM1\n")
        if cmd[:3] == ["mpremote", "connect", "/dev/ttyACM0"]:
            return Result("sys11\n")
        if cmd[:3] == ["mpremote", "connect", "/dev/ttyACM1"]:
            return Result("wpc\n")
        return Result("")

    mock_run.side_effect = side_effect

    mapping = detect_boards.detect_boards()
    assert mapping == {"sys11": ["/dev/ttyACM0"], "wpc": ["/dev/ttyACM1"]}
    # Expect one call for listing and one per port
    assert mock_run.call_count == 3
    # Each subprocess call should include a timeout
    assert all(timeout == 5.0 for _, timeout in calls)
