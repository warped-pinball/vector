#!/usr/bin/env python3
"""Bring a wedged bench board back, without anyone walking over to it.

    cd ~/vector && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python dev/hil/recover.py

A Vector board can deadlock in a way that leaves the USB device enumerated but
the firmware gone: the port is there, `mpremote` opens it, and nothing ever
answers. TrenchCoat names the mechanism in its own source (`src/ray.py`,
`send_command`):

    if nothing ever drains the board's output, the USB CDC buffers fill up,
    MicroPython blocks writing to stdout, and the board deadlocks mid-script

That is what happened to the WPC board on the bench: silent console, no reply
to Ctrl-C, for an hour. `dev/hil/config_matrix.py` no longer creates the
condition, but a board already in it needs getting out, and the bench is
supposed to run unattended.

So this escalates, cheapest first, re-testing after each step:

  1. drain      - read whatever the board has queued and send Ctrl-C. If it is
                  blocked writing to a full CDC buffer, reading is the remedy.
  2. usb reset  - ask the kernel to re-enumerate the device (USBDEVFS_RESET).
                  Resets the host side of the link and TinyUSB's endpoint
                  state, which can free a write that is stuck on a buffer the
                  host was not draining.
  3. power      - cut and restore power to the board's hub port with uhubctl.
                  The board is USB bus powered (Trench-Coat-Install-Guide.md),
                  so this is a real power cycle, not a signal. Needs a hub that
                  supports per-port power switching.
  4. reflash    - hand the board to TrenchCoat, the team's own tool for
                  recovering a board without the BOOTSEL button. It resets into
                  the ROM bootloader, wipes the whole flash with nuke.uf2, then
                  writes the real firmware. Destructive: the board needs
                  `dev/hil/flash_and_check.py` afterwards to get Vector back.

Only step 4 needs anything from outside the repo: a checkout of
warped-pinball/trench-coat, pinned by commit. dev/hil/trench_coat.py drives
it - the sequence is not reimplemented here.

If all four fail, the board needs a person: hold BOOTSEL while replugging it.
"""

import argparse
import fcntl
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trench_coat  # noqa: E402
from bench import (  # noqa: E402
    CTRL_C,
    DRAIN_QUIET_SECONDS,
    DRAIN_SECONDS,
    REPO_ROOT,
    CheckFailure,
    endgroup,
    ensure_tools_on_path,
    group,
    interrupt_board,
    list_ports,
    log,
    mpremote,
    open_serial,
    parse_board_map,
    read_until_quiet,
    time_limit,
)

# ioctl number for USBDEVFS_RESET, from <linux/usbdevice_fs.h>: _IO('U', 20).
USBDEVFS_RESET = ord("U") << 8 | 20

PROBE_TIMEOUT = 20
SETTLE_SECONDS = 5

# No single step may hang the job. Generous enough for the slowest one - the
# TrenchCoat reflash, which clones, waits for a drive, and writes two UF2s -
# and still short of the workflow's own timeout, so the run always gets to
# print its summary.
STEP_TIMEOUT = 600


def responsive(port, timeout=PROBE_TIMEOUT):
    """Can we still get a REPL out of this board?

    Deliberately the cheapest question that distinguishes "wedged" from
    "busy": a board running the Vector application answers this, because
    mpremote interrupts it to do so.
    """
    try:
        result = mpremote("connect", port, "exec", "print('alive')", timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0 and "alive" in result.stdout


def survey(board_map):
    """Report which ports answer, and work out what each dead one should be.

    A wedged board cannot tell us its chip id, so it cannot be looked up in
    VECTOR_HIL_BOARD_MAP directly. What it can be is deduced: ask every board
    that does answer who it is, and whatever targets the map still expects are
    the dead ones. With one board down and the rest alive, that is exact.
    """
    ports = list_ports()
    if not ports:
        raise CheckFailure("no boards found at all - check the USB hub and power")

    alive, dead, claimed = [], [], set()
    note("")
    note("### Boards")
    note("")
    note("```")
    note(f"{'port':16} {'state':14} chip id")
    for port in ports:
        if not responsive(port):
            dead.append(port)
            note(f"{port:16} {'NOT ANSWERING':14} -")
            continue
        alive.append(port)
        try:
            chip = mpremote("connect", port, "exec", "from machine import unique_id;from binascii import hexlify;print(hexlify(unique_id()).decode())", timeout=30)
            chip_id = chip.stdout.strip() if chip.returncode == 0 else None
        except subprocess.TimeoutExpired:
            # Answered once and not the second time. Not our problem to solve
            # here, but it does mean we cannot attribute a target to it.
            chip_id = None
        if chip_id in board_map:
            claimed.add(board_map[chip_id])
        note(f"{port:16} {'ok':14} {chip_id or '?'}")

        # Probing a board means interrupting it, which leaves it sitting at a
        # bare REPL with the Vector application stopped. A tool that only meant
        # to look must put it back, or a "nothing to recover" run quietly
        # leaves the whole bench not running its firmware.
        try:
            mpremote("connect", port, "exec", "--no-follow", "import machine; machine.reset()", timeout=30)
        except subprocess.TimeoutExpired:
            log(f"    warning: could not restart {port} after probing it")

    note("```")

    unclaimed = sorted(set(board_map.values()) - claimed)
    targets = {}
    if len(dead) == 1 and len(unclaimed) == 1:
        targets[dead[0]] = unclaimed[0]
        log(f"\n{dead[0]} is the only board not answering and {unclaimed[0]} is the only target unaccounted for, so that is what it is")
    elif dead:
        log(f"\ncannot tell which target {', '.join(dead)} should be ({len(unclaimed)} unaccounted for: {', '.join(unclaimed) or 'none'})")
        log("a reflash needs --target to say which UF2 to use")

    return alive, dead, targets


# --------------------------------------------------------------------------
# 1. drain
# --------------------------------------------------------------------------


def drain(port, seconds=DRAIN_SECONDS):
    """Read whatever is queued until the board goes quiet, then interrupt it.

    This is the only rung of the ladder this runner can always reach - the USB
    reset needs a udev rule and the power cycle needs uhubctl, and neither is
    installed - so it is worth being patient here. A bench run proved the
    point: a board written off after a three-second drain of 63 bytes was read
    with `cat` moments later and turned out to be a healthy, running server
    that had merely blocked on a full output buffer.
    """
    try:
        connection = open_serial(port)
    except Exception as exc:
        log(f"    could not open {port}: {exc}")
        return False

    drained = 0
    interrupted = False
    try:
        drained += read_until_quiet(connection, seconds)
        # Ctrl-C twice: once to break out of a sleep, once for whatever the
        # first one dropped us into.
        interrupted = interrupt_board(connection, port, CTRL_C + CTRL_C)
        drained += read_until_quiet(connection, DRAIN_QUIET_SECONDS * 2)
    except Exception as exc:
        log(f"    error draining {port}: {exc}")
    finally:
        try:
            connection.close()
        except Exception:
            pass

    log(f"    drained {drained} byte(s) and {'sent Ctrl-C' if interrupted else 'could not send Ctrl-C'}")

    # What the two directions did is the diagnosis, and they point at
    # different remedies.
    if drained and not interrupted:
        log("    this board is talking but not listening: it is producing output")
        log("    normally and never servicing what we send it, so no amount of")
        log("    reading will reach it. That is what the USB reset and power")
        log("    cycle rungs are for - see RUNNER_SETUP.md if they are skipped")
        log("    below, because without them there is nothing left to try.")
    elif not drained:
        # A board merely blocked on a full buffer has a backlog to give up the
        # moment somebody reads.
        log("    (nothing queued - so it is not simply blocked on a full output buffer)")

    return True


# --------------------------------------------------------------------------
# 2. usb reset
# --------------------------------------------------------------------------


def usb_device_path(port):
    """Map /dev/ttyACM* to its /dev/bus/usb/BBB/DDD node."""
    name = os.path.basename(port)
    link = Path(f"/sys/class/tty/{name}/device")
    try:
        node = link.resolve()
    except OSError as exc:
        log(f"    cannot resolve {link}: {exc}")
        return None

    # The tty hangs off the CDC interface; the device is its parent.
    for candidate in [node] + list(node.parents):
        busnum = candidate / "busnum"
        devnum = candidate / "devnum"
        if busnum.exists() and devnum.exists():
            return Path(f"/dev/bus/usb/{int(busnum.read_text()):03d}/{int(devnum.read_text()):03d}")
    log(f"    could not find the USB device behind {port}")
    return None


def usb_reset(port):
    """Ask the kernel to re-enumerate the device behind `port`."""
    node = usb_device_path(port)
    if node is None:
        return False
    log(f"    resetting {node}")
    try:
        with open(node, "wb") as handle:
            fcntl.ioctl(handle.fileno(), USBDEVFS_RESET, 0)
    except PermissionError:
        log(f"    permission denied on {node} - the runner user needs write access to it (a udev rule, or the plugdev group)")
        return False
    except OSError as exc:
        log(f"    ioctl failed: {exc}")
        return False
    return True


# --------------------------------------------------------------------------
# 3. power cycle
# --------------------------------------------------------------------------


def hub_location(port):
    """Return (hub, port number) for uhubctl, from the device's sysfs path.

    A USB path looks like 1-1.4:1.0 - bus 1, hub at 1-1, port 4. uhubctl wants
    the hub and the port separately.

    Returns None for a device sitting directly on a root hub (1-1:1.0). That is
    not a case worth handling: cutting power there takes down the whole bus and
    every other board on it, which on this bench means killing the two healthy
    boards to recover one. Only a downstream hub port is ours to switch.
    """
    name = os.path.basename(port)
    try:
        node = Path(f"/sys/class/tty/{name}/device").resolve()
    except OSError:
        return None

    for candidate in [node] + list(node.parents):
        if (candidate / "busnum").exists():
            usb_path = candidate.name.split(":")[0]
            if "." in usb_path:
                hub, _, portnum = usb_path.rpartition(".")
                return hub, portnum
            log(f"    {port} is on a root hub ({usb_path}); power cycling it would cut every board on the bus")
            return None
    return None


def power_cycle(port, off_seconds=3):
    """Cut and restore power to the board's hub port.

    The board is powered off the USB cable, so this is the real thing - a cold
    boot, with no dependence on the firmware being alive to cooperate. Needs a
    hub with per-port power switching; plenty do not have it, which is why this
    reports rather than fails.
    """
    if not shutil.which("uhubctl"):
        log("    uhubctl is not installed - skipping the power cycle (sudo apt install uhubctl)")
        return False

    location = hub_location(port)
    if location is None:
        log(f"    could not work out which hub port {port} is on")
        return False
    hub, portnum = location

    log(f"    power cycling hub {hub} port {portnum}")
    for action in ("off", "on"):
        result = subprocess.run(["uhubctl", "--location", hub, "--ports", portnum, "--action", action], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            log(f"    uhubctl {action} failed: {detail}")
            if "No compatible" in detail or "not support" in detail:
                log("    this hub cannot switch port power - a smart hub is the only way to make this step work")
            return False
        if action == "off":
            time.sleep(off_seconds)
    return True


# --------------------------------------------------------------------------
# 4. reflash, using TrenchCoat
# --------------------------------------------------------------------------


def can_complete_a_reflash():
    """Is there any way this runner could write a UF2 once the board is in BOOTSEL?

    Asked *before* anything touches the board into its bootloader, because that
    is a one-way door: it takes a board that is at least enumerated as a serial
    device and turns it into a mass-storage device that only a UF2 (or a
    replug) gets it out of. Doing that with no way to finish the job makes the
    board harder to recover, not easier.
    """
    if trench_coat.find_bootloader_drives():
        return True, "a bootloader drive is already mounted"
    if shutil.which("udisksctl"):
        return True, "udisksctl is available to mount the drive"
    if any(Path(root).is_dir() and os.access(root, os.W_OK) for root in trench_coat.MOUNT_ROOTS):
        return True, "an automount directory is writable"
    return False, "nothing here can mount an RPI-RP2 drive (no udisksctl, no writable automount directory)"


def reflash(port, target, cache_dir, force=False):
    """Hand the board to TrenchCoat, which is the tool for exactly this job.

    Not reimplemented here on purpose. TrenchCoat is what the team uses to
    recover a board without the BOOTSEL button, and its sequence includes the
    step a naive UF2 copy misses: a nuke.uf2 wipe of the whole flash before the
    real firmware, so nothing from the old filesystem survives. See
    dev/hil/trench_coat.py for how it is pointed at one board instead of all of
    them.
    """
    possible, why = can_complete_a_reflash()
    log(f"    {'can' if possible else 'cannot'} finish a reflash here: {why}")
    if not possible and not force:
        log("    not touching the board into BOOTSEL, because that would leave it as a mass-storage")
        log("    device with no way to flash it - strictly worse than how it is now. Install udisksctl")
        log("    on the runner (or pass --force-bootsel) to make this step usable.")
        return False

    return trench_coat.flash(port, target, cache_dir / "trench-coat")


# --------------------------------------------------------------------------


def recover(port, target, args):
    """Escalate until the board answers, or until we run out of ideas."""
    steps = [("drain the console", lambda: drain(port)), ("reset the USB device", lambda: usb_reset(port))]
    if not args.no_power_cycle:
        steps.append(("power cycle the hub port", lambda: power_cycle(port)))
    if args.reflash:
        if target:
            steps.append(("reflash MicroPython over the ROM bootloader", lambda: reflash(port, target, args.cache_dir, args.force_bootsel)))
        else:
            log(f"::warning::{port}: skipping the reflash step - no target known for this board, pass --target")

    note("")
    note(f"### Recovering {port}" + (f" ({target})" if target else ""))
    note("")

    for name, step in steps:
        group(f"{port}: {name}")
        try:
            with time_limit(args.step_timeout, name):
                attempted = step()
        except CheckFailure as exc:
            log(f"::error::{exc}")
            attempted = False
        except Exception as exc:  # noqa: BLE001 - a failed recovery step is not a crash
            log(f"::error::unexpected error: {exc}")
            attempted = False

        if attempted:
            time.sleep(SETTLE_SECONDS)
            if responsive(port):
                note(f"- **{port}: recovered by {name}**")
                endgroup()
                return name
            note(f"- {port}: tried {name} - still not answering")
        else:
            note(f"- {port}: could not attempt {name}")
        endgroup()

    return None


def note(line):
    """Append a line to the Actions job summary as well as the log.

    Job summaries are stored separately from the log archive, and the last two
    bench runs proved why that matters: the runner died mid-job, never uploaded
    its logs, and every finding went with them. Written incrementally rather
    than at the end for the same reason.
    """
    log(line)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a") as handle:
            handle.write(line.replace("::warning::", "WARNING: ").replace("::error::", "ERROR: ") + "\n")
    except OSError:
        pass


def preflight():
    """Report which recovery steps are actually available here.

    A recovery that fails is still worth the run if it says precisely which
    one-time bit of runner setup would have made the bench self-healing. Each
    line below is a step that either works or names what it needs.
    """
    ports = []
    try:
        ports = list_ports()
    except CheckFailure:
        pass

    note("### What this runner can do")
    note("")
    note("```")
    note(f"  serial      ok        {len(ports)} port(s) visible")

    node = usb_device_path(ports[0]) if ports else None
    if node is None:
        note("  usb reset   unknown   no device to check")
    elif os.access(node, os.W_OK):
        note(f"  usb reset   ok        {node} is writable")
    else:
        note(f"  usb reset   no        {node} is not writable - needs a udev rule granting the runner user write access")

    if shutil.which("uhubctl"):
        note("  power       ok        uhubctl is installed (still needs a hub that switches port power)")
    else:
        note("  power       no        uhubctl not installed - `sudo apt install uhubctl`")

    possible, why = can_complete_a_reflash()
    note(f"  reflash     {'ok      ' if possible else 'no      '}  {why}")
    note(f"  {'':11} {'':9} TrenchCoat pinned at {trench_coat.TRENCH_COAT_COMMIT[:8]}")
    note("```")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", action="append", help="recover only this port (repeatable); default is every board that is not answering")
    parser.add_argument("--target", help="target for the dead board, e.g. wpc - only needed when it cannot be deduced")
    parser.add_argument("--no-reflash", dest="reflash", action="store_false", help="stop before replacing the firmware; the board is left as found if the cheaper steps fail")
    parser.add_argument("--no-power-cycle", action="store_true", help="skip the uhubctl step")
    parser.add_argument("--force-bootsel", action="store_true", help="touch the board into BOOTSEL even when nothing here can mount the drive to flash it")
    parser.add_argument("--step-timeout", type=int, default=STEP_TIMEOUT, help=f"hard ceiling on any one recovery step, in seconds (default {STEP_TIMEOUT})")
    parser.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "build" / "hil", help="where to keep the trench-coat checkout")
    args = parser.parse_args()

    ensure_tools_on_path()

    group("What this runner can do")
    preflight()
    endgroup()

    group("Survey")
    board_map = parse_board_map(os.environ.get("VECTOR_HIL_BOARD_MAP"))
    alive, dead, targets = survey(board_map)
    endgroup()

    if args.port:
        dead = [port for port in args.port]
        log(f"recovering {', '.join(dead)} because --port says so")
    if not dead:
        log(f"\nall {len(alive)} board(s) are answering - nothing to recover")
        return 0

    recovered, lost = [], []
    for port in dead:
        target = args.target or targets.get(port)
        log("")
        log(f"recovering {port}" + (f" (expected to be {target})" if target else " (target unknown)"))
        method = recover(port, target, args)
        if method:
            recovered.append((port, method))
        else:
            lost.append(port)

    log("")
    log("=" * 60)
    for port, method in recovered:
        log(f"  recovered  {port:16} by: {method}")
    for port in lost:
        log(f"  NOT ANSWERING {port}")
    log("=" * 60)

    if lost:
        log("")
        log(f"{len(lost)} board(s) need a person at the bench:")
        log("  hold the BOOTSEL button while replugging the USB cable, then run")
        log("  dev/hil/flash_and_check.py to put Vector back on it.")
        # A board that would not answer is not necessarily a board that is
        # gone, and saying so matters: "still dead" sent a maintainer looking
        # for a bricked Pico when the board in question was running the
        # application and printing to its console the whole time, and only
        # ever refused input.
        log("")
        log("  (a board here has failed every rung this runner can reach, which is not")
        log("  the same as being bricked - check the drain output above for what it was")
        log("  doing, and RUNNER_SETUP.md for the rungs that were skipped)")
        return 1

    log("")
    log("Every board answers again. A board recovered by the reflash step is running")
    log("bare MicroPython, so run dev/hil/flash_and_check.py before trusting the bench.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckFailure as exc:
        log(f"::error::{exc}")
        sys.exit(1)
