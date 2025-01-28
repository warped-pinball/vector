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

# large array for the 'shadow' ram
SRAM_DATA_BASE = 0x2003F000  # 0x20040000-0x20042000  (8k available)
SRAM_DATA_BASE_21 = SRAM_DATA_BASE >> 11  # 21 MSBits to be preloaded in pio for address generation

# SRAM_DATA_LENGTH = 0x00002000  #8k byte total
SRAM_DATA_LENGTH = 0x00000800  # 2k byte total

# write access counter location
SRAM_COUNT_BASE = 0x2003F800
SRAM_COUNT_BASE_21 = SRAM_COUNT_BASE >> 11

SRAM_COUNT_LENGTH = SRAM_DATA_LENGTH

shadowRam = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)

# large array for the number of writes to ram
SRAM_COUNT_BASE = 0x20041000
SRAM_COUNT_BASE_21 = SRAM_COUNT_BASE >> 11
writeCountRam = uctypes.bytearray_at(SRAM_COUNT_BASE, SRAM_DATA_LENGTH)
