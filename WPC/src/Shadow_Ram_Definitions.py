# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Sys11Wifi ShadowRamDefs.py

Definitions for the location and length of internal RP2040
    ram used to replace the on mother-board SRAM
    These definitions used by all modules
"""
import uctypes

# system 9 and 11 need 2k array for the 'shadow' ram
#SRAM_DATA_BASE = 0x20040000  # 0x20040000-0x20040800 (2k)

#SRAM_DATA_BASE = 0x20041800   #very end of ram - 2k

SRAM_DATA_BASE = 0x20080000 # WPC!  PICO2W



#SRAM_DATA_BASE_21 = SRAM_DATA_BASE >> 11  # 21 MSBits to be preloaded in pio for address generation
#SRAM_DATA_LENGTH = 0x00000800  # 2k byte total

#going to FULL 8k ->
SRAM_DATA_BASE_19 = SRAM_DATA_BASE >> 13    #19 MSBits to be preloaded in pio for address generation
SRAM_DATA_LENGTH = 0x00002000    #8k byte total

shadowRam = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)

print("sram->", len(shadowRam), hex(SRAM_DATA_BASE), hex(SRAM_DATA_LENGTH))
