'''
serial flash program update storage driver

calls lower level SPI_Store driver (shared with FRAM)

- planning to use fram to track the statu sof the update slots
- will also include headers int he serial flash sections

'''
import uctypes
import SPI_Store


# the first 64k and the last 64k blocks can be protected in 4k sectors
# so we will not use those here.  we need only 3 aresa of 6Mbyte each

#status stuff in FRAM
FRAM_ADDRESS = 0x2000
FRAM_LENGTH  = 0x0FF     #reserved


#Serial Flash usage 
SFLASH_PRG_START = 0x0010000
SFLASH_PRG_SIZE  = 0x600000   #6Mbyte
SFLASH_NUM_PGMS  = 3

'''
total part is 32M byte:

Three section of 6M byte each used in this module
    0x0010000-0x0610000
    0x0610000-0x0C10000
    0x0C10000-0x1210000
    
'''



# each section has a status descriptor:
SECTION_STATUS_DESC = {
    "state": uctypes.UINT32 | 0,          # 4 bytes
    "version": (uctypes.ARRAY | 4, uctypes.UINT8),  # 8 bytes, assuming ASCII encoding
    "complete": uctypes.UINT8 | 12,       # 1 byte (boolean)
    "status": uctypes.UINT32 | 16         # 4 bytes 
}

#overall datas structure
DATA_STRUCTURE_DESC = {
    "state": uctypes.UINT32 | 0,          # 4 bytes  (general state)
    "block": uctypes.UINT32 | 4,          # 4 bytes  (block progress in active states)
    "block_status_1": (16, SECTION_STATUS_DESC),  
    "block_status_2": (32, SECTION_STATUS_DESC), 
    "block_status_3": (48, SECTION_STATUS_DESC)   
}

FRAM_BYTES_USED = 64
data_buffer = bytearray(FRAM_BYTES_USED)  
data = uctypes.struct(uctypes.addressof(data_buffer), DATA_STRUCTURE_DESC, uctypes.LITTLE_ENDIAN)





#write structure to fram
def _write_status_to_fram():
    SPI_Store.write(FRAM_ADDRESS,data_buffer)

#read struct from fram to local ram
def _read_status_from_fram():
    return SPI_Store.read(FRAM_ADDRESS,FRAM_BYTES_USED)


def print_data_structure(data):
    print("Main Data Structure:")
    print("  State:", data.state)
    print("  Block:", data.block)

    # Function to print each block status
    def print_block_status(block_status, name):
        print(f"  {name}:")
        print("    State:", block_status.state)
        version_string = bytes(block_status.version[0:8]).decode('utf-8')
        print("    Version:", version_string)
        print("    Complete:", bool(block_status.complete))
        print("    Status:", block_status.status)

    # Print each block status structure
    print_block_status(data.block_status_1, "Block Status 1")
    print_block_status(data.block_status_2, "Block Status 2")
    print_block_status(data.block_status_3, "Block Status 3")




if __name__ == "__main__":

    data.state = 112
    data.block = 22
    data.block_status_1.state = 3
    data.block_status_1.version[0:8] = b'VER12345'
    data.block_status_1.complete = 1
    data.block_status_1.status = 0

    data.block_status_2.state = 4
    data.block_status_2.version[0:8] = b'VER23456'
    data.block_status_2.complete = 0
    data.block_status_2.status = 1

    data.block_status_3.state = 5
    data.block_status_3.version[0:8] = b'VER34567'
    data.block_status_3.complete = 1
    data.block_status_3.status = 2

    _write_status_to_fram()  
    restored_data_buffer = _read_status_from_fram()

    restored_data = uctypes.struct(uctypes.addressof(restored_data_buffer), DATA_STRUCTURE_DESC, uctypes.LITTLE_ENDIAN)
    print(restored_data.state, restored_data.block)

    print_data_structure

    print("Restored block status 1 version:", bytes(restored_data.block_status_1.version[0:8]).decode())


