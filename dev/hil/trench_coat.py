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

Only `src.core`, `src.ray`, `src.ui` and `src.util` are imported, and between
them they need nothing but pyserial - which the bench venv already has because
mpremote ships it. `src.main` and `src.interactive` are the parts that want
InquirerPy and a human, and neither is used here.
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench import CheckFailure, log, open_serial  # noqa: E402

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
    uf2 = bundled_uf2(root, target)

    drives = enter_bootloader(core, ray, port)
    if not drives:
        log("    the board never presented a bootloader drive, so there is nothing to flash")
        return False

    # From here TrenchCoat drives, on this board only. find_board_ports is
    # emptied because the board is already a drive - that makes its
    # get_all_boards_into_bootloader() a no-op instead of a second attempt, and
    # keeps it away from the healthy boards on the bench.
    ray.Ray.find_board_ports = classmethod(lambda cls: [])
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
