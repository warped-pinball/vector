#!/usr/bin/env python3
"""Drive warped-pinball/trench-coat to reflash a bench board.

TrenchCoat is the tool the Warped Pinball team already uses to recover boards
without touching the BOOTSEL button, so the bench uses *it* rather than a
second implementation of the same delicate sequence. Its `flash_firmware()`
does the part that matters and that a naive "copy a UF2" misses:

    bootloader -> nuke.uf2 -> wait for the drive to cycle -> real UF2 -> wait
    for the board to re-enumerate as a serial device

The `nuke.uf2` wipe is the load-bearing step. It erases the whole flash, so
nothing from the old filesystem survives into the new firmware - which is what
makes this a recovery rather than an upgrade.

Two things have to be adapted for the bench, and both are done by narrowing
what TrenchCoat can see rather than by changing what it does:

  * It flashes *every* board it finds. On the bench that would nuke the two
    healthy boards along with the broken one, so `Ray.find_board_ports` is
    narrowed to the single port being recovered.
  * It finds bootloader drives by looking for INFO_UF2.TXT under /media and
    /Volumes, which assumes a desktop automounter. A headless runner has none,
    so `list_rpi_rp2_drives` is wrapped to mount the RPI-RP2 volume with
    udisksctl first.

A board found *already* in BOOTSEL is the one case its `flash_firmware` cannot
be narrowed to - see the second half of this file for why, and for the copy
sequence that replaces it there. It keeps the parts that matter: the nuke.uf2
wipe, and the pinned UF2 bundle from this checkout.

Only `src.core`, `src.ray`, `src.ui` and `src.util` are imported, and between
them they need nothing but pyserial - which the bench venv already has because
mpremote ships it. `src.main` and `src.interactive` are the parts that want
InquirerPy and a human, and neither is used here.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bench  # noqa: E402
from bench import (  # noqa: E402
    SERIAL_WRITE_TIMEOUT,
    CheckFailure,
    endgroup,
    group,
    log,
    open_serial,
)

# Pinned, like every other third-party input to this bench. Bumping it means
# reviewing what changed in the flashing sequence first.
TRENCH_COAT_COMMIT = "26e6d508c362bed1f6d1323155435c18528de758"
TRENCH_COAT_URL = "https://github.com/warped-pinball/trench-coat"

# Which bundled UF2 belongs to which bench target.
TARGET_UF2 = {
    "wpc": "Vector_WPC_v5.uf2",
    "data_east": "Vector_DataEast_v1.uf2",
    "sys11": "vector_system_11_and_9_v4.uf2",
    "em": "Vector_WPC_v5.uf2",  # EM runs on the WPC OS (see TrenchCoat's series menu)
}


def clone(root, commit=TRENCH_COAT_COMMIT):
    """Make sure `root` holds trench-coat at exactly `commit`."""
    root = Path(root)
    if not (root / ".git").is_dir():
        root.parent.mkdir(parents=True, exist_ok=True)
        log(f"    cloning trench-coat into {root}")
        subprocess.run(["git", "clone", "--quiet", TRENCH_COAT_URL, str(root)], check=True, timeout=600)

    subprocess.run(["git", "-C", str(root), "fetch", "--quiet", "origin", commit], check=True, timeout=600)
    subprocess.run(["git", "-C", str(root), "checkout", "--quiet", commit], check=True, timeout=120)

    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=60).stdout.strip()
    if head != commit:
        raise CheckFailure(f"trench-coat checkout is at {head}, expected the pinned {commit}")
    log(f"    trench-coat at {commit[:8]}")
    return root


def load(root):
    """Import TrenchCoat's modules from `root` and return (core, ray).

    Guarded because both repositories have a top-level `src` package, and
    importing the wrong one would be a confusing way to fail.
    """
    root = str(Path(root).resolve())
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)

    for name in [module for module in sys.modules if module == "src" or module.startswith("src.")]:
        del sys.modules[name]

    import src.core as core
    import src.ray as ray

    if not str(Path(core.__file__).resolve()).startswith(root):
        raise CheckFailure(f"imported the wrong `src` package: got {core.__file__}, expected it under {root}")
    return core, ray


def bound_serial_writes(ray):
    """Give TrenchCoat's serial connections a write timeout.

    `Ray.open` uses `serial.Serial(port, 115200, timeout=0.1)`, which is the
    READ timeout only - the same trap this harness had. On a desktop talking to
    a healthy board that is fine, which is the case TrenchCoat is written for.
    Here the board is wedged by definition, so the Ctrl-C that `open()` writes
    blocks with nothing to time it out: one recovery run spent its entire 600s
    step budget inside enter_bootloader_mode before the SIGALRM backstop cut it
    short.

    Injected rather than patched upstream: it is their code, and this is our
    unusual way of using it.
    """
    original = ray.serial.Serial

    def bounded(*args, **kwargs):
        kwargs.setdefault("write_timeout", SERIAL_WRITE_TIMEOUT)
        return original(*args, **kwargs)

    ray.serial.Serial = bounded


def bundled_uf2(root, target):
    if target not in TARGET_UF2:
        raise CheckFailure(f"no TrenchCoat UF2 known for target {target!r} (have: {', '.join(sorted(TARGET_UF2))})")
    path = Path(root) / "uf2" / TARGET_UF2[target]
    if not path.exists():
        raise CheckFailure(f"{path} is missing from the trench-coat checkout")
    return path


# Where automounters actually put a volume: /media/LABEL, /media/<user>/LABEL,
# /run/media/<user>/LABEL. Deliberately NOT a recursive walk - the first
# version used rglob over /media, /run/media and /mnt, which walks whatever
# else happens to be mounted there. On a 512MB Zero 2 W with a drive under
# /mnt that is minutes of I/O and enough memory pressure to take the runner
# down with it, which is the most likely reason a bench job died without
# uploading its logs.
MOUNT_ROOTS = ("/media", "/run/media")


def find_bootloader_drives():
    """Mounted RPI-RP2 volumes, found without walking arbitrary filesystems."""
    drives = []
    for root in MOUNT_ROOTS:
        base = Path(root)
        if not base.is_dir():
            continue
        try:
            candidates = list(base.iterdir())
            for entry in list(candidates):
                if entry.is_dir():
                    candidates.extend(entry.iterdir())
        except OSError:
            continue
        for entry in candidates:
            try:
                if entry.is_dir() and (entry / "INFO_UF2.TXT").exists():
                    drives.append(str(entry))
            except OSError:
                continue
    return drives


def mount_rpi_rp2():
    """Mount an RPI-RP2 volume that nothing automounted. Returns the path or None."""
    by_label = Path("/dev/disk/by-label")
    if not by_label.is_dir():
        return None
    for link in sorted(by_label.glob("RPI-RP2*")):
        device = link.resolve()
        result = subprocess.run(["udisksctl", "mount", "-b", str(device)], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            mounted = result.stdout.strip().rsplit(" at ", 1)[-1].rstrip(".")
            log(f"    mounted {device} at {mounted}")
            return mounted
        if "AlreadyMounted" in result.stderr:
            continue
        log(f"    udisksctl could not mount {device}: {(result.stderr or result.stdout).strip()}")
    return None


def bootsel_touch(port):
    """Open the port at 1200 baud, which asks the RP2040 to reset to its ROM.

    TrenchCoat's own route into the bootloader is `machine.bootloader()` over
    the REPL, fire-and-forget. That is the right first try - it is what the
    team uses and it needs no privileges - but it does need the firmware alive
    enough to run one statement. The 1200 baud touch is a CDC line-coding
    change handled in USB interrupt context, so it can still land when the
    Python VM cannot run anything at all.
    """
    try:
        connection = open_serial(port, baudrate=1200)
        connection.dtr = False
        time.sleep(0.5)
        connection.close()
    except Exception as exc:
        # The port disappearing underneath us is what a reboot looks like.
        log(f"    port closed during the 1200 baud touch ({exc})")


def wait_for_drive(core, timeout=45):
    """Wait for a bootloader drive, mounting it ourselves if nothing else does.

    Uses our bounded search rather than TrenchCoat's os.walk of /media and
    /Volumes - same answer on a normal machine, without the risk of walking
    into something large.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        drives = find_bootloader_drives()
        if drives:
            return drives
        if mount_rpi_rp2():
            drives = find_bootloader_drives()
            if drives:
                return drives
        time.sleep(1)
    return []


def enter_bootloader(core, ray, port):
    """Get one board into its ROM bootloader, TrenchCoat's way then ours."""
    log("    asking the board to reset into the bootloader (TrenchCoat's machine.bootloader())")
    try:
        ray.Ray(port).enter_bootloader_mode()
    except Exception as exc:
        log(f"    that did not go through: {exc}")

    drives = wait_for_drive(core, timeout=20)
    if drives:
        log(f"    board is in bootloader mode: {', '.join(drives)}")
        return drives

    log("    no drive yet, falling back to the 1200 baud touch")
    bootsel_touch(port)
    drives = wait_for_drive(core, timeout=45)
    if drives:
        log(f"    board is in bootloader mode: {', '.join(drives)}")
    return drives


def flash(port, target, root):
    """Recover one board by running TrenchCoat's own firmware flash against it.

    Returns True if TrenchCoat reported the board back as a serial device.
    """
    core, ray = load(clone(root))
    bound_serial_writes(ray)
    uf2 = bundled_uf2(root, target)

    port_being_recovered = port
    drives = enter_bootloader(core, ray, port)
    if not drives:
        log("    the board never presented a bootloader drive, so there is nothing to flash")
        return False

    # From here TrenchCoat drives, on this board only. It sees every serial
    # port except the healthy boards' - which is empty right now (the board
    # being recovered is a drive, not a port), so its
    # get_all_boards_into_bootloader() is a no-op instead of a second attempt,
    # and it never touches the rest of the bench.
    #
    # Hiding *every* port instead would break the other end of the sequence:
    # flash_firmware finishes by waiting for as many ports as it flashed
    # drives, so a permanently empty list makes that wait unsatisfiable and
    # turns a successful reflash into a timeout. Filtering rather than
    # emptying also survives the board coming back on a different ttyACM
    # number, which it often does.
    others = {port for port in serial_ports() if port != port_being_recovered}
    ray.Ray.find_board_ports = classmethod(lambda cls: [p for p in serial_ports() if p not in others])
    core.list_rpi_rp2_drives = lambda: find_bootloader_drives() or drives

    # Their failure path prints advice and calls sys.exit; make it an exception
    # this harness can report and carry on from.
    def refuse_to_exit(now=False):
        raise CheckFailure("TrenchCoat could not complete the flash (see its output above)")

    core.graceful_exit = refuse_to_exit

    log(f"    handing over to TrenchCoat: nuke.uf2, then {uf2.name}")
    core.flash_firmware(str(uf2))

    # flash_firmware only returns cleanly once the board is back as a serial
    # port, so reaching here is the success condition.
    log("    TrenchCoat reports the board restarted")
    return True


# --------------------------------------------------------------------------
# Boards that are already in the bootloader
# --------------------------------------------------------------------------
#
# A board found in BOOTSEL needs the second half of the sequence above and not
# the first: there is no port to reset, because the board is a mass-storage
# device already. TrenchCoat's own `core.flash_firmware` cannot be pointed at
# one board here - it wipes every drive it can see and then waits on
# `Ray.find_board_ports()` for as many boards as it flashed, so restricting it
# to one board (which the bench must do, or a rescue takes the healthy boards
# with it) makes its final wait unsatisfiable. So the copy sequence is spelled
# out below, with the parts that matter kept: nuke.uf2 first, and the pinned
# UF2 bundle from the checkout.

BOOTSEL_SETTLE = 5
DRIVE_TIMEOUT = 60
RESTART_TIMEOUT = 90


def serial_ports():
    return sorted(str(path) for path in Path("/dev").glob("ttyACM*"))


def block_device(usb_device):
    """The /dev node behind a bootloader's mass-storage interface.

    Walked from the USB device's own sysfs directory rather than looked up in
    /dev/disk/by-id, because that is exact: with three boards in BOOTSEL the
    by-id names differ only by a serial string whose format is the bootrom's
    business, while this path belongs to the one device we are holding.
    """
    for block in sorted(Path(usb_device).glob("*/host*/target*/*/block/*")):
        # A filesystem lives on a partition when the drive has a partition
        # table, and udisks rightly refuses to mount the whole disk in that
        # case - "/dev/sda is not a mountable filesystem" is exactly what a
        # bench board produced, with `blkid` reporting PTTYPE="dos" on it.
        # A plain RP2 bootloader drive has no partition table and no
        # partitions, so this falls through to the disk as before.
        for partition in sorted(block.glob(f"{block.name}[0-9]*")):
            return Path("/dev") / partition.name
        return Path("/dev") / block.name
    return None


def mount_point(device):
    """Where `device` is mounted, if it is."""
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            fields = line.split()
            if len(fields) > 1 and fields[0] == str(device):
                return fields[1].replace("\\040", " ")
    except OSError:
        pass
    return None


_mount_error = None


def mount(device):
    """Mount a bootloader drive, whoever has to do it. Returns the path or None."""
    existing = mount_point(device)
    if existing:
        return existing
    result = subprocess.run(["udisksctl", "mount", "--no-user-interaction", "-b", str(device)], capture_output=True, text=True, timeout=120)
    if result.returncode == 0:
        return result.stdout.strip().rsplit(" at ", 1)[-1].rstrip(".")
    if "AlreadyMounted" in result.stderr:
        return mount_point(device)

    # Said once. bootsel_drive keeps asking while it waits for a drive that
    # may still be settling, and the same permission error sixty times over
    # buries everything else in the log.
    global _mount_error
    detail = (result.stderr or result.stdout).strip()
    if detail != _mount_error:
        _mount_error = detail
        log(f"    could not mount {device}: {detail}")
        for line in describe_block_device(device):
            log(f"    {line}")
    return None


def describe_block_device(device):
    """What the kernel thinks of a drive udisks would not mount.

    "not a mountable filesystem" is where a bench recovery actually stopped,
    and on its own it does not say whether the board is presenting a broken
    filesystem or no drive at all. The size settles it: a bootloader offering
    zero sectors is a board-side fault that no amount of retrying fixes, and
    it needs picotool or a person rather than this code.
    """
    name = Path(device).name
    lines = []
    try:
        sectors = int((Path("/sys/block") / name / "size").read_text().strip())
    except (OSError, ValueError):
        return ["(could not read the drive's size from sysfs)"]

    if sectors == 0:
        lines.append("the drive reports ZERO sectors, so there is no filesystem to mount and never will be.")
        lines.append("The board is in the bootloader but its mass storage is presenting nothing - a UF2 cannot")
        lines.append("be copied to it. picotool talks to the bootrom directly and does not need the drive:")
        lines.append(f"  picotool load -x <uf2>   # or: picotool info    (board is {name})")
    else:
        lines.append(f"the drive reports {sectors} sectors ({sectors * 512 // 1024} KiB) but no filesystem udisks will mount.")
        lines.append("Worth checking by hand on the bench host: sudo blkid " + str(device) + " ; sudo dmesg | tail -30")
        lines.append("A `PTTYPE=` in blkid's output means the drive is partitioned and the filesystem is on a")
        lines.append("partition; a bootloader drive normally has neither. picotool talks to the bootrom directly")
        lines.append("and needs no drive at all, which is the way past this: picotool info ; picotool load -x <uf2>")
    return lines


def unmount(device):
    """Best effort, so the next flash does not trip over a stale mount."""
    subprocess.run(["udisksctl", "unmount", "--no-user-interaction", "-b", str(device)], capture_output=True, text=True, timeout=60)


def bootsel_drive(chip_id, timeout=DRIVE_TIMEOUT):
    """Wait for one board's bootloader drive, by chip id, and mount it.

    Looked up afresh every time rather than remembered: writing a UF2 reboots
    the board, so the device node, the sysfs path and the mount point are all
    different on the other side of a copy. The chip id is the only handle that
    survives.
    """
    deadline = time.monotonic() + timeout
    while True:
        for board in bench.bootsel_boards():
            if board["chip_id"] != chip_id:
                continue
            device = block_device(board["usb_device"])
            if device is None or not device.exists():
                break
            path = mount(device)
            if path and (Path(path) / "INFO_UF2.TXT").exists():
                return device, path
            break
        if time.monotonic() >= deadline:
            return None, None
        time.sleep(1)


def wait_for_bootsel(chip_id, present, timeout=DRIVE_TIMEOUT, poll=0.25):
    """Wait until the board is (or is no longer) enumerated as a bootloader.

    Polled quickly, because one of the two things it watches for is a gap:
    the board vanishes when it starts running a UF2 and is back moments later,
    and a slow poll can step straight over that.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        here = any(board["chip_id"] == chip_id for board in bench.bootsel_boards())
        if here == present:
            return True
        time.sleep(poll)
    return False


def copy_uf2(uf2, device, drive):
    """Write a UF2 to a mounted bootloader drive.

    An I/O error at the end of the copy is not reported as a failure: the
    board reboots the moment the last block lands, which is exactly what a
    successful flash looks like from this side - the device goes away
    mid-write. Whether it worked is decided by what comes back, below.
    """
    log(f"    writing {uf2.name} to {drive}")
    try:
        shutil.copy(str(uf2), drive)
        os.sync()
    except OSError as exc:
        log(f"    the drive went away during the copy ({exc}) - that is usually the board rebooting")
    unmount(device)


PICOTOOL_TIMEOUT = 300


def picotool_available():
    return bool(shutil.which("picotool"))


def usb_address(chip_id):
    """(bus, address) for one board in BOOTSEL, so picotool can be aimed.

    This is the whole safety story for the fallback. picotool with no device
    selection acts on whatever RP2 device it finds first, which on this bench
    could be a healthy board someone is mid-flash on. Reading bus and address
    out of the sysfs directory we already matched by chip id means the command
    can only ever reach the board we identified.
    """
    for board in bench.bootsel_boards():
        if board["chip_id"] != chip_id:
            continue
        try:
            bus = int((Path(board["usb_device"]) / "busnum").read_text())
            address = int((Path(board["usb_device"]) / "devnum").read_text())
        except (OSError, ValueError):
            return None
        return bus, address
    return None


def picotool(arguments, chip_id, timeout=PICOTOOL_TIMEOUT):
    """Run picotool against exactly one board."""
    where = usb_address(chip_id)
    if where is None:
        return None
    command = ["picotool", *arguments, "--bus", str(where[0]), "--address", str(where[1])]
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout)


def _picotool_output(result, lines=10):
    return [line for line in (result.stderr or result.stdout or "").strip().splitlines()[-lines:]]


def flash_over_picotool(chip_id, uf2):
    """Write a UF2 without a drive, by talking to the ROM bootloader itself.

    The drive-copy route needs the board's mass storage to work. A bench board
    came back from a power cycle mid-flash with a drive udisks would not touch
    - `blkid` saw a DOS partition table where a bootloader drive should have a
    bare filesystem - and no retry was ever going to fix that. picotool speaks
    the bootrom's own USB protocol (PICOBOOT) and needs no filesystem at all;
    on that same board `picotool info` answered while the drive was unusable.

    The erase keeps the property that makes this a recovery rather than an
    upgrade - nothing of the old filesystem survives - and is best effort,
    because a board that will not erase may still accept the firmware.
    """
    if not picotool_available():
        log("    picotool is not installed, so there is no way past an unusable drive here")
        log("    (`sudo apt install picotool` gives the bench a route that needs no filesystem)")
        return False

    where = usb_address(chip_id)
    if where is None:
        log("    could not read the board's USB bus/address, and picotool must be aimed at one board")
        return False

    log(f"    falling back to picotool on bus {where[0]} address {where[1]} - it needs no drive")
    erased = picotool(["erase"], chip_id)
    if erased is None or erased.returncode != 0:
        detail = "; ".join(_picotool_output(erased, 2)) if erased is not None else "the board moved"
        log(f"    erase declined ({detail}) - writing the firmware anyway")

    loaded = picotool(["load", "-x", str(uf2)], chip_id)
    if loaded is None:
        log("    the board stopped being a bootloader before the firmware could be written")
        return False
    if loaded.returncode != 0:
        log("    picotool could not write the firmware:")
        for line in _picotool_output(loaded):
            log(f"      {line}")
        return False

    log(f"    picotool wrote {uf2.name} and started it")
    return True


def wait_for_serial(before, uf2):
    """Wait for a flashed board to come back as a port it did not hold before."""
    deadline = time.monotonic() + RESTART_TIMEOUT
    while time.monotonic() < deadline:
        new = [port for port in serial_ports() if port not in before]
        if new:
            log(f"    back as {new[0]} running {uf2.name}")
            return new[0]
        time.sleep(1)
    log(f"    {uf2.name} was written but the board never came back as a serial device")
    return None


def flash_bootsel(chip_id, target, root):
    """Put firmware back on a board that is sitting in its ROM bootloader.

    Returns the serial port it came back on, or None. The board is left
    running TrenchCoat's bundled firmware for its target, which is a working
    Vector board and, more to the point, a board the normal build-and-flash
    path can talk to again.
    """
    uf2 = bundled_uf2(root, target)
    nuke = Path(root) / "uf2" / "nuke.uf2"
    if not nuke.exists():
        raise CheckFailure(f"{nuke} is missing from the trench-coat checkout")

    before = set(serial_ports())
    device, drive = bootsel_drive(chip_id)
    if drive is None:
        log(f"    no usable bootloader drive for {chip_id}: it is enumerated and in the bootloader, but")
        log("    nothing here could mount a filesystem to copy a UF2 onto - see the reason above")
        if not flash_over_picotool(chip_id, uf2):
            return None
        return wait_for_serial(before, uf2)

    # The wipe is the load-bearing step: it erases the whole flash, so nothing
    # from whatever state the board was left in survives into the new firmware.
    copy_uf2(nuke, device, drive)
    # Not seeing it leave is not a failure: a wipe can start and finish
    # between two polls, and what matters is the state it settles in.
    if not wait_for_bootsel(chip_id, present=False, timeout=30):
        log("    never saw it restart - either the wipe was quick or it never began")
    if not wait_for_bootsel(chip_id, present=True, timeout=DRIVE_TIMEOUT):
        log("    the board did not come back as a bootloader after the wipe")
        return None
    time.sleep(BOOTSEL_SETTLE)

    device, drive = bootsel_drive(chip_id)
    if drive is None:
        log("    the wiped board never presented its drive again")
        if not flash_over_picotool(chip_id, uf2):
            return None
        return wait_for_serial(before, uf2)
    copy_uf2(uf2, device, drive)

    return wait_for_serial(before, uf2)


def rescue_bootsel(board_map, cache_dir):
    """Flash every board found in BOOTSEL back to a serial device.

    Runs before anything else on the bench, because a board in this state is
    invisible to every other stage: no serial port, no chip id over the REPL,
    nothing to flash or health-check. Boards the map does not cover are
    reported and left alone - there is no way to guess which UF2 they need,
    and writing the wrong system's firmware is worse than leaving them.

    Returns the number of boards put back.
    """
    stranded = bench.bootsel_boards()
    if not stranded:
        return 0

    group(f"Rescue {len(stranded)} board(s) in BOOTSEL")
    log("These boards are in the ROM bootloader, not running firmware. Flashing them back.")
    unmapped = [board for board in stranded if board["chip_id"] not in board_map]
    if unmapped:
        log(f"::error::{bench.report_unknown_boards(unmapped, stranded, board_map)}")

    rescued = 0
    root = None
    for board in stranded:
        chip_id = board["chip_id"]
        target = board_map.get(chip_id)
        if not target:
            continue
        log(f"  {chip_id}  {board['processor']}  ->  {target}")
        try:
            if root is None:
                root = clone(cache_dir / "trench-coat")
            if flash_bootsel(chip_id, target, root):
                rescued += 1
        except CheckFailure as exc:
            log(f"::error::{chip_id} ({target}): {exc}")
        except Exception as exc:  # noqa: BLE001 - one board's rescue never stops the next
            log(f"::error::{chip_id} ({target}): {type(exc).__name__}: {exc}")

    log(f"{rescued} of {len(stranded)} board(s) rescued")
    endgroup()
    return rescued
