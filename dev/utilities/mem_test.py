
import uctypes
import SPI_Store as fram
from displayMessage import fixAdjustmentChecksum
from logger import logger_instance
Log = logger_instance
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH, shadowRam


#high_ram = uctypes.bytearray_at(SRAM_DATA_BASE+2048, 1500)

high_ram = uctypes.bytearray_at(SRAM_DATA_BASE+2048, 1024*4)



def w():
    for i in range(1024*4):
        high_ram[i] = 0


def print_memory():
    for i in range(0, 1024*4, 16):
        print(f"{i:04x}: ", end="")
        ascii_repr = ""
        for j in range(16):
            if i + j < 1024*4:
                byte = high_ram[i + j]
                print(f"{byte:02x} ", end="")
                ascii_repr += chr(byte) if 32 <= byte <= 126 else "."
        print(f" {ascii_repr}")


def r():
    print_memory()
    print("Address of shadowRam:", hex(uctypes.addressof(shadowRam)))   
    print("Address of high_ram:", hex(uctypes.addressof(high_ram)))


    

