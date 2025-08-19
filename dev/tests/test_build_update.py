import os
from pathlib import Path

import pytest

import dev.build_update as build_update


def _make_file(path: Path, content: str = "data"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_resolve_build_dir_defaults_to_subdir():
    expected = os.path.join("build", "sys11")
    assert build_update.resolve_build_dir(None, "sys11") == expected
    assert build_update.resolve_build_dir("custom", "sys11") == "custom"


def test_update_file_uses_only_specified_subdir(tmp_path: Path):
    build_root = tmp_path / "build"
    sys11_dir = build_root / "sys11"
    wpc_dir = build_root / "wpc"
    _make_file(sys11_dir / "sys11.txt", "sys11")
    _make_file(wpc_dir / "wpc.txt", "wpc")

    output_file = tmp_path / "update.json"
    build_update.build_update_file(
        build_dir=str(sys11_dir),
        output_file=str(output_file),
        version="1.0.0",
        private_key_path=None,
        target_hardware="sys11",
    )

    contents = output_file.read_text()
    assert "sys11.txt" in contents
    assert "wpc.txt" not in contents

    with pytest.raises(ValueError):
        build_update.build_update_file(
            build_dir=str(build_root),
            output_file=str(output_file),
            version="1.0.0",
            private_key_path=None,
            target_hardware="sys11",
        )
