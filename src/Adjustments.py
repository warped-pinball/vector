"""
Save and Restore adjustments

four save indexes
16 character name for each

"""
import machine

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


def get_names():
    """read out all four names"""
    return [fram.read(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, ADJ_NAMES_LENGTH).decode("ascii").rstrip("\x00") for i in range(4)]


def set_name(index, name):
    """set name for index"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        # TODO raise exception
        return "Fault: index"

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
        Log.log("ADJS: No restore - game in progress")
        return "Fault: Game in Progress"

    fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
    data = fram.read(fram_adr, ADJ_FRAM_RECORD_SIZE)

    # Check the first 20 bytes of data
    if all(byte == 0 for byte in data[:20]):
        Log.log("ADJS: Fault - Data is empty")
        return "Fault: empty"

    # game file can have special range
    cpyStart = S.gdata["Adjustments"].get("cpyStart", -1)
    cpyEnd = S.gdata["Adjustments"].get("cpyEnd", -1)
    # or load standard based on adjustment types in game file
    if cpyStart < 0 or cpyEnd < 0:
        if S.gdata["Adjustments"].get("Type", 0) == 1:
            cpyStart = 0x780
            cpyEnd = 0x800

    # copy
    if cpyStart > 0 and cpyEnd > 0 and (cpyEnd - cpyStart) <= len(data):
        shadowRam[cpyStart:cpyEnd] = data[: cpyEnd - cpyStart]
        Log.log(f"ADJS: Adjustments restored {index}")

        displayMessage.fixAdjustmentChecksum()
        fram.write_all_fram_now()

        # trigger a reset
        if reset:
            Log.log("ADJS: Reset")
            machine.reset()
    else:
        Log.log("ADJS: range fault")


def store_adjustments(index):
    """store current adjustments into a storage location (0-3)"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        return "Fault: Invalid Index"

    # for ranges check game data:
    #       1) check Adjustment.cpyStart / cpyEnd
    #       2) then if Adjustments.Type ==1 assume 780-7ff
    #       3) fault - no ranges
    cpyStart = S.gdata["Adjustments"].get("cpyStart", -1)
    cpyEnd = S.gdata["Adjustments"].get("cpyEnd", -1)
    if cpyStart < 0 or cpyEnd < 0:
        if S.gdata["Adjustments"].get("Type", 0) == 1:
            cpyStart = 0x780
            cpyEnd = 0x800

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
        Log.log("ADJS: No Ranges")
