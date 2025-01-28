import uctypes
import uos

# from machine import SPI, Pin

"""
try for vfs compatibility with micropython -

    still use SPI driver (musy play nice with fram)


"""

import SPI_Store

SPI_Store.initialize()


class SerialFlashVFS:
    def __init__(self):
        self.block_size = 4096  # block (sector!) size
        self.page_size = 256  # page size
        self.block_count = (1 * 1024 * 1024) // 4096
        SPI_Store.sflash_protect_sectors(0, 4096 * 256, "off")

    def readblocks(self, block_num, buf, offset=0):
        print("*read", block_num, len(buf), "offset=", offset, "\n")
        address = (block_num * self.block_size) + offset
        data = SPI_Store.sflash_read(address, len(buf))
        print(data, len(data))
        buf[:] = data
        print(buf, len(buf))

    def writeblocks(self, block_num, buf, offset=0):
        print("*write", block_num, len(buf), "offset=", offset, "\n")
        address = (block_num * self.block_size) + offset
        SPI_Store.sflash_write(address, buf)

    def ioctl(self, op, arg):
        print("*ioctl", op, arg, "\n")
        if op == 1:  # MP_BLOCKDEV_IOCTL_INIT
            return 0  # Success
        elif op == 2:  # MP_BLOCKDEV_IOCTL_DEINIT
            return 0  # Success
        elif op == 3:  # MP_BLOCKDEV_IOCTL_SYNC
            return 0  # Success
        elif op == 4 or op == 6:  # Get number of blocks
            print("block count", self.block_count)
            return self.block_count  # Example number of blocks
        elif op == 5 or op == 7:  # Get block size
            print("block size", self.block_size)
            return self.block_size
        elif op == 8:  # MP_BLOCKDEV_IOCTL_BLOCK_ERASE
            print("op 8 !!!!!")
            self.eraseblock(arg)
            return 0  # Success
        else:
            return -1  # Unknown operation

    def eraseblock(self, block_num):
        print("*erase")
        address = block_num * self.block_size
        sector_address = address & 0xFFFFF000
        SPI_Store.sflash_sector_erase(sector_address)


bdev = SerialFlashVFS()

"""
# Format with FAT
uos.VfsFat.mkfs(bdev)  # or older builds: uos.VfsFat.mkfs(bdev, ...)
vfs = uos.VfsFat(bdev)
uos.mount(vfs, '/test')

with open('/test/hello.txt', 'w') as f:
    f.write("Testing FAT!")

with open("/test/hello.txt", "r") as f:
    print(f.read())

"""

"""
#test my driver---
bdev.ioctl(8, 0)
# Write 32 bytes
test_data = b"Hello, block device!"
bdev.writeblocks(0, test_data)
# Read it back
rbuf = bytearray(len(test_data))
bdev.readblocks(0, rbuf)
print("Read back:", rbuf)
bdev.ioctl(8, 0)
"""


# format little fs - -
try:
    uos.VfsLfs2.mkfs(bdev)
except Exception as e:
    print("Failed to format filesystem:", e)

vfs = uos.VfsLfs2(bdev)

uos.mount(vfs, "/flash")

with open("/flash/test.txt", "w") as f:
    f.write("Hello from custom VFS!")

with open("/flash/test.txt", "r") as f:
    print(f.read())
