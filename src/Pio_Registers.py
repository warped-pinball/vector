from uctypes import UINT32, struct

PIO0_BASE = 0x50200000
PIO1_BASE = 0x50300000

# fmt: off
PIO_0_R = {
        "TXF":			0x10 | UINT32,
        "RXF":			0x20 | UINT32,
        "CLKDIV":		0xC8 | UINT32,
        "EXECCTRL":		0xCC | UINT32,
        "SHIFTCTRL":	0xD0 | UINT32,
        "ADDR":			0xD4 | UINT32,
        "INSTR":		0xD8 | UINT32,
        "PINCTRL":		0xDC | UINT32
        }

PIO_1_R = {
        "TXF":			0x14 | UINT32,
        "RXF":			0x24 | UINT32,
        "CLKDIV":		0xE0 | UINT32,
        "EXECCTRL":		0xE4 | UINT32,
        "SHIFTCTRL":	0xE8 | UINT32,
        "ADDR":			0xEC | UINT32,
        "INSTR":		0xF0 | UINT32,
        "PINCTRL":		0xF4 | UINT32
        }

PIO_2_R = {
        "TXF":			0x18 | UINT32,
        "RXF":			0x28 | UINT32,
        "CLKDIV":		0xF8 | UINT32,
        "EXECCTRL":		0xFC | UINT32,
        "SHIFTCTRL":	0x100 | UINT32,
        "ADDR":			0x104 | UINT32,
        "INSTR":		0x108 | UINT32,
        "PINCTRL":		0x10C | UINT32,
          }

PIO_3_R = {
        "TXF":			0x1C | UINT32,
        "RXF":			0x2C | UINT32,
        "CLKDIV":		0x110 | UINT32,
        "EXECCTRL":		0x114 | UINT32,
        "SHIFTCTRL":	0x118 | UINT32,
        "ADDR":			0x11C | UINT32,
        "INSTR":		0x120 | UINT32,
        "PINCTRL":		0x124 | UINT32,
          }

PIO_REGS = {
        "CTRL":		 0x00 | UINT32,
        "FSTAT":	 0x04 | UINT32,
        "FDEBUG":	 0x08 | UINT32,
        "FLEVEL":	 0x0C | UINT32,
        "TXF0":		 0x10 | UINT32,
        "TXF1":		 0x14 | UINT32,
        "TXF2":		 0x18 | UINT32,
        "TXF3":		 0x1C | UINT32,
        "RXF0":		 0x20 | UINT32,
        "RXF1":		 0x24 | UINT32,
        "RXF2":		 0x28 | UINT32,
        "RXF3":		 0x2C | UINT32,
        "IRQ":		 0x30 | UINT32,
        "IRQ_FORCE": 0x34 | UINT32,
        "INPUT_SYNC_BYPASS": 0x38 | UINT32,
        "DBG_PADOUT":		 0x3C | UINT32,
        "DBG_PADOE":		 0x40 | UINT32,
        "DBG_CFGINFO":		 0x44 | UINT32,
        "INSTR_MEM0":	0x48 | UINT32,
        "INSTR_MEM1":	0x4C | UINT32,
        "INSTR_MEM2":	0x50 | UINT32,
        "INSTR_MEM3":	0x54 | UINT32,
        "INSTR_MEM4":	0x58 | UINT32,
        "INSTR_MEM5":	0x5C | UINT32,
        "INSTR_MEM6":	0x60 | UINT32,
        "INSTR_MEM7":	0x64 | UINT32,
        "INSTR_MEM8":	0x68 | UINT32,
        "INSTR_MEM9":	0x6C | UINT32,
        "INSTR_MEM10":	0x70 | UINT32,
        "INSTR_MEM11":	0x74 | UINT32,
        "INSTR_MEM12":	0x78 | UINT32,
        "INSTR_MEM13":	0x7C | UINT32,
        "INSTR_MEM14":	0x80 | UINT32,
        "INSTR_MEM15":	0x84 | UINT32,
        "INSTR_MEM16":	0x88 | UINT32,
        "INSTR_MEM17":	0x8C | UINT32,
        "INSTR_MEM18":	0x90 | UINT32,
        "INSTR_MEM19":	0x94 | UINT32,
        "INSTR_MEM20":	0x98 | UINT32,
        "INSTR_MEM21":	0x9C | UINT32,
        "INSTR_MEM22":	0xA0 | UINT32,
        "INSTR_MEM23":	0xA4 | UINT32,
        "INSTR_MEM24":	0xA8 | UINT32,
        "INSTR_MEM25":	0xAC | UINT32,
        "INSTR_MEM26":	0xB0 | UINT32,
        "INSTR_MEM27":	0xB4 | UINT32,
        "INSTR_MEM28":	0xB8 | UINT32,
        "INSTR_MEM29":	0xBC | UINT32,
        "INSTR_MEM30":	0xC0 | UINT32,
        "INSTR_MEM31":	0xC4 | UINT32,

        "SM0_CLKDIV":	0xC8 | UINT32,
        "SM0_EXECCTRL":	0xCC | UINT32,
        "SM0_SHIFTCTRL":0xD0 | UINT32,
        "SM0_ADDR":		0xD4 | UINT32,
        "SM0_INSTR":	0xD8 | UINT32,
        "SM0_PINCTRL":	0xDC | UINT32,

        "SM1_CLKDIV":	0xE0 | UINT32,
        "SM1_EXECCTRL":	0xE4 | UINT32,
        "SM1_SHIFTCTRL":0xE8 | UINT32,
        "SM1_ADDR":		0xEC | UINT32,
        "SM1_INSTR":	0xF0 | UINT32,
        "SM1_PINCTRL":	0xF4 | UINT32,

        "SM2_CLKDIV":	0xF8 | UINT32,
        "SM2_EXECCTRL":	0xFC | UINT32,
        "SM2_SHIFTCTRL":0x100 | UINT32,
        "SM2_ADDR":		0x104 | UINT32,
        "SM2_INSTR":	0x108 | UINT32,
        "SM2_PINCTRL":	0x10C | UINT32,

        "SM3_CLKDIV":	0x110 | UINT32,
        "SM3_EXECCTRL":	0x114 | UINT32,
        "SM3_SHIFTCTRL":0x118 | UINT32,
        "SM3_ADDR":		0x11C | UINT32,
        "SM3_INSTR":	0x120 | UINT32,
        "SM3_PINCTRL":	0x124 | UINT32,

        "INTR": 		0x128 | UINT32,
        "IRQ0_INTE":	0x12C | UINT32,
        "IRQ0_INTF":	0x130 | UINT32,
        "IRQ0_INTS":	0x134 | UINT32,
        "IRQ1_INTE":	0x138 | UINT32,
        "IRQ1_INTF":	0x13C | UINT32,
        "IRQ1_INTS":	0x140 | UINT32
        }
# fmt: on

# access to entire PIO data structure
PIO0_DEVICE = struct(PIO0_BASE, PIO_REGS)
PIO1_DEVICE = struct(PIO1_BASE, PIO_REGS)

# access to PIO0 state machine specific registers SM0-3
PIO0_SM0 = struct(PIO0_BASE, PIO_0_R)
PIO0_SM1 = struct(PIO0_BASE, PIO_1_R)
PIO0_SM2 = struct(PIO0_BASE, PIO_2_R)
PIO0_SM3 = struct(PIO0_BASE, PIO_3_R)

# access to PIO1 state machine specific registers SM0-3
PIO1_SM0 = struct(PIO1_BASE, PIO_0_R)
PIO1_SM1 = struct(PIO1_BASE, PIO_1_R)
PIO1_SM2 = struct(PIO1_BASE, PIO_2_R)
PIO1_SM3 = struct(PIO1_BASE, PIO_3_R)
