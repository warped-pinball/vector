#!/usr/bin/env python3
"""Boot every board against every game config it can be flashed with.

Run from the repo root on the bench Pi:

    cd ~/vector && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python dev/hil/config_matrix.py

Inside an Actions job the runner's .env already provides VECTOR_HIL_VENV, so
plain `python dev/hil/config_matrix.py` is enough there.

This is DESIGN.md's G3: "every available config can be parsed and boot". A
config is a JSON file in src/<target>/config/ that the build packs into the
firmware's config bundle; the board picks one at boot from the `gamename` field
of the FRAM `configuration` record. So one iteration is:

    write gamename -> reset -> wait for the server -> ask the board what it
    loaded

and the pass condition is that the board reports *that* config, by name.

Why the game name is the assertion that matters: when a config fails to apply -
missing from the bundle, unparseable, or a filename the board cannot store -
GameDefsLoad falls back to `safe_defaults`, and the board comes up looking
perfectly healthy while running a generic definition for that hardware. Nothing
faults from the outside. Comparing `/api/game/name` against `GameInfo.GameName`
in the *source* JSON is what separates "loaded my config" from "silently fell
back", and it cross-checks the on-board bundle against the repo at the same
time.

Stages:

  1. inventory   - probe every attached board (shared with flash_and_check.py)
  2. resolve     - decide which target each board should be flashed with
  3. build/flash - one firmware flash per board, so the bundle under test is
                   the one built from this checkout
  4. matrix      - per board, per config: set, reset, boot, assert
  5. restore     - put each board back on its generic config

Boards are visited one after another, and a boot cycle is 15-25s, so a full run
is dominated by whichever target has the most configs (WPC, at 63). Use
--target/--configs/--limit to cut it down while iterating.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bench  # noqa: E402
from bench import (  # noqa: E402
    _TIMINGS,
    BENCH_WARN_FAULTS,
    DEFAULT_GAMENAME,
    EXPECTED_FAULTS,
    REPO_ROOT,
    CheckFailure,
    UsbApiClient,
    endgroup,
    get,
    group,
    inventory,
    log,
    parse_board_map,
    prime_usb,
    reset_board,
    resolve_targets,
    set_game_config,
    wait_for_server,
)

# Raised by GameDefsLoad when the configured game cannot be loaded (CONF01) or
# blew up on the way (CONF00). Either one means the board is running
# safe_defaults, which is exactly the failure this harness exists to catch.
CONFIG_FAULTS = {"CONF00", "CONF01"}


def source_configs(target):
    """{config filename without .json: {"name": ..., "adjustments": bool}}.

    This is the expectation side of every assertion below - the board's answers
    are compared against the source JSON, never against the board's own idea of
    what it has.

    `adjustments` records whether the config declares an Adjustments section,
    which decides how hard /api/adjustments/status is held to account. See
    check_config().
    """
    config_dir = REPO_ROOT / "src" / target / "config"
    if not config_dir.is_dir():
        raise CheckFailure(f"no config directory for target {target} at {config_dir}")

    configs = {}
    for path in sorted(config_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CheckFailure(f"{path} is not valid JSON: {exc}")
        try:
            name = data["GameInfo"]["GameName"]
        except (KeyError, TypeError):
            raise CheckFailure(f"{path} has no GameInfo.GameName")
        configs[path.stem] = {"name": name, "adjustments": "Adjustments" in data}

    if not configs:
        raise CheckFailure(f"no game configs found in {config_dir}")
    return configs


def changed_configs(target, ref):
    """Config names under test that git says changed since `ref`.

    Ordering these first means a run that is going to fail because of the diff
    fails in the first minute rather than the twentieth.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}...HEAD", "--", f"src/{target}/config"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log(f"::warning::could not diff against {ref}: {result.stderr.strip()}")
        return []
    return [Path(line).stem for line in result.stdout.split()]


def order_configs(names, first):
    """Put `first` at the front, keeping the rest in their existing order."""
    lead = [name for name in first if name in names]
    return lead + [name for name in names if name not in lead]


def select_configs(target, args):
    configs = source_configs(target)
    names = list(configs)

    if args.configs:
        requested = [name.strip() for name in args.configs.split(",") if name.strip()]
        unknown = [name for name in requested if name not in configs]
        if unknown:
            raise CheckFailure(f"unknown config(s) for {target}: {', '.join(unknown)}")
        names = requested
    elif args.changed_since:
        names = order_configs(names, changed_configs(target, args.changed_since))

    if args.limit:
        names = names[: args.limit]
    return names, configs


def check_faults(client, config):
    """Fail on anything that makes the config assertions meaningless."""
    faults = get(client, "/api/fault") or []
    if isinstance(faults, dict):
        faults = faults.get("faults", [])
    codes = {str(f)[:6] for f in faults}

    config_faults = codes & CONFIG_FAULTS
    if config_faults:
        raise CheckFailure(f"{sorted(config_faults)} raised - the board did not load {config!r} and is on safe defaults")

    # HDWR01 is a warning in flash_and_check.py because it does not stop the
    # API working. Here it is fatal: it puts main.py down the safe_mode path,
    # where GameDefsLoad never reads the config at all, so every assertion
    # below would pass or fail for reasons that have nothing to do with the
    # config under test.
    if codes & BENCH_WARN_FAULTS:
        raise CheckFailure(f"{sorted(codes & BENCH_WARN_FAULTS)} raised - the board booted in safe mode, so no config was loaded and this result would be meaningless")

    unexpected = codes - EXPECTED_FAULTS
    if unexpected:
        raise CheckFailure(f"unexpected fault(s): {sorted(unexpected)}")


def check_adjustments(client, config, declares_adjustments):
    """Prove the loaded definition is usable, not merely loadable.

    Held to 200 only for configs that declare an Adjustments section. The rest
    are a known firmware gap rather than a config problem: GameDefsLoad assigns
    the parsed config straight to SharedState.gdata without merging
    safe_defaults into it, so a config with no Adjustments section leaves
    gdata["Adjustments"] absent and Adjustments._get_range_from_gamedef raises
    KeyError, which route_wrapper turns into a 500. Failing those here would
    bury the signal this harness exists for under a defect it cannot fix, so
    they are warned about instead - loudly, and once per occurrence.
    """
    try:
        adjustments = get(client, "/api/adjustments/status")
    except CheckFailure as exc:
        if declares_adjustments:
            raise
        log(f"::warning::{config}: /api/adjustments/status failed ({exc}). The config declares no Adjustments section and gdata is not merged with safe_defaults - see check_adjustments().")
        return

    if not isinstance(adjustments, dict):
        raise CheckFailure(f"/api/adjustments/status returned {type(adjustments).__name__}, expected an object")


def check_config(port, target, config, expected):
    """Boot one board on one config and prove it is the config that loaded."""
    expected_name = expected["name"]

    set_game_config(port, config)
    reset_board(port)

    connection, boot_log = wait_for_server(port)
    client = None
    try:
        prime_usb(connection)
        client = UsbApiClient(connection)

        check_faults(client, config)

        active = get(client, "/api/game/active_config")
        active = active.get("active_config") if isinstance(active, dict) else active

        # EM boards answer this route with the game name rather than the
        # filename (backend.py:481), so accept either for that target.
        expected_active = {config, expected_name} if target == "em" else {config}
        if active not in expected_active:
            raise CheckFailure(f"active config is {active!r}, expected {config!r}")

        name = get(client, "/api/game/name")
        if isinstance(name, dict):
            name = name.get("name")
        name = str(name).strip()
        if name != expected_name:
            raise CheckFailure(f"board reports game name {name!r}, but {config}.json says {expected_name!r} - the config did not apply and the board fell back to a generic definition")

        # A config that parses but is not usable still fails a customer. Both
        # of these read the loaded definition rather than just its presence.
        if get(client, "/api/leaders") is None:
            raise CheckFailure("/api/leaders returned no body")
        check_adjustments(client, config, expected["adjustments"])

        return name, boot_log
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        else:
            try:
                connection.close()
            except Exception:
                pass


def check_bundle(port, target, configs):
    """Compare the board's config list against the repo, once per board.

    Cheap, and it localises a whole class of failure before the matrix starts:
    if the build dropped or mangled a config, this says so in one boot instead
    of once per affected iteration.
    """
    reset_board(port)
    connection, _ = wait_for_server(port)
    try:
        prime_usb(connection)
        client = UsbApiClient(connection)
        on_board = get(client, "/api/game/configs_list")
        if not isinstance(on_board, dict) or not on_board:
            raise CheckFailure("/api/game/configs_list is empty - the config bundle is missing from the build")

        missing = sorted(set(configs) - set(on_board))
        extra = sorted(set(on_board) - set(configs))
        if missing:
            raise CheckFailure(f"{len(missing)} config(s) in src/{target}/config are not in the build's bundle: {', '.join(missing)}")
        if extra:
            raise CheckFailure(f"the build's bundle carries {len(extra)} config(s) with no source JSON: {', '.join(extra)}")

        mismatched = [f"{name}: bundle says {on_board[name].get('name')!r}, source says {configs[name]['name']!r}" for name in sorted(configs) if on_board[name].get("name") != configs[name]["name"]]
        if mismatched:
            raise CheckFailure("game name mismatch between the bundle and the source JSON:\n      " + "\n      ".join(mismatched))

        log(f"    bundle matches source: {len(configs)} configs, names identical")
    finally:
        try:
            connection.close()
        except Exception:
            pass


def restore_default(port, target):
    """Leave the board on its generic config, as flash_and_check.py expects."""
    default = DEFAULT_GAMENAME[target]
    try:
        set_game_config(port, default)
        reset_board(port)
        log(f"    restored {default}")
    except CheckFailure as exc:
        log(f"::warning::could not restore {default} on {port}: {exc}")


def run_matrix(board, args):
    """Walk one board through its configs. Returns (passed, failures)."""
    port = board["port"]
    target = board["target"]
    names, configs = select_configs(target, args)

    group(f"Config bundle {target} on {port}")
    check_bundle(port, target, configs)
    endgroup()

    log("")
    log(f"{len(names)} config(s) to check on {port} ({target})")
    log("")

    passed = []
    failures = []
    for index, config in enumerate(names, 1):
        started = time.monotonic()
        group(f"[{index}/{len(names)}] {target} {config}")
        try:
            name, _boot_log = check_config(port, target, config, configs[config])
            elapsed = time.monotonic() - started
            log(f"    ok  {config:20} -> {name!r}  [{elapsed:.1f}s]")
            passed.append(config)
        except CheckFailure as exc:
            log(f"::error::{target} {config}: {exc}")
            failures.append((config, str(exc)))
            if not args.keep_going:
                endgroup()
                break
        except Exception as exc:  # noqa: BLE001 - one bad config must not end the run
            log(f"::error::{target} {config}: unexpected error: {exc}")
            failures.append((config, str(exc)))
            if not args.keep_going:
                endgroup()
                break
        endgroup()

    group(f"Restore {target} on {port}")
    restore_default(port, target)
    endgroup()

    return passed, failures


def write_step_summary(results):
    """Render the run as a table in the Actions job summary, when there is one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return

    lines = ["## HIL config matrix", "", "| board | target | configs | passed | failed |", "|---|---|---|---:|---:|"]
    for board, passed, failures in results:
        lines.append(f"| `{board['port']}` | {board['target']} | {len(passed) + len(failures)} | {len(passed)} | {len(failures)} |")

    failed = [(board, config, reason) for board, _passed, failures in results for config, reason in failures]
    if failed:
        lines += ["", "### Failures", ""]
        for board, config, reason in failed:
            lines.append(f"- **{board['target']} `{config}`** - {reason.splitlines()[0]}")

    with open(path, "a") as handle:
        handle.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", action="append", help="only run boards for this target (repeatable), e.g. --target wpc")
    parser.add_argument("--configs", help="comma-separated config names to run instead of all of them, e.g. AttackMars_11,Taxi_L4")
    parser.add_argument("--limit", type=int, help="stop after this many configs per board - useful for a quick smoke run")
    parser.add_argument("--changed-since", metavar="REF", help="run configs changed since REF first, so a config-touching PR fails fast")
    parser.add_argument("--skip-flash", action="store_true", help="matrix what is already on the boards instead of building and flashing first")
    parser.add_argument("--stop-on-first-failure", dest="keep_going", action="store_false", help="stop a board's matrix at its first failing config (default: run them all)")
    args = parser.parse_args()

    bench.ensure_tools_on_path()

    workdir = REPO_ROOT / "build"
    workdir.mkdir(exist_ok=True)

    group("Inventory")
    boards = inventory()
    endgroup()

    group("Resolve targets")
    boards = resolve_targets(boards, parse_board_map(os.environ.get("VECTOR_HIL_BOARD_MAP")))
    for b in boards:
        log(f"  {b['port']}  ->  {b['target']}")
    endgroup()

    if args.target:
        wanted = set(args.target)
        boards = [b for b in boards if b["target"] in wanted]
        if not boards:
            raise CheckFailure(f"no attached board matches --target {', '.join(sorted(wanted))}")

    if not args.skip_flash:
        # Flash first so the bundle under test is the one this checkout builds.
        # Without it the matrix would validate whatever happened to be on the
        # boards, which is the one thing it must not do.
        for target in sorted({b["target"] for b in boards}):
            group(f"Build {target}")
            bench.build(target)
            log(f"built {target} at version {bench.source_version(target)}")
            endgroup()

        for b in boards:
            group(f"Flash {b['target']} on {b['port']}")
            config_path = bench.write_bench_config(b["target"], workdir)
            bench.flash(b["target"], b["port"], workdir / b["target"], config_path)
            log("flashed")
            endgroup()

    results = []
    for b in boards:
        try:
            passed, failures = run_matrix(b, args)
        except CheckFailure as exc:
            # A board that cannot even be set up is one board's problem. The
            # bench is a singleton and a run is expensive, so the other boards
            # still get their matrix.
            log(f"::error::{b['target']} on {b['port']}: {exc}")
            passed, failures = [], [("(board setup)", str(exc))]
        results.append((b, passed, failures))

    log("")
    log("stage timings:")
    for title, elapsed in _TIMINGS:
        log(f"  {elapsed:7.1f}s  {title}")

    log("")
    log("=" * 60)
    total_failures = 0
    for board, passed, failures in results:
        state = "FAIL" if failures else "ok"
        log(f"  {state:5} {board['port']:16} {board['target']:12} {len(passed)} passed, {len(failures)} failed")
        total_failures += len(failures)
    log("=" * 60)

    write_step_summary(results)

    if total_failures:
        log(f"\n{total_failures} config(s) failed:")
        for board, _passed, failures in results:
            for config, reason in failures:
                log(f"  - {board['target']} {config}: {reason}")
        return 1

    checked = sum(len(passed) for _board, passed, _failures in results)
    log(f"\nall {checked} config(s) booted and reported the right game name")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckFailure as exc:
        log(f"::error::{exc}")
        sys.exit(1)
