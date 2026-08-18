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
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dev"))

import serial  # noqa: E402  (ships with mpremote)
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

# Boot is slow and variable, so we watch the console for the firmware saying
# it is ready rather than guessing at a delay.
#
# "Server: Loop Forever" is the correct marker and the only one: phew prints
# it immediately before loop.run_forever() (phew/server.py:381). The earlier
# "> starting web server on port 80" line is NOT a ready signal - it is
# printed before start_server is even scheduled, let alone bound, so matching
# it returns while the socket is still closed. backend.go() has already run
# connect_to_wifi() by this point, so the marker covers both transports.
READY_MARKER = "Server: Loop Forever"

# The marker is printed just *before* run_forever(), so give the event loop a
# moment to actually accept the listening socket. http_get's retries cover any
# remainder.
SERVER_SETTLE_SECONDS = 2

BOOT_TIMEOUT = 150
HTTP_TIMEOUT = 10

# Read-only routes exercised over HTTP. Kept side-effect free so the check can
# run against a board repeatedly without changing its state.
HTTP_ROUTES = (
    "/api/version",
    "/api/fault",
    "/api/game/name",
    "/api/game/status",
    "/api/game/active_config",
    "/api/game/configs_list",
    "/api/leaders",
    "/api/players",
    "/api/machine_id",
    "/api/wifi/status",
    "/api/settings/get_tournament_mode",
    "/api/auth/challenge",
)


class CheckFailure(Exception):
    pass


def log(msg):
    print(msg, flush=True)


_TIMINGS = []
_group = None


def group(title):
    global _group
    _group = (title, time.monotonic())
    print(f"::group::{title}", flush=True)


def endgroup():
    global _group
    if _group:
        title, started = _group
        elapsed = time.monotonic() - started
        _TIMINGS.append((title, elapsed))
        print(f"  [{elapsed:.1f}s]", flush=True)
        _group = None
    print("::endgroup::", flush=True)


# --------------------------------------------------------------------------
# 1. inventory
# --------------------------------------------------------------------------


def ensure_tools_on_path():
    """Put the bench venv's bin dir on PATH and pick the interpreter to use.

    The harness gets run three ways - from an Actions job, from a login shell,
    and by hand - and only the first has the runner's .env applied. dev/build.py
    shells out to a bare `mpy-cross` and dev/flash.py to a bare `mpremote`, so
    PATH has to be right for subprocesses too, not just for our own calls.
    """
    candidates = []
    if os.environ.get("VECTOR_HIL_VENV"):
        candidates.append(Path(os.environ["VECTOR_HIL_VENV"]) / "bin")
    candidates.append(Path(sys.executable).parent)
    candidates.append(REPO_ROOT / ".venv" / "bin")

    for bindir in candidates:
        if (bindir / "mpremote").exists():
            os.environ["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
            python = bindir / "python"
            return str(python) if python.exists() else sys.executable

    if shutil.which("mpremote"):
        return sys.executable

    raise CheckFailure(
        "mpremote not found. Run with the bench venv, e.g.\n"
        f"  cd {REPO_ROOT} && PATH=\"$PWD/.venv/bin:$PATH\" .venv/bin/python dev/hil/flash_and_check.py ...\n"
        "(VECTOR_HIL_VENV is exported by the runner service, so it is not set in a login shell.)"
    )


VENV_PYTHON = sys.executable


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


IDENTIFY_SNIPPET = """
import machine, time
try:
    import BoardLED as L
    L.startUp()
except Exception:
    L = None
led = machine.Pin("LED", machine.Pin.OUT)
for i in range({blinks}):
    led.on()
    if L:
        L.ledColor(L.BLUE)
    time.sleep(0.25)
    led.off()
    if L:
        L.ledColor(L.BLACK)
    time.sleep(0.25)
"""


def identify(boards, seconds=8):
    """Blink each board in turn so a human can tell which is which.

    Uses the Pico W onboard LED, which works from the REPL no matter what
    firmware is loaded, plus the Vector board's WS2812 in blue when the
    flashed firmware happens to provide the driver.
    """
    log(f"Blinking each board for ~{seconds}s. Watch the bench and note the order.")
    log("")
    for index, board in enumerate(boards, 1):
        log(f"  [{index}/{len(boards)}] BLINKING NOW: {board['port']}  chip {board['chip_id']}")
        result = mpremote(
            "connect", board["port"], "exec",
            IDENTIFY_SNIPPET.format(blinks=int(seconds / 0.5)),
            timeout=seconds + 30,
        )
        if result.returncode != 0:
            log(f"        could not blink this board: {result.stderr.strip()}")
        else:
            log("        done")
    log("")
    log("Now map what you saw to the chip ids, and put this in the runner's .env:")
    log("")
    log("  VECTOR_HIL_BOARD_MAP=" + ",".join(f"{b['chip_id']}=<target>" for b in boards))


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
        [VENV_PYTHON, "dev/build.py", "--target_hardware", target, "--build-dir", str(build_dir)],
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
        [VENV_PYTHON, "dev/flash.py", str(build_dir), "--port", port, "--write-config", str(config_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        log(result.stdout[-3000:])
        log(result.stderr[-3000:])
        raise CheckFailure(f"flash failed for {target} on {port}")


# --------------------------------------------------------------------------
# 5. health
# --------------------------------------------------------------------------


def wait_for_server(port, timeout=BOOT_TIMEOUT):
    """Watch the boot console until the firmware reports its web server is up.

    Polling an API that is not listening yet tells you nothing about why, and
    burns the whole timeout when a board fails to boot. Reading the console
    instead gives an exact ready signal and, on failure, the boot log that
    explains it.

    Returns the open serial connection so the USB API can reuse it - the
    Pico exposes one CDC endpoint, so a second connection would fight this one.
    """
    deadline = time.monotonic() + timeout
    transcript = []
    connection = None

    while time.monotonic() < deadline:
        if connection is None:
            try:
                # The port disappears and re-enumerates across the reset, so a
                # failure to open here is expected for the first second or two.
                connection = serial.Serial(port=port, baudrate=115200, timeout=1)
            except Exception:
                time.sleep(1)
                continue
        try:
            raw = connection.readline()
        except Exception:
            try:
                connection.close()
            except Exception:
                pass
            connection = None
            continue

        if not raw:
            continue
        text = raw.decode(errors="replace").rstrip("\r\n")
        if not text:
            continue
        transcript.append(text)

        if READY_MARKER in text:
            elapsed = timeout - (deadline - time.monotonic())
            log(f"    server up after {elapsed:.1f}s ({text.strip()!r})")
            time.sleep(SERVER_SETTLE_SECONDS)
            return connection, transcript

    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass

    tail = "\n      ".join(transcript[-20:]) or "(nothing on the console)"
    raise CheckFailure(
        f"{port} never reported its web server within {timeout}s. Last console output:\n      {tail}"
    )


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
    for route in HTTP_ROUTES:
        status, body = http_get(f"{base}{route}")
        if status != 200:
            raise CheckFailure(f"http {route} returned {status}")
        try:
            payloads[route] = json.loads(body)
        except json.JSONDecodeError:
            raise CheckFailure(f"http {route} did not return JSON: {body[:120]!r}")
        log(f"    GET {route:34} 200  {_summarise(payloads[route])}")

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


# --------------------------------------------------------------------------


def _dump_boot_log(board, lines=25):
    """Show what the board actually said. A failed health check is usually
    explained by the boot output, and by this point we already have it."""
    transcript = board.get("boot_log")
    if not transcript:
        return
    log(f"    last {min(lines, len(transcript))} lines of {board['port']} boot console:")
    for line in transcript[-lines:]:
        log(f"      {line}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-http", action="store_true", help="USB checks only; do not exercise the network stack")
    parser.add_argument("--skip-flash", action="store_true", help="health-check what is already on the boards")
    parser.add_argument("--inventory-only", action="store_true",
                        help="print each board's chip id and stop - use this to build VECTOR_HIL_BOARD_MAP")
    parser.add_argument("--identify", action="store_true",
                        help="blink each board in turn so you can tell which physical board is which")
    args = parser.parse_args()

    global VENV_PYTHON
    VENV_PYTHON = ensure_tools_on_path()

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
            connection, boot_log = wait_for_server(b["port"])
            b["boot_log"] = boot_log
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
