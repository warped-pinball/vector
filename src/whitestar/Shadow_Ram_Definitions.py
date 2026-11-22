# This file is part of the Warped Pinball Vector (Whitestar) Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Whitestar ShadowRamDefs.py

Definitions for the location and length of internal RP2350
    ram used to replace the on mother-board SRAM
    These definitions used by all modules

Whitestar (Sega / Stern 1995-2006) CPU boards keep 8K of battery backed
RAM at $0000-$1FFF, the same layout as Data East. There is no real time
clock inside the RAM window (unlike WPC), so no clock addresses exist here.
"""
import uctypes

# 8k block
SRAM_DATA_BASE = 0x20080000                 # PICO2W, 8k block (same placement as WPC)
SRAM_DATA_BASE_19 = SRAM_DATA_BASE >> 13    # MSBits to be preloaded in pio for address generation
SRAM_DATA_LENGTH = 0x00002000               # 8k byte total

shadowRam = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)

if __name__ == "__main__":
    print("sram->", len(shadowRam), hex(SRAM_DATA_BASE), hex(SRAM_DATA_LENGTH))
