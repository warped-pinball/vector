# This file is part of the Warped Pinball Vector (DataEast) Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
DE Wifi ShadowRamDefs.py

Definitions for the location and length of internal RP2350
    ram used to replace the on mother-board SRAM
    These definitions used by all modules
"""
import uctypes

# 8k block
# two locations 0x1FFA and 0x1FFB are also read and written by the clock module
SRAM_DATA_BASE = 0x20080000                 #WPC!  PICO2W  original 8k block
SRAM_DATA_BASE_19 = SRAM_DATA_BASE >> 13    #MSBits to be preloaded in pio for address generation
SRAM_DATA_LENGTH = 0x00002000               #8k byte total

shadowRam = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
print("sram->", len(shadowRam), hex(SRAM_DATA_BASE), hex(SRAM_DATA_LENGTH))

SRAM_CLOCK_MINUTES = 0x20081FFB
SRAM_CLOCK_HOURS = 0x20081FFA
