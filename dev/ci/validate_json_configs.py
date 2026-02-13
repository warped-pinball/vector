#!/usr/bin/env python3
"""Validate JSON files and enforce required config fields."""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from pathlib import Path

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


def main() -> int:
    errors: list[str] = []

    for relative_path in tracked_json_files():
        file_path = REPO_ROOT / relative_path
        try:
            with file_path.open("r", encoding="utf-8") as json_file:
                payload = json.load(json_file)
        except Exception as exc:  # pragma: no cover - explicit error reporting path
            errors.append(f"{relative_path}: invalid JSON ({exc})")
            continue

        rule = rule_for_path(str(relative_path))
        if rule is None:
            continue

        if not isinstance(payload, dict):
            errors.append(f"{relative_path}: expected top-level JSON object")
            continue

        field_errors = validate_required_fields(str(relative_path), payload, rule)
        for field_error in field_errors:
            errors.append(f"{relative_path} [{rule['name']}]: {field_error}")

    if errors:
        print("JSON validation failed:")
        for entry in errors:
            print(f" - {entry}")
        return 1

    print("JSON validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
