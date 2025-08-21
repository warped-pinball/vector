# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
EM - there is no shadow ram ~~~~~~~~~

Definitions for the location and length of internal RP2040
    ram used to replace the on mother-board SRAM
    These definitions used by all modules
"""
import uctypes



SRAM_DATA_BASE = 0x20080000
SRAM_DATA_LENGTH = 0x0000000    
shadowRam = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)

print("sram->", len(shadowRam), hex(SRAM_DATA_BASE), hex(SRAM_DATA_LENGTH))
