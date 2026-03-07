import uctypes

DMA_BASE = 0x50000000
DMA_LENGTH = 256  # 0x0AC8
DmaRam = uctypes.bytearray_at(DMA_BASE, DMA_LENGTH + 32)


def printdma():
    print("Address       |  00  01  02  03  04  05  06  07  08  09  0A  0B  0C  0D  0E  0F")
    print("--------------+------------------------------------------------")
    for line in range(0, DMA_LENGTH - 16, 16):
        # Print the starting address of the row
        print(f"0x{DMA_BASE + line:08X} | ", end="")

        # Print the 16 bytes in the row
        for i in range(line, line + 16):
            print(f"{DmaRam[i]:02X} ", end="")

        print("")  # Newline after each row
    print("")






import uctypes

DMA_BASE = 0x50000000
DMA_CHANNEL_OFFSET = 0x40  # Offset between DMA channels
DMA6_BASE = DMA_BASE + (6 * DMA_CHANNEL_OFFSET)  # Base address for DMA6

# Define the bitfields for CTRL_REG as a separate structure
CTRL_REG_FIELDS = {
    "CHAIN_TO": uctypes.BFUINT32 | 0x0C | 0 << uctypes.BF_POS | 4 << uctypes.BF_LEN,
    "INCR_WRITE": uctypes.BFUINT32 | 0x0C | 4 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "INCR_READ": uctypes.BFUINT32 | 0x0C | 5 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "IRQ_QUIET": uctypes.BFUINT32 | 0x0C | 21 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "TREQ_SEL": uctypes.BFUINT32 | 0x0C | 15 << uctypes.BF_POS | 6 << uctypes.BF_LEN,
    "DATA_SIZE": uctypes.BFUINT32 | 0x0C | 2 << uctypes.BF_POS | 2 << uctypes.BF_LEN,
    "EN": uctypes.BFUINT32 | 0x0C | 31 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "HIGH_PRIORITY": uctypes.BFUINT32 | 0x0C | 30 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
}

# Define the main DMA register structure
DMA_REGISTERS = {
    "READ_ADDR_REG": uctypes.UINT32 | 0x00,
    "WRITE_ADDR_REG": uctypes.UINT32 | 0x04,
    "TRANS_COUNT_REG": uctypes.UINT32 | 0x08,
    "CTRL_REG": uctypes.UINT32 | 0x0C,  # Define CTRL_REG as a single 32-bit register
    "CTRL_REG_FIELDS": (0x00, CTRL_REG_FIELDS),  # Reference the bitfields structure
    "TRANS_COUNT_REG_TRIG": uctypes.UINT32 | 0x0C,
}

# Map the DMA6 registers
dma6 = uctypes.struct(DMA6_BASE, DMA_REGISTERS)

def print_dma6_registers():
    """Print human-readable DMA6 register data."""
    print("DMA6 Register Data:")
    print(f"  READ_ADDR_REG:  0x{dma6.READ_ADDR_REG:08X}")
    print(f"  WRITE_ADDR_REG: 0x{dma6.WRITE_ADDR_REG:08X}")
    print(f"  TRANS_COUNT_REG: {dma6.TRANS_COUNT_REG}")
    print(f"  CTRL_REG: 0x{dma6.CTRL_REG:08X}")
    print(f"    CHAIN_TO:      {dma6.CTRL_REG_FIELDS.CHAIN_TO}")
    print(f"    INCR_WRITE:    {dma6.CTRL_REG_FIELDS.INCR_WRITE}")
    print(f"    INCR_READ:     {dma6.CTRL_REG_FIELDS.INCR_READ}")
    print(f"    IRQ_QUIET:     {dma6.CTRL_REG_FIELDS.IRQ_QUIET}")
    print(f"    TREQ_SEL:      {dma6.CTRL_REG_FIELDS.TREQ_SEL}")
    print(f"    DATA_SIZE:     {dma6.CTRL_REG_FIELDS.DATA_SIZE}")
    print(f"    EN:            {dma6.CTRL_REG_FIELDS.EN}")
    print(f"    HIGH_PRIORITY: {dma6.CTRL_REG_FIELDS.HIGH_PRIORITY}")
    print(f"  TRANS_COUNT_REG_TRIG: {dma6.TRANS_COUNT_REG_TRIG}")

# Call this function after the memory dump
#print_dma6_registers()




def hex_dump_memory(ptr, num):
    n = 0
    lines = []
    data = list((num * uctypes.c_byte).from_address(ptr))

    if len(data) == 0:
        return "<empty>"

    for i in range(0, num, 16):
        line = ""
        line += "%04x | " % (i)
        n += 16

        for j in range(n - 16, n):
            if j >= len(data):
                break
            line += "%02x " % abs(data[j])

        line += " " * (3 * 16 + 7 - len(line)) + " | "

        for j in range(n - 16, n):
            if j >= len(data):
                break
            c = data[j] if not (data[j] < 0x20 or data[j] > 0x7E) else "."
            line += "%c" % c

        lines.append(line)
    return "\n".join(lines)
