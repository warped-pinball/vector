"""Validate required version bumps for pull requests."""
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
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


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str, file_path: str) -> "SemVer":
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", raw)
        if not match:
            raise RuntimeError(
                f"Invalid semantic version '{raw}' in {file_path}; expected MAJOR.MINOR.PATCH"
            )
        major, minor, patch = (int(group) for group in match.groups())
        return cls(major=major, minor=minor, patch=patch)

    def bump_patch(self) -> "SemVer":
        return SemVer(major=self.major, minor=self.minor, patch=self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class RuleOutcome:
    rule: VersionRule
    base_version: str
    head_version: str
    touched: bool
    requires_bump: bool
    target_version: str | None


RULES: tuple[VersionRule, ...] = (
    VersionRule(
        name="common shared-state version (all src changes)",
        scope_prefixes=("src/",),
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
    merge_base = _run_git("merge-base", base_ref, head_ref)
    output = _run_git("diff", "--name-only", f"{merge_base}...{head_ref}")
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
    changed_list = list(changed)
    for rule in RULES:
        if not touches_scope(changed_list, rule.scope_prefixes):
            continue
        if not rule_results.get(rule.name, False):
            prefixes = ", ".join(rule.scope_prefixes)
            failures.append(
                f"Changes in [{prefixes}] require updating version in {rule.version_file}"
            )
    return failures


def analyze_rule(rule: VersionRule, changed: Iterable[str], base_ref: str, head_ref: str) -> RuleOutcome:
    base_version = version_at_ref(base_ref, rule.version_file, rule.version_pattern)
    head_version = version_at_ref(head_ref, rule.version_file, rule.version_pattern)
    touched = touches_scope(changed, rule.scope_prefixes)

    if not touched:
        return RuleOutcome(
            rule=rule,
            base_version=base_version,
            head_version=head_version,
            touched=False,
            requires_bump=False,
            target_version=None,
        )

    base_semver = SemVer.parse(base_version, rule.version_file)
    head_semver = SemVer.parse(head_version, rule.version_file)
    if head_semver > base_semver:
        return RuleOutcome(
            rule=rule,
            base_version=base_version,
            head_version=head_version,
            touched=True,
            requires_bump=False,
            target_version=None,
        )

    return RuleOutcome(
        rule=rule,
        base_version=base_version,
        head_version=head_version,
        touched=True,
        requires_bump=True,
        target_version=str(base_semver.bump_patch()),
    )


def apply_bumps(outcomes: Iterable[RuleOutcome]) -> list[str]:
    updated_files: list[str] = []
    for outcome in outcomes:
        if not outcome.requires_bump:
            continue

        path = Path(outcome.rule.version_file)
        text = path.read_text(encoding="utf-8")
        updated_text, replacements = re.subn(
            outcome.rule.version_pattern,
            lambda match: match.group(0).replace(match.group(1), outcome.target_version or ""),
            text,
            count=1,
        )
        if replacements != 1:
            raise RuntimeError(f"Unable to update version in {outcome.rule.version_file}")

        path.write_text(updated_text, encoding="utf-8")
        updated_files.append(outcome.rule.version_file)

    return updated_files


def write_summary(path: str, outcomes: Iterable[RuleOutcome], applied: bool) -> None:
    touched = [outcome for outcome in outcomes if outcome.touched]
    lines = ["## Version bump report", ""]
    if not touched:
        lines.append("No scoped source changes detected; no version bumps required.")
    else:
        lines.extend(
            [
                "| Rule | Version file | Base branch | PR branch | Required bump |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for outcome in touched:
            required = (
                f"{outcome.target_version} ({'applied' if applied else 'required'})"
                if outcome.requires_bump and outcome.target_version
                else "None (already higher in PR)"
            )
            lines.append(
                "| "
                f"{outcome.rule.name} | `{outcome.rule.version_file}` | "
                f"`{outcome.base_version}` | `{outcome.head_version}` | {required} |"
            )

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate required version bumps.")
    parser.add_argument("--base", required=True, help="Base git ref/sha")
    parser.add_argument("--head", required=True, help="Head git ref/sha")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply required patch version bumps to the working tree.",
    )
    parser.add_argument(
        "--summary-file",
        help="Optional path to write a Markdown summary table.",
    )
    args = parser.parse_args()

    changed = changed_files(args.base, args.head)
    outcomes: list[RuleOutcome] = []
    for rule in RULES:
        try:
            outcomes.append(analyze_rule(rule, changed, args.base, args.head))
        except subprocess.CalledProcessError as exc:
            print(f"Failed to read {rule.version_file}: {exc}")
            return 2
        except RuntimeError as exc:
            print(str(exc))
            return 2

    if args.apply:
        updated_files = apply_bumps(outcomes)
        if updated_files:
            print("Applied patch version bumps:")
            for file_path in updated_files:
                print(f" - {file_path}")
        else:
            print("No version bumps needed.")
    else:
        rule_results = {
            outcome.rule.name: not outcome.requires_bump if outcome.touched else True
            for outcome in outcomes
        }
        failures = evaluate_rules(changed, rule_results)
        if failures:
            print("Version bump checks failed:")
            for failure in failures:
                print(f" - {failure}")
            return 1

    if args.summary_file:
        write_summary(args.summary_file, outcomes, applied=args.apply)

    print("Version bump checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
