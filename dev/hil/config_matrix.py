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
    BOOT_TIMEOUT,
    DEFAULT_GAMENAME,
    EXPECTED_FAULTS,
    REPO_ROOT,
    BootCrash,
    CheckFailure,
    UsbApiClient,
    _dump_boot_log,
    drain_port,
    endgroup,
    get,
    group,
    inventory,
    log,
    parse_board_map,
    prime_usb,
    repl_reset,
    reset_board,
    resolve_targets,
    set_game_config,
    time_limit,
    wait_for_server,
)

# Raised by GameDefsLoad when the configured game cannot be loaded (CONF01) or
# blew up on the way (CONF00). Either one means the board is running
# safe_defaults, which is exactly the failure this harness exists to catch.
CONFIG_FAULTS = {"CONF00", "CONF01"}

# Measured on the bench: 12.5s (wpc), 15.3s (sys11), and the flash harness's
# 150s default only buys a wedged board more time to waste.
MATRIX_BOOT_TIMEOUT = 90

# Hard ceiling on one config, as a backstop to the individual timeouts inside
# it. A healthy config takes ~21s; anything past this is a board that has
# stopped behaving, and it must not be allowed to hang the job. See
# bench.time_limit.
CONFIG_TIMEOUT = 240


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


class Session:
    """One board's serial connection, carried across the whole matrix.

    The connection is the point. The Pico has a single CDC endpoint, so every
    close is an invitation for something else to grab the port and for the
    board to be left printing into an endpoint nothing is draining. The first
    bench run wedged the WPC board on exactly that, one config in, and then
    spent 63 minutes timing out against a board that was never coming back.

    So: open once per boot, hold it through the assertions AND through setting
    the next config, and close it only in `reboot()` - by which point the board
    is already resetting and has stopped printing.
    """

    def __init__(self, port, boot_timeout=BOOT_TIMEOUT):
        self.port = port
        self.boot_timeout = boot_timeout
        self.connection = None
        self.client = None
        self.boot_log = []
        self.crashes = []

    def start(self, reset=True):
        """First boot of the run: watch the board come up, resetting it first
        only when something else has not already done so.

        Every later boot is triggered by reboot() over our own connection, but
        the first one has to be triggered here, and it must be triggered:
        dev/flash.py resets at the end of flashing, and flashing runs over
        every board before any of this starts, so the board booted minutes ago
        and printed its one ready marker long before we opened a console. That
        is bench.reset_board's whole reason for existing, and dropping it is
        what made the first matrix run time out on all three boards without
        checking a single config.

        `reset=False` is for a board that was just flashed. dev/flash.py ends
        by resetting it, so it is already booting - and resetting again lands
        on top of that boot, while the firmware is still reading its freshly
        written filesystem. That is not theoretical: sys11 wedged in exactly
        that window, flashed successfully and then refusing a reset seconds
        later, and it is the same shape as the ENOENT-on-a-file-that-exists
        crashes the WPC board raises at boot. One reset per boot.

        mpremote is safe here, unlike mid-matrix: no connection of ours is
        open yet, so there is no handoff to lose.

        A board that will not take the reset gets one drain and one retry. A
        board whose stdout is blocked on an undrained USB endpoint comes back
        the moment somebody reads it, and reading costs three seconds - much
        less than writing off a board's whole matrix.
        """
        if reset:
            try:
                reset_board(self.port)
            except Exception as exc:
                log(f"::warning::{self.port} did not take a reset ({exc}); draining its console and retrying once")
                drain_port(self.port)
                reset_board(self.port)
        else:
            log("    already booting from the flash; watching that boot rather than forcing another")
        return self.wait_for_boot()

    def wait_for_boot(self):
        """Watch one boot, retrying once if the firmware raises on the way up.

        A crash is not a timing problem and no amount of waiting fixes it - the
        program has exited. But it can be intermittent, and losing a whole
        board's matrix to one flaky boot buys nothing: the retry is what lets
        the 63 configs actually get checked.

        The crash is never swallowed. Every one is counted, logged with its
        traceback, and reported in the run summary, so a board that only
        sometimes comes up still shows up as a problem rather than as a clean
        run that happened to take longer.
        """
        for attempt in range(2):
            try:
                self.connection, self.boot_log = wait_for_server(self.port, timeout=self.boot_timeout)
                break
            except BootCrash as crash:
                self.crashes.append(str(crash))
                self.boot_log = crash.transcript
                if attempt:
                    raise
                log(f"::warning::{self.port} crashed on boot; retrying once. {crash}")
                reset_board(self.port)

        prime_usb(self.connection)
        self.client = UsbApiClient(self.connection)
        return self.client

    def _require_connection(self, what):
        if self.connection is None:
            raise CheckFailure(f"cannot {what} on {self.port}: the board is not connected (its last boot did not complete)")
        return self.connection

    def set_config(self, gamename):
        """Point the board at a config over the REPL we already have open."""
        set_game_config(self._require_connection("set a config"), gamename)

    def reboot(self):
        """Reset from the REPL, then drop the port while the board is down."""
        self._require_connection("reset the board")
        try:
            repl_reset(self.connection)
        finally:
            self.close()

    def nudge(self):
        """Try to unstick a board that stopped answering, before giving up."""
        self.close()
        drain_port(self.port)

    def close(self):
        connection, self.connection, self.client = self.connection, None, None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def check_bundle(client, target, configs):
    """Compare the board's config list against the repo, once per board.

    Cheap, and it localises a whole class of failure before the matrix starts:
    if the build dropped or mangled a config, this says so in one boot instead
    of once per affected iteration.
    """
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


def check_booted_config(client, target, config, expected):
    """Assert that the board in front of us booted on `config`."""
    expected_name = expected["name"]

    check_faults(client, config)

    active = get(client, "/api/game/active_config")
    active = active.get("active_config") if isinstance(active, dict) else active

    # EM boards answer this route with the game name rather than the filename
    # (backend.py:481), so accept either for that target.
    expected_active = {config, expected_name} if target == "em" else {config}
    if active not in expected_active:
        raise CheckFailure(f"active config is {active!r}, expected {config!r}")

    name = get(client, "/api/game/name")
    if isinstance(name, dict):
        name = name.get("name")
    name = str(name).strip()
    if name != expected_name:
        raise CheckFailure(f"board reports game name {name!r}, but {config}.json says {expected_name!r} - the config did not apply and the board fell back to a generic definition")

    # A config that parses but is not usable still fails a customer. Both of
    # these read the loaded definition rather than just its presence.
    if get(client, "/api/leaders") is None:
        raise CheckFailure("/api/leaders returned no body")
    check_adjustments(client, config, expected["adjustments"])

    return name


def restore_default(session, target):
    """Leave the board on its generic config, as flash_and_check.py expects.

    Best effort by design: this runs in teardown, including after the board has
    stopped answering, and a failure here must not lose the results the matrix
    already produced.
    """
    default = DEFAULT_GAMENAME[target]
    try:
        if session.connection is None:
            session.start()
        session.set_config(default)
        session.reboot()
        log(f"    restored {default}")
    except Exception as exc:  # noqa: BLE001 - teardown never fails the run
        log(f"::warning::could not restore {default} on {session.port}: {exc}")
        session.close()


# A board that stops answering does not start again on its own, and the bench
# is a shared singleton. Two setup failures in a row is the signal to stop
# spending an hour proving it: the first bench run burned 63 minutes writing
# the same 60s timeout 63 times, which is 62 wasted minutes and one lost
# data_east matrix.
MAX_CONSECUTIVE_SETUP_FAILURES = 2


def flash_before_matrix(board, workdir):
    """Flash one board immediately before its own matrix, not all up front.

    The ordering is the point, and it is what the bench taught us. Flashing
    every board first leaves the ones further down the queue running the
    application for as long as the boards ahead of them take - half an hour or
    more - printing to a USB CDC console that nothing is draining. TrenchCoat
    documents where that ends (src/ray.py, send_command): "if nothing ever
    drains the board's output, the USB CDC buffers fill up, MicroPython blocks
    writing to stdout, and the board deadlocks mid-script".

    That is not a hypothetical. It is what killed data_east 36 minutes into a
    run, and it is the most likely explanation for the WPC board that went
    silent for an hour on the very first bench run.

    Flashed here, a board starts running seconds before we start talking to it.
    Boards waiting their turn sit at the REPL, where inventory's probe left
    them, producing no output at all.
    """
    group(f"Flash {board['target']} on {board['port']}")
    try:
        config_path = bench.write_bench_config(board["target"], workdir)
        bench.flash(board["target"], board["port"], workdir / board["target"], config_path)
        log("flashed")
    finally:
        endgroup()


def run_matrix(board, args, just_flashed=False):
    """Walk one board through its configs. Returns (passed, failures).

    One connection per boot, held across the assertions and across setting the
    next config, closed only while the board is resetting. See Session.
    """
    port = board["port"]
    target = board["target"]
    names, configs = select_configs(target, args)

    session = Session(port, boot_timeout=args.boot_timeout)
    passed = []
    failures = []
    flakes = []
    consecutive_setup_failures = 0

    try:
        group(f"Config bundle {target} on {port}")
        try:
            # A board we just flashed is already booting - see Session.start.
            client = session.start(reset=not just_flashed)
            check_bundle(client, target, configs)
        finally:
            endgroup()

        log("")
        log(f"{len(names)} config(s) to check on {port} ({target})")
        log("")

        for index, config in enumerate(names, 1):
            started = time.monotonic()
            group(f"[{index}/{len(names)}] {target} {config}")
            first_error = None
            try:
                # Two attempts, because "this config is broken" and "this board
                # is flaky" produce the identical symptom on one attempt, and
                # they need opposite responses. A config that fails twice is a
                # config bug and fails the run; one that passes on the retry is
                # the board, and is reported as a flake instead of being
                # blamed on the config. The bench has already shown it can do
                # this - a WPC board raising ENOENT mid-boot on files that
                # exist will do it to a route just as readily.
                for attempt in range(2):
                    try:
                        with time_limit(args.config_timeout, f"{target} {config}"):
                            # Set the config on the board we are already talking
                            # to, then reboot into it. The connection dies with
                            # the reset; the next wait_for_boot opens a fresh one.
                            session.set_config(config)
                            session.reboot()
                            client = session.wait_for_boot()
                            consecutive_setup_failures = 0

                            name = check_booted_config(client, target, config, configs[config])
                        break
                    except CheckFailure as exc:
                        if attempt:
                            raise
                        first_error = exc
                        log(f"::warning::{target} {config} failed, retrying once to tell a broken config from a flaky board: {exc}")

                elapsed = time.monotonic() - started
                if first_error is None:
                    log(f"    ok  {config:20} -> {name!r}  [{elapsed:.1f}s]")
                else:
                    log(f"    ok  {config:20} -> {name!r}  [{elapsed:.1f}s] (FLAKY - failed once, passed on retry)")
                    flakes.append((config, str(first_error)))
                passed.append(config)
            except CheckFailure as exc:
                log(f"::error::{target} {config}: failed twice, so this is the config, not the board: {exc}")
                _dump_boot_log({"port": port, "boot_log": session.boot_log})
                failures.append((config, str(exc)))
                # An assertion that ran is a result about the config. Anything
                # that stopped us reaching the assertions is about the board.
                if session.client is None:
                    consecutive_setup_failures += 1
            except Exception as exc:  # noqa: BLE001 - one bad config must not end the run
                log(f"::error::{target} {config}: unexpected error: {exc}")
                failures.append((config, str(exc)))
                consecutive_setup_failures += 1
            finally:
                endgroup()

            if consecutive_setup_failures:
                # One cheap attempt at recovery before spending another cycle,
                # and it doubles as diagnosis: whether the board has anything
                # queued on its console says a lot about how it is stuck.
                session.nudge()

            if consecutive_setup_failures >= MAX_CONSECUTIVE_SETUP_FAILURES:
                remaining = names[index:]
                log(f"::error::{port} stopped responding - abandoning this board after {consecutive_setup_failures} consecutive setup failures")
                if remaining:
                    log(f"    {len(remaining)} config(s) not run: {', '.join(remaining[:8])}{' ...' if len(remaining) > 8 else ''}")
                    failures.append(("(not run)", f"{len(remaining)} config(s) skipped after {port} stopped responding"))
                break

            if not args.keep_going and failures:
                break
    finally:
        group(f"Restore {target} on {port}")
        restore_default(session, target)
        endgroup()

    return passed, failures, session.crashes, flakes


def write_step_summary(results):
    """Render the run as a table in the Actions job summary, when there is one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return

    lines = ["## HIL config matrix", "", "| board | target | configs | passed | failed |", "|---|---|---|---:|---:|"]
    for board, passed, failures in results:
        lines.append(f"| `{board['port']}` | {board['target']} | {len(passed) + len(failures)} | {len(passed)} | {len(failures)} |")

    flaky = [(board, config, reason) for board, _p, _f in results for config, reason in (board.get("flakes") or [])]
    if flaky:
        lines += ["", "### Flaky (failed once, passed on retry - the board, not the config)", ""]
        for board, config, reason in flaky:
            lines.append(f"- **{board['target']} `{config}`** - {reason.splitlines()[0]}")

    crashed = [(board, crash) for board, _passed, _failures in results for crash in (board.get("crashes") or [])]
    if crashed:
        lines += ["", "### Boot crashes (recovered by a retry)", ""]
        for board, crash in crashed:
            lines.append(f"- **{board['target']}** - {crash.splitlines()[0]}")

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
    # A healthy boot answers in 12-16s on the bench, so the flash harness's
    # 150s is generous here and only makes a dead board expensive.
    parser.add_argument("--boot-timeout", type=int, default=MATRIX_BOOT_TIMEOUT, help=f"seconds to wait for a board's web server after a reset (default {MATRIX_BOOT_TIMEOUT})")
    parser.add_argument("--config-timeout", type=int, default=CONFIG_TIMEOUT, help=f"hard ceiling on one config, in seconds (default {CONFIG_TIMEOUT})")
    args = parser.parse_args()

    bench.ensure_tools_on_path()

    workdir = REPO_ROOT / "build"
    workdir.mkdir(exist_ok=True)

    group("Inventory")
    boards = inventory()
    endgroup()

    # A board that will not answer is one board's problem. It cannot be
    # identified and so cannot be safely flashed, but the boards that do work
    # still have configs worth checking - and aborting the whole run before
    # anything is tested is how a single board left wedged by an earlier run
    # took out the next one entirely.
    unresponsive = [b for b in boards if not b.get("responsive", True)]
    boards = [b for b in boards if b.get("responsive", True)]
    for b in unresponsive:
        log(f"::error::{b['port']} is not answering - skipping it. Run dev/hil/recover.py to get it back.")
    if not boards:
        raise CheckFailure("no board on the bench is answering - run dev/hil/recover.py")

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
        # Building touches no hardware, so it all happens up front. Flashing
        # does not - see flash_before_matrix().
        for target in sorted({b["target"] for b in boards}):
            group(f"Build {target}")
            bench.build(target)
            log(f"built {target} at version {bench.source_version(target)}")
            endgroup()

    results = [({"port": b["port"], "target": "(unknown)", "crashes": [], "flakes": []}, [], [("(board setup)", "board is not answering - run dev/hil/recover.py")]) for b in unresponsive]
    for b in boards:
        try:
            just_flashed = not args.skip_flash
            if just_flashed:
                flash_before_matrix(b, workdir)
            passed, failures, crashes, flakes = run_matrix(b, args, just_flashed=just_flashed)
        except Exception as exc:  # noqa: BLE001
            # A board that cannot even be set up is one board's problem. The
            # bench is a singleton and a run is expensive, so the other boards
            # still get their matrix. Deliberately broad: the first bench run
            # died on a TimeoutExpired escaping teardown, which threw away the
            # results already in hand and skipped the untouched board entirely.
            log(f"::error::{b['target']} on {b['port']}: {exc}")
            passed, failures, crashes, flakes = [], [("(board setup)", str(exc))], [], []
        b["crashes"] = crashes
        b["flakes"] = flakes
        results.append((b, passed, failures))

    log("")
    log("stage timings:")
    for title, elapsed in _TIMINGS:
        log(f"  {elapsed:7.1f}s  {title}")

    log("")
    log("=" * 60)
    total_failures = 0
    total_crashes = 0
    for board, passed, failures in results:
        state = "FAIL" if failures else "ok"
        crashes = board.get("crashes") or []
        flaky = board.get("flakes") or []
        extra = f", {len(crashes)} boot crash(es)" if crashes else ""
        extra += f", {len(flaky)} flaky" if flaky else ""
        log(f"  {state:5} {board['port']:16} {board['target']:12} {len(passed)} passed, {len(failures)} failed{extra}")
        total_failures += len(failures)
        total_crashes += len(crashes)
    log("=" * 60)

    # A crash that a retry got past is not a passing board. The configs were
    # still checked, so it does not fail the run, but it is a firmware fault
    # and gets said out loud rather than buried in a green result.
    flaky_all = [(board, config, reason) for board, _p, _f in results for config, reason in (board.get("flakes") or [])]
    if flaky_all:
        log("")
        log(f"::warning::{len(flaky_all)} config(s) failed once and passed on retry - the board, not the config:")
        for board, config, reason in flaky_all:
            log(f"  {board['target']} {config}: {reason}")

    if total_crashes:
        log("")
        log(f"::warning::{total_crashes} boot crash(es) recovered by a retry - the firmware raised on the way up:")
        for board, _passed, _failures in results:
            for crash in board.get("crashes") or []:
                log(f"  {board['target']}: {crash}")

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
