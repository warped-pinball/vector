from pathlib import Path

from dev.build_update import build_update_file, resolve_build_dir


def test_resolve_build_dir_accepts_root(tmp_path):
    build_root = tmp_path / "build"
    (build_root / "sys11").mkdir(parents=True)

    resolved = resolve_build_dir(str(build_root), "sys11")
    assert Path(resolved) == build_root / "sys11"


def test_build_update_uses_resolved_dir(tmp_path):
    build_root = tmp_path / "build"
    sys11_dir = build_root / "sys11"
    sys11_dir.mkdir(parents=True)
    (sys11_dir / "foo.txt").write_text("hi", encoding="utf-8")

    resolved = resolve_build_dir(str(build_root), "sys11")
    output = tmp_path / "update.json"
    build_update_file(
        build_dir=resolved,
        output_file=str(output),
        version="0.0.0",
        private_key_path=None,
        target_hardware="sys11",
    )

    assert "foo.txt" in output.read_text()


def test_remove_extra_files_keeps_preserved_files(tmp_path):
    import base64

    from dev.build_update import build_remove_extra_files_code

    (tmp_path / "main.py").write_text("", encoding="utf-8")

    line = build_remove_extra_files_code(str(tmp_path))
    code = base64.b64decode(line.split("}", 1)[1]).decode("utf-8")

    assert "'/main.py'" in code
    assert "'/webhook.json'" in code
