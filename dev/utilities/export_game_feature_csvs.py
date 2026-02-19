#!/usr/bin/env python3
"""Export game feature support from config JSON files into CSV.

Default output:
- game_features.csv (one row per distinct title + MPU)

Design goals:
- Distinct game names grouped by MPU/system family
- Centralized, modular feature rules that are easy to extend
- Optional MPU/system filtering per run
- Optional JSON path query mode for ad-hoc feature exploration
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_CONFIG_GLOB = "src/*/config/*.json"
DEFAULT_OUT_DIR = Path("dev/generated/game_features")
DEFAULT_CONSOLIDATED_CSV = "game_features.csv"

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
# =============================================================================


def supports_live_scores(rec: ConfigRecord) -> bool:
    inplay_type = get_path(rec.data, "InPlay.Type", 0)

    # EM live scoring is sensor-driven and not gated by InPlay.Type in config.
    if rec.system_family == "EM":
        return True

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


def get_known_formats(rec: ConfigRecord) -> list[str]:
    formats = get_path(rec.data, "Formats", {})
    if not isinstance(formats, dict):
        return []
    return sorted([name for name in formats.keys() if name in KNOWN_FORMATS], key=str.casefold)


def build_feature_rules() -> dict[str, FeatureRule]:
    return {
        "live_scores": FeatureRule(
            name="live_scores",
            description="Games where runtime live score paths are enabled by InPlay.Type.",
            predicate=supports_live_scores,
        ),
        "switch_diagnostics": FeatureRule(
            name="switch_diagnostics",
            description="Games where switch diagnostics can return labeled switch health entries.",
            predicate=supports_switch_diagnostics,
        ),
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
# Consolidated CSV output
# =============================================================================


def write_consolidated_csv(path: Path, records: list[ConfigRecord]) -> None:
    """Write one large CSV with each title + MPU and all features as columns.

    Dedupe key is (game_name, system_family), so multiple ROM revisions collapse
    into one row per title/MPU.
    """
    rows: dict[tuple[str, str], dict[str, Any]] = {}

    for rec in records:
        key = (rec.game_name, rec.system_family)
        row = rows.setdefault(
            key,
            {
                "game_name": rec.game_name,
                "mpu": rec.system_family,
                "live_scores": False,
                "switch_diagnostics": False,
                "special_formats": False,
                "formats": set(),
            },
        )

        for feature_name, rule in FEATURE_RULES.items():
            if rule.predicate(rec):
                row[feature_name] = True

        row["formats"].update(get_known_formats(rec))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "game_name",
            "mpu",
            "live_scores",
            "switch_diagnostics",
            "special_formats",
            "formats",
        ])

        sorted_rows = sorted(rows.values(), key=lambda r: (str(r["mpu"]).casefold(), str(r["game_name"]).casefold()))
        for row in sorted_rows:
            writer.writerow(
                [
                    row["game_name"],
                    row["mpu"],
                    "yes" if row["live_scores"] else "no",
                    "yes" if row["switch_diagnostics"] else "no",
                    "yes" if row["special_formats"] else "no",
                    ";".join(sorted(row["formats"], key=str.casefold)),
                ]
            )


# =============================================================================
# Optional ad-hoc query mode
# =============================================================================


def apply_json_query(records: list[ConfigRecord], dotted_path: str, op: str, value: str | None) -> list[ConfigRecord]:
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

    return [rec for rec in records if _match(rec)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-glob", default=DEFAULT_CONFIG_GLOB)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--out-file", default=DEFAULT_CONSOLIDATED_CSV)
    parser.add_argument(
        "--systems",
        nargs="*",
        help="Optional normalized system filter: WPC SYS11 DATA_EAST",
    )

    # Optional query mode: filter input configs before consolidated export
    parser.add_argument("--query-path", help="Dotted JSON path for ad-hoc filter")
    parser.add_argument("--query-op", choices=["exists", "eq", "contains"], default="exists")
    parser.add_argument("--query-value", help="Value for eq/contains query ops")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_records(args.config_glob)

    if args.systems:
        wanted = {s.upper() for s in args.systems}
        records = [r for r in records if r.system_family in wanted]

    if args.query_path:
        records = apply_json_query(records, args.query_path, args.query_op, args.query_value)

    out_path = Path(args.out_dir) / args.out_file
    write_consolidated_csv(out_path, records)
    print(f"wrote {out_path} ({len(records)} config rows scanned)")


if __name__ == "__main__":
    main()
