import json
from pathlib import Path

from dev import build_update
from dev.build_update import build_update_file, maybe_compress_file, resolve_build_dir


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
    (sys11_dir / "update.py").write_text("supports_compression = True\n", encoding="utf-8")

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


def test_build_update_adds_compression_enablement_step(tmp_path):
    build_dir = tmp_path / "build" / "sys11"
    build_dir.mkdir(parents=True)
    (build_dir / "update.py").write_text("supports_compression = True\n", encoding="utf-8")
    (build_dir / "large.txt").write_text("abc123\n" * 300, encoding="utf-8")

    output = tmp_path / "update.json"
    build_update_file(str(build_dir), str(output), "0.0.0", None, "sys11")

    lines = output.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("enable_compression.py") for line in lines)

    update_index = next(i for i, line in enumerate(lines) if line.startswith("update.py"))
    enablement_index = next(i for i, line in enumerate(lines) if line.startswith("enable_compression.py"))
    remove_extra_index = next(i for i, line in enumerate(lines) if line.startswith("remove_extra_files.py"))
    assert update_index < enablement_index < remove_extra_index

    large_line = next(line for line in lines if line.startswith("large.txt"))
    metadata_start = large_line.index("{")
    metadata_end = large_line.index("}") + 1
    metadata = json.loads(large_line[metadata_start:metadata_end])
    assert metadata.get("wbits") is None


def test_maybe_compress_file_prefers_smallest_wbits_for_same_size(monkeypatch):
    class _Compressor:
        def __init__(self, payload):
            self.payload = payload

        def compress(self, _):
            return self.payload

        def flush(self):
            return b""

    outputs = {5: b"x" * 10, 6: b"x" * 10, 7: b"x" * 8}

    def fake_compressobj(level, wbits):
        return _Compressor(outputs[wbits])

    monkeypatch.setattr(build_update.zlib, "compressobj", fake_compressobj)

    compressed, wbits = maybe_compress_file("foo.txt", b"y" * 30, execute=False)
    assert compressed == b"x" * 8
    assert wbits == 7


def test_maybe_compress_file_keeps_smaller_wbits_when_size_ties(monkeypatch):
    class _Compressor:
        def __init__(self, payload):
            self.payload = payload

        def compress(self, _):
            return self.payload

        def flush(self):
            return b""

    outputs = {5: b"x" * 8, 6: b"x" * 8, 7: b"x" * 8}

    def fake_compressobj(level, wbits):
        return _Compressor(outputs[wbits])

    monkeypatch.setattr(build_update.zlib, "compressobj", fake_compressobj)

    _, wbits = maybe_compress_file("foo.txt", b"y" * 30, execute=False)
    assert wbits == 5
