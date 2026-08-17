#!/usr/bin/env python3
"""Flash every attached Vector board and health-check its API after boot.

Run from the repo root on the bench Pi, with the dev venv on PATH:

    python dev/hil/flash_and_check.py

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
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dev"))

from usb_coms_demo import UsbApiClient  # noqa: E402

# A bare bench board has nothing driving the game bus, so this one is correct
# and expected rather than a regression.
EXPECTED_FAULTS = {"HDWR02"}

# Floating data lines can trip the >250-transition check in main.py and send
# the board down the safe_mode path, where the game config is never loaded.
# Warned about rather than failed, but it invalidates the config assertions -
# see DESIGN.md §8 (G1).
BENCH_WARN_FAULTS = {"HDWR01"}

# Config key is the config filename without .json (dev/build.py:253).
DEFAULT_GAMENAME = {
    "sys11": "GenericSystem11_",
    "wpc": "Generic_WPC",
    "data_east": "GenericDE_",
    "em": "EM_machine_",
}

BOOT_TIMEOUT = 90
HTTP_TIMEOUT = 10


class CheckFailure(Exception):
    pass


def log(msg):
    print(msg, flush=True)


def group(title):
    print(f"::group::{title}", flush=True)


def endgroup():
    print("::endgroup::", flush=True)


# --------------------------------------------------------------------------
# 1. inventory
# --------------------------------------------------------------------------


def mpremote(*args, timeout=60):
    return subprocess.run(["mpremote", *args], capture_output=True, text=True, timeout=timeout)


def list_ports():
    result = mpremote("devs", timeout=30)
    if result.returncode != 0:
        raise CheckFailure(f"`mpremote devs` failed: {result.stderr.strip()}")
    return [line.split()[0] for line in result.stdout.strip().splitlines() if line.strip()]


def probe(port):
    """Return {port, chip_id, system, version} for one board.

    chip_id comes from the RP2040 itself so it survives any firmware state;
    system/version come from the flashed firmware and may be missing if the
    board is unflashed or broken.
    """
    board = {"port": port, "chip_id": None, "system": None, "version": None}

    chip = mpremote(
        "connect", port, "exec",
        "from machine import unique_id;from binascii import hexlify;print(hexlify(unique_id()).decode())",
        timeout=30,
    )
    if chip.returncode == 0:
        board["chip_id"] = chip.stdout.strip()

    info = mpremote(
        "connect", port, "exec",
        "import systemConfig;print(systemConfig.vectorSystem, systemConfig.SystemVersion)",
        timeout=30,
    )
    if info.returncode == 0 and info.stdout.strip():
        parts = info.stdout.split()
        board["system"] = parts[0]
        if len(parts) > 1:
            board["version"] = parts[1]

    return board


def inventory():
    boards = [probe(port) for port in list_ports()]
    if not boards:
        raise CheckFailure("no boards found - check the USB hub and power")

    log(f"{'port':16} {'chip id':18} {'running':12} version")
    for b in boards:
        log(f"{b['port']:16} {b['chip_id'] or '?':18} {b['system'] or '(none)':12} {b['version'] or '-'}")
    return boards


# --------------------------------------------------------------------------
# 2. resolve
# --------------------------------------------------------------------------


def parse_board_map(raw):
    """Parse VECTOR_HIL_BOARD_MAP: 'chipid=target,chipid=target'."""
    mapping = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise CheckFailure(f"bad VECTOR_HIL_BOARD_MAP entry {entry!r}, expected chipid=target")
        chip, target = entry.split("=", 1)
        mapping[chip.strip()] = target.strip()
    return mapping


def resolve_targets(boards, board_map):
    """Decide the target for each board, refusing to guess when it matters.

    An explicit chip-id map is authoritative. Without one we fall back to what
    each board's firmware reports, which is only trustworthy when every board
    reports something different - if two boards claim the same system, that is
    the signature of a previous mis-flash rather than of the hardware, and
    flashing on that basis would silently perpetuate it.
    """
    if board_map:
        unmapped = [b for b in boards if b["chip_id"] not in board_map]
        if unmapped:
            raise CheckFailure(
                "VECTOR_HIL_BOARD_MAP is set but does not cover: "
                + ", ".join(f"{b['port']} ({b['chip_id']})" for b in unmapped)
            )
        for b in boards:
            b["target"] = board_map[b["chip_id"]]
        log("targets from VECTOR_HIL_BOARD_MAP")
        return boards

    missing = [b for b in boards if not b["system"]]
    if missing:
        raise CheckFailure(
            "cannot identify "
            + ", ".join(b["port"] for b in missing)
            + " - firmware did not report a system. Set VECTOR_HIL_BOARD_MAP."
        )

    systems = [b["system"] for b in boards]
    duplicates = {s for s in systems if systems.count(s) > 1}
    if duplicates:
        raise CheckFailure(
            "refusing to flash from autodetection: "
            + ", ".join(sorted(duplicates))
            + " is reported by more than one board.\n"
            "Detection reads the *flashed firmware*, not the hardware, so duplicates mean\n"
            "at least one board is running firmware for a system it is not wired for.\n"
            "Pin them explicitly instead, using the chip ids above:\n"
            "  VECTOR_HIL_BOARD_MAP="
            + ",".join(f"{b['chip_id']}=<target>" for b in boards)
        )

    for b in boards:
        b["target"] = b["system"]
    log("targets from firmware self-report (all distinct)")
    return boards


# --------------------------------------------------------------------------
# 3. build
# --------------------------------------------------------------------------


def source_version(target):
    config = REPO_ROOT / "src" / target / "systemConfig.py"
    match = re.search(r'SystemVersion\s*=\s*"([^"]+)"', config.read_text())
    if not match:
        raise CheckFailure(f"could not read SystemVersion from {config}")
    return match.group(1)


def build(target):
    build_dir = REPO_ROOT / "build" / target
    result = subprocess.run(
        [sys.executable, "dev/build.py", "--target_hardware", target, "--build-dir", str(build_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        log(result.stdout[-3000:])
        log(result.stderr[-3000:])
        raise CheckFailure(f"build failed for {target}")
    return build_dir


# --------------------------------------------------------------------------
# 4. flash
# --------------------------------------------------------------------------


def write_bench_config(target, workdir):
    ssid = os.environ.get("VECTOR_HIL_WIFI_SSID", "")
    password = os.environ.get("VECTOR_HIL_WIFI_PASSWORD", "")
    game_password = os.environ.get("VECTOR_HIL_GAME_PASSWORD", "hiltest")

    if not ssid or not password:
        raise CheckFailure("VECTOR_HIL_WIFI_SSID / VECTOR_HIL_WIFI_PASSWORD are not set")

    # dev/flash.py builds a MicroPython snippet with single-quoted values, so a
    # single quote anywhere here would produce a syntax error on the board
    # rather than an obvious failure here.
    for name, value in (("ssid", ssid), ("password", password), ("game password", game_password)):
        if "'" in value or "\\" in value:
            raise CheckFailure(f"bench {name} contains a quote or backslash, which dev/flash.py cannot write")

    config = {
        "ssid": ssid,
        "password": password,
        "gamename": DEFAULT_GAMENAME[target],
        "Gpassword": game_password,
    }
    path = workdir / f"hil-config-{target}.json"
    path.write_text(json.dumps(config))
    return path


def flash(target, port, build_dir, config_path):
    result = subprocess.run(
        [sys.executable, "dev/flash.py", str(build_dir), "--port", port, "--write-config", str(config_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        log(result.stdout[-3000:])
        log(result.stderr[-3000:])
        raise CheckFailure(f"flash failed for {target} on {port}")


# --------------------------------------------------------------------------
# 5. health
# --------------------------------------------------------------------------


def wait_for_api(port, timeout=BOOT_TIMEOUT):
    """Poll the USB API until the board answers, or give up."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        client = None
        try:
            client = UsbApiClient.from_device(port=port, timeout=5)
            response = client.send_and_receive(route="/api/version", payload=None, timeout=5)
            if response.get("status") == 200:
                return client
        except Exception as exc:  # serial not ready, board mid-boot, no response yet
            last_error = exc
        if client:
            try:
                client.close()
            except Exception:
                pass
        time.sleep(3)
    raise CheckFailure(f"{port} did not answer the USB API within {timeout}s (last error: {last_error})")


def get(client, route, expect=200):
    response = client.send_and_receive(route=route, payload=None, timeout=15)
    status = response.get("status")
    if status != expect:
        raise CheckFailure(f"{route} returned {status}, expected {expect}")
    return response.get("body")


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

    expected_config = DEFAULT_GAMENAME[target]
    if safe_mode:
        log("    skipping active-config check (board is in safe mode)")
    else:
        active = get(client, "/api/game/active_config")
        active_name = active.get("name") if isinstance(active, dict) else active
        log(f"    active config: {active_name}")
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


def http_get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "vector-hil"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.status, response.read()


def health_check_http(board):
    ip = board.get("ip")
    if not ip:
        raise CheckFailure("board reported no IP address - it did not join the bench wifi")

    status, body = http_get(f"http://{ip}/api/version")
    if status != 200:
        raise CheckFailure(f"http /api/version returned {status}")
    payload = json.loads(body)
    log(f"    http {ip} /api/version -> {payload}")

    usb_version = board["usb_version"]
    if str(payload.get("version")) != str(usb_version):
        raise CheckFailure(f"http version {payload.get('version')} disagrees with USB {usb_version}")

    status, body = http_get(f"http://{ip}/")
    if status != 200:
        raise CheckFailure(f"http / returned {status}")
    if b"<html" not in body[:2000].lower():
        raise CheckFailure("http / did not return an HTML page")
    log(f"    http {ip} / -> 200, {len(body)} bytes")

    status, _ = http_get(f"http://{ip}/api/fault")
    if status != 200:
        raise CheckFailure(f"http /api/fault returned {status}")


# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-http", action="store_true", help="USB checks only; do not exercise the network stack")
    parser.add_argument("--skip-flash", action="store_true", help="health-check what is already on the boards")
    parser.add_argument("--inventory-only", action="store_true",
                        help="print each board's chip id and stop - use this to build VECTOR_HIL_BOARD_MAP")
    args = parser.parse_args()

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
            b["client"] = wait_for_api(b["port"])
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
            failures.append(f"{b['port']} ({b['target']}): {exc}")
        except Exception as exc:
            log(f"::error::unexpected error: {exc}")
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
