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
  4. reflash    - 1200 baud touch to drop the RP2040 into its ROM bootloader,
                  then copy a MicroPython UF2 onto the RPI-RP2 drive that
                  appears. The touch is handled in USB interrupt context rather
                  than by the Python VM, so it can work when everything above
                  has failed. Destructive: it replaces the firmware, and the
                  board needs `dev/flash.py` afterwards to get Vector back.

Only step 4 needs anything from outside the repo - the UF2s come from
warped-pinball/trench-coat, pinned by commit and verified by checksum.

If all four fail, the board needs a person: hold BOOTSEL while replugging it.
"""

import argparse
import fcntl
import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import serial  # noqa: E402
from bench import (  # noqa: E402
    CTRL_C,
    REPO_ROOT,
    CheckFailure,
    endgroup,
    ensure_tools_on_path,
    group,
    list_ports,
    log,
    mpremote,
    parse_board_map,
)

# warped-pinball/trench-coat, pinned by commit. The checksums are what this
# revision ships; a mismatch means the pin moved under us and the file is not
# flashed. UF2s are large, so they are fetched rather than vendored here.
TRENCH_COAT_COMMIT = "26e6d508c362bed1f6d1323155435c18528de758"
TRENCH_COAT_RAW = f"https://raw.githubusercontent.com/warped-pinball/trench-coat/{TRENCH_COAT_COMMIT}/uf2"

TARGET_UF2 = {
    "wpc": ("Vector_WPC_v5.uf2", "3d02a60de852c11087f76ad61a1baf5921270c9a98ca9542a450aad26fac5191"),
    "data_east": ("Vector_DataEast_v1.uf2", "11afc1d22f28099921e63950ba1e86832f47f2c558f8384ff04d9cf6650e7047"),
    "sys11": ("vector_system_11_and_9_v4.uf2", "ba63972475f5126c1e5270c30b418510505f5859da9366eb0fac9ef35c9e7a15"),
}

# ioctl number for USBDEVFS_RESET, from <linux/usbdevice_fs.h>: _IO('U', 20).
USBDEVFS_RESET = ord("U") << 8 | 20

PROBE_TIMEOUT = 20
SETTLE_SECONDS = 5


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
    log(f"{'port':16} {'state':14} chip id")
    for port in ports:
        if not responsive(port):
            dead.append(port)
            log(f"{port:16} {'NOT ANSWERING':14} -")
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
        log(f"{port:16} {'ok':14} {chip_id or '?'}")

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


def drain(port, seconds=5):
    """Read whatever is queued and interrupt the board."""
    try:
        connection = serial.Serial(port=port, baudrate=115200, timeout=1)
    except Exception as exc:
        log(f"    could not open {port}: {exc}")
        return False

    drained = 0
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            drained += len(connection.read(connection.in_waiting or 1))
        connection.write(CTRL_C + CTRL_C)
        connection.flush()
    except Exception as exc:
        log(f"    error draining {port}: {exc}")
    finally:
        try:
            connection.close()
        except Exception:
            pass

    log(f"    drained {drained} byte(s) and sent Ctrl-C")
    # Nothing queued is itself the diagnosis: a board merely blocked on a full
    # buffer has a backlog to give up the moment somebody reads.
    if drained == 0:
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
            bus, _, portnum = usb_path.partition("-")
            return bus, portnum
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
# 4. reflash over the ROM bootloader
# --------------------------------------------------------------------------


def bootsel_touch(port):
    """Open the port at 1200 baud to drop the RP2040 into its ROM bootloader.

    The last resort that does not need a person, and the reason it can work
    when the REPL cannot: the 1200 baud touch is a CDC line-coding change,
    handled in USB interrupt context, so a blocked Python VM does not stop it.
    TrenchCoat's own enter_bootloader_mode() goes through `machine.bootloader()`
    on the REPL instead, which a wedged board will never run.
    """
    try:
        connection = serial.Serial(port=port, baudrate=1200)
        connection.dtr = False
        time.sleep(0.5)
        connection.close()
    except Exception as exc:
        # The port vanishing underneath us IS the board rebooting into the
        # bootloader, so this is as often success as failure.
        log(f"    port closed during the 1200 baud touch ({exc}) - which is what a reboot looks like")
    return True


def find_bootloader_drive(timeout=30):
    """Wait for an RPI-RP2 drive to appear, the way TrenchCoat looks for it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for root in ("/media", "/run/media", "/mnt"):
            base = Path(root)
            if not base.is_dir():
                continue
            try:
                for path in base.rglob("INFO_UF2.TXT"):
                    return path.parent
            except OSError:
                continue
        time.sleep(1)
    return None


def mount_bootloader_drive(timeout=30):
    """Mount the RPI-RP2 volume ourselves when nothing automounts it.

    A headless runner has no desktop automounter, so the drive that appears
    after the touch is a block device and nothing more. udisksctl goes through
    polkit rather than sudo, which is the one route a service user might
    actually have.
    """
    if not shutil.which("udisksctl"):
        log("    udisksctl is not available, so the bootloader drive cannot be mounted here")
        return None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for link in sorted(Path("/dev/disk/by-label").glob("RPI-RP2*")) if Path("/dev/disk/by-label").is_dir() else []:
            device = link.resolve()
            log(f"    mounting {device} with udisksctl")
            result = subprocess.run(["udisksctl", "mount", "-b", str(device)], capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                # "Mounted /dev/sda1 at /media/xxx"
                mounted = result.stdout.strip().rsplit(" at ", 1)[-1].rstrip(".")
                log(f"    mounted at {mounted}")
                return Path(mounted)
            log(f"    udisksctl could not mount it: {(result.stderr or result.stdout).strip()}")
            return None
        time.sleep(1)
    return None


def can_complete_a_reflash():
    """Is there any way this runner could write a UF2 once the board is in BOOTSEL?

    Asked *before* the 1200 baud touch, because the touch is a one-way door: it
    takes a board that is at least enumerated as a serial device and turns it
    into a mass-storage device that only a UF2 (or a replug) gets it out of.
    Doing that with no way to finish the job makes the board harder to recover,
    not easier.
    """
    if find_bootloader_drive(timeout=0) is not None:
        return True, "a bootloader drive is already mounted"
    if shutil.which("udisksctl"):
        return True, "udisksctl is available to mount the drive"
    if any(Path(root).is_dir() and os.access(root, os.W_OK) for root in ("/media", "/run/media")):
        return True, "an automount directory is writable"
    return False, "nothing here can mount an RPI-RP2 drive (no udisksctl, no writable automount directory)"


def fetch_uf2(target, cache_dir):
    """Download the pinned UF2 for `target` and verify it before use."""
    if target not in TARGET_UF2:
        raise CheckFailure(f"no UF2 known for target {target!r} (have: {', '.join(sorted(TARGET_UF2))})")
    filename, expected = TARGET_UF2[target]

    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / filename
    if not path.exists():
        url = f"{TRENCH_COAT_RAW}/{filename}"
        log(f"    downloading {filename} from trench-coat@{TRENCH_COAT_COMMIT[:8]}")
        request = urllib.request.Request(url, headers={"User-Agent": "vector-hil"})
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        path.unlink(missing_ok=True)
        raise CheckFailure(f"{filename} does not match the checksum pinned for trench-coat@{TRENCH_COAT_COMMIT[:8]} (got {digest}) - refusing to flash it")
    log(f"    {filename} verified ({path.stat().st_size} bytes)")
    return path


def reflash(port, target, cache_dir, force=False):
    """1200 baud touch, then drop a UF2 on the drive that appears."""
    possible, why = can_complete_a_reflash()
    log(f"    {'can' if possible else 'cannot'} finish a reflash here: {why}")
    if not possible and not force:
        log("    not touching the board into BOOTSEL, because that would leave it as a mass-storage")
        log("    device with no way to flash it - strictly worse than how it is now. Install udisksctl")
        log("    on the runner (or pass --force-bootsel) to make this step usable.")
        return False

    # Fetch and verify before the point of no return, so a bad download cannot
    # strand the board in BOOTSEL.
    uf2 = fetch_uf2(target, cache_dir)

    bootsel_touch(port)

    drive = find_bootloader_drive() or mount_bootloader_drive()
    if drive is None:
        log("    no RPI-RP2 drive appeared, so either the board did not reach its ROM bootloader")
        log("    or nothing mounted the drive it presented")
        return False
    log(f"    board is in bootloader mode at {drive}")

    log(f"    copying {uf2.name} to {drive}")
    shutil.copy(uf2, drive)
    # The board reboots as soon as the copy lands, taking the drive with it.
    time.sleep(10)
    return True


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

    for name, step in steps:
        group(f"{port}: {name}")
        try:
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
                log(f"    {port} is answering again")
                endgroup()
                return name
            log(f"    {port} still not answering")
        endgroup()

    return None


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

    log(f"  serial      ok        {len(ports)} port(s) visible")

    node = usb_device_path(ports[0]) if ports else None
    if node is None:
        log("  usb reset   unknown   no device to check")
    elif os.access(node, os.W_OK):
        log(f"  usb reset   ok        {node} is writable")
    else:
        log(f"  usb reset   no        {node} is not writable - needs a udev rule granting the runner user write access")

    if shutil.which("uhubctl"):
        log("  power       ok        uhubctl is installed (still needs a hub that switches port power)")
    else:
        log("  power       no        uhubctl not installed - `sudo apt install uhubctl`")

    possible, why = can_complete_a_reflash()
    log(f"  reflash     {'ok      ' if possible else 'no      '}  {why}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", action="append", help="recover only this port (repeatable); default is every board that is not answering")
    parser.add_argument("--target", help="target for the dead board, e.g. wpc - only needed when it cannot be deduced")
    parser.add_argument("--no-reflash", dest="reflash", action="store_false", help="stop before replacing the firmware; the board is left as found if the cheaper steps fail")
    parser.add_argument("--no-power-cycle", action="store_true", help="skip the uhubctl step")
    parser.add_argument("--force-bootsel", action="store_true", help="touch the board into BOOTSEL even when nothing here can mount the drive to flash it")
    parser.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "build" / "uf2", help="where to keep downloaded UF2s")
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
        log(f"  STILL DEAD {port}")
    log("=" * 60)

    if lost:
        log("")
        log(f"{len(lost)} board(s) need a person at the bench:")
        log("  hold the BOOTSEL button while replugging the USB cable, then run")
        log("  dev/hil/flash_and_check.py to put Vector back on it.")
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
