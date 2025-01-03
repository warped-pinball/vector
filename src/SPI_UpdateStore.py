'''
serial flash program update storage driver

Be sure to call initialize() at power  up !  

calls lower level SPI_Store driver (shared with FRAM)


Usage:
    initialize() - call at power up
    tick() - call periodically to manage ongoing erase operations
    is_busy() - returns True if there is an ongoing erase operation
    blank_all() - Factory use only, blocking. deletes all
    erase_oldest_version_program_space() - erase the oldest version in the serial flash if there is no open block


    start_write_program_space() - start a write operation
    write_program_space() - write data to the serial flash
    start_read_program_space() - start a read operation
    read_program_space() - read data from the serial flash

   diagnostics: 
    report_all_version_numbers() - return a list of all version numbers in the serial flash
    newest_version_program_space() - return the newest version number in the serial flash
    oldest_version_program_space() - return the oldest version number in the serial flash



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
    "state": (uctypes.UINT32 | 0),              # 4 bytes (section status types below)
    "version_major": (uctypes.UINT8 | 4),       #0-99, byte
    "version_middle": (uctypes.UINT8 | 5),      #0-99, byte
    "version_minor": (uctypes.UINT8 | 6),       #0-99, byte
    "erase_pointer": (uctypes.UINT8 | 7),       # 1 byte (block number)
    "read_pointer": (uctypes.UINT32 | 8),       #32 bit address
    "write_pointer": (uctypes.UINT32 | 12)      #32 bit address   (offset 12,13,14,15)
}

#section state types
SECTION_STATUS_FULL = 1
SECTION_STATUS_EMPTY = 2
SECTION_STATUS_ERASING = 3 
SECTION_STATUS_FILLING = 4 
SECTION_STATUS_READING = 5
SECTION_STATUS_VALID = {SECTION_STATUS_FULL, SECTION_STATUS_EMPTY, SECTION_STATUS_ERASING,SECTION_STATUS_FILLING,SECTION_STATUS_READING }

#overall datas structure in FRAM
BLOCK_STATUS_OFFSETS = [16, 48, 80]  #80-112
DATA_STRUCTURE_DESC = {
    "state_reserve": uctypes.UINT32 | 0,          # 4 bytes  (general state)
    "progr_reserve": uctypes.UINT32 | 4,          # 4 bytes  (block progress in active states)
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

#helper function to set block status
def _set_block_status(block, state, version_major, version_middle, version_minor, erase_pointer, read_pointer, write_pointer):            
    block.state=state
    block.version_major = version_major
    block.version_middle = version_middle
    block.version_minor = version_minor
    block.erase_pointer = erase_pointer
    block.read_pointer = read_pointer
    block.write_pointer = write_pointer

def _print_block_status(block_status, name):
    print(f"  {name}:")
    print("    State:", block_status.state)                    
    print("    Version:", block_status.version_major,":", block_status.version_middle,":", block_status.version_minor)            
    print("    Complete:", bool(block_status.complete))
    print("    progress:", block_status.progress)


#return index for open block - return index
def _find_open_block():
    #find an empty block
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state == SECTION_STATUS_EMPTY & dblk.complete == True:            
            return i
    return None    


#reports [index,string] of newest version
def _newest_version_program_space():
    newest = 0
    ans = None
    version_str = "none"
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state != SECTION_STATUS_EMPTY:
            version = dblk.version_major * 10000 + dblk.version_middle * 100 + dblk.version_minor    
            if version > newest:
                newest = version
                version_str = f"{dblk.version_major}.{dblk.version_middle}.{dblk.version_minor}"
                ans = i
    return ans,version_str

#find oldest version avilable - return [index,version]
def _oldest_version_program_space():
    oldest = 999999    
    ans = None
    version_str= "none"
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state != SECTION_STATUS_EMPTY:
            version = dblk.version_major * 10000 + dblk.version_middle * 100 + dblk.version_minor    
            if version < oldest:
                oldest = version
                version_str = f"{dblk.version_major}.{dblk.version_middle}.{dblk.version_minor}"
                ans = i
    return ans,version_str


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




#system must call peridocially - minimum period 100mS - reccommand 1 second
# At 1 second call rate erase block will take 97 seconds
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
    
   

#
#can check before read or write or erase operation is started
def is_busy():
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        if dblk.state == SECTION_STATUS_ERASING:
            return True
    return False


#will only erase if all spaces are full
#erase can interrupt other operations
def erase_oldest_version_program_space():
    if _find_open_block() != None:  #there is already an open space
        return
    oldest, _ = _oldest_version_program_space()
    if oldest != None:        
        dblk=_get_block_status(data, oldest)
        _set_block_status(dblk, SECTION_STATUS_ERASING, 0, 0, 0, 0, 0)

        data.block = oldest      
        _write_status_to_fram() 
        return True
    Log.log("UPST: fault erase oldest")


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
    versions = []
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        if dblk:
            version_str = f"{dblk.version_major}.{dblk.version_middle}.{dblk.version_minor}"
            versions.append(version_str)
    return versions

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
    _read_status_from_fram()
    #look for any block in the middle of erase and restart it
    for i in range(SFLASH_NUM_PGMS):
        dblk=_get_block_status(data, i)
        if dblk.state == SECTION_STATUS_ERASING:
            dblk.erase_pointer = 0

    

#dump all sflash data for all programs, reset structures
#BLOCKING - intended for facotry reset only
def blank_all():
    
    data.state_reserve = 0
    data.progr_reserve = 0

    # Erase each block with wait on
    for i in range(SFLASH_NUM_PGMS):
        SPI_Store.sflash_protect_sectors(SFLASH_PRG_START+SFLASH_PRG_SIZE*i,SFLASH_PRG_START+SFLASH_PRG_SIZE*(i+1),"off")
        print("UPDSTORE: erasing block",i)
        SPI_Store.sflash_erase(SFLASH_PRG_START+SFLASH_PRG_SIZE*i,SFLASH_PRG_START+SFLASH_PRG_SIZE*(i+1),True)
        block_status=_get_block_status(data, i)
        _set_block_status(block_status, SECTION_STATUS_EMPTY, 0, 0, 0, 0, 0,0)
        _write_status_to_fram()
        SPI_Store.sflash_protect_sectors(SFLASH_PRG_START+SFLASH_PRG_SIZE*i,SFLASH_PRG_START+SFLASH_PRG_SIZE*(i+1),"on")
    







if __name__ == "__main__":

    def print_data_structure(data):
        print("Main Data Structure:")
        print("  State Reserve:", data.state_reserve)
        print("  Progr Reserve:", data.progr_reserve)

        def print_block_status(block_status, name):
            print(f"  {name}:")
            print("    State:", block_status.state)                    
            print("    Version:", block_status.version_major,":", block_status.version_middle,":", block_status.version_minor)            
            print("    Erase Pointer:", block_status.erase_pointer)
            print("    Read Pointer:", block_status.read_pointer)
            print("    Write Pointer:", block_status.write_pointer)    

        print_block_status(data.block_status_0, "Block Status 0")
        print_block_status(data.block_status_1, "Block Status 1")
        print_block_status(data.block_status_2, "Block Status 2")


    SPI_Store.initialize()
    #_read_status_from_fram()
    #blank_all()  #<<manufacturing reset all
    initialize()

    print_data_structure(data)

    print("\nVersion numbers in storage now:")
    print(report_all_version_numbers())

    print("\nNewest Verrsion number in storage now (index,version):")
    print(_newest_version_program_space())

    print("\nOldest Verrsion number in storage now (index,version):")
    print(_oldest_version_program_space())





















    
    data.state_reserve = 3
    data.progr_reserve = 4
    data.block_status_0.state = SECTION_STATUS_ERASING
    data.block_status_0.version_major = 11
    data.block_status_0.version_middle = 10
    data.block_status_0.version_minor = 11
    data.block_status_0.erase_pointer = 115
    data.block_status_0.read_pointer = 116
    data.block_status_0.write_pointer = 117

    data.block_status_1.state = SECTION_STATUS_ERASING
    data.block_status_1.version_major = 12
    data.block_status_1.version_middle = 13
    data.block_status_1.version_minor = 14
    data.block_status_1.erase_pointer = 1
    data.block_status_1.read_pointer = 2
    data.block_status_1.write_pointer = 3

    data.block_status_2.state = SECTION_STATUS_EMPTY
    data.block_status_2.version_major = 72
    data.block_status_2.version_middle = 83
    data.block_status_2.version_minor = 94
    data.block_status_2.erase_pointer = 0
    data.block_status_2.read_pointer = 0
    data.block_status_2.write_pointer = 0
    
    _write_status_to_fram()     

    
    
   
   
    
    