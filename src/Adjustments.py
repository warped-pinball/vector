"""
Save and Restore adjustments

four save indexes
16 character name for each

"""
import displayMessage
import SharedState as S
import SPI_Store as fram
from logger import logger_instance as Log
from Shadow_Ram_Definitions import shadowRam

ADJ_FRAM_START = 0x2100  # to 0x2340
ADJ_FRAM_RECORD_SIZE = 0x80
ADJ_NUM_SLOTS = 4
ADJ_NAMES_START = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * ADJ_NUM_SLOTS
ADJ_NAMES_LENGTH = 16


def blank_all():
    """blank out all names and storage - only for manufacturing init"""
    for i in range(4):
        set_name(i, "")
        # blank the data also
        data = bytearray(ADJ_FRAM_RECORD_SIZE)
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * i
        fram.write(fram_adr, data)


def _get_range_from_gamedef():
    # for ranges check game data:
    #       1) check Adjustment.cpyStart / cpyEnd
    #       2) then if ChecksumStartAdr / ChecksumResultAdr
    #       2) then if Adjustments.Type ==1 assume 780-7ff
    #       3) then : fault - no ranges
    cpyStart = S.gdata["Adjustments"].get("cpyStart", 0)
    cpyEnd = S.gdata["Adjustments"].get("cpyEnd", 0)
    if cpyStart == 0 or cpyEnd == 0:
        cpyStart = S.gdata["Adjustments"].get("ChecksumStartAdr", 0)
        cpyEnd = S.gdata["Adjustments"].get("ChecksumResultAdr", 0)
    if cpyStart == 0 or cpyEnd == 0:
        if S.gdata["Adjustments"].get("Type", 0) == 1:
            cpyStart = 0x780
            cpyEnd = 0x800
    return cpyStart, cpyEnd


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
    # Log.log(f"ADJS: Name set at index {index}: {name}")


def restore_adjustments(index, reset=True):
    """pull from fram data and put in shadow ram in the machine, reset after by default"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        return "Fault: Invalid Index"

    # Check if a game is in progress and reset is requested
    if reset and shadowRam[S.gdata["BallInPlay"]["Address"]] in [
        S.gdata["BallInPlay"]["Ball1"],
        S.gdata["BallInPlay"]["Ball2"],
        S.gdata["BallInPlay"]["Ball3"],
        S.gdata["BallInPlay"]["Ball4"],
        S.gdata["BallInPlay"]["Ball5"],
    ]:
        # TODO do we have to fail if a game is in progress? can we restart the machine anyway?
        # if we do need this, we should raise an exception and catch it in the backend
        Log.log("ADJS: No restore - game in progress")
        return "Fault: Game in Progress"

    fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
    data = fram.read(fram_adr, ADJ_FRAM_RECORD_SIZE)

    # Check the data is not empty
    if not is_populated(index):
        raise ValueError(f"No data in the adjustment profile {index}")

    # will return 0,0 if none found
    cpyStart, cpyEnd = _get_range_from_gamedef()

    # copy
    if (cpyStart == 0 and cpyEnd == 0) or (cpyEnd - cpyStart) > len(data):
        raise ValueError("No valid range found in game data")

    # shut down the pinball machine
    import reset_control

    reset_control.reset()

    from time import sleep

    sleep(2)

    shadowRam[cpyStart:cpyEnd] = data[: cpyEnd - cpyStart]
    Log.log(f"ADJS: Adjustments restored {index}")

    displayMessage.fixAdjustmentChecksum()
    fram.write_all_fram_now()

    # restart the pinball machine
    reset_control.release()
    sleep(4)

    # restart the server schedule
    from phew.server import restart_schedule

    restart_schedule()


def store_adjustments(index):
    """store current adjustments into a storage location (0-3)"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        return "Fault: Invalid Index"

    # will return 0,0 if none found
    cpyStart, cpyEnd = _get_range_from_gamedef()

    # if valid ranges do the copy
    if cpyStart > 0 and cpyEnd > 0:
        Log.log(f"ADJS: Store {index} Range {cpyStart}:{cpyEnd}")

        # copy shadowram to fram
        data = shadowRam[cpyStart:cpyEnd]
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
        fram.write(fram_adr, data)
        # hex_data = " ".join(f"{byte:02X}" for byte in data)
        # print(f"ADR: {fram_adr:04X} DAT: {hex_data}")

    else:
        Log.log("ADJS: No Gamedef Ranges")


def get_active_adjustment():
    """look for acive adjustment profile
    Do not use built in checksum, it is simple and duplicates are common
    (System 9 does not have checksum)
    return None iff no match, 0-3 if found
    """
    index_match = None

    cpyStart, cpyEnd = _get_range_from_gamedef()
    end_address = S.gdata["Adjustments"].get("ChecksumEndAdr", 0)
    if cpyStart == 0 or cpyEnd == 0 or end_address == 0:
        return None

    # try to do this 16 bytes at a time for speed - (one SPI read cycle)
    for i in range(4):
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * i
        active_data = shadowRam[cpyStart:end_address]
        match = True
        for offset in range(0, end_address - cpyStart, 16):
            len = min(16, end_address - cpyStart - offset)
            stored_data = fram.read(fram_adr + offset, len)
            if stored_data != active_data[offset : offset + 16]:
                match = False
                break
        if match:
            index_match = i
            break

    return index_match


def is_populated(index):
    """return True if the profile is populated"""
    return fram.read(ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index, ADJ_FRAM_RECORD_SIZE) != b"\x00" * ADJ_FRAM_RECORD_SIZE


def get_adjustments_status():
    """return list of tuples with names and active index, and if the profile is populated"""
    start, end = _get_range_from_gamedef()
    adjustments_support = start > 0 and end > 0
    names = get_names()
    active_index = get_active_adjustment()
    profile_status = []
    for i in range(ADJ_NUM_SLOTS):
        profile_status.append((names[i], i == active_index, is_populated(i)))
    return {"adjustments_support": adjustments_support, "profiles": profile_status}


if __name__ == "__main__":

    def fill_shadow_ram_with_pattern(pattern):
        """Fill shadowRam from cpyStart to cpyEnd with a given pattern."""
        cpyStart, cpyEnd = 1920, 2020  # (2020-1920)/16 = 6.25
        pattern_length = len(pattern)
        for i in range(cpyStart, cpyEnd):
            shadowRam[i] = pattern[i % pattern_length]

    import GameDefsLoad

    GameDefsLoad.go(True)

    fill_shadow_ram_with_pattern([1, 2, 3, 4])
    store_adjustments(0)
    print("store 0 done")
    fill_shadow_ram_with_pattern([11, 22, 33])
    store_adjustments(1)
    print("store 1 done")
    fill_shadow_ram_with_pattern([100, 200, 300, 400])
    store_adjustments(2)
    print("store 2 done")
    fill_shadow_ram_with_pattern([8, 7, 6, 5])
    store_adjustments(3)
    print("store 3 done")

    restore_adjustments(0, reset=False)
    print("A0", shadowRam[1920:1940])
    restore_adjustments(1, reset=False)
    print("A1", shadowRam[1920:1940])
    restore_adjustments(2, reset=False)
    print("A2", shadowRam[1920:1940])
    restore_adjustments(3, reset=False)
    print("A3", shadowRam[1920:1940])

    import time

    start_time = time.ticks_ms()

    i = get_active_adjustment()
    # print("ACTIVE= ", get_active_adjustment())

    end_time = time.ticks_ms()
    execution_time_ms = time.ticks_diff(end_time, start_time)
    print(f"Execution time: {execution_time_ms} ms")
