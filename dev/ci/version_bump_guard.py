"""Validate required version bumps for pull requests."""
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

VECTOR_VERSION_PATTERN = r'VectorVersion\s*=\s*"([^"]+)"'
SYSTEM_VERSION_PATTERN = r'SystemVersion\s*=\s*"([^"]+)"'


@dataclass(frozen=True)
class VersionRule:
    name: str
    scope_prefixes: tuple[str, ...]
    version_file: str
    version_pattern: str


RULES: tuple[VersionRule, ...] = (
    VersionRule(
        name="common shared-state version",
        scope_prefixes=("src/common/",),
        version_file="src/common/SharedState.py",
        version_pattern=VECTOR_VERSION_PATTERN,
    ),
    VersionRule(
        name="EM system config version",
        scope_prefixes=("src/em/",),
        version_file="src/em/systemConfig.py",
        version_pattern=SYSTEM_VERSION_PATTERN,
    ),
    VersionRule(
        name="System11 system config version",
        scope_prefixes=("src/sys11/",),
        version_file="src/sys11/systemConfig.py",
        version_pattern=SYSTEM_VERSION_PATTERN,
    ),
    VersionRule(
        name="WPC system config version",
        scope_prefixes=("src/wpc/",),
        version_file="src/wpc/systemConfig.py",
        version_pattern=SYSTEM_VERSION_PATTERN,
    ),
    VersionRule(
        name="Data East system config version",
        scope_prefixes=("src/data_east/",),
        version_file="src/data_east/systemConfig.py",
        version_pattern=SYSTEM_VERSION_PATTERN,
    ),
    VersionRule(
        name="WhiteStar system config version",
        scope_prefixes=("src/whitestar/",),
        version_file="src/whitestar/systemConfig.py",
        version_pattern=SYSTEM_VERSION_PATTERN,
    ),
)


def _run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def changed_files(base_ref: str, head_ref: str) -> list[str]:
    output = _run_git("diff", "--name-only", base_ref, head_ref)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _extract_version(text: str, pattern: str, file_path: str) -> str:
    match = re.search(pattern, text)
    if not match:
        raise RuntimeError(f"Unable to find version in {file_path}")
    return match.group(1)


def version_at_ref(ref: str, file_path: str, pattern: str) -> str:
    content = _run_git("show", f"{ref}:{file_path}")
    return _extract_version(content, pattern, file_path)


def touches_scope(paths: Iterable[str], prefixes: tuple[str, ...]) -> bool:
    for raw_path in paths:
        path = str(PurePosixPath(raw_path))
        for prefix in prefixes:
            if path.startswith(prefix):
                return True
    return False


def evaluate_rules(changed: Iterable[str], rule_results: dict[str, bool]) -> list[str]:
    failures: list[str] = []
    for rule in RULES:
        if not touches_scope(changed, rule.scope_prefixes):
            continue
        if not rule_results.get(rule.name, False):
            prefixes = ", ".join(rule.scope_prefixes)
            failures.append(
                f"Changes in [{prefixes}] require updating version in {rule.version_file}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate required version bumps.")
    parser.add_argument("--base", required=True, help="Base git ref/sha")
    parser.add_argument("--head", required=True, help="Head git ref/sha")
    args = parser.parse_args()

    changed = changed_files(args.base, args.head)
    rule_results: dict[str, bool] = {}
    for rule in RULES:
        try:
            base_version = version_at_ref(args.base, rule.version_file, rule.version_pattern)
            head_version = version_at_ref(args.head, rule.version_file, rule.version_pattern)
        except subprocess.CalledProcessError as exc:
            print(f"Failed to read {rule.version_file}: {exc}")
            return 2
        except RuntimeError as exc:
            print(str(exc))
            return 2

        rule_results[rule.name] = base_version != head_version

    failures = evaluate_rules(changed, rule_results)
    if failures:
        print("Version bump checks failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("Version bump checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
