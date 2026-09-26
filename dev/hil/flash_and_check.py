#!/usr/bin/env python3
"""Flash every attached Vector board and health-check its API after boot.

Run from the repo root on the bench Pi:

    cd ~/vector && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python dev/hil/flash_and_check.py

Inside an Actions job the runner's .env already provides VECTOR_HIL_VENV, so
plain `python dev/hil/flash_and_check.py` is enough there. In a login shell it
is not - .env is read by the runner service, not by your shell.

Stages, in order:

  1. inventory   - probe every attached board for its RP2040 chip id and the
                   system its *current firmware* reports
  2. resolve     - decide which target each board should be flashed with
  3. build       - build each needed target once
  4. flash       - wipe, copy, write bench config, reboot
  5. health      - wait for boot, then exercise the API over USB and HTTP

A note on identification, because it is the subtle part: nothing on the board
reports what *hardware* it is. ``systemConfig.vectorSystem`` is a build-time
constant baked into whatever was last flashed, and ``machine.unique_id()`` is
the RP2040 chip id - stable per board, but it says nothing about which system
the board is wired for. So "autodetection" can only tell you what a board is
currently *running*, which is exactly wrong after a mis-flash. See
resolve_targets() for how that is handled.
"""

import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trench_coat  # noqa: E402
from bench import (  # noqa: E402
    _TIMINGS,
    _drain_serial,
    BENCH_WARN_FAULTS,
    DEFAULT_GAMENAME,
    EXPECTED_FAULTS,
    HTTP_TIMEOUT,
    REPO_ROOT,
    CheckFailure,
    UsbApiClient,
    _dump_boot_log,
    as_block,
    board_map_instructions,
    build,
    check_bench_complete,
    endgroup,
    ensure_tools_on_path,
    flash_boards,
    get,
    group,
    identify,
    inventory,
    log,
    parse_board_map,
    prime_usb,
    reset_board_with_drain,
    resolve_targets,
    source_version,
    wait_for_server,
    wait_out_post_flash_boot,
)

# Read-only routes exercised over HTTP. Kept side-effect free so the check can
# run against a board repeatedly without changing its state.
# Route -> expected body kind. Not everything is JSON: /api/game/name is
# documented as "Plain-text game name" (backend.py:451) and returns a bare
# string, even though route_wrapper still labels it application/json.
HTTP_ROUTES = (
    ("/api/version", "json"),
    ("/api/fault", "json"),
    ("/api/game/name", "text"),
    ("/api/game/status", "json"),
    ("/api/game/active_config", "json"),
    ("/api/game/configs_list", "json"),
    ("/api/leaders", "json"),
    ("/api/players", "json"),
    ("/api/machine_id", "json"),
    ("/api/wifi/status", "json"),
    ("/api/settings/get_tournament_mode", "json"),
    ("/api/auth/challenge", "json"),
)


# --------------------------------------------------------------------------
# machine id
# --------------------------------------------------------------------------
#
# Origin identifies a machine by this one value: it is the only field every
# datagram carries (src/common/origin.py:98), so a board that reports a wrong
# id is attributed to the wrong machine, and one that cannot report an id at
# all drops out of Origin entirely. Both failures are invisible from the board
# - it keeps serving scores happily - which is what makes it bench work.
#
# It is also the one piece of the API that is *not* pure shared code.
# origin.get_machine_id() is common to every target, but it leans on two things
# that come from the MicroPython image rather than from src/: machine.unique_id()
# and binascii.crc32. The bench runs a different image per system (see
# dev/hil/trench_coat.py TARGET_UF2 - Data East has its own UF2), so "does this
# work on this hardware" genuinely cannot be answered anywhere but here.

# crc32 folded to four big-endian bytes, hex-encoded (origin.py:55).
MACHINE_ID_DIGITS = 8

# An id that is arithmetically possible but means something has gone wrong:
# crc32 of an empty string is 0, which is what an empty unique_id() and an
# empty game name together produce.
DEGENERATE_MACHINE_IDS = {"00000000", "ffffffff"}


def expected_machine_id(chip_id, gamename):
    """The id this board must report, recomputed host-side.

    Mirrors origin.get_machine_id() exactly: crc32 over the hex-encoded
    machine.unique_id() concatenated with the configured game name, folded to
    four big-endian bytes and hex-encoded. Both inputs are already in hand -
    `chip_id` is that same hex unique id, read in the inventory stage
    (bench.probe), and the game name comes from /api/game/active_config, which
    reads the very FRAM record origin.py reads (backend.py:490).

    zlib.crc32 is the same CRC-32 MicroPython's binascii.crc32 computes, so the
    two values are directly comparable. Recomputing beats a shape check: a
    regex passes just as happily on an id derived from the wrong inputs, and
    "wrong inputs" is the failure mode that costs a machine its identity.
    """
    message = (chip_id or "") + (gamename or "")
    return (zlib.crc32(message.encode()) & 0xFFFFFFFF).to_bytes(4, "big").hex()


def check_machine_id(board):
    """Every board reports a machine id, and the right one.

    Failures are told apart on purpose, because they have different causes:
    a missing key or a non-200 is the route or origin.py failing on this image
    (a MicroPython build without binascii.crc32 would land here), a bad shape
    is get_machine_id() returning something that is not an id at all, and a
    mismatch against the recomputation is the value being derived from the
    wrong inputs on a board whose inputs we know.
    """
    client = board["client"]

    # A handler that raises leaves the USB bridge with nothing to send
    # (usb_comms.py:176), so the client times out rather than reporting a
    # status. That is the shape an ImportError inside get_machine_id() takes
    # from here - the most likely way this fails on one system and not the
    # others - and a bare "no response within timeout" hides it. The board
    # prints its own reason; drain it into the failure.
    try:
        payload = get(client, "/api/machine_id")
    except TimeoutError:
        raise CheckFailure(
            "/api/machine_id never answered - the handler raised on the board rather than returning, "
            "which is what origin.get_machine_id() failing on this firmware image looks like from here" + _drain_serial(client.ser)
        )

    if not isinstance(payload, dict) or "machine_id" not in payload:
        raise CheckFailure(f"/api/machine_id returned {payload!r}, expected an object with a machine_id")

    machine_id = payload["machine_id"]
    log(f"    machine id: {machine_id!r}")
    if not isinstance(machine_id, str) or not machine_id:
        raise CheckFailure(f"/api/machine_id reported {machine_id!r}, which is not an id")

    if len(machine_id) != MACHINE_ID_DIGITS or any(c not in "0123456789abcdef" for c in machine_id):
        raise CheckFailure(f"machine id {machine_id!r} is not {MACHINE_ID_DIGITS} lowercase hex digits - " "origin.get_machine_id() did not produce a crc32 (origin.py:55)")

    if machine_id in DEGENERATE_MACHINE_IDS:
        raise CheckFailure(f"machine id is {machine_id!r} - the placeholder a board reports when both inputs to " "origin.get_machine_id() came back empty, not an identity")

    # The value is cached on the board after the first call (origin.py:52). A
    # second answer that differs means the cache is not holding, and a listener
    # would see one machine turn into another mid-game.
    again = get(client, "/api/machine_id")
    repeated = again.get("machine_id") if isinstance(again, dict) else again
    if repeated != machine_id:
        raise CheckFailure(f"machine id is not stable: {machine_id!r} then {repeated!r}")

    # Same FRAM record origin.py reads, so this is the game name that went into
    # the id - not the one we think we flashed.
    active = get(client, "/api/game/active_config")
    gamename = active.get("active_config") if isinstance(active, dict) else None
    if not isinstance(gamename, str):
        raise CheckFailure(f"/api/game/active_config returned {active!r}, so the machine id's inputs cannot be checked")

    chip_id = board.get("chip_id")
    if not chip_id:
        log("::warning::this board never reported a chip id, so its machine id can only be shape-checked")
        board["machine_id"] = machine_id
        return machine_id

    expected = expected_machine_id(chip_id, gamename)
    if machine_id != expected:
        raise CheckFailure(
            f"machine id {machine_id!r} is not the {expected!r} that "
            f"crc32(unique_id + gamename) gives for this board "
            f"(unique_id {chip_id!r}, gamename {gamename!r}) - the board is deriving its identity from "
            "something other than those two inputs, so Origin will attribute it to the wrong machine"
        )

    log(f"    machine id matches crc32({chip_id} + {gamename!r})")
    board["machine_id"] = machine_id
    return machine_id


def check_machine_ids_distinct(boards):
    """No two boards may claim the same machine id.

    Origin treats the id as the machine, so a collision is not a cosmetic
    duplicate: two boards' games land in one machine's history. Distinct chip
    ids make a collision essentially impossible by construction, which is the
    point - if one shows up, the id is not being derived per board.
    """
    seen = {}
    for board in boards:
        machine_id = board.get("machine_id")
        if not machine_id:
            continue
        seen.setdefault(machine_id, []).append(f"{board['port']} ({board.get('target', '?')})")

    collisions = {machine_id: owners for machine_id, owners in seen.items() if len(owners) > 1}
    if not collisions:
        if seen:
            log(f"{len(seen)} distinct machine id(s) across {sum(len(o) for o in seen.values())} board(s)")
        return []

    failures = []
    for machine_id, owners in sorted(collisions.items()):
        message = f"machine id {machine_id} is reported by more than one board: {', '.join(owners)}"
        log(f"::error::{message}")
        failures.append(message)
    return failures


def check_faults(board):
    faults = get(board["client"], "/api/fault") or []
    if isinstance(faults, dict):
        faults = faults.get("faults", [])
    codes = {str(f)[:6] for f in faults}

    log(f"    faults: {faults if faults else 'none'}")

    unexpected = codes - EXPECTED_FAULTS - BENCH_WARN_FAULTS
    if unexpected:
        raise CheckFailure(f"unexpected fault(s): {sorted(unexpected)}")

    warned = codes & BENCH_WARN_FAULTS
    if warned:
        log(f"::warning::{board['port']} raised {sorted(warned)} - bare-board bus noise, " "the board is in safe mode and the game config was NOT loaded")
    return warned


def health_check_usb(board):
    client = board["client"]
    target = board["target"]
    expected_version = source_version(target)

    version = get(client, "/api/version")
    reported = version.get("version") if isinstance(version, dict) else version
    log(f"    version: {reported}")
    if expected_version not in str(reported):
        raise CheckFailure(f"version {reported!r} does not match built {expected_version!r}")

    safe_mode = check_faults(board)

    status = get(client, "/api/game/status")
    if not isinstance(status, dict):
        raise CheckFailure(f"/api/game/status returned {type(status).__name__}, expected an object")
    log(f"    game status keys: {sorted(status)[:6]}")

    configs = get(client, "/api/game/configs_list")
    if not isinstance(configs, dict) or not configs:
        raise CheckFailure("/api/game/configs_list is empty - config bundle missing from the build")
    log(f"    configs available: {len(configs)}")
    board["usb_config_count"] = len(configs)

    expected_config = DEFAULT_GAMENAME[target]
    if safe_mode:
        log("    skipping active-config check (board is in safe mode)")
    else:
        active = get(client, "/api/game/active_config")
        log(f"    active config: {active}")
        if expected_config not in json.dumps(active):
            raise CheckFailure(f"active config {active!r} is not the {expected_config!r} we flashed")

    check_machine_id(board)

    leaders = get(client, "/api/leaders")
    if leaders is None:
        raise CheckFailure("/api/leaders returned no body")

    # Unauthenticated over USB by design (backend.py:280) - just prove it routes.
    get(client, "/api/auth/challenge")

    wifi = get(client, "/api/wifi/status")
    log(f"    wifi: {wifi}")

    ip = None
    try:
        last_ip = get(client, "/api/last_ip")
        ip = last_ip.get("ip") if isinstance(last_ip, dict) else None
    except CheckFailure:
        pass
    return ip, wifi


def http_get(url, attempts=3):
    """GET a URL, decompressing gzip and retrying transient failures.

    The board serves its web assets pre-gzipped with Content-Encoding: gzip
    (backend.py:183) and urllib does not decompress automatically. Retries
    exist because phew is a single-threaded server on a microcontroller that
    is also fielding discovery broadcasts - an occasional dropped body is not
    a regression worth failing a bench run over.
    """
    last_error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "vector-hil"})
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.decompress(body)
                return response.status, body
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2)
    raise CheckFailure(f"GET {url} failed after {attempts} attempts: {last_error!r}")


def http_status(url):
    """Return the status code, including for responses urllib treats as errors."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "vector-hil"})
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def health_check_http(board):
    ip = board.get("ip")
    if not ip:
        raise CheckFailure("board reported no IP address - it did not join the bench wifi")
    base = f"http://{ip}"

    # The index page is served pre-gzipped; http_get transparently inflates it.
    status, body = http_get(f"{base}/")
    if status != 200:
        raise CheckFailure(f"http / returned {status}")
    head = body[:2000].lower()
    if b"<html" not in head and b"<!doctype" not in head:
        raise CheckFailure(f"http / did not return an HTML page (first bytes: {body[:80]!r})")
    log(f"    GET {'/':34} 200  {len(body)} bytes (html)")

    payloads = {}
    for route, kind in HTTP_ROUTES:
        status, body = http_get(f"{base}{route}")
        if status != 200:
            raise CheckFailure(f"http {route} returned {status}")
        if kind == "json":
            try:
                payloads[route] = json.loads(body)
            except json.JSONDecodeError:
                raise CheckFailure(f"http {route} did not return JSON: {body[:120]!r}")
            rendered = _summarise(payloads[route])
        else:
            if not body.strip():
                raise CheckFailure(f"http {route} returned an empty body")
            payloads[route] = body.decode(errors="replace").strip()
            rendered = repr(payloads[route])[:60]
        log(f"    GET {route:34} 200  {rendered}")

    # Both transports must agree. They share the route table but not the
    # plumbing, so a mismatch means one of the two bridges is misbehaving.
    http_version = str(payloads["/api/version"].get("version"))
    if http_version != str(board["usb_version"]):
        raise CheckFailure(f"http version {http_version} disagrees with USB {board['usb_version']}")

    http_configs = payloads["/api/game/configs_list"]
    if len(http_configs) != board["usb_config_count"]:
        raise CheckFailure(f"http lists {len(http_configs)} configs, USB lists {board['usb_config_count']}")

    # The id a listener on the network sees is the HTTP one, so it is the one
    # that has to be right - and it must be the same machine, whichever way you
    # ask it.
    http_payload = payloads["/api/machine_id"]
    http_machine_id = http_payload.get("machine_id") if isinstance(http_payload, dict) else http_payload
    if http_machine_id != board.get("machine_id"):
        raise CheckFailure(f"http machine id {http_machine_id!r} disagrees with USB {board.get('machine_id')!r} - " "one board is reporting two identities")

    # Authentication is enforced over HTTP and deliberately bypassed over USB
    # (backend.py:280), so this is the only transport that can prove the gate
    # works. password_check is the one auth route with no side effects.
    status = http_status(f"{base}/api/auth/password_check")
    if status != 401:
        raise CheckFailure(f"/api/auth/password_check returned {status} without credentials, expected 401 - " "HTTP authentication is not being enforced")
    log(f"    GET {'/api/auth/password_check':34} 401  (auth enforced, as expected)")

    # A challenge must not be reusable: the handler deletes it on use.
    first = http_get(f"{base}/api/auth/challenge")[1]
    second = http_get(f"{base}/api/auth/challenge")[1]
    if json.loads(first).get("challenge") == json.loads(second).get("challenge"):
        raise CheckFailure("/api/auth/challenge issued the same nonce twice")

    log(f"    {len(HTTP_ROUTES)} routes + index + auth checks OK over HTTP")


def _summarise(payload):
    """One-line rendering of a response body for the log."""
    if isinstance(payload, dict):
        if len(payload) == 1:
            key, value = next(iter(payload.items()))
            return f"{key}={value!r}"
        return f"{len(payload)} keys"
    if isinstance(payload, list):
        return f"{len(payload)} items"
    return repr(payload)[:60]


def write_step_summary(boards, failures, missing):
    """Render the run as a table in the Actions job summary, when there is one.

    Without this, a failing "flash + health check" step showed up in the HIL
    stages table as a bare `failure` - the actual reason (a board that would
    not reset, a config bundle that came up empty) only ever reached the raw
    log and the annotations panel, which is not where a developer chasing a
    red run starts looking.
    """
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return

    lines = ["## Flash + health check", "", "| board | target | machine id | result |", "|---|---|---|---|"]
    for b in boards:
        state = "FAIL" if any(b["port"] in f for f in failures) else "ok"
        lines.append(f"| `{b['port']}` | {b.get('target', '?')} | `{b.get('machine_id') or '-'}` | {state} |")
    for target in missing:
        lines.append(f"| - | {target} | - | ABSENT |")

    if failures:
        lines += ["", "### Failures", ""]
        for failure in failures:
            head, _, rest = failure.partition("\n")
            lines.append(f"- {head}")
            if rest.strip():
                lines += as_block(rest)

    with open(path, "a") as handle:
        handle.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-http", action="store_true", help="USB checks only; do not exercise the network stack")
    parser.add_argument("--skip-flash", action="store_true", help="health-check what is already on the boards")
    parser.add_argument("--inventory-only", action="store_true", help="print each board's chip id and stop - use this to build VECTOR_HIL_BOARD_MAP")
    parser.add_argument("--identify", action="store_true", help="blink each board in turn so you can tell which physical board is which")
    args = parser.parse_args()

    ensure_tools_on_path()
    board_map = parse_board_map(os.environ.get("VECTOR_HIL_BOARD_MAP"))

    if args.identify:
        group("Inventory")
        boards = inventory()
        endgroup()
        group("Identify")
        identify(boards)
        endgroup()
        return 0

    if args.inventory_only:
        group("Inventory")
        boards = inventory()
        endgroup()
        log(board_map_instructions(boards, board_map))
        return 0

    workdir = REPO_ROOT / "build"
    workdir.mkdir(exist_ok=True)
    failures = []

    # A board in BOOTSEL has no serial port, so it is invisible to every stage
    # below. Put firmware back on it first and it joins the run normally.
    trench_coat.rescue_bootsel(board_map, REPO_ROOT / "build" / "hil")

    group("Inventory")
    boards = inventory(board_map)
    endgroup()

    group("Resolve targets")
    boards = resolve_targets(boards, board_map)
    for b in boards:
        log(f"  {b['port']}  ->  {b['target']}")
    missing = check_bench_complete(boards)
    endgroup()

    if missing:
        failures.append("the bench is missing " + ", ".join(missing))

    if not args.skip_flash:
        for target in sorted({b["target"] for b in boards}):
            group(f"Build {target}")
            build(target)
            log(f"built {target} at version {source_version(target)}")
            endgroup()

        group(f"Flash {len(boards)} board(s)")
        errors = flash_boards(boards, workdir)
        for b in boards:
            if b["port"] in errors:
                failures.append(f"{b['port']} ({b['target']}): {errors[b['port']]}")
                b["skip"] = True
        endgroup()

    for b in boards:
        if b.get("skip"):
            continue
        group(f"Health check {b['target']} on {b['port']}")
        try:
            # Set by flash_boards, and absent under --skip-flash: a board we
            # did not just flash is not mid-boot and needs no grace period.
            if b.get("flashed_at") is not None:
                wait_out_post_flash_boot(b["port"], b["flashed_at"])
            reset_board_with_drain(b["port"])
            connection, boot_log = wait_for_server(b["port"])
            b["boot_log"] = boot_log
            prime_usb(connection)
            b["client"] = UsbApiClient(connection)
            ip, _wifi = health_check_usb(b)
            b["ip"] = ip
            b["usb_version"] = source_version(b["target"])
            log("    USB API OK")

            if args.skip_http:
                log("    HTTP checks skipped")
            else:
                health_check_http(b)
                log("    HTTP API OK")
        except CheckFailure as exc:
            log(f"::error::{exc}")
            _dump_boot_log(b)
            failures.append(f"{b['port']} ({b['target']}): {exc}")
        except Exception as exc:
            log(f"::error::unexpected error: {exc}")
            _dump_boot_log(b)
            failures.append(f"{b['port']} ({b['target']}): {exc}")
        finally:
            client = b.get("client")
            if client:
                try:
                    client.close()
                except Exception:
                    pass
            endgroup()

    # Across boards rather than per board, so it can only run once they have
    # all answered.
    group("Machine ids")
    failures.extend(check_machine_ids_distinct(boards))
    endgroup()

    log("")
    log("stage timings (build cost on the Zero 2 W is the number to watch):")
    for title, elapsed in _TIMINGS:
        log(f"  {elapsed:7.1f}s  {title}")

    log("")
    log("=" * 60)
    for b in boards:
        state = "FAIL" if any(b["port"] in f for f in failures) else "ok"
        log(f"  {state:5} {b['port']:16} {b['target']:12} {b.get('machine_id') or '-':10} {b.get('ip') or ''}")
    for target in missing:
        log(f"  {'ABSENT':5} {'-':16} {target}")
    log("=" * 60)

    write_step_summary(boards, failures, missing)

    if failures:
        log(f"\n{len(failures)} failure(s):")
        for failure in failures:
            log(f"  - {failure}")
        return 1

    log(f"\nall {len(boards)} board(s) flashed and healthy")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckFailure as exc:
        log(f"::error::{exc}")
        sys.exit(1)
