"""
Data East

Save and Restore adjustments
four save indexes
16 character name for each


for Data East checksum result is out of address range - store @ chekEnd+1

also store "extra" section outside of normal checsksum range
"""

from Shadow_Ram_Definitions import shadowRam
import SharedState as S
import SPI_Store as fram
from logger import logger_instance as Log
from FramMap import ADJUSTMENTS_CONFIG

#print("ADJS: fram map config", ADJUSTMENTS_CONFIG)

#FRAM address constants
ADJ_NUM_SLOTS = ADJUSTMENTS_CONFIG["NumRecords"]
ADJ_FRAM_START = ADJUSTMENTS_CONFIG["AddressStart"]
ADJ_FRAM_RECORD_SIZE = ADJUSTMENTS_CONFIG["RecordSize"] 
ADJ_FRAM_TOTAL_DATA_LENGTH = ADJUSTMENTS_CONFIG["TotalDataLength"]

ADJ_NAMES_START = ADJUSTMENTS_CONFIG["NamesAddress"]
ADJ_NAMES_LENGTH = ADJUSTMENTS_CONFIG["NamesLength"]

ADJ_LAST_LOADED_ADR = ADJUSTMENTS_CONFIG["LastLoadedAddress"]


def sanitize_adjustment_names():
    """
        Replace invalid characters in adjustment names with spaces.
    """
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
    """
        Blank out all adjustment storage and names.
    """
    # Clear adjustment data
    fram.write(ADJ_FRAM_START, bytearray(ADJ_FRAM_TOTAL_DATA_LENGTH))
    Log.log(f"ADJS: Blanked {ADJ_FRAM_TOTAL_DATA_LENGTH} bytes from {ADJ_FRAM_START:04X}")

    # Clear adjustment names
    empty_name = bytearray(ADJ_NAMES_LENGTH)
    for i in range(ADJ_NUM_SLOTS):
        fram.write(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, empty_name)
    Log.log("ADJS: All adjustment names cleared")


def _get_range_from_gamedef():
    # get range of adjustments in shadowram from gamedef json
    cpyStart = cpyEnd = chkAdr = 0
    if S.gdata["Adjustments"]["Type"] == 20:
        cpyStart = S.gdata["Adjustments"].get("ChecksumStartAdr", 0)
        cpyEnd = S.gdata["Adjustments"].get("ChecksumEndAdr", 0)
        chkAdr = S.gdata["Adjustments"].get("ChecksumResultAdr", 0)
        
        extraStart = S.gdata["Adjustments"].get("ExtraStartAdr", 0)
        extraEnd = S.gdata["Adjustments"].get("ExtraEndAdr", 0)

    print("ADJS: Range", cpyStart, "to", cpyEnd, "chk at", chkAdr)
    print("ADJS: EXRange:",extraStart,"to ",extraEnd)  

    if ((cpyEnd-cpyStart)+(extraEnd-extraStart)+4) > ADJ_FRAM_RECORD_SIZE:
        Log.log("ADJ: fault adjustment record size")
        return 0,0,0,0,0
    return cpyStart, cpyEnd, chkAdr, extraStart, extraEnd


def set_message_state(on=True):
    """
        set the message state for adjustments
    """
    import displayMessage
    displayMessage.refresh()                

def set_name(index, name):
    """set name for index"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid Index sn")

    name = name[:16]
    name_bytes = bytearray(name.encode("ascii") + b"\x00" * (16 - len(name)))
    # Calculate the FRAM address for this index
    fram_address = ADJ_NAMES_START + index * ADJ_NAMES_LENGTH
    fram.write(fram_address, name_bytes)
    print(f"ADJS: Name set at index {index}: {name}")


def restore_adjustments(index, reset=True):
    """pull from FRAM data and put in shadow ram in the machine, reset after by default"""

    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid Index ra")

    fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
    data = fram.read(fram_adr, ADJ_FRAM_RECORD_SIZE)

    # Check the data is not empty
    #if all(byte == 0 for byte in data[:50]):
    #    Log.log(f"ADJS: No data in the adjustment profile {index}")

    cpyStart, cpyEnd, chkAdr, extraStart, extraEnd = _get_range_from_gamedef()
    if (cpyStart == 0 or cpyEnd == 0):
        Log.log("ADJS: No valid range found in game data 2")
        return

    # store this one as the last loaded
    fram.write(ADJ_LAST_LOADED_ADR, bytearray([index]))
  
    # shut down the pinball machine
    from reset_control import reset, release  
    reset()

    from time import sleep
    sleep(2)

    # Bulk adjustment data
    shadowRam[cpyStart:cpyEnd+1] = data[: cpyEnd - cpyStart +1]
    print(f"ADJS: Adjustments restored {index}")

    # Checksum byte
    print("length data - - - ",len(data),chkAdr,cpyEnd,"chk index=",cpyEnd - cpyStart+1)
    checksumOffset = cpyEnd - cpyStart +1
    shadowRam[chkAdr] = data[checksumOffset]
    print("ADJS: restore checksum ", shadowRam[chkAdr] )

    if extraStart!=0 and extraEnd!=0:
        print("restore extra section",extraStart,extraEnd,"len=",extraEnd-extraStart+1)
        extraLength = extraEnd-extraStart+1
        shadowRam[extraStart:extraEnd+1] = data[checksumOffset+1  : checksumOffset +1 +extraLength]

        print("ADJS: REstoring EX adjustment:","  - ".join(f"{b:02X}" for b in shadowRam[extraStart:extraEnd+1]))




    from DataMapper import _set_adjustment_checksum
    _set_adjustment_checksum()

    print("ADJS: checksum after re-calc", shadowRam[chkAdr] )

    fram.write_all_fram_now()
    print("ADJS: load done - resetting now ---------------------")
   
    # restart the pinball machine
    release(True)

    sleep(2)
    # restart the server schedule
    from phew.server import restart_schedule
    restart_schedule()


def store_adjustments(index):
    """
        store current adjustments into a storage location (0-3)
    """
    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid Index sa")
        return

    cpyStart, cpyEnd, chkAdr, exStart, exEnd = _get_range_from_gamedef()    
   
    # if valid ranges do the copy
    if cpyStart > 0 and cpyEnd > 0:
        Log.log(f"ADJS: Store {index} Range {cpyStart}:{cpyEnd}")

        # copy shadowram to fram
        data = bytearray(shadowRam[cpyStart:cpyEnd+1])
        print("data length a", len(data))

        print ("ADJS: storing checksum value ", shadowRam[chkAdr])
        data.extend(bytes( [shadowRam[chkAdr]] ))  #checksum 
        print("data length b", len(data))

        if exStart>0 and exEnd>0:
            print("ADJS: storing EX adjustment:","  - ".join(f"{b:02X}" for b in shadowRam[exStart:exEnd+1]))
            data.extend(bytearray(shadowRam[exStart:exEnd+1]))

        print("data length c", len(data))
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
        fram.write(fram_adr, data)
       
        # store this one as the last 'loaded'
        fram.write(ADJ_LAST_LOADED_ADR, bytearray([index]))
    else:
        Log.log("ADJS: No Gamedef ranges")


def get_active_adjustment():
    """look for acive adjustment profile
        Do not use built in checksum, it is simple and duplicates are common

        return None if no match, 0-3 if found
        in case of two matches use last_loaded number from fram
    """
    cpyStart, cpyEnd, chkAdr, x,y = _get_range_from_gamedef()
    if cpyStart == 0 or cpyEnd == 0 or chkAdr == 0:
        Log.log("ADJS: No valid range aa")
        return None

    #last_loaded_index = fram.read(ADJ_LAST_LOADED_ADR, 1)[0]
    #indexList = [last_loaded_index] + [x for x in range(4) if x != last_loaded_index]
    #print("ADJS: Active search list :",indexList)  

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
        Log.log("ADJS: No acitve adjustment found")
        return None

    # If there are multiple matches, use the last loaded index
    last_loaded_index = fram.read(ADJ_LAST_LOADED_ADR, 1)[0]

    if last_loaded_index in matches:
        return last_loaded_index

    return matches[0]  # Return the first match if last loaded index is not in matches


def is_populated(index):
    """
        return True if the profile is populated
        no need to lok at the whole thing - do 32 bytes only for speed
    """
    LOOK_SIZE = 32
    return fram.read(ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index, LOOK_SIZE) != b"\x00" * LOOK_SIZE



def get_profile_status():

    


def get_adjustments_status():
    """
        return list of tuples with names and active index, and if the profile is populated
    """   
    start,end,chk,x,y = _get_range_from_gamedef()
    adjustments_support = start > 0 and end > 0   # support Boolean


    names = [
        fram.read(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, ADJ_NAMES_LENGTH).decode("ascii").rstrip("\x00")
        for i in range(4)
    ]

    profile_status = get_profile_status()  # List of four (active, populated) tuples

    # Merge names and profile_status into one tuple per profile
    name_tuples = [
        (name, active, populated)
        for name, (active, populated) in zip(names, profile_status)
    ]

    print("ADJS: get_adjustments_status: adjustments_support $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$", adjustments_support, "profiles", name_tuples)

    # adjustment support is True/False
    # name_tuples   [('name1',active bool, poulated bool),('name2', , ),(),()]
    return {"adjustments_support": adjustments_support, "profiles": name_tuples}














if __name__ == "__main__":

    def fill_shadow_ram_with_pattern(pattern):
        """Fill shadowRam from cpyStart to cpyEnd with a given pattern."""
        cpyStart, cpyEnd = 6141, 7160  # johnny 
        pattern_length = len(pattern)
        print(len(shadowRam), cpyStart, cpyEnd, pattern_length)
        for i in range(0,  cpyEnd-cpyStart):
            #print(i)
            shadowRam[i+cpyStart] = pattern[i % pattern_length]

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
    print("A0:",   " ".join(f"{b:02X}" for b in shadowRam[6141:6141+16]))
    restore_adjustments(1, reset=False)
    print("A1:",   " ".join(f"{b:02X}" for b in shadowRam[6141:6141+16]))
    restore_adjustments(2, reset=False)
    print("A2:",   " ".join(f"{b:02X}" for b in shadowRam[6141:6141+16]))
    restore_adjustments(3, reset=False)
    print("A3:",   " ".join(f"{b:02X}" for b in shadowRam[6141:6141+16]))

    import time

    start_time = time.ticks_ms()

    i = get_active_adjustment()
    print("ACTIVE= ", get_active_adjustment())

    end_time = time.ticks_ms()
    execution_time_ms = time.ticks_diff(end_time, start_time)
    print(f"Execution time: {execution_time_ms} ms")
