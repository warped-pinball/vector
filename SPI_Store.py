# This file is part of the Warped Pinball SYS11Wifi Project.
#
# SYS11Wifi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# SYS11Wifi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# see <http://www.gnu.org/licenses/>.

"""
    SPI module - to non-volatile serial RAM (FRAM)

    SYS11Wifi Project
    Dec 2023        
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


#reverse bits(order) in a byte
def rbit8(v):
    v = (v & 0x0f) << 4 | (v & 0xf0) >> 4
    v = (v & 0x33) << 2 | (v & 0xcc) >> 2
    return (v & 0x55) << 1 | (v & 0xaa) >> 1


#enable and prep spi fram
def initialize():
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
             
