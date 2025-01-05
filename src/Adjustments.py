'''
Save and Restosre adjustments 

four save indexes
16 character name for each

'''
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
import SPI_Store as fram
from logger import logger_instance
Log = logger_instance
import SharedState as S
import displayMessage

ADJ_FRAM_START = 0x2100
ADJ_FRAM_RECORD_SIZE = 0x80
ADJ_NUM_SLOTS = 4
ADJ_NAMES_START = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * ADJ_NUM_SLOTS
ADJ_NAMES_LENGTH = 16    


def blank_all():
    for i in range(4):
        set_name(i, "")
    
    

#get names for all four indexes
def get_names():
     return [
        fram.read(ADJ_NAMES_START + i * ADJ_NAMES_LENGTH, ADJ_NAMES_LENGTH).decode('ascii').rstrip('\x00')
        for i in range(4)
    ]


#set a name value
def set_name(index, name):
    if index<0 or index>=ADJ_NUM_SLOTS :
        Log.log("ADJS: invalid index nm")
        return
   
    name = name[:16]     
    name_bytes = bytearray(name.encode('ascii') + b'\x00' * (16 - len(name)))

    # Calculate the FRAM address for this index
    fram_address = ADJ_NAMES_START + index * ADJ_NAMES_LENGTH
    fram.write(fram_address, name_bytes)

    Log.log(f"ADJS: Name set at index {index}: {name}")




#pull memory of index and pu in the game memory
#optionally cause a reset so the change take effectdef restore_adjustments(index, reset=True):
def restore_adjustments(index, reset=True):
    if index < 0 or index >= ADJ_NUM_SLOTS:
        Log.log("ADJS: Invalid index ra")
        return

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

    cpyStart = S.gdata["Adjustments"].get("cpyStart", -1)
    cpyEnd = S.gdata["Adjustments"].get("cpyEnd", -1)
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
            #machine.reset()
    else:
        Log.log("ADJS: range fault")



    



#store current game adjustments into a storage location (0-3)
def store_adjustments(index):
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
        Log.log("ADJS: No Store")
        print(S.gdata)





if __name__ == "__main__":

    import GameDefsLoad
    GameDefsLoad.go() 

    ADJ_FRAM_START = 0x2000
    ADJ_FRAM_RECORD_SIZE = 0x80
    ADJ_NUM_SLOTS = 4
    ADJ_NAMES_START = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * ADJ_NUM_SLOTS
    ADJ_NAMES_LENGTH = 16    

    print("ADJIUSTMENT save settings:")
    print("   data start=",ADJ_FRAM_START," size=",ADJ_FRAM_RECORD_SIZE," slots=",ADJ_NUM_SLOTS)
    print("   data used area=",ADJ_FRAM_START," to ",ADJ_FRAM_START+ADJ_FRAM_RECORD_SIZE*ADJ_NUM_SLOTS)
    print("   names start=",ADJ_NAMES_START," length=",ADJ_NAMES_LENGTH)
    print("   names used area=", ADJ_NAMES_START, " to ", ADJ_NAMES_START + ADJ_NAMES_LENGTH*ADJ_NUM_SLOTS)

    blank_all()
    store_adjustments(0)
    store_adjustments(1)
    store_adjustments(2)


    set_name(0,"One")
    set_name(1,"two  ")
    set_name(2,"abcdefghijationj")
    set_name(3,"123456789123456789")

    store_adjustments(3)
    print(get_names())

    restore_adjustments(1,False)


