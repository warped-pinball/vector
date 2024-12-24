'''
serial flash program update storage driver

calls lower level SPI_Store driver (shared with FRAM)

'''

# the first 64k and the last 64k blocks can be protected in 4k sectors
# so we will not use those here.  we need only 3 aresa of 6Mbyte each

#usage 
SFLASH_PRG_START 0x0010000
SFLASH_PRG_SIZE  0x600000   #6Mbyte
SFLASH_NUM_PGMS  3
'''
total part is 32M byte:

Three section of 6M byte each used in this module
    0x0010000-0x0610000
    0x0610000-0x0C10000
    0x0C10000-0x1210000
    
'''







