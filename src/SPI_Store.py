# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    SPI module - to non-volatile serial RAM (FRAM)
    -now added serial flash part

    SYS11Wifi Project
    Dec 2024
"""
import time

import machine
import uctypes
from machine import SPI

from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH

# from logger import logger_instance  <<the logger uses this driver, cant really be imported here
# Log = logger_instance

SPI_store_version = 2

# FRAM  Register and command defs for FM25L16B
OPCODE_WREN = 0x06  # set write enable latch
OPCODE_WRDI = 0x04  # write disable              <<clears WEL
OPCODE_RDSR = 0x05  # read status register
OPCODE_WRSR = 0x01  # write status register      <<clears WEL
OPCODE_READ = 0x03  # read memory
OPCODE_WRITE = 0x02  # write memory               <<clears WEL
STATUS_REG_VAL = 0x82  # wrill write this val i

# Assign chip select (CS) pin (and start it high)
cs = machine.Pin(5, machine.Pin.OUT)
cs.value(1)

# Initialize SPI Port
spi = machine.SPI(
    0,
    baudrate=60000,  # 20000,
    polarity=1,
    phase=1,
    bits=8,
    firstbit=SPI.MSB,  # machine.SPI.LSB,
    sck=machine.Pin(2),
    mosi=machine.Pin(3),
    miso=machine.Pin(4),
)


# FRAM write just one byte cmd
def reg_cmd(spi, cs, reg):
    msg = bytearray()
    msg.append(0x00 | reg)
    cs.value(0)
    spi.write(msg)
    cs.value(1)


# FRAM write one byte to one register location
def reg_write(spi, cs, reg, data):
    msg = bytearray()
    msg.append(0x00 | reg)
    msg.append(data)
    cs.value(0)
    spi.write(msg)  # blocking
    cs.value(1)


# FRAM
def mem_write(spi, cs, address, data):
    # Enable write operations
    reg_cmd(spi, cs, OPCODE_WREN)

    # Split data into chunks of 16 bytes
    chunk_size = 16
    for i in range(0, len(data), chunk_size):
        # print("x",i)
        chunk = data[i : i + chunk_size]
        # print(chunk)
        reg_cmd(spi, cs, OPCODE_WREN)

        msg = bytearray()
        msg.append(0x00 | OPCODE_WRITE)
        msg.append((address & 0xFF00) >> 8)
        msg.append(address & 0x00FF)
        msg.extend(chunk)
        # print(msg)

        cs.value(0)
        spi.write(msg)
        cs.value(1)
        address += chunk_size


# FRAM
def write(address, data):
    mem_write(spi, cs, address, data)


# FRAM
def mem_read(spi, cs, address, nbytes):
    data = bytearray()
    chunk_size = 16
    offset = 0

    while offset < nbytes:
        remaining = nbytes - offset
        read_size = min(chunk_size, remaining)

        # Prepare the message
        msg = bytearray()
        msg.append(OPCODE_READ)
        msg.append((address & 0xFF00) >> 8)
        msg.append(address & 0x00FF)

        # Send the message and read the data
        cs.value(0)
        spi.write(msg)
        data.extend(spi.read(read_size))
        cs.value(1)

        # Update the address and offset for the next chunk
        address += chunk_size
        offset += chunk_size
    return data


# FRAM
def read(address, nbytes):
    return mem_read(spi, cs, address, nbytes)


# FRAM read a register
def reg_read(spi, cs, reg, nbytes=1):
    msg = bytearray()
    msg.append(0x00 | reg)
    # Send
    cs.value(0)
    spi.write(msg)
    data = spi.read(nbytes)
    cs.value(1)
    return data


# reverse bits(order) in a byte
def rbit8(v):
    v = (v & 0x0F) << 4 | (v & 0xF0) >> 4
    v = (v & 0x33) << 2 | (v & 0xCC) >> 2
    return (v & 0x55) << 1 | (v & 0xAA) >> 1


# FRAM restore ram from fram (called generally at power up)
def Restore_Mem(ram_address, byte_length):
    for st in range(0, byte_length, 16):
        dat = mem_read(spi, cs, st, 16)
        # print("restore rd ",st," ",ram_address[st])
        for index in range(0, 16, 1):
            ram_address[index + st] = dat[index]


# FRAM write 16 bytes ram to fram - NO DMA Usage
def write_16_fram(ram_address, fram_address):
    RamData = uctypes.bytearray_at(ram_address, 16)
    fram_add = fram_address
    # print(" store fram=",fram_add," ram=",RamData)
    mem_write(spi, cs, fram_add, RamData)


# FRAM
def write_all_fram_now():
    MemIndex = 0
    while True:
        write_16_fram(SRAM_DATA_BASE + MemIndex, MemIndex)
        MemIndex = MemIndex + 16
        # print(".",end="")
        if MemIndex >= SRAM_DATA_LENGTH:
            print("FRAM: complete store done")
            return


"""
Serial Flash
    256M-Bit
    32M-Byte
    Byte addresses 0x0000-0x2 00 00 00
    Requires 4 byte address mode (or only use 1/2)

    Give each software version 4M-bytes section

"""
sflash_is_on_board = False

# serial flash command opcodes
SFLASH_EN4B = 0xB7  # enable 4 byte addresses
SFLASH_RDCR = 0x15  # read config register
SFLASH_RDSR = 0x05  # read status register
SFLASH_RDID = 0x9F  # read chip ID
SFLASH_CHIP_ID = [0xC2, 0x20, 0x19]
# SFLASH_CHIP_ID = [0xC2, 0x20, 0x17]  prototyre pcb chip

SFLASH_READ = 0x13  # regular 4adr byte read
SFLASH_PP = 0x02  # page program (inside 256 byte page)
# erases set all bits to '1'
SFLASH_WREN = 0x06  # write enable command
SFLASH_WRDI = 0x04  # write disable
SFLASH_SE = 0x20  # sector erase  (4k-byte sector)
SFLASH_BE4B = 0xDC  # block erase   (64k-byte block) 4byte adr
SFLASH_CE = 0x60  # Chip erase    (whole chip)
# sector protection - using WPSEL=1 mode
SFLASH_WPSEL = 0x68
SFLASH_GBLK = 0x7E  # lock all
SFLASH_GBULK = 0x98  # unlock all
SFLASH_WRDPB = 0xE1
SFLASH_RDDPB = 0xE0
# WIP write in progress bit for erases also
# serial l=flash CS active when HIGH


# send command with optional following data bytes
def _sflash_cmd_dat(spi, cs, reg, data=bytearray()):
    msg = bytearray([reg]) + data
    cs.value(0)
    time.sleep_us(20)
    cs.value(1)
    time.sleep_us(20)
    spi.write(msg)
    cs.value(0)
    time.sleep_us(20)
    cs.value(1)


# read a register (can be multiple read bytes, deafault 1)
def _sflash_reg_read(spi, cs, reg, nbytes=1):
    msg = bytearray([reg])
    cs.value(0)
    time.sleep_us(20)
    cs.value(1)
    time.sleep_us(20)
    spi.write(msg)
    data = spi.read(nbytes)
    cs.value(0)
    time.sleep_us(20)
    cs.value(1)
    return data


def _sflash_write_enable():
    _sflash_cmd_dat(spi, cs, SFLASH_WREN)


def _sflash_get_chip_id():
    sig = _sflash_reg_read(spi, cs, SFLASH_RDID, 3)
    print(f"SFLASH: Signature: {sig[0]:02X},{sig[1]:02X},{sig[2]:02X}")
    return sig


# erase a single 64k block
def _sflash_block_erase(block_address, wait=False):
    if sflash_is_ready() is False:
        return "ready fault"
    _sflash_write_enable()
    address_bytes = bytearray([(block_address >> 24) & 0xFF, (block_address >> 16) & 0xFF, 0x00, 0x00])  # MSByte

    _sflash_cmd_dat(spi, cs, SFLASH_BE4B, address_bytes)
    print(f"erase {address_bytes.hex()}")

    if wait:
        loop = 0
        while not sflash_is_ready():
            if loop >= 60:
                print("timeout")
                return "timeout"
            time.sleep_ms(50)
            loop += 1


# read any number of bytes (no page boundary problems with read)
def _sflash_mem_read(spi, cs, address, nbytes=16):
    rd_data = bytearray(nbytes)
    size = 16
    rd_offset = 0
    num_bytes = nbytes

    cs.value(0)
    while rd_offset < num_bytes:
        remaining = num_bytes - rd_offset
        read_size = min(size, remaining)

        rd_msg = bytearray(
            [
                SFLASH_READ,
                (address >> 24) & 0x0FF,
                (address >> 16) & 0x0FF,
                (address >> 8) & 0x0FF,
                address & 0x0FF,
            ]
        )

        # Send the message and read the data
        cs.value(1)
        time.sleep_us(20)
        spi.write(rd_msg)
        rd_data[rd_offset : rd_offset + read_size] = spi.read(read_size)
        cs.value(0)
        # Update the address and offset for the next chunk
        address += read_size
        rd_offset += read_size

    time.sleep_us(20)
    cs.value(1)
    return rd_data


#
# write any number of bytes  - - must wait for finish
# single write cannot cross 256 byte boundary!
def _sflash_mem_write(spi, cs, address, data):
    i = 0
    w_chunk_size = 16
    w_data_length = len(data)

    while i < w_data_length:
        distance_to_boundary = 0x100 - (address & 0x0FF)
        write_size = min(w_chunk_size, distance_to_boundary)
        w_chunk_data = data[i : i + write_size]

        w_msg = bytearray(
            [
                SFLASH_PP,
                (address >> 24) & 0x0FF,  # MSByte
                (address >> 16) & 0x0FF,
                (address >> 8) & 0x0FF,
                (address & 0x0FF),
            ]
            + list(w_chunk_data)
        )
        # print(f" write adr= {address:#x}   msg={w_msg.hex()}")

        _sflash_write_enable()
        cs.value(0)
        time.sleep_us(20)
        cs.value(1)
        time.sleep_us(20)
        spi.write(w_msg)
        cs.value(0)
        time.sleep_us(20)
        cs.value(1)

        sflash_wait_for_ready()
        address += write_size
        i += write_size


def sflash_read(address, nbytes=16):
    global sflash_is_on_board
    if not sflash_is_on_board:
        return bytearray(0)
    return _sflash_mem_read(spi, cs, address, nbytes)


def sflash_write(address, data, wait=False):
    global sflash_is_on_board
    if not sflash_is_on_board:
        return
    return _sflash_mem_write(spi, cs, address, data)


def sflash_sector_erase(sector_address):
    global sflash_is_on_board
    if not sflash_is_on_board:
        return
    if sflash_is_ready() is False:
        return "ready fault"
    _sflash_write_enable()
    address_bytes = bytearray(
        [
            (sector_address >> 24) & 0xFF,  # MSByte
            (sector_address >> 16) & 0xFF,
            (sector_address >> 8) & 0xFF,
            sector_address & 0xFF,
        ]
    )

    _sflash_cmd_dat(spi, cs, SFLASH_SE, address_bytes)
    print(f"erase {address_bytes.hex()}")

    loop = 0
    while not sflash_is_ready():
        if loop >= 100:
            print("timeout")
            return "timeout"
        time.sleep_ms(10)
        loop += 1


# erase multiple blocks, wait required
# one block can slecet no wait
def sflash_erase(start_block_address, end_block_address=0, wait=False):
    global sflash_is_on_board
    if not sflash_is_on_board:
        return

    start_block_address &= 0xFFFF0000
    end_block_address &= 0xFFFF0000
    if start_block_address > end_block_address:
        return

    if start_block_address == end_block_address or end_block_address == 0:
        _sflash_block_erase(start_block_address, wait)
    else:
        block_address = start_block_address
        while block_address < end_block_address:
            print(f"e-{block_address:#x}")
            _sflash_block_erase(block_address, True)
            block_address += 0x010000


# check for ready status
def sflash_is_ready():
    global sflash_is_on_board
    if not sflash_is_on_board:
        return True

    sr = _sflash_reg_read(spi, cs, SFLASH_RDSR)
    return (sr[0] & 0x01) == 0x00


# Wait until ready with timeout
def sflash_wait_for_ready(timeout=120):
    while not sflash_is_ready() and timeout > 0:
        time.sleep_ms(10)
        # print("w",end="")
        timeout -= 1
    if timeout == 0:
        return "fault"
    # print("D")
    return "ok"


# default on - send "off" to unprotect
def sflash_protect_sectors(start_address, end_address, protect="on"):
    block_size = 0x10000  # 64K blocks
    sector_size = 0x1000  # 4K sectors

    # these were unused so I commented them out
    # first_block_address = 0x0000000
    # last_block_address = 0x1FF0000

    if protect == "on":
        data_byte = 0xFF
    else:
        data_byte = 0
        # print("all protection off  ")
        # _sflash_write_enable()
        # _sflash_cmd_dat(spi, cs, SFLASH_GBULK)
        # return

    # 64K blocks from 1 to 510
    for block_num in range(1, 511):
        block_address = block_num * block_size
        # print(f"block # {block_num} st={start_address:#x} end={end_address:#x} prot= {protect}")
        if block_address < (start_address & 0xFFFF0000) or block_address >= (end_address & 0xFFFF0000):
            continue

        # print ("block # ",block_num," prot= ",protect)
        msg = bytearray(
            [
                (block_address >> 24) & 0x0FF,  # MSByte
                (block_address >> 16) & 0x0FF,
                (block_address >> 8) & 0x0FF,
                (block_address & 0x0FF),
                data_byte,
            ]
        )
        _sflash_write_enable()
        _sflash_cmd_dat(spi, cs, SFLASH_WRDPB, msg)

    # Protect 4K sectors within the first and last block (block 0 and 511)
    for block_num in [0, 511]:
        block_address = block_num * block_size
        for sector_offset in range(0, block_size, sector_size):
            sector_address = block_address + sector_offset
            if sector_address < (start_address & 0xFFFFF000) or sector_address >= (end_address & 0xFFFFF000):
                continue

            print("4k sector # ", sector_offset, " prot= ", protect)

            msg = bytearray(
                [
                    (sector_address >> 24) & 0xFF,  # MSByte
                    (sector_address >> 16) & 0xFF,
                    (sector_address >> 8) & 0xFF,
                    (sector_address & 0xFF),
                    data_byte,
                ]
            )
            _sflash_write_enable()
            _sflash_cmd_dat(spi, cs, SFLASH_WRDPB, msg)


# init flash chip
def sflash_driver_init():
    global sflash_is_on_board

    # Confirm chip id
    for attempt in range(2):
        chip_id = _sflash_get_chip_id()
        if list(chip_id) == SFLASH_CHIP_ID:
            sflash_is_on_board = True
            break
        print(f"SFLASH: Attempt {attempt + 1} ID mismatch")
        sflash_is_on_board = False

    # 4 byte address mode
    _sflash_write_enable()
    _sflash_cmd_dat(spi, cs, SFLASH_EN4B)
    # read config, check bit 5 for 4 byte mode
    config_reg = _sflash_reg_read(spi, cs, SFLASH_RDCR)
    if config_reg is None or len(config_reg) == 0 or (config_reg[0] & 0x20) == 0:
        print("SFLASH: Fault, cannot confirm config register")
        sflash_is_on_board = False
        return

    # set WPSEL
    _sflash_write_enable()
    _sflash_cmd_dat(spi, cs, SFLASH_WPSEL)
    _sflash_write_enable()
    _sflash_cmd_dat(spi, cs, SFLASH_GBLK)


#
# get system versions
#         (module version:fram type:serial flash type)
def version():
    global sflash_is_on_board
    sflash_ver = 0

    if sflash_is_on_board:
        sflash_ver = 1
    return SPI_store_version, 1, sflash_ver


def test():
    sflash_driver_init()
    print("ready?", sflash_is_ready())
    print("V", version())

    modder = 256
    for looper in range(2):
        print("loop ", looper)

        # Test: Write a known pattern and read it back
        test_address = 0x100AF
        test_length = 479
        test_data = bytearray([(i + 3) % modder for i in range(test_length)])

        sflash_protect_sectors(test_address, test_address + test_length, "off")
        sflash_erase(test_address, test_address + test_length, False)

        sflash_wait_for_ready()

        # Write the test data
        _sflash_mem_write(spi, cs, test_address, test_data)
        sflash_protect_sectors(test_address, test_address + test_length, "on")
        # Read back the data
        read_data = _sflash_mem_read(spi, cs, test_address, test_length)

        # Check for errors
        if test_data == read_data:
            print("Test passed: Data written and read back correctly.")
        else:
            print("Test failed: Data mismatch.")
            for i in range(len(test_data)):
                if test_data[i] != read_data[i]:
                    print(f"Mismatch at byte {i}: wrote {test_data[i]}, read {read_data[i]}")
                    pass


if __name__ == "__main__":
    test()
    print("done")
