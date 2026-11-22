"""
Whitestar

Save and Restore adjustments
four save indexes
16 character name for each

Whitestar (Adjustments Type 40) keeps the Data East layout: a main block at
$1E00 protected by an 8 bit sum stored in a separate byte, an extra block
that is BCD checked but not summed, and on the late Stern titles a third
block (Extra2) that is not checked at all.

At power-on the game sums the main block and checks that every nibble of
the main and extra blocks is 0-9. Any failure clears ALL of NVRAM (audits,
high scores and adjustments) and restores factory settings. So a restore
from Vector must never write a record that is empty, not valid BCD, or
saved from a different ROM. Each stored profile therefore carries a header
that ties it to the config (block lengths and checksum address) and is
validated before anything touches shadow RAM.

FRAM record layout (RecordSize 0x140 = 320 bytes):
    0       magic 0x40
    1       main block length N (79-127)
    2       extra block length (4-37)
    3       extra2 block length (0 or 22-43)
    4-5     checksum result address, big endian
    6-7     main block start address, big endian
    8-15    reserved (0)
    16..    main block, checksum byte, extra block, extra2 block
"""

from Shadow_Ram_Definitions import shadowRam
import SharedState as S
import SPI_Store as fram
import DataMapper
from logger import logger_instance as Log
from FramMap import ADJUSTMENTS_CONFIG

#FRAM address constants
ADJ_NUM_SLOTS = ADJUSTMENTS_CONFIG["NumRecords"]
ADJ_FRAM_START = ADJUSTMENTS_CONFIG["AddressStart"]
ADJ_FRAM_RECORD_SIZE = ADJUSTMENTS_CONFIG["RecordSize"]
ADJ_FRAM_TOTAL_DATA_LENGTH = ADJUSTMENTS_CONFIG["TotalDataLength"]

ADJ_NAMES_START = ADJUSTMENTS_CONFIG["NamesAddress"]
ADJ_NAMES_LENGTH = ADJUSTMENTS_CONFIG["NamesLength"]

ADJ_LAST_LOADED_ADR = ADJUSTMENTS_CONFIG["LastLoadedAddress"]

RECORD_MAGIC = 0x40
HEADER_LENGTH = 16


def sanitize_adjustment_names():
    """Replace invalid characters in adjustment names with spaces."""
    all_names = bytearray(fram.read(ADJ_NAMES_START, ADJ_NAMES_LENGTH * ADJ_NUM_SLOTS))
    changed = False
    for i, b in enumerate(all_names):
        if b and (b < 32 or b > 126):
            all_names[i] = 32
            changed = True
    if changed:
        fram.write(ADJ_NAMES_START, all_names)
        Log.log("ADJS: Fixed invalid characters in adjustment names")


# Run name sanitization at module import time
sanitize_adjustment_names()


def blank_all():
    """Blank out all adjustment storage and names - only for manufacturing init."""
    fram.write(ADJ_FRAM_START, bytearray(ADJ_FRAM_TOTAL_DATA_LENGTH))
    Log.log(f"ADJS: Blanked {ADJ_FRAM_TOTAL_DATA_LENGTH} bytes from {ADJ_FRAM_START:04X}")

    empty_name = bytearray(ADJ_NAMES_LENGTH)
    for i in range(ADJ_NUM_SLOTS):
        fram.write(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, empty_name)
    Log.log("ADJS: All adjustment names cleared")


def _get_range_from_gamedef():
    """
    Adjustment ranges from the game config (Type 40 only).

    Returns (cpyStart, cpyEnd, chkAdr, extraStart, extraEnd, extra2Start, extra2End),
    ends inclusive, all zero when adjustments are not supported for this game.
    """
    r = DataMapper.adjustment_ranges()
    if r is None:
        return 0, 0, 0, 0, 0, 0, 0
    cpyStart, cpyEnd, chkAdr, extraStart, extraEnd, extra2Start, extra2End = r
    if extraStart and extraEnd < extraStart:
        extraStart = extraEnd = 0
    if extra2Start and extra2End < extra2Start:
        extra2Start = extra2End = 0
    total = HEADER_LENGTH + (cpyEnd - cpyStart + 1) + 1
    if extraStart:
        total += extraEnd - extraStart + 1
    if extra2Start:
        total += extra2End - extra2Start + 1
    if total > ADJ_FRAM_RECORD_SIZE:
        Log.log("ADJS: adjustment record size fault")
        return 0, 0, 0, 0, 0, 0, 0
    return cpyStart, cpyEnd, chkAdr, extraStart, extraEnd, extra2Start, extra2End


def _block_lengths(ranges):
    """(main length, extra length, extra2 length) for a range tuple."""
    cpyStart, cpyEnd, chkAdr, extraStart, extraEnd, extra2Start, extra2End = ranges
    main_len = cpyEnd - cpyStart + 1
    extra_len = (extraEnd - extraStart + 1) if extraStart else 0
    extra2_len = (extra2End - extra2Start + 1) if extra2Start else 0
    return main_len, extra_len, extra2_len


def _parse_record(data):
    """
    Split a stored record into its parts.

    Returns None when the record is empty or carries no valid header, else a dict:
        main_len, extra_len, extra2_len, chk_adr, main_start, main, chk, extra, extra2
    """
    if len(data) < HEADER_LENGTH or data[0] != RECORD_MAGIC:
        return None
    main_len = data[1]
    extra_len = data[2]
    extra2_len = data[3]
    if main_len == 0 or HEADER_LENGTH + main_len + 1 + extra_len + extra2_len > len(data):
        return None
    pos = HEADER_LENGTH
    main = bytes(data[pos : pos + main_len])
    pos += main_len
    chk = data[pos]
    pos += 1
    extra = bytes(data[pos : pos + extra_len])
    pos += extra_len
    extra2 = bytes(data[pos : pos + extra2_len])
    return {
        "main_len": main_len,
        "extra_len": extra_len,
        "extra2_len": extra2_len,
        "chk_adr": (data[4] << 8) | data[5],
        "main_start": (data[6] << 8) | data[7],
        "main": main,
        "chk": chk,
        "extra": extra,
        "extra2": extra2,
    }


def _record_fits_config(rec, ranges):
    """True when a parsed record was saved for the loaded config (same blocks, same checksum byte)."""
    cpyStart, cpyEnd, chkAdr = ranges[0], ranges[1], ranges[2]
    main_len, extra_len, extra2_len = _block_lengths(ranges)
    return (
        rec["main_len"] == main_len
        and rec["extra_len"] == extra_len
        and rec["extra2_len"] == extra2_len
        and rec["chk_adr"] == chkAdr
        and rec["main_start"] == cpyStart
    )


def _read_slot(index):
    return fram.read(ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index, ADJ_FRAM_RECORD_SIZE)


def get_names():
    """read out all four names"""
    return [fram.read(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, ADJ_NAMES_LENGTH).decode("ascii").rstrip("\x00") for i in range(ADJ_NUM_SLOTS)]


def set_name(index, name):
    """set name for index"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        raise ValueError("Invalid Index")

    name = name[:ADJ_NAMES_LENGTH]
    name_bytes = bytearray(name.encode("ascii") + b"\x00" * (ADJ_NAMES_LENGTH - len(name)))
    fram.write(ADJ_NAMES_START + index * ADJ_NAMES_LENGTH, name_bytes)
    print(f"ADJS: Name set at index {index}: {name}")


def set_message_state(on=True):
    """Custom message on/off (fixes the adjustment checksum); kept for parity with the WPC module."""
    DataMapper.enable_message(on)


def is_populated(index):
    """True when the profile holds a record with a valid header."""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        return False
    return _parse_record(_read_slot(index)) is not None


def store_adjustments(index):
    """store current adjustments into a storage location (0-3)"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid Index sa")
        return "Fault: Invalid Index"

    ranges = _get_range_from_gamedef()
    cpyStart, cpyEnd, chkAdr, extraStart, extraEnd, extra2Start, extra2End = ranges
    if cpyStart == 0 or cpyEnd == 0:
        Log.log("ADJS: No Gamedef ranges")
        return "Fault: Range"

    if not DataMapper.adjustments_valid():
        # the game itself would reject this on the next boot; never keep it as a profile
        Log.log("ADJS: Store refused, live adjustments are not valid BCD / checksum")
        return "Fault: Invalid adjustments in game"

    main_len, extra_len, extra2_len = _block_lengths(ranges)
    Log.log(f"ADJS: Store {index} Range {cpyStart}:{cpyEnd} extra {extraStart}:{extraEnd} extra2 {extra2Start}:{extra2End}")

    data = bytearray(HEADER_LENGTH)
    data[0] = RECORD_MAGIC
    data[1] = main_len
    data[2] = extra_len
    data[3] = extra2_len
    data[4] = (chkAdr >> 8) & 0xFF
    data[5] = chkAdr & 0xFF
    data[6] = (cpyStart >> 8) & 0xFF
    data[7] = cpyStart & 0xFF

    data.extend(shadowRam[cpyStart : cpyEnd + 1])
    data.append(shadowRam[chkAdr])
    if extra_len:
        data.extend(shadowRam[extraStart : extraEnd + 1])
    if extra2_len:
        data.extend(shadowRam[extra2Start : extra2End + 1])

    fram.write(ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index, data)

    # store this one as the last 'loaded'
    fram.write(ADJ_LAST_LOADED_ADR, bytearray([index]))


def restore_adjustments(index, reset=True, restore_extra2=False):
    """
    Pull a profile from FRAM into the machine's shadow RAM; the game is held
    in reset while the bytes are written and power-cycled afterwards.

    The record is refused (ValueError) when it is empty, was saved for a
    different ROM / config, or is not valid BCD - a bad block would make the
    game wipe all of its NVRAM at the next boot.

    restore_extra2: also restore the unchecked third block (late Stern
    titles). It holds clock-like settings, so it is off by default.
    """
    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid Index ra")
        raise ValueError("Invalid Index")

    ranges = _get_range_from_gamedef()
    cpyStart, cpyEnd, chkAdr, extraStart, extraEnd, extra2Start, extra2End = ranges
    if cpyStart == 0 or cpyEnd == 0:
        Log.log("ADJS: No valid range found in game data")
        raise ValueError("No valid range found in game data")

    rec = _parse_record(_read_slot(index))
    if rec is None:
        raise ValueError(f"No data in the adjustment profile {index}")

    if not _record_fits_config(rec, ranges):
        Log.log(f"ADJS: Profile {index} was saved for a different ROM / config, not restored")
        raise ValueError(f"Adjustment profile {index} does not match this game ROM")

    if all(b == 0 for b in rec["main"]):
        raise ValueError(f"Adjustment profile {index} is empty")

    if not DataMapper.is_bcd(rec["main"]) or not DataMapper.is_bcd(rec["extra"]):
        Log.log(f"ADJS: Profile {index} is not valid BCD, not restored")
        raise ValueError(f"Adjustment profile {index} holds invalid data")

    if restore_extra2 and rec["extra2_len"] and not DataMapper.is_bcd(rec["extra2"]):
        Log.log(f"ADJS: Profile {index} third block is not valid BCD, skipped")
        restore_extra2 = False

    # store this index as the last loaded
    fram.write(ADJ_LAST_LOADED_ADR, bytearray([index]))

    # shut down the pinball machine
    from reset_control import reset as machine_reset, release
    machine_reset()

    from time import sleep
    sleep(2)

    shadowRam[cpyStart : cpyEnd + 1] = rec["main"]
    shadowRam[chkAdr] = rec["chk"]
    if rec["extra_len"]:
        shadowRam[extraStart : extraEnd + 1] = rec["extra"]
    if restore_extra2 and rec["extra2_len"]:
        shadowRam[extra2Start : extra2End + 1] = rec["extra2"]

    # the stored sum should already match; re-sum anyway so the game never sees a mismatch
    DataMapper._set_adjustment_checksum()
    print(f"ADJS: Adjustments restored {index}")

    fram.write_all_fram_now()
    print("ADJS: load done - resetting now")

    # restart the pinball machine
    release(True)

    sleep(2)
    # restart the server schedule
    from phew.server import restart_schedule
    restart_schedule()


def get_active_adjustment():
    """
    Look for the profile that matches what is in the machine now (main and
    extra blocks). The game's own sum is too weak to use for this.

    Returns None if no match, 0-3 if found; with several matches the last
    loaded index wins.
    """
    ranges = _get_range_from_gamedef()
    cpyStart, cpyEnd, chkAdr, extraStart, extraEnd = ranges[0], ranges[1], ranges[2], ranges[3], ranges[4]
    if cpyStart == 0 or cpyEnd == 0:
        return None

    live_main = bytes(shadowRam[cpyStart : cpyEnd + 1])
    live_extra = bytes(shadowRam[extraStart : extraEnd + 1]) if extraStart else b""

    matches = []
    for i in range(ADJ_NUM_SLOTS):
        rec = _parse_record(_read_slot(i))
        if rec is None or not _record_fits_config(rec, ranges):
            continue
        if rec["main"] == live_main and rec["extra"] == live_extra:
            matches.append(i)

    if not matches:
        return None

    last_loaded = fram.read(ADJ_LAST_LOADED_ADR, 1)
    last_loaded_index = last_loaded[0] if last_loaded else -1
    if last_loaded_index in matches:
        return last_loaded_index
    return matches[0]


def get_adjustments_status():
    """
    Status for the web UI:
        {"adjustments_support": bool, "profiles": [(name, active, populated), x4]}
    A profile saved for another ROM version shows as not populated for this game.
    """
    ranges = _get_range_from_gamedef()
    adjustments_support = ranges[0] > 0 and ranges[1] > 0

    names = get_names()
    active_index = get_active_adjustment() if adjustments_support else None

    profile_status = []
    for i in range(ADJ_NUM_SLOTS):
        rec = _parse_record(_read_slot(i)) if adjustments_support else None
        populated = rec is not None and _record_fits_config(rec, ranges)
        profile_status.append((names[i], i == active_index, populated))

    print("ADJS: get_adjustments_status:", adjustments_support, "profiles:", profile_status)
    return {"adjustments_support": adjustments_support, "profiles": profile_status}
