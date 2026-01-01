"""
Data East

Save and Restore adjustments
four save indexes
16 character name for each

for Data East checksum result is seperated from data range
also store "extra" section outside of normal checsksum range
"""

from Shadow_Ram_Definitions import shadowRam
import SharedState as S
import SPI_Store as fram
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
    """ 
        get range of adjustments in shadowram from gamedef json
    """
    cpyStart = cpyEnd = chkAdr = 0
    if S.gdata["Adjustments"]["Type"] == 20:
        cpyStart = S.gdata["Adjustments"].get("ChecksumStartAdr", 0)
        cpyEnd = S.gdata["Adjustments"].get("ChecksumEndAdr", 0)
        chkAdr = S.gdata["Adjustments"].get("ChecksumResultAdr", 0)
        
        extraStart = S.gdata["Adjustments"].get("ExtraStartAdr", 0)
        extraEnd = S.gdata["Adjustments"].get("ExtraEndAdr", 0)

    if ((cpyEnd-cpyStart)+(extraEnd-extraStart)+4) > ADJ_FRAM_RECORD_SIZE:
        Log.log("ADJ: adjustment record size fault")
        return 0,0,0,0,0
    return cpyStart, cpyEnd, chkAdr, extraStart, extraEnd          

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
    """
        pull from FRAM data and put in shadow ram in the machine, 
        reset after by default
    """

    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid Index ra")
        return

    fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
    data = fram.read(fram_adr, ADJ_FRAM_RECORD_SIZE)

    cpyStart, cpyEnd, chkAdr, extraStart, extraEnd = _get_range_from_gamedef()
    if (cpyStart == 0 or cpyEnd == 0):
        Log.log("ADJS: No valid range found in game data 2")
        return

    # store this index as the last loaded
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
    #print("length data - - - ",len(data),chkAdr,cpyEnd,"chk index=",cpyEnd - cpyStart+1)
    checksumOffset = cpyEnd - cpyStart +1
    shadowRam[chkAdr] = data[checksumOffset]
    #print("ADJS: restore checksum ", shadowRam[chkAdr] )

    if extraStart!=0 and extraEnd!=0:
        #print("restore extra section",extraStart,extraEnd,"len=",extraEnd-extraStart+1)
        extraLength = extraEnd-extraStart+1
        shadowRam[extraStart:extraEnd+1] = data[checksumOffset+1  : checksumOffset +1 +extraLength]
        #print("ADJS: Restoring EX adjustment:","  - ".join(f"{b:02X}" for b in shadowRam[extraStart:extraEnd+1]))

    from DataMapper import _set_adjustment_checksum
    _set_adjustment_checksum()

    #print("ADJS: checksum after re-calc", shadowRam[chkAdr] )

    fram.write_all_fram_now()
    print("ADJS: load done - resetting now")
   
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

        #print ("ADJS: storing checksum value ", shadowRam[chkAdr])
        data.extend(bytes( [shadowRam[chkAdr]] ))  #checksum 

        if exStart>0 and exEnd>0:
            #print("ADJS: storing EX adjustment:","  - ".join(f"{b:02X}" for b in shadowRam[exStart:exEnd+1]))
            data.extend(bytearray(shadowRam[exStart:exEnd+1]))

        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
        fram.write(fram_adr, data)
       
        # store this one as the last 'loaded'
        fram.write(ADJ_LAST_LOADED_ADR, bytearray([index]))
    else:
        Log.log("ADJS: No Gamedef ranges")




def get_profile_status():
    """
        2x Booleans for each of four adjustments profiles
        [(active now,populated with data),  x4]
    """
    start, end, chk, extra_start, extra_end = _get_range_from_gamedef()
    result = [(False, False), (False, False), (False, False), (False, False)]
    lastLoaded = fram.read(ADJ_LAST_LOADED_ADR, 1)
    lastLoadedIndex = lastLoaded[0] if lastLoaded and len(lastLoaded) > 0 else -1

    active_data = shadowRam[start:end+1]
    stored_datas = []
    for i in range(4):
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * i
        stored_data = fram.read(fram_adr, end - start + 1)
        stored_datas.append(stored_data)

    # Default: all inactive, but set is_active True only for lastLoadedIndex if it matches
    for i in range(4):
        is_populated = any(b != 0 for b in stored_datas[i])
        result[i] = (False, is_populated)

    if 0 <= lastLoadedIndex < 4:
        if active_data == stored_datas[lastLoadedIndex]:
            # Only this one is active
            is_populated = any(b != 0 for b in stored_datas[lastLoadedIndex])
            result[lastLoadedIndex] = (True, is_populated)

    return result

    


def get_adjustments_status():
    """
        return list of tuples with names and active index, and if the profile is populated
    """   
    start,end,chk,x,y = _get_range_from_gamedef()
    adjustments_support = start > 0 and end > 0   # support Boolean

    names = ("","","","")
    profile_status = [(False,False),(False,False),(False,False),(False,False)]

    if adjustments_support:
        names = (
            fram.read(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, ADJ_NAMES_LENGTH).decode("ascii").rstrip("\x00")
            for i in range(4)
        )

        profile_status = get_profile_status()  # List of four (active, populated) tuples

    # Merge names and profile_status into one tuple per profile
    name_tuples = [
        (name, active, populated)
        for name, (active, populated) in zip(names, profile_status)
    ]

    print("ADJS: get_adjustments_status:", adjustments_support, "profiles:", name_tuples)

    # adjustment support is True/False
    # name_tuples   [('name1',active bool, poulated bool),('name2', , ),(),()]
    return {"adjustments_support": adjustments_support, "profiles": name_tuples}

