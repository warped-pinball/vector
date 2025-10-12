"""
WPC

Save and Restore adjustments
four save indexes
16 character name for each
"""

import SharedState as S
import SPI_Store as fram
from FramMap import ADJUSTMENTS_CONFIG
from logger import logger_instance as Log
from Shadow_Ram_Definitions import shadowRam

print("ADJS: fram map config", ADJUSTMENTS_CONFIG)

# FRAM address constants
ADJ_NUM_SLOTS = ADJUSTMENTS_CONFIG["NumRecords"]
ADJ_FRAM_START = ADJUSTMENTS_CONFIG["AddressStart"]
ADJ_FRAM_RECORD_SIZE = ADJUSTMENTS_CONFIG["RecordSize"]
ADJ_FRAM_TOTAL_DATA_LENGTH = ADJUSTMENTS_CONFIG["TotalDataLength"]

ADJ_NAMES_START = ADJUSTMENTS_CONFIG["NamesAddress"]
ADJ_NAMES_LENGTH = ADJUSTMENTS_CONFIG["NamesLength"]

ADJ_LAST_LOADED_ADR = ADJUSTMENTS_CONFIG["LastLoadedAddress"]

# print(S.gdata)


def sanitize_adjustment_names():
    """Check adjustment names in one sweep and replace invalid characters with spaces"""
    # Read the entire block of names at once
    all_names_address = ADJ_NAMES_START
    all_names_length = ADJ_NAMES_LENGTH * ADJ_NUM_SLOTS
    all_names = bytearray(fram.read(all_names_address, all_names_length))

    # Track if we made any changes
    changes_made = False

    # Replace invalid characters with spaces
    for i in range(len(all_names)):
        b = all_names[i]
        if b != 0 and (b < 32 or b > 126):
            all_names[i] = 32
            changes_made = True

    # Only write back if we made changes
    if changes_made:
        fram.write(all_names_address, all_names)
        Log.log("ADJS: Fixed invalid characters in adjustment names")


# Run name sanitization at module import time
sanitize_adjustment_names()


def blank_all():
    """blank out all adjustment storage - only for manufacturing init"""
    chunk_size = 16
    zero_chunk = bytearray(chunk_size)

    fram_adr = ADJ_FRAM_START
    remaining = ADJ_FRAM_TOTAL_DATA_LENGTH
    offset = 0
    Log.log(f"ADJS: Blanking {remaining:04X} bytes from {fram_adr:04X}")

    while remaining > 0:
        write_size = min(chunk_size, remaining)
        if write_size < chunk_size:
            # For the last partial chunk
            fram.write(fram_adr + offset, zero_chunk[:write_size])
        else:
            fram.write(fram_adr + offset, zero_chunk)

        offset += write_size
        remaining -= write_size

    Log.log("ADJS: All adjustment data cleared")

    # Write valid empty strings for names at ADJ_NAMES_START
    empty_name = bytearray(b"\x00" * ADJ_NAMES_LENGTH)
    for i in range(ADJ_NUM_SLOTS):
        fram.write(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, empty_name)
    Log.log("ADJS: All adjustment names cleared")


def _get_range_from_gamedef():
    # get range of adjustments in shadowram from gamedef json
    cpyStart = cpyEnd = chkAdr = 0
    if S.gdata["Adjustments"]["Type"] == 10:
        cpyStart = S.gdata["Adjustments"].get("ChecksumStartAdr", 0)
        cpyEnd = S.gdata["Adjustments"].get("ChecksumEndAdr", 0)
        chkAdr = S.gdata["Adjustments"].get("ChecksumResultAdr", 0)

    return cpyStart, cpyEnd, chkAdr


def _fixChecksum():
    cpyStart, cpyEnd, chkAdr = _get_range_from_gamedef()
    if cpyStart == 0 or cpyEnd == 0:
        raise ValueError("No valid range found in game data 1")

    chk = 0
    for adr in range(cpyStart, cpyEnd + 1):
        chk = chk + shadowRam[adr]
    chk = 0xFFFF - chk

    # Store MSByte and LSByte
    msb = (chk >> 8) & 0xFF
    lsb = chk & 0xFF
    print("ADJ: Old Checksum: ---------------- ", hex(shadowRam[chkAdr]), hex(shadowRam[chkAdr + 1]))
    print("ADJ: New Checksum: ---------------- ", hex(msb), hex(lsb))
    shadowRam[chkAdr] = msb
    shadowRam[chkAdr + 1] = lsb


def set_message_state(on=True):
    """set the message state for adjustments"""
    message_adr = S.gdata["Adjustments"].get("CustomMessageOn")
    if message_adr is not None:
        if on:
            shadowRam[message_adr] = 1
        else:
            shadowRam[message_adr] = 0

        Log.log(f"ADJS: Message State set to {on}")
        _fixChecksum()
        # fram.write_all_fram_now()


def get_names():
    """read out all four names"""
    return [fram.read(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, ADJ_NAMES_LENGTH).decode("ascii").rstrip("\x00") for i in range(4)]


def set_name(index, name):
    """set name for index"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        raise ValueError("Invalid Index")

    name = name[:16]
    name_bytes = bytearray(name.encode("ascii") + b"\x00" * (16 - len(name)))
    # Calculate the FRAM address for this index
    fram_address = ADJ_NAMES_START + index * ADJ_NAMES_LENGTH
    fram.write(fram_address, name_bytes)
    print(f"ADJS: Name set at index {index}: {name}")


def restore_adjustments(index, reset=True):
    """pull from FRAM data and put in shadow ram in the machine, reset after by default"""

    print("ADJS: --------------------------- restore -------")
    if index < 0 or index >= ADJ_NUM_SLOTS:
        return "Fault: Invalid Index"

    # Check if a game is in progress and reset is requested
    """
    if reset:
        import GameStatus as GS
        if GS._get_ball_in_play() != 0:
            Log.log("ADJS: No restore - game in progress")
            return "Fault: Game in Progress"
    """

    fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
    data = fram.read(fram_adr, ADJ_FRAM_RECORD_SIZE)

    # Check the data is not empty
    if all(byte == 0 for byte in data[:100]):
        raise ValueError(f"No data in the adjustment profile {index}")

    cpyStart, cpyEnd, chkAdr = _get_range_from_gamedef()
    cpyEndCheck = max(cpyEnd, chkAdr + 2)
    if cpyStart == 0 or cpyEnd == 0:
        raise ValueError("No valid range found in game data 2")

    # store this one as the last loaded
    fram.write(ADJ_LAST_LOADED_ADR, bytearray([index]))

    # shut down the pinball machine
    from reset_control import release, reset

    reset()

    from time import sleep

    sleep(2)

    shadowRam[cpyStart:cpyEndCheck] = data[: cpyEndCheck - cpyStart]
    print(f"ADJS: Adjustments restored {index}")

    fram.write_all_fram_now()
    print("ADJ: load done - resetting now ---------------------")
    # import machine
    # machine.reset()

    # restart the pinball machine
    release(True)

    sleep(2)
    # restart the server schedule
    from phew.server import restart_schedule

    restart_schedule()


def store_adjustments(index):
    """store current adjustments into a storage location (0-3)"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        return "Fault: Invalid Index"

    # will return 0,0 if none found
    cpyStart, cpyEnd, chkAdr = _get_range_from_gamedef()
    cpyEndCheck = max(cpyEnd, chkAdr + 2)
    if cpyEndCheck - cpyStart > ADJ_FRAM_RECORD_SIZE:
        Log.log("ADJS: Range too large for adjustment storage")
        return "Fault: Range"

    # if valid ranges do the copy
    if cpyStart > 0 and cpyEndCheck > 0:
        Log.log(f"ADJS: Store {index} Range {cpyStart}:{cpyEndCheck}")

        # copy shadowram to fram
        data = shadowRam[cpyStart:cpyEndCheck]
        print("data length", len(data))
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
        fram.write(fram_adr, data)

        # store this one as the last 'loaded'
        fram.write(ADJ_LAST_LOADED_ADR, bytearray([index]))

        # hex_data = " ".join(f"{byte:02X}" for byte in data)
        # print(f"ADR: {fram_adr:04X} DAT: {hex_data}")
    else:
        Log.log("ADJS: No Gamedef Ranges")


def get_active_adjustment():
    """look for acive adjustment profile
    Do not use built in checksum, it is simple and duplicates are common

    return None if no match, 0-3 if found
    in case of two matches use last_loaded number from fram
    """
    cpyStart, cpyEnd, chkAdr = _get_range_from_gamedef()
    if cpyStart == 0 or cpyEnd == 0 or chkAdr == 0:
        print("ADJS: No valid range found in game data 3")
        return None

    matches = []
    # try to do this 16 bytes at a time for speed - (one SPI read cycle)
    for i in range(4):
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * i
        active_data = shadowRam[cpyStart:cpyEnd]
        match = True
        print(f"ADJS: Checking {i} at {fram_adr:04X} against shadowRam {cpyStart:04X}:{cpyEnd:04X}")
        for offset in range(0, cpyEnd - cpyStart, 16):
            length = min(16, cpyEnd - cpyStart - offset)
            stored_data = fram.read(fram_adr + offset, length)

            if stored_data != active_data[offset : offset + 16]:
                match = False
                break
        if match:
            matches.append(i)
    if not matches:
        print("ADJS: No active adjustment found")
        return None

    # If there are multiple matches, use the last loaded index
    last_loaded_index = fram.read(ADJ_LAST_LOADED_ADR, 1)[0]

    if last_loaded_index in matches:
        return last_loaded_index

    return matches[0]  # Return the first match if last loaded index is not in matches


def is_populated(index):
    """return True if the profile is populated"""
    return fram.read(ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index, ADJ_FRAM_RECORD_SIZE) != b"\x00" * ADJ_FRAM_RECORD_SIZE


def get_adjustments_status():
    """return list of tuples with names and active index, and if the profile is populated"""
    start, end, chk = _get_range_from_gamedef()
    adjustments_support = start > 0 and end > 0
    names = get_names()
    active_index = get_active_adjustment()
    print("ADJ: acitve adj", active_index)
    profile_status = []
    for i in range(ADJ_NUM_SLOTS):
        profile_status.append((names[i], i == active_index, is_populated(i)))

    print("ADJS: get_adjustments_status: adjustments_support", adjustments_support, "profiles", profile_status)

    return {"adjustments_support": adjustments_support, "profiles": profile_status}


if __name__ == "__main__":

    def fill_shadow_ram_with_pattern(pattern):
        """Fill shadowRam from cpyStart to cpyEnd with a given pattern."""
        cpyStart, cpyEnd = 6141, 7160  # johnny
        pattern_length = len(pattern)
        print(len(shadowRam), cpyStart, cpyEnd, pattern_length)
        for i in range(0, cpyEnd - cpyStart):
            # print(i)
            shadowRam[i + cpyStart] = pattern[i % pattern_length]

    import GameDefsLoad

    GameDefsLoad.go()

    fill_shadow_ram_with_pattern([1, 2, 3, 4])
    store_adjustments(0)
    print("store 0 done")
    fill_shadow_ram_with_pattern([0x0B, 0xCC, 0xEE])
    store_adjustments(1)
    print("store 1 done")
    fill_shadow_ram_with_pattern([0x11, 0x22, 0x33, 0x44])
    store_adjustments(2)
    print("store 2 done")
    fill_shadow_ram_with_pattern([8, 7, 6, 5])
    store_adjustments(3)
    print("store 3 done")

    restore_adjustments(0, reset=False)
    print("A0:", " ".join(f"{b:02X}" for b in shadowRam[6141 : 6141 + 16]))
    restore_adjustments(1, reset=False)
    print("A1:", " ".join(f"{b:02X}" for b in shadowRam[6141 : 6141 + 16]))
    restore_adjustments(2, reset=False)
    print("A2:", " ".join(f"{b:02X}" for b in shadowRam[6141 : 6141 + 16]))
    restore_adjustments(3, reset=False)
    print("A3:", " ".join(f"{b:02X}" for b in shadowRam[6141 : 6141 + 16]))

    import time

    start_time = time.ticks_ms()

    i = get_active_adjustment()
    print("ACTIVE= ", get_active_adjustment())

    end_time = time.ticks_ms()
    execution_time_ms = time.ticks_diff(end_time, start_time)
    print(f"Execution time: {execution_time_ms} ms")
