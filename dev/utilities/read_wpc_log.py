# Standalone WPC FRAM log reader.
#
# No project imports (not even SPI_Store/FramMap/logger) - copy this single
# file to the Pico and run it directly, e.g.:

# run like this from command line:::
#   mpremote connect <PORT> run dev/utilities/read_wpc_log.py


# or copy it onto the board and `import read_wpc_log` / run it from the REPL.
#
# Reads the FRAM log region the same way logger.py's get_logs_stream() does:
# starts at the next-write pointer (oldest byte) and reads forward, wrapping
# around the circular buffer, so output comes out in chronological order.

import machine
from machine import SPI

# --- FRAM SPI wiring (fixed hardware, same pins SPI_Store.py uses) ---
cs = machine.Pin(5, machine.Pin.OUT)
cs.value(1)

spi = SPI(
    0,
    baudrate=1000000,
    polarity=1,
    phase=1,
    bits=8,
    firstbit=SPI.MSB,
    sck=machine.Pin(2),
    mosi=machine.Pin(3),
    miso=machine.Pin(4),
)

OPCODE_READ = 0x03


def fram_read(address, nbytes):
    data = bytearray()
    chunk_size = 16
    offset = 0
    while offset < nbytes:
        remaining = nbytes - offset
        read_size = min(chunk_size, remaining)
        msg = bytearray([OPCODE_READ, (address & 0xFF00) >> 8, address & 0x00FF])
        cs.value(0)
        spi.write(msg)
        data.extend(spi.read(read_size))
        cs.value(1)
        address += chunk_size
        offset += chunk_size
    return data


# --- WPC logger region (values from src/wpc/FramMap.py: LOGGER_CONFIG) ---
AddressStart = 0x2600
LoggerLength = 0x1FFF
AddressEnd = AddressStart + LoggerLength - 16
AddressPointer = AddressStart + LoggerLength - 6

pointer_bytes = fram_read(AddressPointer, 4)
next_write_address = int.from_bytes(pointer_bytes, "big")
if next_write_address < AddressStart or next_write_address >= AddressEnd:
    next_write_address = AddressStart

current_address = next_write_address
remaining_bytes = AddressEnd - AddressStart
read_size = 16
chars = []

while remaining_bytes > 0:
    bytes_to_read = min(read_size, remaining_bytes)
    data = fram_read(current_address, bytes_to_read)
    for byte in data:
        chars.append(chr(byte))
        current_address += 1
        remaining_bytes -= 1
        if current_address >= AddressEnd:
            current_address = AddressStart
            break

print("".join(chars))
