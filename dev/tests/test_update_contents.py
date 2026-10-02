"""The update file a release publishes must match the source tree it was built from.

Release 1.11.27 shipped `update_classic.json` with no `DataMapper.mpy` and no
game configs in it, and every check in CI passed: the file was well formed and
correctly signed, it was simply built from a `src/classic/` that held nothing but
`systemConfig.py`. A Classic board installs that update and cannot boot. Nothing
compared what was packed against what the source tree says belongs there, so
these tests make that comparison the thing that fails.
"""

from pathlib import Path

import pytest

from dev.ci.check_update_contents import (
    built_name,
    check_target,
    expected_entries,
    layered_sources,
    update_entries,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_update(path: Path, entries):
    """A stand-in for a built update file: metadata, a line per file, signature."""
    lines = ['{"update_file_format":"1.0","version":"0.0.0"}']
    lines += [f'{entry}{{"checksum":"ABCD","bytes":2,"log":"Uploading {entry}"}}aGk=' for entry in entries]
    lines.append('{"sha256":"0","signature":"NOT_ENCRYPTED"}')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_source_tree(root: Path, common=(), target=(), target_name="classic"):
    for layer, files in ((root / "common", common), (root / target_name, target)):
        for relative in files:
            path = layer / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x = 1\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# what the build does to each source file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        ("DataMapper.py", {"DataMapper.mpy"}),
        ("phew/server.py", {"phew/server.mpy"}),
        ("LICENSE.txt", {"LICENSE.txt"}),
        # boot and main are compiled under an m-prefix behind a stub that imports them
        ("boot.py", {"boot.py", "mboot.mpy"}),
        ("main.py", {"main.py", "mmain.mpy"}),
        # viper sources must stay source - mpy-cross is skipped for them
        ("ScoreTrackFilter_viper.py", {"ScoreTrackFilter_viper.py"}),
        # every game config is folded into one compressed bundle
        ("config/Generic_.json", {"config/all.jsonl.z"}),
        ("config/Supersonic_1.json", {"config/all.jsonl.z"}),
        # web assets are gzipped, and anything already compressed is left alone
        ("web/index.html", {"web/index.html.gz"}),
        ("web/svg/logo.svg", {"web/svg/logo.svg.gz"}),
        ("web/js/main.js.gz", {"web/js/main.js.gz"}),
    ],
)
def test_built_name_follows_the_build_steps(source, expected):
    assert built_name(source) == expected


# ---------------------------------------------------------------------------
# what the source tree says a target should ship
# ---------------------------------------------------------------------------


def test_a_target_file_shadows_the_common_one(tmp_path):
    root = make_source_tree(tmp_path, common=["ScoreTrack.py", "backend.py"], target=["ScoreTrack.py"])

    sources = layered_sources("classic", root)

    assert sources["ScoreTrack.py"] == root / "classic" / "ScoreTrack.py"
    assert sources["backend.py"] == root / "common" / "backend.py"


def test_expected_entries_cover_both_layers_and_the_generated_scripts(tmp_path):
    root = make_source_tree(tmp_path, common=["backend.py"], target=["DataMapper.py", "config/Generic_.json"])

    entries = expected_entries("classic", root)

    assert {"backend.mpy", "DataMapper.mpy", "config/all.jsonl.z"} <= entries
    assert {"confirm_compatibility.py", "remove_extra_files.py", "remove_update_file.py"} <= entries


def test_a_tiny_build_ships_the_updater_alone(tmp_path):
    root = make_source_tree(tmp_path, common=["backend.py"], target=["DataMapper.py"], target_name="sys11")

    assert expected_entries("sys11", root, tiny=True) == {"update.mpy", "confirm_compatibility.py", "remove_update_file.py"}


# ---------------------------------------------------------------------------
# the release-blocking comparison
# ---------------------------------------------------------------------------


def test_a_complete_update_passes(tmp_path):
    root = make_source_tree(tmp_path / "src", common=["backend.py"], target=["DataMapper.py", "config/Generic_.json"])
    build = tmp_path / "build"
    build.mkdir()
    write_update(
        build / "update_classic.json",
        ["confirm_compatibility.py", "remove_extra_files.py", "backend.mpy", "DataMapper.mpy", "config/all.jsonl.z", "remove_update_file.py"],
    )

    report = check_target({"id": "classic", "output": "update_classic.json"}, root, build)

    assert report.ok, report.describe()


def test_the_classic_release_that_shipped_without_datamapper_is_caught(tmp_path):
    """The 1.11.27 failure, reduced: sources on disk, no DataMapper in the update."""
    root = make_source_tree(tmp_path / "src", common=["backend.py"], target=["DataMapper.py", "config/Generic_.json"])
    build = tmp_path / "build"
    build.mkdir()
    write_update(build / "update_classic.json", ["confirm_compatibility.py", "remove_extra_files.py", "backend.mpy", "remove_update_file.py"])

    report = check_target({"id": "classic", "output": "update_classic.json"}, root, build)

    assert not report.ok
    assert report.missing == {"DataMapper.mpy", "config/all.jsonl.z"}
    assert "DataMapper.mpy" in report.describe()


def test_a_file_with_no_source_behind_it_is_caught(tmp_path):
    """The other direction: a stale file left in the build directory."""
    root = make_source_tree(tmp_path / "src", common=["backend.py"])
    build = tmp_path / "build"
    build.mkdir()
    write_update(build / "update_classic.json", ["confirm_compatibility.py", "remove_extra_files.py", "backend.mpy", "leftover.mpy", "remove_update_file.py"])

    report = check_target({"id": "classic", "output": "update_classic.json"}, root, build)

    assert not report.ok
    assert report.unexpected == {"leftover.mpy"}


def test_a_target_whose_update_was_never_built_is_caught(tmp_path):
    root = make_source_tree(tmp_path / "src", common=["backend.py"])
    build = tmp_path / "build"
    build.mkdir()

    report = check_target({"id": "classic", "output": "update_classic.json"}, root, build)

    assert not report.ok
    assert "never built" in report.describe()


def test_the_hardware_id_picks_the_source_tree(tmp_path):
    """sys11_tiny is the sys11 board built twice, so it reads src/sys11."""
    root = make_source_tree(tmp_path / "src", common=["backend.py"], target=["DataMapper.py"], target_name="sys11")
    build = tmp_path / "build"
    build.mkdir()
    write_update(build / "update_sys11_tiny.json", ["confirm_compatibility.py", "update.mpy", "remove_update_file.py"])

    report = check_target(
        {"id": "sys11_tiny", "hardware_id": "sys11", "output": "update_sys11_tiny.json", "tiny": True},
        root,
        build,
    )

    assert report.ok, report.describe()


# ---------------------------------------------------------------------------
# against the real tree
# ---------------------------------------------------------------------------


def test_classic_sources_are_expected_in_the_classic_update():
    """Guards the specific regression: these are the files 1.11.27 shipped without."""
    entries = expected_entries("classic")

    assert "DataMapper.mpy" in entries
    assert "config/all.jsonl.z" in entries


def test_update_entries_reads_paths_out_of_a_real_update_line(tmp_path):
    update_file = tmp_path / "update.json"
    write_update(update_file, ["DataMapper.mpy", "web/index.html.gz", "config/all.jsonl.z"])

    assert update_entries(update_file) == {"DataMapper.mpy", "web/index.html.gz", "config/all.jsonl.z"}
