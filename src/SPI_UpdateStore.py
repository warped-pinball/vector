"""
serial flash program update storage driver

Be sure to call initialize() at power  up !

calls lower level SPI_Store driver (shared with FRAM)

flash chip performance:
    block erase - max 2s
    byte program 30uS

Usage:
    initialize() - call at power up
    tick() - call periodically always! to manage ongoing erase operations
    is_busy_erasing() - returns True if there is an ongoing erase operation
    read_generator(chunk_size_bytes=1000,readNewest=True) - read out code block newest or oldest
    write_consumer(version)  - write into blank block


    blank_all() - Factory use only, blocking. deletes all
    erase_oldest_version_program_space() - launched automatically by tick()
"""
import uctypes

import SPI_Store
from logger import logger_instance

Log = logger_instance

# the first 64k and the last 64k blocks can be protected in 4k sectors
# so we will not use those here.  we need only 3 aresa of 6Mbyte each

# Serial Flash usage
SFLASH_PRG_START = 0x0010000
SFLASH_PRG_SIZE = 0x0200000  # 2Mbyte
SFLASH_ERASE_SECTOR_SIZE = 0x010000  # 64k
SFLASH_NUM_PGMS = 5
"""
total SFLASH part is 32M byte:
Five Blocks of Mbyte each used in this module (could be expanded to more)
    0x0010000-0x0210000  sflash protect= 1-32
    0x0210000-0x0410000  sflash protect= 33-64
    0x0410000-0x0610000  sflash protect= 65-96
    0x0610000-0x0810000  sflash protect= 97-128
    0x0810000-0x0A10000  sflash protect= 129-160
"""

# status of state machines stuff in FRAM
FRAM_ADDRESS = 0x2000
FRAM_LENGTH = 0x0FF  # reserved (256 bytes)
FRAM_BYTES_USED = 250

# each section has a status descriptor in FRAM:
SECTION_STATUS_DESC = {
    "state": (uctypes.UINT32 | 0),  # 4 bytes (section status types below)
    "version_major": (uctypes.UINT8 | 4),  # 0-99, byte
    "version_middle": (uctypes.UINT8 | 5),  # 0-99, byte
    "version_minor": (uctypes.UINT8 | 6),  # 0-99, byte
    "erase_pointer": (uctypes.UINT8 | 7),  # 1 byte (block number)
    "read_pointer": (uctypes.UINT32 | 8),  # 32 bit address
    "write_pointer": (uctypes.UINT32 | 12),  # 32 bit address   (offset 12,13,14,15)
    "description": (
        uctypes.ARRAY | 16,
        uctypes.UINT8 | 20,
    ),  # string of length 20  (16-35)
    "dev_version_flag": (uctypes.UINT8 | 36),  # 1 byte (0=dev version, 1=production version)
    "reserved": (uctypes.ARRAY | 37, uctypes.UINT8 | 2),  # reserved for future use
}

# section state types
BLOCK_STATUS_FULL = 1
BLOCK_STATUS_EMPTY = 2
BLOCK_STATUS_ERASING = 3
BLOCK_STATUS_FILLING = 4
BLOCK_STATUS_READING = 5
BLOCK_STATUS_VALID = {
    BLOCK_STATUS_FULL,
    BLOCK_STATUS_EMPTY,
    BLOCK_STATUS_ERASING,
    BLOCK_STATUS_FILLING,
    BLOCK_STATUS_READING,
}

# overall data structure in FRAM
BLOCK_STATUS_OFFSETS = [0, 40, 80, 120, 160]
DATA_STRUCTURE_DESC = {
    "block_status_0": (BLOCK_STATUS_OFFSETS[0], SECTION_STATUS_DESC),
    "block_status_1": (BLOCK_STATUS_OFFSETS[1], SECTION_STATUS_DESC),
    "block_status_2": (BLOCK_STATUS_OFFSETS[2], SECTION_STATUS_DESC),
    "block_status_3": (BLOCK_STATUS_OFFSETS[3], SECTION_STATUS_DESC),
    "block_status_4": (BLOCK_STATUS_OFFSETS[4], SECTION_STATUS_DESC),
}

data_buffer = bytearray(FRAM_BYTES_USED)
data = uctypes.struct(uctypes.addressof(data_buffer), DATA_STRUCTURE_DESC, uctypes.LITTLE_ENDIAN)


# write structure to fram
def _write_status_to_fram():
    SPI_Store.write(FRAM_ADDRESS, data_buffer)


# read struct from fram to local ram
def _read_status_from_fram():
    data_buffer[:] = SPI_Store.read(FRAM_ADDRESS, FRAM_BYTES_USED)


# Get the block status struct by index from the data structure.
def _get_block_status(data, index):
    if 0 <= index < len(BLOCK_STATUS_OFFSETS):
        # Calculate the actual memory address of the block status
        address = uctypes.addressof(data) + BLOCK_STATUS_OFFSETS[index]
        return uctypes.struct(address, SECTION_STATUS_DESC, uctypes.LITTLE_ENDIAN)
    else:
        return None


# helper function to set block status
def _set_block_status(
    block,
    state,
    version_major,
    version_middle,
    version_minor,
    erase_pointer=0,
    read_pointer=0,
    write_pointer=0,
    description=" \n",
    devflag=0,
):
    block.state = state
    block.version_major = version_major
    block.version_middle = version_middle
    block.version_minor = version_minor
    block.erase_pointer = erase_pointer
    block.read_pointer = read_pointer
    block.write_pointer = write_pointer

    if isinstance(description, str):
        description = description.encode("utf-8")
    max_len = len(data.block_status_0.description)
    write_len = min(len(description), max_len)
    block.description[: len(description)] = description[:write_len]
    block.dev_version_flag = devflag


def _print_block_status(block_status, name):
    print(f"  {name}:")
    state_text = {
        BLOCK_STATUS_FULL: "FULL",
        BLOCK_STATUS_EMPTY: "EMPTY",
        BLOCK_STATUS_ERASING: "ERASING",
        BLOCK_STATUS_FILLING: "FILLING",
        BLOCK_STATUS_READING: "READING",
    }.get(block_status.state, "UNKNOWN")
    print("    State:", state_text, "    ", end="")
    print(
        "    Version:",
        block_status.version_major,
        ":",
        block_status.version_middle,
        ":",
        block_status.version_minor,
        "   ",
        end="",
    )
    print("    Dev Version Flag:", block_status.dev_version_flag)
    print("    Erase Pointer:", block_status.erase_pointer, "   ", end="")
    print("    Read Pointer:", block_status.read_pointer, "   ", end="")
    print("    Write Pointer:", block_status.write_pointer)
    description = block_status.description.split(b"\0", 1)[0].split(b"\n", 1)[0].decode("utf-8")
    print("    Description:", description)


# return index for open block - return index
def _find_empty_block():
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        if dblk.state == BLOCK_STATUS_EMPTY:
            return i
    return None


# reports [index,string] of newest version
def _find_newest_version_program_block():
    newest = 0
    ans = None
    version_str = "none"
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        if dblk.state != BLOCK_STATUS_EMPTY:
            version = dblk.version_major * 10000 + dblk.version_middle * 100 + dblk.version_minor
            if version > newest:
                newest = version
                version_str = f"{dblk.version_major}.{dblk.version_middle}.{dblk.version_minor}"
                ans = i
    return ans, version_str


# find oldest version avilable - return [index,version]
def _find_oldest_version_program_block():
    oldest = 999999
    ans = None
    version_str = "none"
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        if dblk.state != BLOCK_STATUS_EMPTY:
            version = dblk.version_major * 10000 + dblk.version_middle * 100 + dblk.version_minor
            if version < oldest:
                oldest = version
                version_str = f"{dblk.version_major}.{dblk.version_middle}.{dblk.version_minor}"
                ans = i
    return ans, version_str


start_erase_count = 0


def tick():
    """
    system must call periodically - minimum period 100mS - recommend 1 second
    can be called continuous regardless of use.
    At 1 second call rate erase block will take 97 seconds
    set to automatically erase oldest block when all blocks are full
    """
    global start_erase_count
    # loop through blocks, find the first one in erase state
    for blk_num in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, blk_num)
        if dblk.state == BLOCK_STATUS_ERASING:
            if SPI_Store.sflash_is_ready():
                if dblk.erase_pointer == 0:  # unlock all sectors in this block
                    SPI_Store.sflash_protect_sectors(
                        SFLASH_PRG_START + (SFLASH_PRG_SIZE * blk_num),
                        SFLASH_PRG_START + SFLASH_PRG_SIZE * (blk_num + 1),
                        "off",
                    )
                    _set_block_status(dblk, BLOCK_STATUS_ERASING, 0, 0, 0, 0, 0, 0)
                    _write_status_to_fram()

                next_address = SFLASH_PRG_START + (SFLASH_PRG_SIZE * blk_num) + (SFLASH_ERASE_SECTOR_SIZE * dblk.erase_pointer)
                dblk.erase_pointer += 1

                if next_address >= SFLASH_PRG_START + SFLASH_PRG_SIZE * (blk_num + 1):
                    # done erasing with all sectors
                    SPI_Store.sflash_protect_sectors(
                        SFLASH_PRG_START + (SFLASH_PRG_SIZE * blk_num),
                        SFLASH_PRG_START + SFLASH_PRG_SIZE * (blk_num + 1),
                        "on",
                    )
                    _set_block_status(dblk, BLOCK_STATUS_EMPTY, 0, 0, 0, 0, 0, 0)
                    _write_status_to_fram()
                    print("erase done")
                    return

                print(f"erase {next_address:#x}")
                SPI_Store.sflash_erase(next_address, next_address, False)

    # this section in tick() starts an automatic erase if there is no open block.
    # erase startup is delayed in case there is a read for updgrade following
    # a write that filled the last open block.  This erase could be manual -
    # decided on this approach to keep blocks mostlyh hidden from the next level up
    for blk_num in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, blk_num)
        if dblk.state in {
            BLOCK_STATUS_EMPTY,
            BLOCK_STATUS_ERASING,
            BLOCK_STATUS_FILLING,
            BLOCK_STATUS_READING,
        }:
            start_erase_count = 0
            return

    # If no blocks are empty, erasing, or filling, start erasing the oldest block after 900 ticks (nominal 15minutes)
    start_erase_count += 1
    # print("ec ",start_erase_count)
    if start_erase_count >= 900:
        start_erase_count = 0
        erase_oldest_version_program_space()
        _write_status_to_fram()


def erase_oldest_version_program_space():
    """
    will only erase if all spaces are full
    no need to call this - tick will do it automatically if no other operations in progress
    """
    if _find_empty_block() is not None:  # there is already an open space
        return False
    oldest, _ = _find_oldest_version_program_block()
    if oldest is not None:
        dblk = _get_block_status(data, oldest)
        _set_block_status(dblk, BLOCK_STATUS_ERASING, 0, 0, 0, 0, 0, 0)
        _write_status_to_fram()
        return True


def report_all_version_numbers():
    """
    diagnostic / reporting function
    """
    versions = []
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        if dblk:
            # TODO use Version class to handle version numbers
            # description = bytes(filter(lambda x: 32 <= x <= 126, dblk.description)).decode('utf-8').split('\0', 1)[0].split('\n', 1)[0]

            description = dblk.description.split(b"\0", 1)[0].split(b"\n", 1)[0].decode("utf-8")

            version_str = f"{dblk.version_major}.{dblk.version_middle}.{dblk.version_minor} - {description}"
            versions.append(version_str)

    return versions


# Reccomended to check for busy before using read/write below -
# can check before read or write or erase operation is started
def is_busy_erasing():
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        if dblk.state == BLOCK_STATUS_ERASING:
            return True
    return False


def read_generator_by_description(description, chunk_size_bytes=1000):
    """
    read generator - pick program by description string
    """
    if isinstance(description, str):
        description = description.encode("utf-8")

    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)
        block_description = dblk.description.split(b"\0", 1)[0].split(b"\n", 1)[0]
        if block_description == description:
            yield from read_generator(chunk_size_bytes, i)
            return


def read_generator_oldest(chunk_size_bytes=1000):
    """
    read the oldest stored block
    """
    block_number, _ = _find_oldest_version_program_block()
    yield from read_generator(chunk_size_bytes, block_number)
    return


def read_generator(chunk_size_bytes=1000, block_number=-1):
    """
    read generator
        picks the newest block if no block number is given

        repeat calls until end,
    ]"""
    if is_busy_erasing():
        return None

    if block_number == -1:
        block_number, _ = _find_newest_version_program_block()

    if block_number is None or block_number >= SFLASH_NUM_PGMS or block_number < 0:
        return None

    dblk = _get_block_status(data, block_number)
    dblk.state = BLOCK_STATUS_READING
    dblk.read_pointer = 0
    print(f"Reading from block {block_number} ...")

    while dblk.read_pointer < dblk.write_pointer:
        read_size = min(chunk_size_bytes, dblk.write_pointer - dblk.read_pointer)
        yield SPI_Store.sflash_read(
            SFLASH_PRG_START + (SFLASH_PRG_SIZE * block_number) + dblk.read_pointer,
            read_size,
        )
        dblk.read_pointer += read_size

    dblk.state = BLOCK_STATUS_FULL


def write_consumer(version):
    """
    A generator *consumer* that waits for data chunks sent via `.send(chunk)`,
    writes them to the SPI flash, and stops when `None` is sent.

    send in version as a string "xx.yy.zz"

    you must close by sending 'None' after all data is sent to mark the end of the block
    """
    import time

    timeout = time.time() + 5
    while time.time() < timeout:
        if not is_busy_erasing():
            break
        time.sleep(0.1)
    else:
        print("Can't write: erasing in progress.")
        return "fault busy"

    blk_num = _find_empty_block()
    if blk_num is None:
        return "fault - no block"
    dblk = _get_block_status(data, blk_num)
    description = version + "\0"

    try:
        # Find the first non-numeric or non-decimal point character
        dev = 0
        non_numeric_count = 0
        for i, char in enumerate(version):
            if not (char.isdigit() or char == "."):
                non_numeric_count += 1
                version = version[:i]
                if non_numeric_count >= 3:
                    dev = 1

        version_numbers = version.split(".")[0:3]
        # Extract only the numeric part from each version component
        a, b, c = [int("".join(filter(str.isdigit, v))) for v in version_numbers]
        _set_block_status(dblk, BLOCK_STATUS_FILLING, a, b, c, 0, 0, 0, description, dev)

    except ValueError:
        print("Invalid version format. Expected 'xx.yy.zz'")
        return "fault invalid version"

    _write_status_to_fram()

    # open protection
    SPI_Store.sflash_protect_sectors(
        SFLASH_PRG_START + (SFLASH_PRG_SIZE * blk_num),
        SFLASH_PRG_START + SFLASH_PRG_SIZE * (blk_num + 1),
        "off",
    )
    print(f"Writing to block {blk_num} ...")

    # -- The "priming" yield --
    # The first time someone calls next(consumer) or consumer.send(None),
    # execution will pause right here and wait for `.send()`.
    chunk = yield

    while chunk is not None:
        SPI_Store.sflash_write(SFLASH_PRG_START + (SFLASH_PRG_SIZE * blk_num) + dblk.write_pointer, chunk)
        dblk.write_pointer += len(chunk)

        # Wait for the *next* chunk
        chunk = yield

    # If we receive None, we treat that as "done"
    print("Done writing.")
    dblk.state = BLOCK_STATUS_FULL
    # close protection
    SPI_Store.sflash_protect_sectors(
        SFLASH_PRG_START + (SFLASH_PRG_SIZE * blk_num),
        SFLASH_PRG_START + SFLASH_PRG_SIZE * (blk_num + 1),
        "on",
    )
    # leave write_pointer as end marker for future reads
    _write_status_to_fram()


def initialize():
    """
    call at power up
    re-launches erase processes that were stopped mid way
    """
    # TODO do we need to check the sflash exists? maybe by calling SPI_Store.sflash_init()?
    _read_status_from_fram()
    # look for any block in the middle of erase and restart it
    for i in range(SFLASH_NUM_PGMS):
        dblk = _get_block_status(data, i)

        # invalid state or power off during fill or erase?
        if (dblk.state not in BLOCK_STATUS_VALID) or (dblk.state in [BLOCK_STATUS_ERASING, BLOCK_STATUS_FILLING]):
            _set_block_status(dblk, BLOCK_STATUS_ERASING, 0, 0, 0, 0, 0, 0)
            _write_status_to_fram()

        # power off during read?
        if dblk.state == BLOCK_STATUS_READING:
            dblk.state == BLOCK_STATUS_FULL
            _write_status_to_fram()


# dump all sflash data for all programs, reset structures
# BLOCKING - intended for facotry reset only
def blank_all():
    block_status = _get_block_status(data, 0)
    _set_block_status(block_status, BLOCK_STATUS_EMPTY, 0, 0, 0, 0, 0, 0)

    # Erase each block with wait on
    for i in range(SFLASH_NUM_PGMS):
        SPI_Store.sflash_protect_sectors(
            SFLASH_PRG_START + SFLASH_PRG_SIZE * i,
            SFLASH_PRG_START + SFLASH_PRG_SIZE * (i + 1),
            "off",
        )
        print("UPDSTORE: erasing block", i)
        SPI_Store.sflash_erase(
            SFLASH_PRG_START + SFLASH_PRG_SIZE * i,
            SFLASH_PRG_START + SFLASH_PRG_SIZE * (i + 1),
            True,
        )

        block_status = _get_block_status(data, i)
        _set_block_status(block_status, BLOCK_STATUS_EMPTY, 0, 0, 0, 0, 0, 0)
        _write_status_to_fram()
        SPI_Store.sflash_protect_sectors(
            SFLASH_PRG_START + SFLASH_PRG_SIZE * i,
            SFLASH_PRG_START + SFLASH_PRG_SIZE * (i + 1),
            "on",
        )


def test():
    import time

    def print_data_structure(data):
        print(" Each Block:")
        _print_block_status(data.block_status_0, "Block Status 0")
        _print_block_status(data.block_status_1, "Block Status 1")
        _print_block_status(data.block_status_2, "Block Status 2")
        _print_block_status(data.block_status_3, "Block Status 3")
        _print_block_status(data.block_status_4, "Block Status 4")

    def print_all_status():
        print_data_structure(data)
        print("\nVersion numbers in storage now:")
        print(report_all_version_numbers())
        print("\nNewest Verrsion number in storage now (index,version):")
        print(_find_newest_version_program_block())
        print("\nOldest Verrsion number in storage now (index,version):")
        print(_find_oldest_version_program_block())

    SPI_Store.initialize()
    initialize()
    print_all_status()

    # blank_all()  #<<manufacturing reset all

    # basic read newest block out
    if False:
        r = read_generator(25, True)
        for d in r:
            print("data read: ", d)

    # read test looking at data pattern
    expected_value = 0
    num_of_bytes = 0
    if False:  # read test
        # rgen=read_generator(25,True)
        rgen = read_generator_by_description("1.3.5 dev-3", 25)
        for d in rgen:
            print("data read-: ", d)
            for byte in d:
                num_of_bytes += 1
                # print(" ",byte,end="")
                if byte != expected_value:
                    print("FAULT")
                expected_value = (expected_value + 1) % 15
        print("total bytes = ", num_of_bytes)

    if True:  # write progrm to block
        print("start test write - - - - - ")
        # test_data = bytearray([(i) for i in range(9)])
        test_data = bytearray([(i) for i in range(15)])  # b1
        # test_data = bytearray([(i) for i in range(11)])  #b0
        w = write_consumer("2.2.2\n")
        next(w)
        for i in range(1000):
            w.send(test_data)
        try:
            w.send(None)
        except StopIteration:
            pass

    # print_all_status()
    print_data_structure(data)

    # tick auto-erase test if all blocks are full
    if False:
        for x in range(890):
            tick()
            print(".", end="")

        for x in range(50):
            tick()
            print(";", end="")
            time.sleep(1)

    print_data_structure(data)
    print(report_all_version_numbers())


if __name__ == "__main__":
    test()

    # SPI_Store.initialize()

    # print("blank everything")
    # SPI_Store.sflash_protect_sectors(SFLASH_PRG_START+SFLASH_PRG_SIZE , SFLASH_PRG_START+SFLASH_PRG_SIZE,"off")
    # SPI_Store.sflash_erase(0, 0xFFFF0000  ,True)
