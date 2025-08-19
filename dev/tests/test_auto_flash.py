from unittest.mock import patch

from .. import auto_flash


class Proc:
    def wait(self) -> int:
        return 0


def test_build_once_and_flash_after_build():
    calls = []

    def fake_build(hw: str) -> str:
        calls.append(("build", hw))
        return f"build/{hw}"

    def fake_flash(build_dir: str, port: str) -> Proc:
        calls.append(("flash", build_dir, port))
        return Proc()

    mapping = {"sys11": ["p0", "p1"], "wpc": ["p2"]}

    with patch("dev.auto_flash.build_for_hardware", side_effect=fake_build) as mock_build, patch("dev.auto_flash.flash_port", side_effect=fake_flash) as mock_flash:
        rc = auto_flash.build_and_flash(mapping)

    assert rc == 0
    assert mock_build.call_count == 2
    assert mock_flash.call_count == 3
    build_indices = [i for i, c in enumerate(calls) if c[0] == "build"]
    flash_indices = [i for i, c in enumerate(calls) if c[0] == "flash"]
    assert max(build_indices) < min(flash_indices)
