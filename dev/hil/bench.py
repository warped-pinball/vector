#!/usr/bin/env python3
"""Shared bench plumbing for the hardware-in-the-loop harnesses.

Everything here is about *getting a board into a known state and talking to
it*: enumerating what is attached, deciding what each board should be flashed
with, building and flashing it, and waiting for the firmware to come up on the
other side of a reset.

The assertions live in the harnesses that import this:

  flash_and_check.py  - one flash per board, then a broad API health check
  config_matrix.py    - one flash per board, then every game config in turn

Nothing in here asserts anything about firmware behaviour, so a change to what
a harness checks does not belong in this file.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "dev"))

import serial  # noqa: E402  (ships with mpremote)
from usb_coms_demo import UsbApiClient  # noqa: E402,F401  (re-exported by this module)

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


VENV_PYTHON = sys.executable


def ensure_tools_on_path():
    """Put the bench venv's bin dir on PATH and pick the interpreter to use.

    Sets VENV_PYTHON, which build() and flash() shell out to, and returns it.

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

    global VENV_PYTHON

    for bindir in candidates:
        if (bindir / "mpremote").exists():
            os.environ["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
            python = bindir / "python"
            VENV_PYTHON = str(python) if python.exists() else sys.executable
            return VENV_PYTHON

    if shutil.which("mpremote"):
        VENV_PYTHON = sys.executable
        return VENV_PYTHON

    raise CheckFailure(
        "mpremote not found. Run with the bench venv, e.g.\n"
        f"  cd {REPO_ROOT} && PATH=\"$PWD/.venv/bin:$PATH\" .venv/bin/python dev/hil/<harness>.py ...\n"
        "(VECTOR_HIL_VENV is exported by the runner service, so it is not set in a login shell.)"
    )


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


def reset_board(port):
    """Reset the board so we own the boot we are about to watch.

    The ready marker is printed exactly once per boot. dev/flash.py already
    resets at the end of flashing, but flashing runs over every board before
    any health check starts, so by the time we open a console the board booted
    a minute ago and the marker is long gone. Resetting here makes the wait
    deterministic and the reported boot time meaningful.
    """
    result = mpremote(
        "connect", port, "exec", "--no-follow", "import machine; machine.reset()",
        timeout=30,
    )
    if result.returncode != 0:
        raise CheckFailure(f"could not reset {port} before the health check: {result.stderr.strip()}")


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


def prime_usb(connection):
    """Clear both ends of the serial line before the first API request.

    usb_comms accumulates stdin characters into a module-level `buffer` until
    it sees a newline (usb_comms.py:132). Anything left there without a
    terminator - a partial line, stray bytes from the raw-REPL session that
    issued the reset - silently prefixes the next request, so the board parses
    a route like "\x02/api/version", fails the `_routes` lookup and answers
    404. A lone newline flushes whatever is pending into a discarded request.
    """
    try:
        connection.reset_input_buffer()
        connection.reset_output_buffer()
        connection.write(b"\n")
        connection.flush()
    except Exception as exc:
        log(f"    warning: could not prime the USB link: {exc}")
        return
    # usb_request_handler is scheduled every 1000ms (phew/server.py:342), so
    # give it a turn to consume the flush before the first real request.
    time.sleep(1.5)
    try:
        connection.reset_input_buffer()
    except Exception:
        pass


def get(client, route, expect=200):
    response = client.send_and_receive(route=route, payload=None, timeout=15)
    status = response.get("status")
    if status != expect:
        # The board narrates its own routing failures ("USB REQ: route not
        # found: ..."), but the client discards every line that is not a
        # response. Drain whatever is pending so the reason is visible.
        raise CheckFailure(
            f"{route} returned {status}, expected {expect}"
            f"{_drain_serial(client.ser)}"
        )
    return response.get("body")


def _drain_serial(connection, limit=12):
    """Return any pending board chatter, formatted for an error message."""
    try:
        time.sleep(0.5)
        pending = connection.read(connection.in_waiting or 0)
    except Exception:
        return ""
    if not pending:
        return ""
    lines = [line for line in pending.decode(errors="replace").splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n      board said: " + "\n      board said: ".join(lines[:limit])


# --------------------------------------------------------------------------
# reporting
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


# --------------------------------------------------------------------------
# game configuration
# --------------------------------------------------------------------------


def gamename_field_bytes():
    """Width of the `gamename` field in the FRAM `configuration` record.

    Read out of the firmware source rather than hard-coded, so that widening
    the field is picked up here instead of silently leaving a stale limit in
    the harness. A filename longer than this cannot round-trip: struct.pack
    truncates the value, the truncated name matches no config, and the board
    boots on safe defaults with CONF01 raised.
    """
    source = (REPO_ROOT / "src" / "common" / "SPI_DataStore.py").read_text()
    match = re.search(r'"<32s32s(\d+)s\d+s"', source)
    if not match:
        raise CheckFailure("could not find the configuration record format in SPI_DataStore.py")
    return int(match.group(1))


SET_CONFIG_SNIPPET = ";".join(
    [
        "import SPI_DataStore as ds",
        "c = ds.read_record('configuration')",
        "c['gamename'] = '{gamename}'",
        "ds.write_record('configuration', c)",
        "print('GAMENAME=' + ds.read_record('configuration')['gamename'])",
    ]
)


def set_game_config(port, gamename):
    """Point a board at one game config and prove the value survived the write.

    The board picks its config up from the FRAM `configuration` record at boot
    (GameDefsLoad.go), so setting it is a REPL write plus a reset - no
    authentication, no HTTP, and no reflash. mpremote interrupts whatever the
    board is running to get the REPL, which is fine here because the caller
    resets immediately afterwards.

    The read-back is the load-bearing part. `gamename` is a fixed-width field
    and struct.pack truncates silently, so a name that is too long is written,
    accepted, and then never matches any config on the next boot. Catching it
    here costs nothing; catching it after the boot costs a boot cycle and
    reports a confusing CONF01.
    """
    if "'" in gamename or "\\" in gamename:
        raise CheckFailure(f"config name {gamename!r} contains a quote or backslash")

    result = mpremote("connect", port, "exec", SET_CONFIG_SNIPPET.format(gamename=gamename), timeout=60)
    if result.returncode != 0:
        raise CheckFailure(f"could not write gamename={gamename!r} to {port}: {result.stderr.strip()}")

    stored = None
    for line in result.stdout.splitlines():
        if line.startswith("GAMENAME="):
            stored = line.split("=", 1)[1].strip()
    if stored is None:
        raise CheckFailure(f"board did not read back a gamename after the write (said {result.stdout.strip()!r})")

    if stored != gamename:
        limit = gamename_field_bytes()
        detail = ""
        if len(gamename) > limit:
            detail = f" - the FRAM `gamename` field is {limit} bytes and this filename is {len(gamename)}," " so no board can ever store it and the config is unreachable in the field"
        raise CheckFailure(f"wrote gamename={gamename!r} but the board stored {stored!r}{detail}")
