'''
save and restosre adjustments 

four save indexes
16 character name for each


'''
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
import SPI_Store as fram
from logger import logger_instance
Log = logger_instance



def blank_all():


#get names for all four indexes
def get_names():


#pull memory of index and pu in the game memory
#optionally cause a reset so the change take effect
def restore_adjustments(index,restore=True):



#store current game adjustments into a storage location (0-3)
def store_adjustments(index):
    if index not in [0,1,2,3]:
        Log.Log("ADJS: invalid index")
        return

    #copy 0x780 to 0x7FF from shadowram to fram
    fram[target_address:target_address + (end - start)] = shadowram[start:end]


