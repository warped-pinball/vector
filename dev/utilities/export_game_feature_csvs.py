#!/usr/bin/env python3
"""Export feature-support game lists from config JSON files to CSV.

Default output:
- live_scores.csv
- switch_diagnostics.csv
- special_formats.csv

Design goals:
- Distinct game names only (no ROM filename dependency)
- Feature rules are centralized and easy to extend
- Optional MPU/system filtering per run
- Optional JSON path query mode for ad-hoc list generation
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


DEFAULT_CONFIG_GLOB = "src/*/config/*.json"
DEFAULT_OUT_DIR = Path("dev/generated/game_features")

KNOWN_FORMATS = {
    "Standard",
    "Limbo",
    "LowBall",
    "Golf",
    "Practice",
    "HalfLife",
    "LongestBall",
}


@dataclass(frozen=True)
class ConfigRecord:
    path: Path
    game_name: str
    system_raw: str
    system_family: str
    data: dict[str, Any]


@dataclass(frozen=True)
class FeatureRule:
    name: str
    description: str
    predicate: Callable[[ConfigRecord], bool]


# =============================================================================
# Common JSON/config helpers
# =============================================================================


def normalize_system(system_raw: str) -> str:
    s = (system_raw or "").strip().lower()
    if s == "wpc":
        return "WPC"
    if s == "dataeast":
        return "DATA_EAST"
    if s.startswith("11") or s == "9":
        return "SYS11"
    return s.upper() if s else "UNKNOWN"


def get_path(data: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    cur: Any = data
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def has_labeled_switch_defs(rec: ConfigRecord) -> bool:
    switches = get_path(rec.data, "Switches", {}) or {}
    defs = switches.get("Names") or switches.get("Sensitivity")
    if not isinstance(defs, list):
        return False

    for entry in defs:
        if entry in (-1, None, []):
            continue
        if isinstance(entry, list):
            if entry and entry[0]:
                return True
        elif isinstance(entry, int):
            return True
        elif isinstance(entry, str) and entry:
            return True
    return False


# =============================================================================
# Feature extraction predicates
#
# Add a new exported feature by:
#   1) adding a new `supports_<feature>()` predicate in this section,
#   2) registering it in `build_feature_rules()` below.
#
# This keeps the "what defines support" logic isolated per feature.
# =============================================================================


def supports_live_scores(rec: ConfigRecord) -> bool:
    inplay_type = get_path(rec.data, "InPlay.Type", 0)
    if rec.system_family == "WPC":
        return inplay_type == 10
    if rec.system_family == "SYS11":
        return inplay_type == 1
    if rec.system_family == "DATA_EAST":
        return isinstance(inplay_type, int) and 20 <= inplay_type < 30
    return False


def supports_switch_diagnostics(rec: ConfigRecord) -> bool:
    return get_path(rec.data, "Switches.Type") == 10 and has_labeled_switch_defs(rec)


def supports_special_formats(rec: ConfigRecord) -> bool:
    formats = get_path(rec.data, "Formats", {})
    if not isinstance(formats, dict) or not formats:
        return False
    return any(name in KNOWN_FORMATS for name in formats.keys())


def build_feature_rules() -> dict[str, FeatureRule]:
    """Return all built-in feature extractors.

    Structure note:
    - each block below represents one output CSV file,
    - each block points to one focused predicate function.

    This function is intended as the single "registry" breakpoint for adding
    future feature exports.
    """
    return {
        # ---------------------------------------------------------------------
        # live_scores.csv
        # How support is detected:
        # - WPC: InPlay.Type == 10
        # - SYS11: InPlay.Type == 1
        # - DATA_EAST: InPlay.Type in [20..29]
        # ---------------------------------------------------------------------
        "live_scores": FeatureRule(
            name="live_scores",
            description="Games where runtime live score paths are enabled by InPlay.Type.",
            predicate=supports_live_scores,
        ),

        # ---------------------------------------------------------------------
        # switch_diagnostics.csv
        # How support is detected:
        # - Switches.Type == 10
        # - AND at least one usable switch definition exists (Names/Sensitivity)
        # ---------------------------------------------------------------------
        "switch_diagnostics": FeatureRule(
            name="switch_diagnostics",
            description="Games where switch diagnostics can return labeled switch health entries.",
            predicate=supports_switch_diagnostics,
        ),

        # ---------------------------------------------------------------------
        # special_formats.csv
        # How support is detected:
        # - Formats object exists in config
        # - AND it includes one or more known format names
        # ---------------------------------------------------------------------
        "special_formats": FeatureRule(
            name="special_formats",
            description="Games defining one or more known special format entries.",
            predicate=supports_special_formats,
        ),
    }


FEATURE_RULES = build_feature_rules()


def load_records(config_glob: str) -> list[ConfigRecord]:
    records: list[ConfigRecord] = []
    for raw_path in sorted(glob.glob(config_glob)):
        path = Path(raw_path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        game_name = get_path(data, "GameInfo.GameName", path.stem)
        system_raw = get_path(data, "GameInfo.System", "")
        records.append(
            ConfigRecord(
                path=path,
                game_name=game_name,
                system_raw=system_raw,
                system_family=normalize_system(system_raw),
                data=data,
            )
        )
    return records


# =============================================================================
# CSV output + ad-hoc query helpers
# =============================================================================


def write_game_csv(path: Path, game_names: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["game_name"])
        for name in sorted(set(game_names), key=str.casefold):
            writer.writerow([name])


def apply_json_query(records: list[ConfigRecord], dotted_path: str, op: str, value: str | None) -> list[str]:
    def _match(rec: ConfigRecord) -> bool:
        current = get_path(rec.data, dotted_path, None)
        if op == "exists":
            return current is not None
        if op == "eq":
            return str(current) == str(value)
        if op == "contains":
            if isinstance(current, dict):
                return str(value) in current.keys()
            if isinstance(current, list):
                return any(str(v) == str(value) for v in current)
            return str(value) in str(current)
        raise ValueError(f"Unsupported op: {op}")

    return [rec.game_name for rec in records if _match(rec)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-glob", default=DEFAULT_CONFIG_GLOB)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--feature",
        action="append",
        choices=sorted(FEATURE_RULES.keys()),
        help="Feature(s) to export. Default exports all built-ins.",
    )
    parser.add_argument(
        "--systems",
        nargs="*",
        help="Optional normalized system filter: WPC SYS11 DATA_EAST",
    )

    # Ad-hoc query mode (optional reusable hook for future feature discovery)
    parser.add_argument("--query-name", help="Name for ad-hoc query output CSV")
    parser.add_argument("--query-path", help="Dotted JSON path for ad-hoc query")
    parser.add_argument("--query-op", choices=["exists", "eq", "contains"], default="exists")
    parser.add_argument("--query-value", help="Value for eq/contains query ops")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_records(args.config_glob)

    if args.systems:
        wanted = {s.upper() for s in args.systems}
        records = [r for r in records if r.system_family in wanted]

    out_dir = Path(args.out_dir)
    features = args.feature or list(FEATURE_RULES.keys())

    for feature_name in features:
        rule = FEATURE_RULES[feature_name]
        games = [rec.game_name for rec in records if rule.predicate(rec)]
        write_game_csv(out_dir / f"{feature_name}.csv", games)
        print(f"wrote {feature_name}.csv ({len(set(games))} games)")

    if args.query_name and args.query_path:
        games = apply_json_query(records, args.query_path, args.query_op, args.query_value)
        write_game_csv(out_dir / f"{args.query_name}.csv", games)
        print(f"wrote {args.query_name}.csv ({len(set(games))} games)")


if __name__ == "__main__":
    main()
