# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Sys11Wifi ShadowRamDefs.py

Detect Pico 1 (RP2040) vs Pico 2 (RP2350) and set SRAM constants accordingly.

We reserve a 2 KB shadow RAM window at the very end of on-chip SRAM:
  RP2040 total SRAM = 264 KB  -> end = 0x20000000 + 0x00042000 -> base = end - 0x800 = 0x20041800
  RP2350 total SRAM = 520 KB  -> end = 0x20000000 + 0x00082000 -> base = end - 0x800 = 0x20081800
"""
import os
import uctypes

def _is_rp2350():
    try:
        m = os.uname().machine
        # Typical strings include "Raspberry Pi Pico 2 with RP2350"
        return ("RP2350" in m) or ("Pico 2" in m)
    except Exception:
        return False

IS_RP2350 = _is_rp2350()

if IS_RP2350 == True:
  # only need 2k block
  SRAM_DATA_BASE = 0x20081800                 #PICO2W  original 8k block
  SRAM_DATA_BASE_21 = SRAM_DATA_BASE >> 11    #MSBits to be preloaded in pio for address generation
  SRAM_DATA_LENGTH = 0x00000800               #2k byte total

  shadowRam = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
  print("RP2350 SRam->", len(shadowRam), hex(SRAM_DATA_BASE), hex(SRAM_DATA_LENGTH))


else:
  # PICO1 - RP2040
  # system 9 and 11 need 2k array for the 'shadow' ram
  # SRAM_DATA_BASE = 0x20040000  # 0x20040000-0x20040800 (2k)
  SRAM_DATA_BASE = 0x20041800  # very end of ram - 2k

  SRAM_DATA_BASE_21 = SRAM_DATA_BASE >> 11  # 21 MSBits to be preloaded in pio for address generation
  SRAM_DATA_LENGTH = 0x00000800  # 2k byte total

  shadowRam = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
  print("RP2040 SRam->", len(shadowRam), hex(SRAM_DATA_BASE), hex(SRAM_DATA_LENGTH))

