# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
"""
    SPI module - to non-volatile serial RAM (FRAM)
    -now added serial flash part

    SYS11Wifi Project
    Dec 2024        
"""

import machine
from machine import SPI
import utime
import ustruct
import sys
import time
import uctypes
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE

#from logger import logger_instance  <<the logger uses this driver, cant really be imported here
#Log = logger_instance

SPI_store_version=2

#FRAM  Register and command defs for FM25L16B
OPCODE_WREN = 0x06      #set write enable latch
OPCODE_WRDI = 0x04      #write disable              <<clears WEL
OPCODE_RDSR = 0x05      #read status register
OPCODE_WRSR = 0x01      #write status register      <<clears WEL
OPCODE_READ = 0x03      #read memory
OPCODE_WRITE = 0x02     #write memory               <<clears WEL
STATUS_REG_VAL = 0x82   #wrill write this val i

# Assign chip select (CS) pin (and start it high)
cs = machine.Pin(5, machine.Pin.OUT)
cs.value(1)

# Initialize SPI Port
spi = machine.SPI(0,
                  baudrate=60000,  #20000,
                  polarity=1,
                  phase=1,
                  bits=8,
                  firstbit=SPI.MSB, #machine.SPI.LSB,
                  sck=machine.Pin(2),
                  mosi=machine.Pin(3),
                  miso=machine.Pin(4))


#FRAM write just one byte cmd
def reg_cmd(spi, cs, reg):   
    msg = bytearray()
    msg.append(0x00 | reg)    
    cs.value(0)
    spi.write(msg)
    cs.value(1)

#FRAM write one byte to one register location
def reg_write(spi, cs, reg, data):        
    msg = bytearray()
    msg.append(0x00 | reg)
    msg.append(data)
    cs.value(0)
    spi.write(msg)   #blocking
    cs.value(1)
  
#FRAM  
def mem_write(spi, cs, address, data):
    # Enable write operations
    reg_cmd(spi, cs, OPCODE_WREN)
    
    # Split data into chunks of 16 bytes
    chunk_size = 16
    for i in range(0, len(data), chunk_size):
        print("x",i)
        chunk = data[i:i + chunk_size]
        print(chunk)
        reg_cmd(spi, cs, OPCODE_WREN)

        msg = bytearray()
        msg.append(0x00 | OPCODE_WRITE)        
        msg.append((address & 0xFF00) >> 8)
        msg.append(address & 0x00FF)
        msg.extend(chunk)
        print(msg)
       
        cs.value(0)
        spi.write(msg)
        cs.value(1)
        address += chunk_size

#FRAM
def write(address,data):
    mem_write(spi, cs, address, data)

#FRAM
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

#FRAM
def read(address, nbytes):
    return mem_read(spi, cs, address, nbytes)

#FRAM read a register
def reg_read(spi, cs, reg, nbytes=1):  
    msg = bytearray()
    msg.append(0x00 | reg)    
    # Send 
    cs.value(0)
    spi.write(msg)
    data = spi.read(nbytes)
    cs.value(1)
    return data


#reverse bits(order) in a byte
def rbit8(v):
    v = (v & 0x0f) << 4 | (v & 0xf0) >> 4
    v = (v & 0x33) << 2 | (v & 0xcc) >> 2
    return (v & 0x55) << 1 | (v & 0xaa) >> 1


  
#FRAM restore ram from fram (called generally at power up)
def Restore_Mem(ram_address, byte_length):
            
    for st in range(0, byte_length, 16):
        dat = mem_read(spi, cs, st, 16)
        #print("restore rd ",st," ",ram_address[st])
        for index in range(0, 16 ,1):
            ram_address[index+st]=dat[index]
            

#FRAM write 16 bytes ram to fram - NO DMA Usage
def write_16_fram(ram_address, fram_address):    
    RamData=uctypes.bytearray_at(ram_address,16)
    fram_add = fram_address
    #print(" store fram=",fram_add," ram=",RamData)       
    mem_write(spi, cs, fram_add, RamData)        
            
#FRAM 
def write_all_fram_now():       
    MemIndex=0   
    while True:
        write_16_fram(SRAM_DATA_BASE+MemIndex, MemIndex)
        MemIndex = MemIndex + 16
        print(".",end="")
        if MemIndex >= SRAM_DATA_LENGTH:
            print(" ")
            print("FRAM: complete store done")
            return
             


'''
Serial Flash
    256M-Bit
    32M-Byte
    Byte addresses 0x0000-0x2 00 00 00     
    Requires 4 byte address mode (or only use 1/2)

    Give each software version 4M-bytes section

'''
sflash_is_on_board = False

#serial flash command opcodes
SFLASH_EN4B = 0xB7      #enable 4 byte addresses
SFLASH_RDCR = 0x15      #read config register
SFLASH_RDSR = 0x05      #read status register
SFLASH_RDID = 0x9F      #read chip ID  (0xC2,0x20,0x19)
SFLASH_CHIP_ID = [0xC2, 0x20, 0x19]
SFLASH_READ = 0x13      #regular 4adr byte read
SFLASH_PP   = 0x02      #page program (inside 256 byte page)
#erases set all bits to '1'
SFLASH_WREN = 0x06      #write enable command
SFLASH_WRDI = 0x04      #write disable
SFLASH_SE   = 0x20      #sector erase  (4k-byte sector)
SFLASH_BE4B = 0xDC      #block erase   (64k-byte block) 4byte adr
SFLASH_CE   = 0x60      #Chip erase    (whole chip)
#sector protection - using WPSEL=1 mode
SFLASH_WPSEL = 0x68
SFLASH_GBLK  = 0x7E  #lock all
SFLASH_WRDPB = 0xE1
SFLASH_RDDPB = 0xE0
#WIP write in progress bit for erases also
#serial l=flash CS active when HIGH


#send command with optional following data bytes
def _sflash_cmd_dat(spi, cs, reg, data=bytearray()):       
    cs.value(0)
    msg = bytearray()
    msg.append(reg)    
    msg.extend(data)
    cs.value(1)
    spi.write(msg)
    cs.value(0)
    utime.sleep_us(50) 
    cs.value(1)

#read a register (can be multiple read bytes)
def _sflash_reg_read(spi, cs, reg, nbytes=1):  
    cs.value(0)
    msg = bytearray()
    msg.append(reg)        
    cs.value(1)
    spi.write(msg)
    data = spi.read(nbytes)
    cs.value(0)
    utime.sleep_us(50) 
    cs.value(1)
    return data

def _sflash_write_enable():
    _sflash_cmd_dat(spi,cs,SFLASH_WREN)
   
def _sflash_get_chip_id():
    sig=_sflash_reg_read(spi, cs, SFLASH_RDID ,3)
    hex_values = ' '.join(f"{byte:02X}" for byte in sig)
    print("SFLASH: Signature in hex:", hex_values)
    return sig


#64k block size ERASE
def _sflash_block_erase(block_address,wait=False):
    if sflash_is_ready() is False:
        print("SFLASH: fault not ready, block erase")
        return "fault"

    _sflash_write_enable()    
    address_bytes = bytearray([
        (block_address >> 24) & 0xFF,  #MSByte
        (block_address >> 16) & 0xFF,
        0x00,
        0x00           
    ])
    _sflash_cmd_dat(spi, cs, SFLASH_BE4B, address_bytes)    
    print("ear ",address_bytes)
    if wait:
        utime.sleep_ms(5)  
        loop=0
        while not sflash_is_ready():
            if loop >= 200:
                print("SFLASH: timeout, block erase")
                return "timeout"
            utime.sleep_ms(20)  
            loop += 1


#read any number of bytes
def _sflash_mem_read(spi, cs, address, nbytes=16):
    cs.value(0)
    data = bytearray()
    chunk_size = 16
    offset = 0
    
    while offset < nbytes:
        remaining = nbytes - offset
        read_size = min(chunk_size, remaining)
        
        # Prepare the message
        msg = bytearray()
        msg.append(SFLASH_READ)
        msg.append((address >> 24) & 0xFF)  # adr(MSB)
        msg.append((address >> 16) & 0xFF)
        msg.append((address >> 8) & 0xFF)
        msg.append(address & 0xFF)
        
        # Send the message and read the data
        cs.value(1)
        spi.write(msg)
        data.extend(spi.read(read_size))
        cs.value(0)
        
        # Update the address and offset for the next chunk
        address += chunk_size
        offset += chunk_size    

    utime.sleep_us(50) 
    cs.value(1)  
    return data

#write any number of bytes
def _sflash_mem_write(spi, cs, address, data, wait=False):    
    cs.value(0)

    chunk_size = 16
    for i in range(0, len(data), chunk_size):
        print("x",i)
        chunk = data[i:i + chunk_size]
        print(chunk)
        _sflash_write_enable()  

        msg = bytearray()
        msg.append(SFLASH_PP)    
        address_bytes = bytearray([
            (address >> 24) & 0xFF,  #MSByte
            (address >> 16) & 0xFF,
            (address >>8) & 0xFF,
            (address & 0xFF)           
        ])  
        msg.extend(address_bytes)
        msg.extend(chunk)
        print(msg)
       
        cs.value(1)
        spi.write(msg)
        cs.value(0)
        address += chunk_size

    if wait:
        utime.sleep_ms(5)  
        loop=0
        while not sflash_is_ready():
            if loop >= 400:
                cs.value(1)  
                print("SFLASH: timeout, write")
                return "timeout"
            utime.sleep_ms(10)  
            loop += 1
    cs.value(1)  







def sflash_read(address, nbytes=16):
    if sflash_is_on_board == False: 
        return (0)
    return _sflash_mem_read(spi, cs, address, nbytes)

def sflash_write(address, data, wait=False):   
    if sflash_is_on_board == False: 
        return
    return _sflash_mem_write(spi, cs, address, data, wait)
    
#erase multiple blocks, wait required    
#one block can slecet no wait
def sflash_erase(start_block_address,end_block_address=0,wait=False):
    if sflash_is_on_board == False: 
        return
    start_block_address &= 0xFFFF0000
    end_block_address &= 0xFFFF0000
    #64k blocks
    if start_block_address==end_block_address or end_block_address==0:
        _sflash_block_erase(start_block_address,wait)
        print("erase one block done")
    else:    
        block_address = start_block_address
        while block_address <= end_block_address:
            _sflash_block_erase(block_address,True)
            print("er block",block_address)
            block_address += 0x010000 
        print("erase multi blocks done")

def sflash_is_ready():
    if sflash_is_on_board == False: 
        return (True)
    sr=_sflash_reg_read(spi, cs,SFLASH_RDSR)
    if (sr[0] & 0x01): return False
    else: return True


def sflash_protect_sectors(start_address, end_address, protect="on"):
    block_size = 0x10000  # 64K blocks
    sector_size = 0x1000  # 4K sectors
    first_block_address = 0x0000000
    last_block_address  = 0x1FF0000  

    if protect=="on":
        data_byte = 0xFF
    else:
        data_byte = 0

    # 64K blocks from 1 to 510
    for block_num in range(1, 511):
        block_address = block_num * block_size
        if block_address < start_address or block_address >= end_address:
            continue
        print ("block # ",block_num," prot= ",protect)
        _sflash_write_enable()
        msg = bytearray()        
        address_bytes = bytearray([
            (block_address >> 24) & 0xFF,  #MSByte
            (block_address >> 16) & 0xFF,
            (block_address >>8) & 0xFF,
            (block_address & 0xFF),
            data_byte
        ])  
        msg.extend(address_bytes)
        _sflash_cmd_dat(spi, cs, SFLASH_WRDPB, msg)
 
    # Protect 4K sectors within the first and last block (block 0 and 511)
    for block_num in [0, 511]:
        block_address = block_num * block_size
        for sector_offset in range(0, block_size, sector_size):
            sector_address = block_address + sector_offset
            if sector_address < start_address or sector_address >= end_address:
                continue
            _sflash_write_enable()
            print("4k sector # ",sector_offset," prot= ",protect)
            msg = bytearray()        
            address_bytes = bytearray([
                (sector_address >> 24) & 0xFF,  #MSByte
                (sector_address >> 16) & 0xFF,
                (sector_address >>8) & 0xFF,
                (sector_address & 0xFF),
                data_byte
            ])  
            msg.extend(address_bytes)
            _sflash_cmd_dat(spi, cs, SFLASH_WRDPB, msg)




#init flash chip
def sflash_init():  
    global sflash_is_on_board

    #confirm chip id
    id=_sflash_get_chip_id()
    sflash_is_on_board=True
    if list(id) != SFLASH_CHIP_ID:
        print("First attempt ID mismatch. Trying again...")
        id =  id=_sflash_get_chip_id()
        if list(id) != SFLASH_CHIP_ID:
            print("SFLASH: chip ID error")
            sflash_is_on_board=False

    #4 byte address mode
    _sflash_write_enable()
    _sflash_cmd_dat(spi, cs, SFLASH_EN4B)       
    #read config, check bit 5
    config_reg=_sflash_reg_read(spi,cs,SFLASH_RDCR)
    if (config_reg[0] & 0x20) == 0:
        _sflash_cmd_dat(spi, cs, SFLASH_EN4B)
        config_reg=_sflash_reg_read(spi,cs,SFLASH_RDCR)
        if (config_reg[0] & 0x20) == 0:
            print("SFLASH: Fault, cannot set 4byte mode")
            sflash_is_on_board=False

    #set WPSEL
    _sflash_write_enable()
    _sflash_cmd_dat(spi, cs, SFLASH_WPSEL) 
    _sflash_write_enable()
    _sflash_cmd_dat(spi, cs, SFLASH_GBLK) 


#
#Initialize Sysytem!   - Enable and prep spi fram and serial flash
#
def initialize():
    
    #init flash chip if it is there
    sflash_init()         





if __name__ == "__main__":
    import utime

    print("spi store running as main")
    initialize()
    print("ready?",sflash_is_ready())


    sflash_protect_sectors(0x0000, 0x1FF0000, "off")

    
    
    start_time = utime.ticks_ms() 
    sflash_erase(0x00,0x10000 * 96,True)
    elapsed_time = utime.ticks_diff(utime.ticks_ms(), start_time)  
    print(f"The function took {elapsed_time} milliseconds to complete.")
   
    '''
    print("READ 1  ",sflash_read(0, 18))    
 
    data_buffer = bytearray([0xFF] * 1024)
    data_buffer[0]=155
    data_buffer[1]=133
    print("WRITE buf-> ",data_buffer)
    
    start_time = utime.ticks_ms() 
    for i in range(96):
        sflash_write(0x10000 * i, data_buffer)
    elapsed_time = utime.ticks_diff(utime.ticks_ms(), start_time)  
    print(f"The function took {elapsed_time} milliseconds to complete.")
    '''


    print ("READ 2 ",sflash_read(0, 18))
    
    print("done")

