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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench import (  # noqa: E402
    _TIMINGS,
    BENCH_WARN_FAULTS,
    DEFAULT_GAMENAME,
    EXPECTED_FAULTS,
    HTTP_TIMEOUT,
    REPO_ROOT,
    CheckFailure,
    UsbApiClient,
    _dump_boot_log,
    build,
    endgroup,
    ensure_tools_on_path,
    flash,
    get,
    group,
    identify,
    inventory,
    log,
    parse_board_map,
    prime_usb,
    reset_board,
    resolve_targets,
    source_version,
    wait_for_server,
    write_bench_config,
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
        log(f"::warning::{board['port']} raised {sorted(warned)} - bare-board bus noise, "
            "the board is in safe mode and the game config was NOT loaded")
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
        raise CheckFailure(
            f"http lists {len(http_configs)} configs, USB lists {board['usb_config_count']}"
        )

    # Authentication is enforced over HTTP and deliberately bypassed over USB
    # (backend.py:280), so this is the only transport that can prove the gate
    # works. password_check is the one auth route with no side effects.
    status = http_status(f"{base}/api/auth/password_check")
    if status != 401:
        raise CheckFailure(
            f"/api/auth/password_check returned {status} without credentials, expected 401 - "
            "HTTP authentication is not being enforced"
        )
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-http", action="store_true", help="USB checks only; do not exercise the network stack")
    parser.add_argument("--skip-flash", action="store_true", help="health-check what is already on the boards")
    parser.add_argument("--inventory-only", action="store_true",
                        help="print each board's chip id and stop - use this to build VECTOR_HIL_BOARD_MAP")
    parser.add_argument("--identify", action="store_true",
                        help="blink each board in turn so you can tell which physical board is which")
    args = parser.parse_args()

    ensure_tools_on_path()

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
        log("")
        log("The boards are dedicated to the bench, so pin them by chip id once and")
        log("autodetection stops mattering. Put this in the runner's .env, filling in")
        log("the target for each (sys11, wpc, data_east, em, whitestar, classic):")
        log("")
        log("  VECTOR_HIL_BOARD_MAP=" + ",".join(f"{b['chip_id']}=<target>" for b in boards))
        log("")
        log("Then: cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh start")
        return 0

    workdir = REPO_ROOT / "build"
    workdir.mkdir(exist_ok=True)
    failures = []

    group("Inventory")
    boards = inventory()
    endgroup()

    group("Resolve targets")
    boards = resolve_targets(boards, parse_board_map(os.environ.get("VECTOR_HIL_BOARD_MAP")))
    for b in boards:
        log(f"  {b['port']}  ->  {b['target']}")
    endgroup()

    if not args.skip_flash:
        for target in sorted({b["target"] for b in boards}):
            group(f"Build {target}")
            build(target)
            log(f"built {target} at version {source_version(target)}")
            endgroup()

        for b in boards:
            group(f"Flash {b['target']} on {b['port']}")
            try:
                config_path = write_bench_config(b["target"], workdir)
                flash(b["target"], b["port"], REPO_ROOT / "build" / b["target"], config_path)
                log("flashed")
            except CheckFailure as exc:
                log(f"::error::{exc}")
                failures.append(f"{b['port']} ({b['target']}): {exc}")
                b["skip"] = True
            endgroup()

    for b in boards:
        if b.get("skip"):
            continue
        group(f"Health check {b['target']} on {b['port']}")
        try:
            reset_board(b["port"])
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

    log("")
    log("stage timings (build cost on the Zero 2 W is the number to watch):")
    for title, elapsed in _TIMINGS:
        log(f"  {elapsed:7.1f}s  {title}")

    log("")
    log("=" * 60)
    for b in boards:
        state = "FAIL" if any(b["port"] in f for f in failures) else "ok"
        log(f"  {state:5} {b['port']:16} {b['target']:12} {b.get('ip') or ''}")
    log("=" * 60)

    if failures:
        log(f"\n{len(failures)} board(s) failed:")
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
