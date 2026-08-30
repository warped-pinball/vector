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

import concurrent.futures
import json
import os
import re
import shutil
import signal
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

# The other way a boot can end. If the application raises, MicroPython prints a
# traceback and drops to the REPL - and then nothing is ever going to print the
# ready marker, so waiting out the timeout only delays a failure we can already
# describe. These lines appear when, and only when, the program has exited:
# main.py never returns on a healthy board.
#
# Watching for this is what turns "never reported its web server within 90s"
# into the traceback that actually explains the boot.
CRASH_MARKERS = ('Type "help()" for more information.', ">>>")

# Ignore a crash marker in the first moments after opening the port: it can be
# residue from whatever REPL session issued the reset, rather than this boot.
CRASH_MARKER_GRACE = 3

# The marker is printed just *before* run_forever(), so give the event loop a
# moment to actually accept the listening socket. http_get's retries cover any
# remainder.
SERVER_SETTLE_SECONDS = 2

# Measured across 70 boots on the bench: 11.8s min, 15.5s mean, 25.6s max. The
# flash harness keeps 150s; the matrix runs a tighter one (see
# config_matrix.MATRIX_BOOT_TIMEOUT) because it pays the timeout per config.
BOOT_TIMEOUT = 150
HTTP_TIMEOUT = 10


class CheckFailure(Exception):
    pass


class BootCrash(CheckFailure):
    """The firmware raised on the way up and dropped to the REPL.

    Distinct from a timeout because it is actionable in a way a timeout is
    not: the console holds the traceback, and a retry is worth one attempt
    where waiting longer is worth nothing.
    """

    def __init__(self, message, transcript=None):
        super().__init__(message)
        self.transcript = transcript or []


def log(msg):
    print(msg, flush=True)


def _append_summary(line):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a") as handle:
            handle.write(line.replace("::warning::", "WARNING: ").replace("::error::", "ERROR: ") + "\n")
    except OSError:
        pass


def summary(line):
    """Put a line in the Actions job summary as well as the log.

    Job summaries are stored separately from the log archive, and two bench
    runs proved why that matters: the runner died mid-job, never uploaded its
    logs, and every finding went with them. Written incrementally rather than
    at the end for the same reason.
    """
    log(line)
    _append_summary(line)


def summary_once(marker, lines):
    """Log `lines`, and add them to the summary unless `marker` is there already.

    Three stages share one summary page and reach the same conclusion about
    the bench - "this board is not in the map", "this system is missing" - so
    without this the reader gets the same block three times, which reads like
    three problems. The log still says it every time, where repetition is
    exactly what you want: each step's failure explains itself.
    """
    for line in lines:
        log(line)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            if marker in Path(path).read_text():
                return
        except OSError:
            pass
    for line in lines:
        _append_summary(line)


def as_block(text):
    """A multi-line string as preformatted summary lines."""
    return ["", "```", *text.splitlines(), "```"]


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
        f'  cd {REPO_ROOT} && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python dev/hil/<harness>.py ...\n'
        "(VECTOR_HIL_VENV is exported by the runner service, so it is not set in a login shell.)"
    )


def mpremote(*args, timeout=60):
    return subprocess.run(["mpremote", *args], capture_output=True, text=True, timeout=timeout)


def list_ports():
    result = mpremote("devs", timeout=30)
    if result.returncode != 0:
        raise CheckFailure(f"`mpremote devs` failed: {result.stderr.strip()}")
    return [line.split()[0] for line in result.stdout.strip().splitlines() if line.strip()]


# --------------------------------------------------------------------------
# Boards in the ROM bootloader
# --------------------------------------------------------------------------
#
# A board in BOOTSEL/UF2 mode is not a serial device at all: the RP2040 ROM
# bootloader enumerates as USB mass storage, so `mpremote devs` shows nothing
# and every serial-based question about it - chip id, running system, is it
# alive - has no answer. A whole bench in that state reported "no boards found
# - check the USB hub and power" while `lsusb` listed all three, which is the
# most misleading thing the harness has ever said: the boards were fine, and
# one UF2 each away from working.
#
# They can still be identified. The bootrom publishes the board's unique id as
# the USB serial number, which is the same id `machine.unique_id()` returns
# once MicroPython is running, so VECTOR_HIL_BOARD_MAP covers a board in this
# state exactly as it covers a running one.

BOOTSEL_VID = "2e8a"  # Raspberry Pi
BOOTSEL_PIDS = {"0003": "RP2040", "000f": "RP2350"}  # "RP2 Boot"

USB_DEVICES = Path("/sys/bus/usb/devices")


def bootsel_boards():
    """Boards sitting in the ROM bootloader, from sysfs.

    Read straight out of sysfs rather than by shelling out to lsusb: it needs
    no privileges, no package, and it hands us the device directory, which is
    what finds the board's mass-storage drive later.
    """
    boards = []
    for device in sorted(USB_DEVICES.glob("*")):
        try:
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
        except OSError:
            # Interfaces (1-1:1.0) and the like have no ids. Not devices.
            continue
        if vendor != BOOTSEL_VID or product not in BOOTSEL_PIDS:
            continue
        try:
            chip_id = (device / "serial").read_text().strip().lower() or None
        except OSError:
            chip_id = None
        boards.append(
            {
                "port": None,
                "chip_id": chip_id,
                "system": None,
                "version": None,
                "responsive": False,
                "bootsel": True,
                "processor": BOOTSEL_PIDS[product],
                "usb_device": device,
            }
        )
    return boards


CHIP_ID_SNIPPET = "from machine import unique_id;from binascii import hexlify;print(hexlify(unique_id()).decode())"


def _ask_board(port, snippet, timeout=30):
    """Run a snippet on a board, treating a hung board as an answer of its own.

    A wedged board makes mpremote hang until its timeout rather than fail, and
    letting that propagate means one bad board aborts the whole run before
    anything has been tested. It did exactly that: a board left deadlocked by
    an earlier run took out the next run in `inventory`, before a single config
    was checked.

    One drain and one retry, because a board blocked writing to an undrained
    USB endpoint comes back the moment somebody reads it.
    """
    try:
        return mpremote("connect", port, "exec", snippet, timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f"    {port} did not answer in {timeout}s; draining its console and retrying once")
        drain_port(port)

    try:
        return mpremote("connect", port, "exec", snippet, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def probe(port):
    """Return {port, chip_id, system, version, responsive} for one board.

    chip_id comes from the RP2040 itself so it survives any firmware state;
    system/version come from the flashed firmware and may be missing if the
    board is unflashed or broken. `responsive` is False for a board that never
    answered at all - the caller decides what to do about it, but the survey
    itself always completes.
    """
    board = {"port": port, "chip_id": None, "system": None, "version": None, "responsive": True}

    chip = _ask_board(port, CHIP_ID_SNIPPET)
    if chip is None:
        board["responsive"] = False
        return board
    if chip.returncode == 0:
        board["chip_id"] = chip.stdout.strip()

    info = _ask_board(port, "import systemConfig;print(systemConfig.vectorSystem, systemConfig.SystemVersion)")
    if info is not None and info.returncode == 0 and info.stdout.strip():
        parts = info.stdout.split()
        board["system"] = parts[0]
        if len(parts) > 1:
            board["version"] = parts[1]

    return board


def inventory():
    """Survey the bench: every board on serial, plus any stuck in BOOTSEL.

    Only the serial boards are returned - a board in the bootloader cannot be
    flashed by the normal route and has to be rescued first (see
    trench_coat.rescue_bootsel) - but they are always listed, because "no
    boards found" is a wrong and expensive answer when three of them are
    sitting there as mass-storage devices.
    """
    boards = [probe(port) for port in list_ports()]
    stranded = bootsel_boards()

    log(f"{'port':16} {'chip id':18} {'running':12} version")
    for b in boards:
        if not b.get("responsive", True):
            log(f"{b['port']:16} {'NOT ANSWERING':18} {'-':12} -")
            continue
        log(f"{b['port']:16} {b['chip_id'] or '?':18} {b['system'] or '(none)':12} {b['version'] or '-'}")
    for b in stranded:
        log(f"{'(BOOTSEL)':16} {b['chip_id'] or '?':18} {'bootloader':12} {b['processor']} ROM")

    if not boards:
        raise CheckFailure(no_boards_message(stranded))
    if stranded:
        log(f"::warning::{len(stranded)} board(s) are in BOOTSEL/UF2 mode and were not surveyed - run dev/hil/recover.py to put firmware back on them")
    return boards


def usb_devices():
    """Every USB device sysfs knows about - the harness's own `lsusb`.

    Written out whenever the bench looks empty, because "no boards found" and
    "lsusb shows all three" is a contradiction the log has to be able to
    settle: it says whether the boards are absent from the bus, present under
    an id this harness does not know, or present with no driver bound.
    """
    devices = []
    for device in sorted(USB_DEVICES.glob("*")):
        try:
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
        except OSError:
            continue
        if not vendor or not product:
            continue

        def attribute(name):
            try:
                return (device / name).read_text().strip()
            except OSError:
                return ""

        devices.append(
            {
                "path": device.name,
                "id": f"{vendor}:{product}",
                "name": " ".join(filter(None, (attribute("manufacturer"), attribute("product")))) or "(no product string)",
                "serial": attribute("serial"),
            }
        )
    return devices


def usb_bus_report():
    """The USB bus as sysfs sees it, for a log that has to explain an empty bench."""
    devices = usb_devices()
    if not devices:
        return [
            "Nothing at all is on the USB bus (" + str(USB_DEVICES) + " lists no devices),",
            "which is a host-side answer rather than a board-side one: the hub is unplugged,",
            "unpowered, or this process cannot read sysfs.",
        ]

    lines = ["What is on the USB bus, as sysfs sees it:", ""]
    for device in devices:
        lines.append(f"  {device['path']:12} {device['id']:10} {device['name']}" + (f"  serial {device['serial']}" if device["serial"] else ""))

    unknown = [d for d in devices if d["id"].startswith(BOOTSEL_VID + ":")]
    if unknown:
        lines += [
            "",
            "Raspberry Pi devices are on the bus (" + ", ".join(sorted({d["id"] for d in unknown})) + ") but none of them is",
            "a serial port or a bootloader this harness recognises (" + ", ".join(f"{BOOTSEL_VID}:{pid}" for pid in BOOTSEL_PIDS) + ").",
            "That id is the thing to chase - it says what mode the boards are actually in.",
        ]
    return lines


def no_boards_message(stranded=None):
    """Why the bench looks empty, told apart from a bench that is not there."""
    stranded = bootsel_boards() if stranded is None else stranded
    if not stranded:
        return "\n".join(
            [
                "no boards found: nothing on serial, and nothing in the ROM bootloader either.",
                "",
                *usb_bus_report(),
            ]
        )
    ids = ", ".join(b["chip_id"] or "?" for b in stranded)
    return (
        f"no board is on serial, but {len(stranded)} are in the ROM bootloader (BOOTSEL/UF2 mode): {ids}.\n"
        "They are attached and healthy - they are just running the bootloader instead of firmware,\n"
        "which is what a UF2 flash that did not finish leaves behind. dev/hil/recover.py flashes them\n"
        "back; if it already ran, its output above says what stopped it."
    )


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
            "connect",
            board["port"],
            "exec",
            IDENTIFY_SNIPPET.format(blinks=int(seconds / 0.5)),
            timeout=seconds + 30,
        )
        if result.returncode != 0:
            log(f"        could not blink this board: {result.stderr.strip()}")
        else:
            log("        done")
    log("")
    log("Now map what you saw to the chip ids:")
    log(board_map_instructions(boards, parse_board_map(os.environ.get("VECTOR_HIL_BOARD_MAP"))))


# --------------------------------------------------------------------------
# 2. resolve
# --------------------------------------------------------------------------


def board_map_instructions(boards, board_map=None):
    """How to write or amend VECTOR_HIL_BOARD_MAP for this bench.

    Printed with every map-related failure: the map lives in the runner's
    .env on the bench host, so whoever reads the CI log is usually not
    looking at the machine that needs editing.
    """
    board_map = board_map or {}

    def wanted(chip_id):
        """What this board's entry should say - never what a broken one says.

        Echoing the current value back is how a wrong entry survives being
        reported: the line offered as the fix contained the very `de` that
        failed. A value the bench cannot drive is replaced by the target it
        was probably reaching for, or by a blank to fill in.
        """
        target = board_map.get(chip_id)
        if target in bench_targets():
            return target
        suggestion = suggest_target(target)
        return suggestion if suggestion in bench_targets() else "<target>"

    suggested = ",".join(f"{b['chip_id']}={wanted(b['chip_id'])}" for b in boards)
    lines = [
        "",
        "VECTOR_HIL_BOARD_MAP pins each board to the system it is wired to, by RP2040",
        "chip id (stable across reflashing). Every board on the bench must appear in it.",
        "",
        "  format:  <chip id>=<target>,<chip id>=<target>",
        "  targets: " + ", ".join(bench_targets()),
        "",
    ]
    unusable = [target for target in buildable_targets() if target not in bench_targets()]
    if unusable:
        lines += [
            "This checkout also builds " + ", ".join(unusable) + ", which the bench cannot drive:",
            "those targets have no game configs to boot against yet. A board running one of them",
            "cannot be mapped to it - and mapping it to a different system would flash the wrong",
            "firmware to real hardware.",
            "",
        ]
    if board_map:
        lines += ["current map:"] + [f"  {chip}={target}" for chip, target in sorted(board_map.items())] + [""]
    lines += [
        "Fill in the target for each board and set the whole line - it replaces the old",
        "value, so keep the entries that were already right:",
        "",
        "  VECTOR_HIL_BOARD_MAP=" + suggested,
        "",
        "On the bench host (the map is runner environment, not repo config):",
        "",
        "  # drop any existing entry, then append the new one",
        "  sed -i '/^VECTOR_HIL_BOARD_MAP=/d' ~/actions-runner/.env",
        "  echo 'VECTOR_HIL_BOARD_MAP=" + suggested + "' >> ~/actions-runner/.env",
        "  cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh start",
        "",
        "The service only reads .env at start, so the restart is required.",
        "",
        "Not sure which physical board is which chip id? Blink them in turn:",
        "",
        "  cd ~/vector && .venv/bin/python dev/hil/flash_and_check.py --identify",
        "",
        "A board in BOOTSEL cannot blink, and the id above is the one its ROM",
        "bootloader publishes. That is the same unique id MicroPython reports, but if",
        "a board ever turns up under two, map both - a spare entry costs nothing.",
        "",
        "See dev/hil/RUNNER_SETUP.md for the full walkthrough.",
    ]
    return "\n".join(lines)


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


def report_unknown_boards(unmapped, boards, board_map):
    """Say which boards the map does not cover, and how to add them.

    Written to the Actions job summary as well as the log: a board arriving on
    the bench is a one-line edit on the runner host, and whoever has to make
    it is reading the run's summary page, not scrolling a log for the chip id.
    """
    described = ", ".join(f"{b.get('port') or '(BOOTSEL)'} {b['chip_id'] or '?'}" for b in unmapped)
    summary_once(
        described,
        [
            "",
            "### Unrecognised board" + ("s" if len(unmapped) > 1 else ""),
            "",
            f"`VECTOR_HIL_BOARD_MAP` does not cover: **{described}**",
            *as_block(board_map_instructions(boards, board_map)),
        ],
    )
    return "VECTOR_HIL_BOARD_MAP is set but does not cover: " + described


def resolve_targets(boards, board_map):
    """Decide the target for each board, refusing to guess when it matters.

    An explicit chip-id map is authoritative. Without one we fall back to what
    each board's firmware reports, which is only trustworthy when every board
    reports something different - if two boards claim the same system, that is
    the signature of a previous mis-flash rather than of the hardware, and
    flashing on that basis would silently perpetuate it.
    """
    dead = [b for b in boards if not b.get("responsive", True)]
    if dead:
        raise CheckFailure(
            "not answering: " + ", ".join(b["port"] for b in dead) + ".\nA board that will not talk cannot be identified, so it cannot be safely flashed.\n" "Run dev/hil/recover.py to get it back."
        )

    if board_map:
        unmapped = [b for b in boards if b["chip_id"] not in board_map]
        if unmapped:
            raise CheckFailure(report_unknown_boards(unmapped, boards, board_map))
        for b in boards:
            b["target"] = board_map[b["chip_id"]]
        check_targets(boards, board_map)
        log("targets from VECTOR_HIL_BOARD_MAP")
        return boards

    missing = [b for b in boards if not b["system"]]
    if missing:
        raise CheckFailure("cannot identify " + ", ".join(b["port"] for b in missing) + " - firmware did not report a system. Set VECTOR_HIL_BOARD_MAP.\n" + board_map_instructions(boards, board_map))

    systems = [b["system"] for b in boards]
    duplicates = {s for s in systems if systems.count(s) > 1}
    if duplicates:
        raise CheckFailure(
            "refusing to flash from autodetection: " + ", ".join(sorted(duplicates)) + " is reported by more than one board.\n"
            "Detection reads the *flashed firmware*, not the hardware, so duplicates mean\n"
            "at least one board is running firmware for a system it is not wired for.\n"
            "Pin them explicitly instead, using the chip ids above.\n" + board_map_instructions(boards, board_map)
        )

    for b in boards:
        b["target"] = b["system"]
    check_targets(boards, board_map)
    log("targets from firmware self-report (all distinct)")
    return boards


# Every system the bench exists to cover. A run that quietly tests two of the
# three proves nothing about the third while still reporting green, which is
# worse than not running: it is a check that has stopped checking. Overridable
# for a bench that has genuinely lost a board - deliberately, by whoever runs
# it, and visibly in the log.
REQUIRED_TARGETS = ("sys11", "wpc", "data_east")


def required_targets():
    raw = os.environ.get("VECTOR_HIL_REQUIRED_TARGETS")
    if raw is None:
        return list(REQUIRED_TARGETS)
    return [target.strip() for target in raw.split(",") if target.strip()]


def check_bench_complete(boards):
    """Which required systems are not on the bench, reported where it shows.

    Returns the missing targets rather than raising: the boards that *are*
    here still have checks worth running, and a run is expensive. The caller
    keeps the result and fails the run at the end - green on two boards out of
    three is the outcome this exists to prevent.
    """
    wanted = required_targets()
    if not wanted:
        log("no required targets set - running whatever is attached")
        return []
    present = {b.get("target") for b in boards}
    missing = [target for target in wanted if target not in present]
    if not missing:
        log("bench is complete: " + ", ".join(wanted))
        return []

    have = ", ".join(f"{b['target']} ({b['port']})" for b in boards) or "nothing"
    log(f"::error::the bench is missing {', '.join(missing)} - only {have} answered")
    summary_once(
        "### Incomplete bench",
        [
            "",
            "### Incomplete bench",
            "",
            f"Missing: **{', '.join(missing)}**. Attached: {have}.",
            "",
            "A run proves nothing about a system that is not on the bench, so this fails the run rather",
            "than reporting green on two boards out of three. The boards that are here are still checked.",
            "",
            "Either put the missing board back (`dev/hil/recover.py`, and check it is in",
            "`VECTOR_HIL_BOARD_MAP`), or set `VECTOR_HIL_REQUIRED_TARGETS` on the runner to the systems",
            "the bench really has.",
        ],
    )
    return missing


# --------------------------------------------------------------------------
# 3. build
# --------------------------------------------------------------------------


# The repo's own list of what it builds - the same file the bench manifest in
# DESIGN.md §6 says a board's target must match. Read rather than restated,
# because a hardcoded copy is a list that goes stale silently.
TARGETS_JSON = REPO_ROOT / "dev" / "ci" / "targets.json"


def buildable_targets():
    """Every distinct hardware target this checkout can build.

    `hardware_id` collapses the variants that are one board with two firmware
    passes (sys11_tiny is sys11), because this list answers "what can a board
    be", not "what can be built".
    """
    try:
        entries = json.loads(TARGETS_JSON.read_text())
        targets = {entry.get("hardware_id") or entry["id"] for entry in entries}
    except (OSError, ValueError, KeyError):
        # src/common is shared code, not a system.
        targets = {path.parent.name for path in (REPO_ROOT / "src").glob("*/systemConfig.py")} - {"common"}
    return sorted(targets)


def bench_targets():
    """Targets the bench can actually flash and health-check.

    Narrower than what the tree can build, and the gap is real: `classic` and
    `whitestar` have a systemConfig.py and nothing else - no config directory,
    so no generic game config to boot them against and nothing for
    /api/game/configs_list to return. A board running one of them turned up on
    the bench and the harness had no way to say any of this: it offered four
    targets with no hint that the tree has seven, and a map entry naming one of
    the other three died on a bare KeyError three stages later.
    """
    ready = []
    for target in buildable_targets():
        config = DEFAULT_GAMENAME.get(target)
        if config and (REPO_ROOT / "src" / target / "config" / f"{config}.json").exists():
            ready.append(target)
    return ready


def target_labels():
    """{target id: human label} from the repo's target list, for suggestions."""
    labels = {}
    try:
        for entry in json.loads(TARGETS_JSON.read_text()):
            labels.setdefault(entry.get("hardware_id") or entry["id"], entry.get("label", ""))
    except (OSError, ValueError, KeyError):
        pass
    return labels


def suggest_target(name):
    """The target somebody probably meant when they wrote `name`.

    People write the name they use out loud, not the directory: the bench map
    arrived with `de` in it, which is what everyone calls the Data East board
    and is nothing like the `data_east` the tree wants. Matching the label and
    its initials as well as the id turns that from a puzzle into a correction.
    """
    wanted = (name or "").strip().lower().replace("-", "_").replace(" ", "")
    if not wanted:
        return None
    candidates = {}
    for target, label in target_labels().items():
        candidates[target.lower()] = target
        candidates[target.lower().replace("_", "")] = target
        if label:
            candidates[label.lower()] = target
            candidates["".join(c for c in label if c.isupper()).lower()] = target
    return candidates.get(wanted)


def describe_bad_target(target):
    """Why this target cannot be used, in one sentence plus the way out."""
    if target not in buildable_targets():
        suggestion = suggest_target(target)
        did_you_mean = f" - did you mean {suggestion}?" if suggestion else ""
        return f"{target!r} is not a target in this checkout{did_you_mean} The bench can drive " + ", ".join(bench_targets()) + "."
    return (
        f"{target!r} is a real build target but the bench cannot drive it: src/{target}/config holds no "
        f"generic game config to flash and boot against, so there is nothing to boot the board against. "
        f"The bench can drive " + ", ".join(bench_targets()) + "."
    )


def check_targets(boards, board_map=None):
    """Refuse targets the bench cannot drive, while they are still configuration.

    Reported like an unrecognised chip id - to the job summary, with the map
    and how to edit it - because it is the same mistake seen from the other
    end, and the same person on the same host has to fix it. Left to run, it
    would have flashed nothing and died on a bare KeyError two stages later.
    """
    bad = sorted({b["target"] for b in boards if b.get("target") not in bench_targets()}, key=str)
    if not bad:
        return

    described = [describe_bad_target(target) for target in bad]
    summary_once(
        "### Board map names a target the bench cannot use",
        [
            "",
            "### Board map names a target the bench cannot use",
            "",
            *[f"- {line}" for line in described],
            *as_block(board_map_instructions(boards, board_map or {})),
        ],
    )
    raise CheckFailure(" ".join(described))


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
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
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
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        # The output travels with the failure rather than being logged here:
        # boards are flashed concurrently, and a line printed from a worker
        # thread lands next to another board's output with nothing to say
        # which board it came from.
        tail = (result.stdout[-2000:] + result.stderr[-2000:]).strip()
        raise CheckFailure(f"flash failed for {target} on {port}:\n      " + "\n      ".join(tail.splitlines()[-20:]))


def flash_boards(boards, workdir):
    """Flash every board at once, and report per board.

    The boards are independent devices on independent serial ports, and
    dev/flash.py is one subprocess per board that spends nearly all its time
    waiting on USB - so doing them one after another just adds up the waits.
    Three boards on the bench Pi: about a minute, instead of three.

    Returns {port: error message}, empty when every board flashed.
    """

    def flash_one(board):
        started = time.monotonic()
        config_path = write_bench_config(board["target"], workdir)
        flash(board["target"], board["port"], REPO_ROOT / "build" / board["target"], config_path)
        return time.monotonic() - started

    errors = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(boards))) as pool:
        futures = {pool.submit(flash_one, board): board for board in boards}
        for future in concurrent.futures.as_completed(futures):
            board = futures[future]
            try:
                elapsed = future.result()
            except CheckFailure as exc:
                errors[board["port"]] = str(exc)
            except Exception as exc:  # noqa: BLE001 - reported per board, never fatal to the others
                errors[board["port"]] = f"{type(exc).__name__}: {exc}"
            else:
                log(f"  ok    {board['port']:16} {board['target']:12} {elapsed:5.1f}s")

    for port, error in errors.items():
        log(f"  FAIL  {port}")
        log(f"::error::{error}")
    return errors


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
        "connect",
        port,
        "exec",
        "--no-follow",
        "import machine; machine.reset()",
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

    Two ways this ends other than success: the board never gets there
    (timeout), or the firmware raises and drops to the REPL (BootCrash). They
    are worth distinguishing - a crash is described by the traceback sitting in
    the console right now, and there is no point waiting out the rest of the
    budget for a marker a dead program will never print.

    Returns the open serial connection so the USB API can reuse it - the
    Pico exposes one CDC endpoint, so a second connection would fight this one.
    """
    started = time.monotonic()
    deadline = started + timeout
    transcript = []
    connection = None

    while time.monotonic() < deadline:
        if connection is None:
            try:
                # The port disappears and re-enumerates across the reset, so a
                # failure to open here is expected for the first second or two.
                connection = open_serial(port)
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
            elapsed = time.monotonic() - started
            log(f"    server up after {elapsed:.1f}s ({text.strip()!r})")
            time.sleep(SERVER_SETTLE_SECONDS)
            return connection, transcript

        elapsed = time.monotonic() - started
        if elapsed > CRASH_MARKER_GRACE and any(marker in text for marker in CRASH_MARKERS):
            try:
                connection.close()
            except Exception:
                pass
            raise BootCrash(
                f"{port} dropped to the REPL {elapsed:.1f}s into boot - the firmware raised on the way up:\n      " + _explain_crash(transcript),
                transcript,
            )

    # Before calling it a failure: ask the board directly. The ready marker is
    # printed exactly once, so anything that costs us the moment it goes past -
    # a reset we did not trigger, a board that booted while we were still
    # flashing the next one - looks identical to a board that never came up.
    # A board that answers its API is up, whatever we did or did not see.
    if connection is not None and _server_is_answering(connection):
        log(f"::warning::{port} is answering its API but its ready marker was never seen - " "the marker was probably printed before the console was open")
        return connection, transcript

    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass

    tail = "\n      ".join(transcript[-20:]) or "(nothing on the console)"
    raise CheckFailure(f"{port} never reported its web server within {timeout}s. Last console output:\n      {tail}")


def _server_is_answering(connection):
    """One cheap USB request, to tell 'missed the marker' from 'never booted'."""
    try:
        prime_usb(connection)
        response = UsbApiClient(connection).send_and_receive(route="/api/version", payload=None, timeout=10)
        return response.get("status") == 200
    except Exception:
        return False


def _explain_crash(transcript, lines=14):
    """Pull the traceback out of a boot transcript, for the error message.

    The traceback is the whole value of catching this, so it leads; without one
    the tail of the console is the next best thing.
    """
    for index, line in enumerate(transcript):
        if "Traceback (most recent call last)" in line:
            return "\n      ".join(transcript[index : index + lines])
    return "\n      ".join(transcript[-lines:]) or "(nothing on the console)"


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
        raise CheckFailure(f"{route} returned {status}, expected {expect}" f"{_drain_serial(client.ser)}")
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
# talking to a board that might be wedged
# --------------------------------------------------------------------------
#
# Two traps, both of which cost a bench run before they were understood, and
# both the same shape as the board's own failure: blocking on a buffer that
# nothing is draining.
#
#   * `serial.Serial(timeout=...)` sets the READ timeout only. With no
#     `write_timeout` a write to a board that has stopped reading its OUT
#     endpoint blocks forever - which is exactly the state a wedged board is
#     in, and exactly when the recovery tool needs to write to it.
#   * `flush()` is termios tcdrain. It waits for the kernel's output buffer to
#     reach the device and takes no timeout at all, so it hangs on the same
#     board even when the write did not. We never call it: handing the bytes
#     to the kernel is enough, and every exchange here is synchronised by a
#     read with a deadline rather than by tcdrain.

SERIAL_READ_TIMEOUT = 1
SERIAL_WRITE_TIMEOUT = 5


def open_serial(port, baudrate=115200, read_timeout=SERIAL_READ_TIMEOUT, write_timeout=SERIAL_WRITE_TIMEOUT):
    """Open a board's port with BOTH timeouts set. Always use this."""
    return serial.Serial(port=port, baudrate=baudrate, timeout=read_timeout, write_timeout=write_timeout)


def serial_write(connection, data, what="the board"):
    """Write to a board, refusing to wait forever if it has stopped listening."""
    try:
        connection.write(data)
    except serial.SerialTimeoutException:
        raise CheckFailure(f"timed out writing to {what} after {SERIAL_WRITE_TIMEOUT}s - it has stopped draining its USB endpoint")


class time_limit:
    """Hard ceiling on a block of work, however deep it blocks.

    A backstop rather than a design: every call in here is supposed to be
    bounded, but a board in a bad enough state can block a syscall that no
    library timeout covers, and one board must never be able to hang a bench
    job. SIGALRM interrupts the syscall, so this catches cases the individual
    timeouts miss.

    Main thread and POSIX only, which is what the bench is.
    """

    def __init__(self, seconds, what):
        self.seconds = int(seconds)
        self.what = what

    def _expired(self, _signum, _frame):
        raise CheckFailure(f"{self.what} did not finish within {self.seconds}s and was interrupted")

    def __enter__(self):
        self.previous = signal.signal(signal.SIGALRM, self._expired)
        signal.alarm(self.seconds)
        return self

    def __exit__(self, *_exc):
        signal.alarm(0)
        signal.signal(signal.SIGALRM, self.previous)
        return False


# --------------------------------------------------------------------------
# raw REPL, over a connection we already hold
# --------------------------------------------------------------------------
#
# Everything below drives the REPL over an open pyserial connection instead of
# shelling out to `mpremote`. That is not a stylistic preference - it is the
# fix for a board that wedged on the bench.
#
# The Pico exposes one CDC endpoint, so using mpremote mid-run means closing
# our connection, letting a second process open the port, and reopening
# afterwards - for every config. On the first such handoff the WPC board
# (MicroPython 1.26.0-preview) stopped responding entirely: silent console, no
# reply to Ctrl-C, for the following 63 attempts. sys11 (1.24.1) survived the
# same treatment 39 times. A running board printing to a CDC endpoint that
# nothing is draining is the difference between them, so the harness now never
# leaves the port unread while the board is running, and never lets a second
# process contend for it. The port is closed only while the board is mid-reset.

CTRL_A = b"\x01"  # enter raw REPL
CTRL_B = b"\x02"  # back to the friendly REPL
CTRL_C = b"\x03"  # interrupt whatever is running
CTRL_D = b"\x04"  # execute what was pasted / end-of-output marker

RAW_REPL_BANNER = b"raw REPL; CTRL-B to exit"
REPL_TIMEOUT = 15


class Repl:
    """A raw-REPL session over a connection somebody else owns.

    Owns a pending buffer, which is the whole reason this is a class rather
    than a few functions: raw REPL is a sequence of markers (`OK`, \x04, \x04,
    `>`) and a read that syncs on one marker almost always pulls in bytes
    belonging to the next. Dropping them desynchronises everything that
    follows.
    """

    def __init__(self, connection):
        self.connection = connection
        self._pending = bytearray()

    def read_until(self, marker, timeout, what):
        """Return everything up to `marker`, keeping what came after it.

        The board is mid-sentence when we interrupt it, so the stream still
        holds application output. Syncing on a marker rather than on a line
        count is what makes that harmless.
        """
        deadline = time.monotonic() + timeout
        while True:
            index = self._pending.find(marker)
            if index >= 0:
                before = bytes(self._pending[:index])
                del self._pending[: index + len(marker)]
                return before
            if time.monotonic() >= deadline:
                break
            chunk = self.connection.read(self.connection.in_waiting or 1)
            if chunk:
                self._pending.extend(chunk)

        tail = bytes(self._pending[-400:]).decode(errors="replace")
        raise CheckFailure(f"timed out after {timeout}s waiting for {what}. Last output:\n      {tail or '(nothing on the console)'}")

    def enter(self, timeout=REPL_TIMEOUT):
        """Interrupt the running firmware and take the raw REPL.

        Ctrl-C raises KeyboardInterrupt in `main.py`, which ends the
        application and drops to the REPL - the same thing `mpremote` does, and
        the reason this is safe to do to a board we are about to reset anyway.
        """
        self._pending.clear()
        self.connection.reset_input_buffer()
        serial_write(self.connection, CTRL_C + CTRL_C, "the board's REPL")
        time.sleep(0.2)

        serial_write(self.connection, CTRL_A, "the board's REPL")
        self.read_until(RAW_REPL_BANNER, timeout, "the raw REPL prompt")
        self.read_until(b">", timeout, "the raw REPL prompt")
        return self

    def exec(self, code, timeout=REPL_TIMEOUT):
        """Run one snippet and return what it printed.

        Raw REPL framing: paste the code, Ctrl-D to run, the board answers
        `OK`, then stdout, then \x04, then the traceback (empty on success),
        then \x04.
        """
        serial_write(self.connection, code.encode() + CTRL_D, "the board's REPL")

        self.read_until(b"OK", timeout, "the board to accept the snippet")
        output = self.read_until(CTRL_D, timeout, "the snippet to finish")
        error = self.read_until(CTRL_D, timeout, "the snippet's exit status")

        if error.strip():
            detail = error.decode(errors="replace").strip().replace("\n", "\n      ")
            raise CheckFailure(f"the board raised an error running the snippet:\n      {detail}")
        return output.decode(errors="replace")

    def reset(self):
        """Reset the board, without waiting for a reply.

        There is no reply to wait for - the board reboots mid-command and the
        port re-enumerates underneath us. The caller reopens it in
        wait_for_server().
        """
        try:
            serial_write(self.connection, b"import machine; machine.reset()" + CTRL_D, "the board's REPL")
        except Exception as exc:
            raise CheckFailure(f"could not issue a reset over the REPL: {exc}")
        # Let the write reach the board before the port disappears.
        time.sleep(0.5)


def repl_reset(connection):
    """Interrupt whatever the board is doing and reset it, over `connection`."""
    Repl(connection).enter().reset()


DRAIN_SECONDS = 20
DRAIN_QUIET_SECONDS = 2


def read_until_quiet(connection, budget, quiet=DRAIN_QUIET_SECONDS):
    """Read from an open port until it stops producing, or the budget runs out.

    A board blocked writing into a CDC endpoint nothing is draining does not
    hand over its backlog in one gulp: it unblocks, runs a little further,
    prints some more, and only then goes quiet. Reading for a fixed three
    seconds catches the first mouthful and calls the board dead. That is not
    a guess - a bench run declared /dev/ttyACM0 unrecoverable after draining
    63 bytes from it, and the very next step in the same job read it with
    `cat` for eight seconds and got a healthy, running server.

    So read until it has been silent for `quiet` seconds, capped at `budget`.
    A port that is already quiet costs `quiet`; one with a backlog gets as
    long as it needs to finish coughing it up.
    """
    drained = 0
    deadline = time.monotonic() + budget
    silent_since = time.monotonic()
    while time.monotonic() < deadline:
        chunk = connection.read(connection.in_waiting or 1)
        if chunk:
            drained += len(chunk)
            silent_since = time.monotonic()
        elif time.monotonic() - silent_since >= quiet:
            break
    return drained


def interrupt_board(connection, port, keys=CTRL_C):
    """Send Ctrl-C to a board we have just finished draining.

    Returns whether the board accepted it, which is a diagnosis in its own
    right. Both callers read the console to quiet first, because that is the
    remedy for the common wedge: a firmware blocked writing to stdout is not
    reading stdin either, so the host's OUT endpoint backs up behind it and
    the write times out against the very deadlock it is trying to clear.

    A write that still times out after that is a different animal. It means
    the board is producing output happily and simply never services what we
    send it - and no amount of reading fixes that, because reading is not
    what it is waiting for. /dev/ttyACM0 has been in exactly that state for
    three runs: 85, 95 and 112 bytes read, every single write timed out.
    Retrying the write only spends another five seconds saying so.
    """
    try:
        serial_write(connection, keys, port)
        return True
    except CheckFailure as exc:
        log(f"    {exc}")
        return False


def drain_port(port, seconds=DRAIN_SECONDS):
    """Open a port, read the board's console until it goes quiet, interrupt it.

    A cheap attempt at unsticking a board, and it costs one open. The wedge
    worth recovering from is a board blocked writing into a CDC endpoint that
    nothing is draining: reading is the whole remedy, and the Ctrl-C afterwards
    gets it back to a REPL once the read has freed it - which is why the
    interrupt comes after the drain and not before. Reports what it saw either
    way; a board that yields zero bytes and a board that yields a backlog are
    different problems.
    """
    try:
        connection = open_serial(port)
    except Exception as exc:
        log(f"    could not reopen {port} to unstick it: {exc}")
        return 0

    drained = 0
    interrupted = False
    try:
        drained += read_until_quiet(connection, seconds)
        interrupted = interrupt_board(connection, port)
        # Whatever the interrupt shook loose - a KeyboardInterrupt traceback,
        # a REPL banner - is backlog too, and leaving it queued re-wedges the
        # board the moment we close.
        drained += read_until_quiet(connection, DRAIN_QUIET_SECONDS * 2)
    except Exception as exc:
        log(f"    error while draining {port}: {exc}")
    finally:
        try:
            connection.close()
        except Exception:
            pass

    log(f"    drained {drained} byte(s) from {port} and {'sent Ctrl-C' if interrupted else 'could not send Ctrl-C'}")
    return drained


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


def set_game_config(connection, gamename):
    """Point a board at one game config and prove the value survived the write.

    The board picks its config up from the FRAM `configuration` record at boot
    (GameDefsLoad.go), so setting it is a REPL write plus a reset - no
    authentication, no HTTP, and no reflash. Takes the caller's open connection
    rather than a port: see the note above raw REPL for why that matters.

    The read-back is the load-bearing part. `gamename` is a fixed-width field
    and struct.pack truncates silently, so a name that is too long is written,
    accepted, and then never matches any config on the next boot. Catching it
    here costs nothing; catching it after the boot costs a boot cycle and
    reports a confusing CONF01.
    """
    if "'" in gamename or "\\" in gamename:
        raise CheckFailure(f"config name {gamename!r} contains a quote or backslash")

    output = Repl(connection).enter().exec(SET_CONFIG_SNIPPET.format(gamename=gamename))

    stored = None
    for line in output.splitlines():
        if line.startswith("GAMENAME="):
            stored = line.split("=", 1)[1].strip()
    if stored is None:
        raise CheckFailure(f"board did not read back a gamename after the write (said {output.strip()!r})")

    if stored != gamename:
        limit = gamename_field_bytes()
        detail = ""
        if len(gamename) > limit:
            detail = f" - the FRAM `gamename` field is {limit} bytes and this filename is {len(gamename)}, so no board can ever store it and the config is unreachable in the field"
        raise CheckFailure(f"wrote gamename={gamename!r} but the board stored {stored!r}{detail}")
