# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
"""
    SPI module - to non-volatile serial RAM (FRAM)

    SYS11Wifi Project
    Dec 2023        

    version 2, add support for serial flash chip
    Nov 2024
"""

import machine
from machine import SPI
import utime
import ustruct
import sys
import time
import uctypes
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE


#Register and command defs for FM25L16B
OPCODE_WREN = 0x06      #set write enable latch
OPCODE_WRDI = 0x04      #write disable
OPCODE_RDSR = 0x05      #read status register
OPCODE_WRSR = 0x01      #write status register
OPCODE_READ = 0x03      #read memory
OPCODE_WRITE = 0x02     #write memory
STATUS_REG_VAL = 0x82   #wrill write this val i

# Assign chip select (CS) pin (and start it high)
cs = machine.Pin(5, machine.Pin.OUT)
cs.value(1)

# Initialize SPI Port
spi = machine.SPI(0,
                  baudrate=20000,  #10000,
                  polarity=1,
                  phase=1,
                  bits=8,
                  firstbit=SPI.MSB, #machine.SPI.LSB,
                  sck=machine.Pin(2),
                  mosi=machine.Pin(3),
                  miso=machine.Pin(4))

#write just one byte cmd
def reg_cmd(spi, cs, reg):   
    msg = bytearray()
    msg.append(0x00 | reg)    
    cs.value(0)
    spi.write(msg)
    cs.value(1)

#write one byte to one register location
def reg_write(spi, cs, reg, data):        
    msg = bytearray()
    msg.append(0x00 | reg)
    msg.append(data)
    cs.value(0)
    spi.write(msg)   #blocking
    cs.value(1)
  
def mem_write(spi, cs, address, data):
    # Enable write operations
    reg_cmd(spi, cs, OPCODE_WREN)
    
    # Split data into chunks of 16 bytes
    chunk_size = 16
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        
        reg_cmd(spi, cs, OPCODE_WREN)

        msg = bytearray()
        msg.append(0x00 | OPCODE_WRITE)
        msg.append((address & 0xFF00) >> 8)
        msg.append(address & 0x00FF)
        msg.extend(chunk)
       
        cs.value(0)
        spi.write(msg)
        cs.value(1)
        
        address += chunk_size

#regulat call from spi data store, server etc.....
def write(address,data):
    mem_write(spi, cs, address, data)


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

#regular call from spi data store - and server etc....
def read(address, nbytes):
    return mem_read(spi, cs, address, nbytes)



#read a register
def reg_read(spi, cs, reg, nbytes=1):  
    msg = bytearray()
    msg.append(0x00 | reg)    
    # Send 
    cs.value(0)
    spi.write(msg)
    data = spi.read(nbytes)
    cs.value(1)
    return data

'''
#reverse bits(order) in a byte
def rbit8(v):
    v = (v & 0x0f) << 4 | (v & 0xf0) >> 4
    v = (v & 0x33) << 2 | (v & 0xcc) >> 2
    return (v & 0x55) << 1 | (v & 0xaa) >> 1
'''


#enable and prep spi
def initialize():


    #FRAM setup
    cs.value(1)    
    datret = reg_read(spi, cs, OPCODE_RDSR)    
    #write Enable
    reg_cmd(spi,cs,OPCODE_WREN)
    time.sleep(1)



  
  
#restore ram from fram (called generally at power up)
def Restore_Mem(ram_address, byte_length):
            
    for st in range(0, byte_length, 16):
        dat = mem_read(spi, cs, st, 16)
        #print("restore rd ",st," ",ram_address[st])
        for index in range(0, 16 ,1):
            ram_address[index+st]=dat[index]
            

#write 16 bytes ram to fram - NO DMA Usage
def write_16_fram(ram_address, fram_address):    
    RamData=uctypes.bytearray_at(ram_address,16)
    fram_add = fram_address
    #print(" store fram=",fram_add," ram=",RamData)       
    mem_write(spi, cs, fram_add, RamData)        
            
       
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
             






# flash chip defines
FLASH_REMS = bytearray([0x90, 0x00, 0x00, 0x00])  #read manudfacturer
FLASH_RDID = bytearray([0x9F]) #read ID
FLASH_WREN =   0x06 #write enable

FLASH_READ = 0x03
FLASH_SE = bytearray([0x20,0,0,0])  #sector erase
FLASH_PP = 0x02

# FLASH - write registers
def flash_reg_cmd(spi, cs, opcode, read_count):       
    cs.value(0)
    time.sleep_ms(1)
    cs.value(1)
    for byte in opcode:
        msg = bytearray([byte])
        spi.write(msg)
    response = spi.read(read_count)
    cs.value(0)    
    return response


#read bytes from addr
def flash_read(spi, cs, addr, count):
    cs.value(0)
    time.sleep_ms(1)
    cs.value(1)
    
    msg = bytearray([FLASH_READ, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF])
    spi.write(msg)
    
    data = spi.read(count)
    cs.value(0)
    return data



def flash_write(spi, cs, addr, data):   
    cs.value(0)
    time.sleep_ms(1)
    cs.value(1)

    spi.write(bytearray([FLASH_WREN]))
    cs.value(0)
    time.sleep_ms(1)  
    

    # Step 2: Send page program command and address
    cs.value(1)
    msg = bytearray([FLASH_PP, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF])
    spi.write(msg)
    
    spi.write(data)
    cs.value(0)
    


def hexprint(response):
    print(" ".join(f"{byte:02X}" for byte in response))

def test_flash():
    # Call hexprint with flash_reg_cmd directly
    print("REMS ->", end=" ")
    hexprint(flash_reg_cmd(spi, cs, FLASH_REMS, 2))

    print("RDID ->", end=" ")
    hexprint(flash_reg_cmd(spi, cs, FLASH_RDID, 3))


    #print("write")
    dat=bytearray([6,2,3,4,55,66,77,88])
    #flash_write(spi,cs,6000,dat)


    print("read adr 0 ->", end = " ")
    hexprint(flash_read(spi, cs, 0,10))

    print("read adr 6000 ->", end = " ")
    hexprint(flash_read(spi, cs, 6000,10))


import SPI_DataStore as DataStore

if __name__ == "__main__":
    test_flash()

    cfg=DataStore.read_record("configuration",0)
    print( cfg["ssid"].strip('\0') )
    print( cfg["password"].strip('\0') )


    test_flash()

    cfg=DataStore.read_record("configuration",0)
    print( cfg["ssid"].strip('\0') )
    print( cfg["password"].strip('\0') )
