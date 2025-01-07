'''
Save and Restore adjustments 

four save indexes
16 character name for each

'''
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
import SPI_Store as fram
from logger import logger_instance
Log = logger_instance
import SharedState as S
import displayMessage
import machine

ADJ_FRAM_START = 0x2100  # to 0x2340
ADJ_FRAM_RECORD_SIZE = 0x80
ADJ_NUM_SLOTS = 4
ADJ_NAMES_START = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * ADJ_NUM_SLOTS
ADJ_NAMES_LENGTH = 16    


def blank_all():
    """ blank out all names and storage """    
    for i in range(4):
        set_name(i, "")
        #blank the data also
        data = bytearray(ADJ_FRAM_RECORD_SIZE)
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * i
        fram.write(fram_adr, data)       
    
def get_names():
    """read out all four names"""
    return [
        fram.read(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, ADJ_NAMES_LENGTH).decode('ascii').rstrip('\x00')
        for i in range(4)
    ]


def set_name(index, name):
    """set name"""
    if index<0 or index>=ADJ_NUM_SLOTS :
        Log.log("ADJS: invalid index nm")
        return
       
    name = name[:16]     
    name_bytes = bytearray(name.encode('ascii') + b'\x00' * (16 - len(name)))
    # Calculate the FRAM address for this index
    fram_address = ADJ_NAMES_START + index * ADJ_NAMES_LENGTH
    fram.write(fram_address, name_bytes)
    Log.log(f"ADJS: Name set at index {index}: {name}")


def restore_adjustments(index, reset=True):
    """pull from fram data and put in shadow ram, reset after by default"""
    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid index ra")
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

    #game file can have special range
    cpyStart = S.gdata["Adjustments"].get("cpyStart", -1)
    cpyEnd = S.gdata["Adjustments"].get("cpyEnd", -1)
    #or load standard based on adjustment types in game file
    if cpyStart < 0 or cpyEnd < 0:
        if S.gdata["Adjustments"].get("Type", 0) == 1:
            cpyStart = 0x780
            cpyEnd = 0x800        

    # copy
    if cpyStart > 0 and cpyEnd > 0 and (cpyEnd - cpyStart) <= len(data):
        shadowRam[cpyStart:cpyEnd] = data[:cpyEnd - cpyStart]
        Log.log(f"ADJS: Adjustments restored {cpyStart:04X}-{cpyEnd - 1:04X}")

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
    if index<0 or index>=ADJ_NUM_SLOTS :
        Log.log("ADJS: invalid index sa")
        return

    #for ranges check game data:
    #       1) check Adjustment.cpyStart / cpyEnd
    #       2) then if Adjustments.Type ==1 assume 780-7ff
    #       3) fault - no ranges   
    cpyStart = S.gdata["Adjustments"].get("cpyStart",-1)
    cpyEnd = S.gdata["Adjustments"].get("cpyEnd",-1)
    if cpyStart<0 or cpyEnd<0:
        if S.gdata["Adjustments"].get("Type", 0) == 1:
            cpyStart = 0x780
            cpyEnd = 0x800
    
    #if valid ranges do the copy
    if cpyStart>0 and cpyEnd>0:
        Log.log(f"ADJS: Store {index} Range {cpyStart}:{cpyEnd}")

        #copy shadowram to fram
        data = shadowRam[cpyStart:cpyEnd]
        fram_adr = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * index
        fram.write(fram_adr, data)   

        hex_data = " ".join(f"{byte:02X}" for byte in data)
        print(f"ADR: {fram_adr:04X} DAT: {hex_data}")
        
    else:
        Log.log("ADJS: No Ranges")
    





if __name__ == "__main__":

    import GameDefsLoad
    GameDefsLoad.go() 

    print("ADJUSTMENT save settings:")
    print(f"   data start=0x{ADJ_FRAM_START:X} size=0x{ADJ_FRAM_RECORD_SIZE:X} slots={ADJ_NUM_SLOTS}")
    print(f"   data used area=0x{ADJ_FRAM_START:X} to 0x{ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * ADJ_NUM_SLOTS:X}")
    print(f"   names start=0x{ADJ_NAMES_START:X} length=0x{ADJ_NAMES_LENGTH:X}")
    print(f"   names used area=0x{ADJ_NAMES_START:X} to 0x{ADJ_NAMES_START + ADJ_NAMES_LENGTH * ADJ_NUM_SLOTS:X}\n")

    print("blank all")
    blank_all()
    print("blank all done\n")

    set_name(0,'One')
    set_name(1,"two  ")
    set_name(2,"abcdefghijationj")
    set_name(3,"123456789123456789")
    
    print(restore_adjustments(0))

    print("\n read names: ",get_names())

    print(store_adjustments(0))
    print(store_adjustments(1))
    print(store_adjustments(2))
    print(store_adjustments(3))

    print("\n read names: ",get_names())
    print(restore_adjustments(0,False))