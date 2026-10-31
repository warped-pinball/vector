#!/usr/bin/env python3
"""Validate JSON files and enforce required config fields."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    from .json_config_schema import SCHEMA_RULES
except ImportError:
    from json_config_schema import SCHEMA_RULES

REPO_ROOT = Path(__file__).resolve().parents[2]


def tracked_json_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.json"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [Path(file) for file in files]


def rule_for_path(path: str) -> dict | None:
    for rule in SCHEMA_RULES:
        if any(fnmatch.fnmatch(path, pattern) for pattern in rule["include"]):
            return rule
    return None


def is_linkto_config(payload: dict) -> bool:
    """Check if a config uses LinkTo to alias another config."""
    game_info = payload.get("GameInfo")
    return isinstance(game_info, dict) and "LinkTo" in game_info


def validate_linkto_config(relative_path: str, payload: dict) -> list[str]:
    """Validate a LinkTo config: ensure required fields and linked target exists."""
    errors: list[str] = []
    game_info = payload.get("GameInfo", {})

    if "GameName" not in game_info:
        errors.append(f"missing required field 'GameInfo.GameName'")

    link_target = game_info.get("LinkTo", "")
    if not link_target:
        errors.append(f"'GameInfo.LinkTo' is empty")
        return errors

    # Find the linked target config file in the same directory
    config_dir = Path(relative_path).parent
    target_path = config_dir / f"{link_target}.json"
    target_file = REPO_ROOT / target_path

    if not target_file.exists():
        errors.append(f"LinkTo target '{link_target}' not found (expected {target_path.as_posix()})")

    return errors


def validate_required_fields(path: str, payload: dict, rule: dict) -> list[str]:
    errors: list[str] = []
    for top_level, required_nested in rule["required"].items():
        section = payload.get(top_level)
        if not isinstance(section, dict):
            errors.append(f"missing required object '{top_level}'")
            continue

        for nested_field in required_nested:
            if nested_field not in section:
                errors.append(f"missing required field '{top_level}.{nested_field}'")

    return errors


# GameInfo.Abbrev becomes the board's DHCP host name, WP-<Abbrev>, which the
# firmware caps at 32 characters and strips to letters, digits and hyphens.
ABBREV_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,28}$")


def validate_abbrev(payload: dict) -> list[str]:
    abbrev = payload.get("GameInfo", {}).get("Abbrev")
    if abbrev is None or ABBREV_PATTERN.match(str(abbrev)):
        return []
    return [f"'GameInfo.Abbrev' {abbrev!r} must be 1-29 capital letters, digits or hyphens, starting with a letter or digit"]


def main() -> int:
    errors: list[str] = []
    abbrev_owners: dict[str, dict[str, str]] = {}

    for relative_path in tracked_json_files():
        file_path = REPO_ROOT / relative_path
        try:
            with file_path.open("r", encoding="utf-8") as json_file:
                payload = json.load(json_file)
        except Exception as exc:  # pragma: no cover - explicit error reporting path
            errors.append(f"{relative_path.as_posix()}: invalid JSON ({exc})")
            continue

        rule = rule_for_path(relative_path.as_posix())
        if rule is None:
            continue

        if not isinstance(payload, dict):
            errors.append(f"{relative_path.as_posix()}: expected top-level JSON object")
            continue

        # LinkTo configs are lightweight aliases; validate them separately
        if is_linkto_config(payload):
            linkto_errors = validate_linkto_config(relative_path.as_posix(), payload)
            for linkto_error in linkto_errors:
                errors.append(f"{relative_path.as_posix()} [linkto]: {linkto_error}")
            continue

        field_errors = validate_required_fields(relative_path.as_posix(), payload, rule)
        field_errors += validate_abbrev(payload)
        for field_error in field_errors:
            errors.append(f"{relative_path.as_posix()} [{rule['name']}]: {field_error}")

        game_info = payload.get("GameInfo", {})
        if game_info.get("Abbrev"):
            abbrev_owners.setdefault(game_info["Abbrev"], {}).setdefault(game_info.get("GameName", ""), relative_path.as_posix())

    # Two games with one abbreviation would give two different machines the same network name
    for abbrev, owners in sorted(abbrev_owners.items()):
        if len(owners) > 1:
            errors.append(f"'GameInfo.Abbrev' {abbrev!r} is used by different games: {', '.join(sorted(owners.values()))}")

    if errors:
        print("JSON validation failed:")
        for entry in errors:
            print(f" - {entry}")
        return 1

    print("JSON validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
