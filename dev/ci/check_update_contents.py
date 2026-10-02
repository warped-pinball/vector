"""Check that a built update file carries every file its target's source says it should.

`dev/build.py` layers `src/<target>/` over `src/common/` and `dev/build_update.py`
packs whatever ends up in the build directory. Neither step ever asserts that the
two agree, so a build that quietly drops a file still produces a well formed,
correctly signed update file - and the board is where it fails, on the first
import that is not there.

The source tree is the source of truth: a target's update must contain the
`src/common/` files plus the `src/<target>/` files layered on top, each under the
name the build gives it (`.py` compiled to `.mpy`, `config/*.json` folded into
one `config/all.jsonl.z`, `web/` gzipped), and the three scripts the update
builder generates. Anything short of that is a broken image; anything extra is a
file no source tree accounts for.

Run after `build-updates` in the release workflow:

    python -m dev.ci.check_update_contents --targets dev/ci/targets.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Set

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "src"
TARGETS_JSON = REPO_ROOT / "dev" / "ci" / "targets.json"
COMMON_DIR_NAME = "common"

# Scripts `dev/build_update.py` writes into every update file. They have no
# source file behind them, so the source tree cannot account for them.
GENERATED_ENTRIES = frozenset({"confirm_compatibility.py", "remove_extra_files.py", "remove_update_file.py"})

# A tiny build ships the updater alone, so the whole source tree is out of scope
# for it - by design, not by accident.
TINY_ENTRIES = frozenset({"confirm_compatibility.py", "remove_update_file.py", "update.mpy"})

# One line per file: the path, then the metadata dict, then the payload.
ENTRY_PATTERN = re.compile(r'^(?P<path>.*?)\{"checksum":')


@dataclass
class UpdateReport:
    """What one target's update file has, against what its source says it should."""

    target: str
    output: str
    missing: Set[str] = field(default_factory=set)
    unexpected: Set[str] = field(default_factory=set)
    checked: int = 0
    built: bool = True

    @property
    def ok(self) -> bool:
        return self.built and not self.missing and not self.unexpected

    def describe(self) -> str:
        if not self.built:
            return f"{self.target}: {self.output} was never built"
        if self.ok:
            return f"{self.target}: {self.checked} file(s), matches src/{self.target} + src/common"
        lines = [f"{self.target}: {self.output} does not match src/{self.target} + src/common"]
        for path in sorted(self.missing):
            lines.append(f"    missing from the update: {path}")
        for path in sorted(self.unexpected):
            lines.append(f"    in the update with no source: {path}")
        return "\n".join(lines)


def load_targets(targets_json: Path = TARGETS_JSON) -> List[Dict[str, object]]:
    return json.loads(Path(targets_json).read_text())


def layered_sources(target: str, source_dir: Path = SOURCE_DIR) -> Dict[str, Path]:
    """{relative path: file} for the tree `dev/build.py` assembles for *target*.

    Common first, then the target's own files over it, so a target file
    shadowing a common one shadows it here too - one entry, the target's.
    """
    layered: Dict[str, Path] = {}
    for layer in (Path(source_dir) / COMMON_DIR_NAME, Path(source_dir) / target):
        if not layer.is_dir():
            continue
        for path in sorted(layer.rglob("*")):
            if path.is_file():
                layered[path.relative_to(layer).as_posix()] = path
    return layered


def built_name(relative_path: str) -> Set[str]:
    """The names `dev/build.py` gives one source file in the build directory.

    Mirrors the build steps in order: game configs are folded into a single
    compressed bundle, web assets are gzipped, and `.py` is compiled to `.mpy` -
    except the viper sources, which must stay as source, and boot/main, which
    are compiled under an `m` prefix behind a stub that imports them.
    """
    if relative_path.startswith("config/") and relative_path.endswith(".json"):
        return {"config/all.jsonl.z"}

    if relative_path.startswith("web/"):
        # The gzip step skips anything already compressed.
        return {relative_path if relative_path.endswith(".gz") else relative_path + ".gz"}

    if not relative_path.endswith(".py"):
        return {relative_path}

    if relative_path == "boot.py":
        return {"boot.py", "mboot.mpy"}
    if relative_path == "main.py":
        return {"main.py", "mmain.mpy"}

    stem = relative_path[: -len(".py")]
    if stem.rsplit("/", 1)[-1].lower().endswith("viper"):
        return {relative_path}
    return {stem + ".mpy"}


def expected_entries(target: str, source_dir: Path = SOURCE_DIR, tiny: bool = False) -> Set[str]:
    """Every path *target*'s update file should list."""
    if tiny:
        return set(TINY_ENTRIES)

    entries: Set[str] = set(GENERATED_ENTRIES)
    for relative_path in layered_sources(target, source_dir):
        entries |= built_name(relative_path)
    return entries


def update_entries(update_file: Path) -> Set[str]:
    """Every path listed in a built update file.

    The first line is metadata and the last is the signature; every line
    between them starts with a path followed by that file's metadata dict.
    """
    entries: Set[str] = set()
    for index, line in enumerate(Path(update_file).read_text(encoding="utf-8").splitlines()):
        if index == 0 or not line:
            continue
        match = ENTRY_PATTERN.match(line)
        if match:
            entries.add(match.group("path"))
    return entries


def check_target(target: Dict[str, object], source_dir: Path = SOURCE_DIR, build_root: Path = REPO_ROOT) -> UpdateReport:
    hardware = str(target.get("hardware_id") or target["id"])
    output = str(target["output"])
    expected = expected_entries(hardware, source_dir, tiny=bool(target.get("tiny")))

    update_file = Path(build_root) / output
    if not update_file.is_file():
        # A target listed for release with no update file behind it is the same
        # failure seen from the other end: the release is short a firmware image.
        return UpdateReport(target=str(target["id"]), output=output, missing=expected, built=False)

    found = update_entries(update_file)
    return UpdateReport(
        target=str(target["id"]),
        output=output,
        missing=expected - found,
        unexpected=found - expected,
        checked=len(found),
    )


def check_all(targets: Iterable[Dict[str, object]], source_dir: Path = SOURCE_DIR, build_root: Path = REPO_ROOT) -> List[UpdateReport]:
    return [check_target(target, source_dir, build_root) for target in targets]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=TARGETS_JSON)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--build-root", type=Path, default=REPO_ROOT, help="Directory the update files were written to.")
    args = parser.parse_args()

    reports = check_all(load_targets(args.targets), args.source_dir, args.build_root)
    for report in reports:
        print(report.describe())

    if any(not report.ok for report in reports):
        print("")
        print("An update file that does not match its source tree installs a firmware image")
        print("the board cannot boot. Fix the build, or the target's sources, before releasing.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
