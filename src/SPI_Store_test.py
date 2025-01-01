
import micropython
import DiagDisplay as di

import machine
from machine import SPI
import time
import gc
#import ustruct
#import sys
#import uctypes
#from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE

#from logger import logger_instance  <<the logger uses this driver, cant really be imported here
#Log = logger_instance



# Assign chip select (CS) pin (and start it high)
cs = machine.Pin(5, machine.Pin.OUT)
cs.value(1)

# Initialize SPI Port
spi = machine.SPI(0,
                  baudrate=60000,  #20000,
                  polarity=1,
                  phase=1,
                  bits=8,
                  firstbit=SPI.MSB, 
                  sck=machine.Pin(2),
                  mosi=machine.Pin(3),
                  miso=machine.Pin(4))

             


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
#SFLASH_CHIP_ID = [0xC2, 0x20, 0x17]

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
    msg = bytearray([reg]) + data          
    cs.value(0) 
    time.sleep_us(20)         
    cs.value(1)
    time.sleep_us(20) 
    spi.write(msg)
    cs.value(0)
    time.sleep_us(20) 
    cs.value(1)
 
#read a register (can be multiple read bytes)
def _sflash_reg_read(spi, cs, regg, nbytes=1):     

    '''
    #fram way - pass
    msg = bytearray()
    msg.append(0x00 | regg)    
    # Send 
    cs.value(0)
    spi.write(msg)
    data = spi.read(nbytes)
    cs.value(1)
    return data
    '''
    
    #sflash way - fail
    msgg = bytearray([regg])       
    cs.value(0)
    time.sleep_us(20)           
    cs.value(1)    
    time.sleep_us(20)   
    spi.write(msgg)
    data = spi.read(nbytes)
    cs.value(0)
    time.sleep_us(20) 
    cs.value(1)
    
    '''
    #pass
    #sflash way - build the fram way
    #msgg = bytearray([regg])  

    msg = bytearray()
    #msg.append(0x00 | regg)    
    msg.append(regg)    

    cs.value(0)
    time.sleep_us(20)           
    cs.value(1)    
    time.sleep_us(20)   
    spi.write(msg)
    data = spi.read(nbytes)
    cs.value(0)
    time.sleep_us(20) 
    cs.value(1)
   

    msgg = bytearray([regg])   #  fail 4/5  <-- on line from sflash (fail?)
                                # second run fail 1/4

    #msgg = bytearray()  #<-two lines from fram (pass? no one fail from  8)
    #msgg.append(0x00 | regg)   #second run =    fail 0/6

    cs.value(0)
    time.sleep_us(20)           
    cs.value(1)    
    time.sleep_us(20)   
    spi.write(msgg)
    data = spi.read(nbytes)
    cs.value(0)
    time.sleep_us(20) 
    cs.value(1)



  

    #fram with DEALYS - tested pass
    msg = bytearray()
    msg.append(0x00 | regg)    
    # Send 
    time.sleep_us(20) 
    cs.value(0)
    time.sleep_us(20) 
    spi.write(msg)
    time.sleep_us(20) 
    data = spi.read(nbytes)
    time.sleep_us(20) 
    cs.value(1)
    time.sleep_us(20) 
    '''







    return data

    




def _sflash_write_enable():
    global spi,cs
    _sflash_cmd_dat(spi,cs,SFLASH_WREN)
   
def _sflash_get_chip_id():
    global spi,cs
    sig=_sflash_reg_read(spi, cs, SFLASH_RDID ,3)
    print(f"SFLASH: Signature: {sig[0]:02X},{sig[1]:02X},{sig[2]:02X}")
    return sig

#64k block size ERASE
def _sflash_block_erase(block_address,wait=False):
    global spi,cs
    if sflash_is_ready() is False:
        print("SFLASH: fault not ready, block erase")
        return

    _sflash_write_enable()    
    address_bytes = bytearray([
        (block_address >> 24) & 0xFF,  #MSByte
        (block_address >> 16) & 0xFF,
        0x00,
        0x00           
    ])
    
    _sflash_cmd_dat(spi, cs, SFLASH_BE4B, address_bytes)       

  
#read any number of bytes (no page boundary problems with read)
def _sflash_mem_read(spi, cs, address, nbytes=16):    
    rd_data = bytearray(nbytes)
    size = 16
    rd_offset = 0
    num_bytes = nbytes 

    cs.value(0)
    while rd_offset < num_bytes:
        remaining = num_bytes - rd_offset
        read_size = min(size, remaining)
    
        rd_msg = bytearray([
            SFLASH_READ,
            (address >> 24) & 0x0FF,  # adr(MSB)
            (address >> 16) & 0x0FF,
            (address >> 8) & 0x0FF,
            address & 0x0FF
        ])
        
        # Send the message and read the data
        time.sleep_us(20) 
        cs.value(1)
        time.sleep_us(20) 
        spi.write(rd_msg)
        rd_data[rd_offset:rd_offset + read_size] = spi.read(read_size)
        cs.value(0)
        # Update the address and offset for the next chunk
        address += read_size
        rd_offset += read_size    

    time.sleep_us(20) 
    cs.value(1)  
    return rd_data

#
#write any number of bytes
#single write cannot cross 256 byte boundary!
def _sflash_mem_write(spi, cs, address, data, wait=False):  
       
    i=0
    w_chunk_size = 16   
    w_data_length = len(data) 


    while i < w_data_length:     
        distance_to_boundary = 0x100 - (address & 0x0FF)
        write_size = min(w_chunk_size, distance_to_boundary)
        w_chunk_data = data[i:i + write_size]                          

        w_msg = bytearray([
            SFLASH_PP,
            (address >> 24) & 0x0FF,  # MSByte
            (address >> 16) & 0x0FF,
            (address >> 8) & 0x0FF,
            (address & 0x0FF)
        ] + list(w_chunk_data))
        print(f" write adr= {address:#x}   msg={w_msg.hex()}")
 
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
    global spi,cs
    global sflash_is_on_board

    if sflash_is_on_board == False: 
        return (0)
    return _sflash_mem_read(spi, cs, address, nbytes)

def sflash_write(address, data, wait=False):   
    global spi,cs
    global sflash_is_on_board

    if sflash_is_on_board == False: 
        return
    return _sflash_mem_write(spi, cs, address, data, wait)
    
#erase multiple blocks, wait required    
#one block can slecet no wait
def sflash_erase(start_block_address, end_block_address=0, wait=False):
    global sflash_is_on_board

    if sflash_is_on_board == False:
        return

    start_block_address &= 0xFFFF0000
    end_block_address &= 0xFFFF0000

    if start_block_address == end_block_address or end_block_address == 0:
        _sflash_block_erase(start_block_address, wait)       
    else:
        block_address = start_block_address
        while block_address <= end_block_address:
            _sflash_block_erase(block_address, True)
            block_address += 0x010000
            print("block erase+")
       


def sflash_is_ready():
    global sflash_is_on_board
    if sflash_is_on_board == False: 
        return True
 
    #sr = [0]
    sr = _sflash_reg_read(spi, cs, SFLASH_RDSR)  
    return (sr[0] & 0x01) == 0x00
      
def sflash_wait_for_ready():
    while sflash_is_ready() is False:
        time.sleep(0.2)
        print(";",end="")
   

def sflash_protect_sectors(start_address, end_address, protect="on"):
    block_size = 0x10000  # 64K blocks
    sector_size = 0x1000  # 4K sectors
    first_block_address = 0x0000000
    last_block_address  = 0x1FF0000  

    if protect=="on":
        data_byte = 0xFF
    else:
        data_byte = 0x00

    # 64K blocks from 1 to 510
    for block_num in range(1, 511):
        block_address = block_num * block_size
       
        if (block_address < (start_address&0xFFFF0000)) or (block_address > (end_address&0xFFFF0000)):
            continue

        print(f"block # {block_num} st={block_address:#x}  prot= {protect}")
        msg = bytearray([
            (block_address >> 24) & 0x0FF, 
            (block_address >> 16) & 0x0FF,
            (block_address >> 8) & 0x0FF,
            (block_address & 0x0FF),
            data_byte
        ])

        _sflash_write_enable()
        _sflash_cmd_dat(spi, cs, SFLASH_WRDPB, msg)
    
    '''
    # Protect 4K sectors within the first and last block (block 0 and 511)
    for block_num in [0, 511]:
        block_address = block_num * block_size
        for sector_offset in range(0, block_size, sector_size):
            sector_address = block_address + sector_offset
            if sector_address < (start_address & 0xFFFFF000) or sector_address >= (end_address & 0xFFFFF000):
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
    
    print("sector protect done")
    '''



#init flash chip
def sflash_init():  
    global sflash_is_on_board
    

    #confirm chip id
    id=_sflash_get_chip_id()
    sflash_is_on_board=True
    if list(id) != SFLASH_CHIP_ID:
        sflash_is_on_board=False
        print("SFLASH: Fault, chip ID not correct",id)

    #4 byte address mode
    _sflash_write_enable()
    _sflash_cmd_dat(spi, cs, SFLASH_EN4B)       
    #read config, check bit 5
    config_reg=_sflash_reg_read(spi,cs,SFLASH_RDCR)
    if config_reg is None or len(config_reg) == 0 or (config_reg[0] & 0x20) == 0:
        print("SFLASH: Fault, cannot set 4byte mode",config_reg)
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

    #check fram?, version?


def p():
     _sflash_write_enable()


def o():
    _sflash_cmd_dat(spi, cs, SFLASH_EN4B)       



def test():
   
    prog_ind=0
    di.initialize()
    initialize()

    for i in range(12000):       
        print(_sflash_reg_read(spi, cs, 33, 5))

        sflash_wait_for_ready()
        print("1ready=",sflash_is_ready())
        sflash_protect_sectors(0x10000, 0x20000, "off")
        #time.sleep(1)

        print("2ready=",sflash_is_ready())
        _sflash_block_erase(0x10000)

        sflash_wait_for_ready()
        print("3ready=",sflash_is_ready())
        _sflash_mem_write(spi, cs, 0x10000, bytearray([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]))
        
        data_to_write = bytearray(range(1, 90))  
        print(_sflash_mem_write(spi, cs, 0x10000, data_to_write))
        

        print("4ready=",sflash_is_ready())
        print(_sflash_mem_read(spi, cs, 0x10000, 20))  #was 10  fail with 20
        print("loop",i)

        gc.collect()
        di.write_char(chr(prog_ind + ord('0')))
        prog_ind=prog_ind+1
        if prog_ind>9:
            prog_ind=0

    di.write_char('c')


if __name__ == "__main__":
    test()
    print("done")