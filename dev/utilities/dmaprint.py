import uctypes

DMA_BASE = 0x50000000
DMA_LENGTH = 256  # 0x0AC8
DmaRam = uctypes.bytearray_at(DMA_BASE, DMA_LENGTH + 32)


def printdma():
    for line in range(0, DMA_LENGTH - 16, 16):
        for i in range(line, line + 16, 1):
            print(" ", hex(DmaRam[i]), end="")
        print(" ")
    print(" ")

    # hex_dump_memory(DMA_BASE, DMA_LENGTH)


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
