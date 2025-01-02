'''
serial flash program update storage driver

Be sure to call initialize() at power  up !  

calls lower level SPI_Store driver (shared with FRAM)

- planning to use fram to track the status of the update slots
- will also include headers int he serial flash sections
'''
import uctypes
import SPI_Store
from logger import logger_instance
Log = logger_instance

# the first 64k and the last 64k blocks can be protected in 4k sectors
# so we will not use those here.  we need only 3 aresa of 6Mbyte each

#Serial Flash usage 
SFLASH_PRG_START = 0x0010000
SFLASH_PRG_SIZE  = 0x0600000   #6Mbyte
SFLASH_ERASE_SECTOR_SIZE = 0x010000  #64k
SFLASH_NUM_PGMS  = 3
'''
total SFLASH part is 32M byte:

Three section of 6M byte each used in this module
    0x0010000-0x0610000  block 1-96
    0x0610000-0x0C10000  block 97-192
    0x0C10000-0x1210000  block 193-288
    
'''

#status of state machines stuff in FRAM
FRAM_ADDRESS = 0x2000
FRAM_LENGTH  = 0x0FF     #reserved (256 bytes)
FRAM_BYTES_USED = 120

# each section has a status descriptor in FRAM:
SECTION_STATUS_DESC = {
    "state": uctypes.UINT32 | 0,          # 4 bytes (section status types below)
    "version_major": (uctypes.UINT8 | 4), 
    "version_middle": (uctypes.UINT8 | 5), 
    "version_minor": (uctypes.UINT8 | 6), 
    "complete": uctypes.UINT8 | 7,        # 1 byte (boolean)  true/false
    "progress": uctypes.UINT32 | 8  #end at |12           # 4 bytes   step into process (block number or incomming id number)
}

#section state types
SECTION_STATUS_FULL = 1
SECTION_STATUS_EMPTY = 2
SECTION_STATUS_ERASING = 3 
SECTION_STATUS_FILLING = 4 
SECTION_STATUS_READING = 5
SECTION_STATUS_VALID = {SECTION_STATUS_FULL, SECTION_STATUS_EMPTY, SECTION_STATUS_ERASING,SECTION_STATUS_FILLING,SECTION_STATUS_READING }

#overall datas structure in FRAM
BLOCK_STATUS_OFFSETS = [16, 48, 80]
DATA_STRUCTURE_DESC = {
    "state": uctypes.UINT32 | 0,          # 4 bytes  (general state)
    "block": uctypes.UINT32 | 4,          # 4 bytes  (block progress in active states)
    "block_status_0": (BLOCK_STATUS_OFFSETS[0], SECTION_STATUS_DESC),  
    "block_status_1": (BLOCK_STATUS_OFFSETS[1], SECTION_STATUS_DESC), 
    "block_status_2": (BLOCK_STATUS_OFFSETS[2], SECTION_STATUS_DESC)   
}

#overall state types  
SYSTEM_STATUS_IDLE = 0x100
SYSTEM_STATUS_ERASING = 0x200
SYSTEM_STATUS_READING = 0x300
SYSYTEM_STATUS_FILING = 0x400
SYSTEM_STATUS_VALID = {SYSTEM_STATUS_IDLE, SYSTEM_STATUS_ERASING, SYSTEM_STATUS_READING, SYSYTEM_STATUS_FILING}

data_buffer = bytearray(FRAM_BYTES_USED)  
data = uctypes.struct(uctypes.addressof(data_buffer), DATA_STRUCTURE_DESC, uctypes.LITTLE_ENDIAN)



#write structure to fram
def _write_status_to_fram():
    SPI_Store.write(FRAM_ADDRESS,data_buffer)

#read struct from fram to local ram
def _read_status_from_fram():    
    data_buffer[:]=SPI_Store.read(FRAM_ADDRESS,FRAM_BYTES_USED)






def _get_block_status(data, index):
    """ Get the block status struct by index from the data structure. """
    if 0 <= index < len(BLOCK_STATUS_OFFSETS):
        # Calculate the actual memory address of the block status
        address = uctypes.addressof(data) + BLOCK_STATUS_OFFSETS[index]
        return uctypes.struct(address, SECTION_STATUS_DESC, uctypes.LITTLE_ENDIAN)
    else:
        return None 

def _print_block_status(block_status, name):
            print(f"  {name}:")
            print("    State:", block_status.state)                    
            print("    Version:", block_status.version_major,":", block_status.version_middle,":", block_status.version_minor)            
            print("    Complete:", bool(block_status.complete))
            print("    progress:", block_status.progress)

def _find_next_task():
    print("next task find")
    # set system structure for next task if there is one
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        #test for uncomplete task or inconsistent state
        if dblk.state not in SECTION_STATUS_VALID:
            print("invalid state in block",i)
            dblk.state = SECTION_STATUS_ERASING
            dblk.progress = 0
        if dblk.state == SECTION_STATUS_ERASING:
            data.state = SYSTEM_STATUS_ERASING
            data.block = i
            dblk.complete = False
            dblk.progress = 0
            print("next task is block (erasing)",i)
        _write_status_to_fram()       

    #no sections to erase        
    data.state = SYSTEM_STATUS_IDLE
    print("next task done, IDLE")


def _set_block_status(block, state, progress, complete, version_major, version_middle, version_minor):
                block.progress=progress 
                block.complete=complete
                block.state=state
                block.version_major = version_major
                block.version_middle = version_middle
                block.version_minor = version_minor


#system must call peridocially - reccomend 1-5 seconds
# spam call to get an ongoing process finished (load or save etc)
def tick():
    if data.state == SYSTEM_STATUS_IDLE:
        return
    if data.state not in SYSTEM_STATUS_VALID:
        #data.state = SYSTEM_STATUS_IDLE
        _find_next_task()
        return 

    blk_num = data.block  #this is the block we're working on right now
    #print("block num",blk_num)
    dblk = _get_block_status(data,blk_num)
    #_print_block_status(dblk,"block in work now")

    #erase progress
    if dblk.state == SECTION_STATUS_ERASING:
        #ready for operation?
        if True == SPI_Store.sflash_is_ready():
            if dblk.progress == 0:
                #unlock all sectrors in this block
                SPI_Store.sflash_protect_sectors(SFLASH_PRG_START + SFLASH_PRG_SIZE * blk_num, SFLASH_PRG_START - 8 + SFLASH_PRG_SIZE * (blk_num+1), "off")            
            
            #erase next 64k
            dblk.progress += 1
            next_address = SFLASH_PRG_START + (SFLASH_PRG_SIZE * blk_num) - 8 + (SFLASH_ERASE_SECTOR_SIZE * dblk.progress)
    
            if next_address >= SFLASH_PRG_START + SFLASH_PRG_SIZE * (blk_num+1):
                #done erasing with all seectors
                SPI_Store.sflash_protect_sectors(SFLASH_PRG_START + SFLASH_PRG_SIZE * blk_num, SFLASH_PRG_START - 8 + SFLASH_PRG_SIZE * (blk_num+1), "on")                           
                _set_block_status(dblk, SECTION_STATUS_EMPTY, 0, True, 0, 0, 0)               
                _write_status_to_fram()                
                _find_next_task()
                return
            print(f"erase {next_address:#x}")
            SPI_Store.sflash_erase(next_address,next_address)

        else:
            print(" b ",end="")
    
   



def find_open_program_space():
    #find an empty block
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state == SECTION_STATUS_EMPTY & dblk.complete == True:            
            return i
    return None    

'''
def is_empty_program_space_available():
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state == SECTION_STATUS_EMPTY  &  dblk.complete == True:
            return True
    return False
'''

def oldest_nonempty_version_program_space():
    oldest = 999999    
    ans = None
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state != SECTION_STATUS_EMPTY:
            version = dblk.version_major * 10000 + dblk.version_middle * 100 + dblk.version_minor    
            if version < oldest:
                oldest = version
                ans = i
    return ans


def newest_version_program_space():
    newest = 0
    ans = None
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state != SECTION_STATUS_EMPTY:
            version = dblk.version_major * 10000 + dblk.version_middle * 100 + dblk.version_minor    
            if version > newest:
                newest = version
                ans = i
    return ans




#
#
#
def is_busy():
    return data.state != SYSTEM_STATUS_IDLE

#
#will only erase if all spaces are full
#erase can interrupt other operations
def erase_oldest_version_program_space():
    if find_open_program_space() != None:
        return
    oldest = oldest_nonempty_version_program_space()
    if oldest != None:        
        dblk=_get_block_status(data, oldest)
        _set_block_status(dblk, SECTION_STATUS_ERASING, 0, False, 0, 0, 0)
        data.state = SYSTEM_STATUS_ERASING
        data.block = oldest      
        _write_status_to_fram() 
        return True
    Log.log("UPST: fault erase oldest")

#
#start write to an empty space
#will not interrupt an erase operation
def start_write_program_space(version_major, version_middle, version_minor):
    if find_open_program_space() == None:        
        return False
    #find the open space
    open_space = find_open_program_space()
    dblk=_get_block_status(data, open_space)
    _set_block_status(dblk, SECTION_STATUS_FILLING, 0, False, version_major, version_middle, version_minor)
    data.state = SYSTEM_STATUS_
    data.block = open_space
    _write_status_to_fram() 
    return True


def write_program_space(data,last=False):
    pass


def report_all_version_numbers():
    pass

#
#start a read operation
#will not interrupt an erase operation 
def start_read_program_space(version_major, version_middle, version_minor):
    if find_open_program_space() == None:        
        return False
    #find the open space
    open_space = find_open_program_space()
    dblk=_get_block_status(data, open_space)
    _set_block_status(dblk, SECTION_STATUS_READING, 0, False, version_major, version_middle, version_minor)
    data.state = SYSTEM_STATUS_
    data.block = open_space
    _write_status_to_fram() 
    return True



def read_program_space():
    pass



# call at power up - will do integrity check
# relaunch paused processes etc...  
def initialize():
    print("init")

    _read_status_from_fram()
    
    if data.state not in SYSTEM_STATUS_VALID:
        data.state = SYSTEM_STATUS_IDLE

    #unfinished filling changes to erase on power up---
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state == SECTION_STATUS_FILLING:
            dblk.state = SECTION_STATUS_ERASING
            dblk.progress = 0                       
            dblk.complete = False
            data.state = SYSTEM_STATUS_ERASING
            data.block = i
    
    for i in range(SFLASH_NUM_PGMS):
        er=0
        dblk=_get_block_status(data, i)
        if dblk.state == SECTION_STATUS_ERASING:
            er=1
    if er == 0:  #no erase, goto idle
        data.state = SYSTEM_STATUS_IDLE    

    _write_status_to_fram()        
            

    

#dump all sflash data for all programs, reset structures
def blank_all():
    #active work, start with block 0
    data.state = SYSTEM_STATUS_ERASING
    data.block = 0
    # Set each block to ERASE
    for offset in range(SFLASH_NUM_PGMS):
        #block_status = uctypes.struct(uctypes.addressof(data_buffer) + offset, SECTION_STATUS_DESC, uctypes.LITTLE_ENDIAN)
        block_status=_get_block_status(data, offset)
        block_status.state = SECTION_STATUS_ERASING
        block_status.version_major=0
        block_status.version_middle=0
        block_status.version_minor=0
        block_status.complete = False 
        block_status.progress = 0

    #_write_status_to_fram()
    #this could take a while!
    #while(data.state != SYSTEM_STATUS_IDLE):
    for i in range(20):        
        tick()
        print("tick")






if __name__ == "__main__":

    #blank()
    import time

    SPI_Store.sflash_init()

    initialize()

    def print_data_structure(data):
        print("Main Data Structure:")
        print("  State:", data.state)
        print("  Block:", data.block)

        def print_block_status(block_status, name):
            print(f"  {name}:")
            print("    State:", block_status.state)                    
            print("    Version:", block_status.version_major,":", block_status.version_middle,":", block_status.version_minor)            
            print("    Complete:", bool(block_status.complete))
            print("    progress:", block_status.progress)

        print_block_status(data.block_status_0, "Block Status 0")
        print_block_status(data.block_status_1, "Block Status 1")
        print_block_status(data.block_status_2, "Block Status 2")


    '''
    data.state = SYSTEM_STATUS_SECTION_WORK
    data.block = 0
    data.block_status_0.state = SECTION_STATUS_ERASING
    data.block_status_0.version_major = 112
    data.block_status_0.version_middle = 113
    data.block_status_0.version_minor = 114
    data.block_status_0.complete = False
    data.block_status_0.progress = 0

    data.block_status_1.state = SECTION_STATUS_ERASING
    data.block_status_1.version_major = 122
    data.block_status_1.version_middle = 133
    data.block_status_1.version_minor = 144
    data.block_status_1.complete = True
    data.block_status_1.progress = 0

    data.block_status_2.state = SECTION_STATUS_ERASING
    data.block_status_2.version_major = 72
    data.block_status_2.version_middle = 83
    data.block_status_2.version_minor = 94
    data.block_status_2.complete = False
    data.block_status_2.progress = 0

    _write_status_to_fram()  
    
    '''
   
    print_data_structure(data)
    
    
    #blank()
    
    #print("Restored block status 1 version:", bytes(restored_data.block_status_1.version[0:8]).decode())
    
    b=True
    print("BUSY? ",is_busy())
    print_data_structure(data)
    print("stat  ",data.state)
    #for i in range(200):
    while b==True:
        tick()        
        b=is_busy()
        if b==True:
            time.sleep(0.5)
            print("b",b,data.state)

    print_data_structure(data)
    print("BUSY? ",is_busy())
    