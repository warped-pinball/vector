# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 

"""
Ram intercept module for Classics - REVISION 3

    Adapted from WPC (because WPC uses two CE inputs)

    PIO0 and PIO2  and  DMA 2,3,4,5

    This module intercepts all read operations and sources the data from internal RP2350 ram
    All write operations are decoded and stored to internal RP2350 ram (writes are allowed to
    propagate on the main board to the standard ram also)
   

    SM#8 reserved for use by micopython Wifi chip interface
"""

import machine
import micropython
import rp2
from micropython import const
import Dma_Registers_RP2350 as dma_d
import Shadow_Ram_Definitions as RamDef

# I/O Defs, Classics PCB Rev1
# const() so these fold into literals at compile time and are usable inside @rp2.asm_pio
DATA_DIR_PIN = const(28)
A_SELECT_PIN = const(27)
LED_PIN = const(26)
SWITCH_PIN = const(22)
WR_PIN = const(12)
VMA_ADR_U8_PIN = const(13)   #5101 chip (battery backed ram 0x0200-0x02FF)
VMA_ADR_U7_PIN = const(11)   #6810 chip (volatile ram 0x0000-0x007F)
FIRST_ADR_PIN = const(6)
FIRST_DATA_PIN = const(14)


#Catch Address+VMA signal
#   SM#9, PIO2
#   JMP Pin is VMA_ADR_U8_PIN (GPIO#13) 
#   
#   Diagnostic purposes:
#   @rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))  
#
#
#  false pulses found @ about 50nS
#  hold over /CE from last syscle can be 120nS from falling edge of the 2ph clock
@rp2.asm_pio()  
def CatchVMA_U8():
    wrap_target()
    label("start_u8")
    
    wait(0, gpio, 13)  [5] #wait for VMA+ADR to go low
    jmp (pin,"start_u8")  #small amount of debounce here - count on clock being high during noisy adr transistions
    irq(5) #this will keep sending irq5 while gpio is low, but thats ok
    wrap()

#Catch Address+VMA signal for U7
#   SM#10,  PIO2
#   JMP Pin is VMA_ADR_U7 (GPIO#11)
#
#   Diagnostic purposes:
#   @rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))  
#
@rp2.asm_pio()  
def CatchVMA_U7():
    wrap_target()
    label("start_u7")
    
    wait(0, gpio, 11) [5] 
    jmp (pin,"start_u7")                   
    irq(5)   
    wrap()


#
#Pass VMA U7 or U8 on to next pio module
#   SM#11, PIO2
#
#   and wait for clock cycle ignoring future IRQs that can be false
#
#   this needs to happen in one place to lock out U7 when U8 is in process and vice versa
#
#@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))    #Diagnostic side set
@rp2.asm_pio()  
def Pass_VMA():
    wrap_target()
    label("Pass_VMA_start")
    
    wait(1, irq, 5)            #wait for signal from U7/U8 (both use irq5), this also clears IRQ   

    #if 2ph clock is low - go back to waiting - 
    jmp (pin,"Pass_VMA_goahead")    
    jmp ("Pass_VMA_start")          

    label("Pass_VMA_goahead")

    #trigger next pio after 2ph clock is already HIGH
    word(0xC41C)    [7]  #.side(1)      #(1100 0100 0001 1100 ) = ( 0xC41C)   IRQ4 to PIO plus one (we are in PIO2 so up one goes to PIO0)   
    
    wait(0,gpio,1)  [7]        #wait for 2ph Clock LOW, +after delay  7*6.6nS=47nS      
    irq(clear, 5)        # .side(0)     #clear IRQ5 before looping back, will have been spammed
    wrap()

   
# PIO_PRG: Read Address
#
# SM#0, PIO0
#
#   wait for valid adr / Vma signal (from IRQ4)
#   if read cycle, get address, get byte, write to pins   
#   if write cycle, IRQ to next PIO Prg
#
#   PRELOAD: y with 21 bit shadow ram base address
#   PRELOAD: x with all ones for use in pin data direction
#
#   SIDESET: A_select and Data_Dir
#   IN: Address Pins
#   OUT: Data Pins
#
#  ->21

@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW,rp2.PIO.OUT_LOW), out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT) 
def ReadAddress():

    label("start_adr")    
    wrap_target()
    
    wait(1,irq,4)                       #new way for rp2350 - wait for IRQ4, this is the signal from PIO2  
    jmp(pin,"do_write")                 #pin is W/R (not R/W, has been inverted) 

    #READ Process, Get Address  
    in_(pins,1)            .side(0)     #read A8 into EMPTY isr (A_Select=0) -> isr = A8 (clean)
    mov(x,isr)             .side(1)     #X = clean A8 only (0/1) for the 0x100+ low-nibble branch

    mov(isr,y)       [3]   .side(1)     #now load 23-bit shadow base into isr
    in_(x,1)         [3]   .side(1)     #re-insert A8 from X; A_Select=1; [7]=mux settle (restores 8 cyc)
    in_(pins,8)            .side(1)     #read A0-7 (A_Select returns to 0 on the push below)
    push(noblock)          .side(0)     #send out address result for DMA
   
    #READ Process, send data out to pins
    mov(osr, invert(null))
    out(pindirs,8)   [3]    .side(2)     #pins to outputs (1=output), side set is data_dir output

   
    #psm chgange to blocking - remove delays before this...
    pull(block)            .side(2)     #TX fifo -> OSR, getting 8 bits data from DMA transfer
                                         #change to block to give DMA thime it need dynamically instead of wait states in previous lines...
    out(pins,8)            .side(2)     #OSR -> Pins - all 8 bits


    #for 0x100+ (5101 nibble RAM) force low data nibble to 1111 via SM3 (set_lsn_data)
    #  X currently = A8 (0/1); skip the trigger for 0x000-0x0FF (full-byte 6810 region)
    jmp(not_x, "skip_low")
    irq(7)                 .side(2)             #signal SM3 to drive D0-D3 = 1111 (its OUT group = 4 pins only)
    label("skip_low")


    #READ Process, wrap up
    wait(0, gpio, 1)   [2]  .side(2)    #wait eclock LOW then hold data ~10ns (data_dir still out)
    word(0xA063)          #  101 00000 011 00 011  0xA063   mov(pindirs, null)     .side(0)     #pins to inputs (dir=0), data_dir back to normal
    jmp("start_adr")       .side(0)     #read done, back to the top

    #WRITE process
    label("do_write")    
    irq(5)          [3]             
    wait(0,gpio,1)  [3]             #wait for eClock to go low

    wrap() 
    

    
# PIO_PRG: Get Address for Write Cycle
#
# SM#1, PIO0
#
#     read in address (with fixed 21 bits)
#     push address out and launch next pio prg via IRQ
#
#     PRELOAD: Y with 21 bit shadow ram base address
#
#     SIDESET: A_Select
#     IN: Address Pins
#
#  ->7
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW)
def GetWriteAddress():
    wrap_target()
    wait (1,irq,5)         
    
    #WRITE Process, Get Address  
    mov(isr,y)             .side(0)     #copy 23 bit address msb to isr,ready to shift in 11 lsb from pins    
    in_(pins,1)            .side(0)     #read A8, set A_Select to 1  
    nop()            [7]   .side(1)  #    7 * 6.67nS=47nS 
    in_(pins,8)            .side(1)     #read A0-7, set A_Select back to 0        
    push(noblock)          .side(0)     #send out address result for DMA
    irq(6)                         #start write ram pio
    wrap()
  
  
# PIO_PRG : Data write
#
# SM#2, PIO0
#
#   read data from pins
#   write data (to internal rp2 memory) 
#
#   OUT: Data Pins
#
#  ->5
@rp2.asm_pio (out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT  ) 
#@rp2.asm_pio (out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT , sideset_init=rp2.PIO.OUT_LOW )   #DIAG
def WriteRam():
    wrap_target()    
    wait(1,irq,6)       #wait for IRQ6 and reset it    
     
    wait(0,gpio,1)      #wait for clock going-low edge    
    in_(pins,8)         #read all 8 data in one go
    push(noblock)       #push out data byte, picked up by DMA
   
    wrap()
    
 

 
# PIO_PRG : Set Low-nibble data pins to 1s
#
# SM#3, PIO0
#
#   Triggered by ReadAddress via IRQ7, but ONLY on 0x100+ reads (5101 nibble RAM).
#   Drives just the 4 low data pins (D0-D3 = GPIO14-17) to 1111.
#
#   Direction stays under ReadAddress's control (out_init = IN_* here, so this SM never
#   drives pindirs); the value written only appears while ReadAddress has D0-D3 as outputs.
#
#   PRELOAD: X = 0x0F  (the value written to the 4 pins)
#   OUT: D0-D3 only
#
# diag    @rp2.asm_pio(out_init=(rp2.PIO.IN_HIGH,)*4 , sideset_init=rp2.PIO.OUT_LOW)
@rp2.asm_pio(out_init=(rp2.PIO.IN_HIGH,)*4)
def set_lsn_data():
    wrap_target()
    wait(1, irq, 7)          #wait for trigger from ReadAddress (polarity 1 auto-clears IRQ7)
    mov(pins, x)   [7]           #drive D0-D3 from X (=0x0F) -> low data nibble = 1111
    wrap()




def pio_start():

    gpio_1 = machine.Pin(1, machine.Pin.IN)
    gpio_13 = machine.Pin(13, machine.Pin.IN)
    gpio_11 = machine.Pin(11, machine.Pin.IN)
    gpio_22 = machine.Pin(22, machine.Pin.OUT)
    gpio_rw = machine.Pin(12, machine.Pin.IN)  


    for pin_num in range(6, 14):  # range goes from 6 to 13
        machine.Pin(pin_num, machine.Pin.IN)

    #   PRELOAD: y with 21 bit shadow ram base address
    #   PRELOAD: x with all ones for use in pin data direction
    #   SIDESET: A_select and Data_Dir
    #   IN: Address Pins
    #   OUT: Data Pins
    sm_ReadAddress = rp2.StateMachine(0, ReadAddress, freq=150000000, set_base=machine.Pin(22), sideset_base=machine.Pin(27), out_base=machine.Pin(14) ,in_base=machine.Pin(6), jmp_pin=machine.Pin(12))  
       
    #   PRELOAD: Y with 23 bit shadow ram base address
    #   SIDESET: A_Select
    #   IN: Address Pins
    sm_GetWriteAddress = rp2.StateMachine(1, GetWriteAddress, freq=75000000, sideset_base=machine.Pin(27) ,in_base=machine.Pin(6))
    
    #   IN: Data Pins
    #sm_WriteRam = rp2.StateMachine(2, WriteRam, freq=150000000, in_base=machine.Pin(14), out_base=machine.Pin(14), sideset_base=machine.Pin(22))

    #sm_WriteRam = rp2.StateMachine(2, WriteRam,  freq= 75000000, in_base=machine.Pin(14), out_base=machine.Pin(14))

    sm_WriteRam = rp2.StateMachine(2, WriteRam,  freq=150000000, in_base=machine.Pin(14), out_base=machine.Pin(14))

    #   PIO0_SM3 - force low data nibble (D0-D3) to 1 for 0x100+ reads (5101 nibble RAM)
    #   OUT group is ONLY 4 pins (out_base=GPIO14, count=4 from set_lsn_data's out_init)
    #diag ->
    #sm_set_lsn_data = rp2.StateMachine(3, set_lsn_data, freq=150000000, out_base=machine.Pin(14),sideset_base=machine.Pin(22))
    sm_set_lsn_data = rp2.StateMachine(3, set_lsn_data, freq=150000000, out_base=machine.Pin(14))

    #VMA Catch for U8
    # JMP pin is VMA U8 GPIO#13
    sm_CatchVMA_U8 = rp2.StateMachine(9, CatchVMA_U8, freq=150000000, jmp_pin=machine.Pin(13) )  
  
    # VMA catch for U7
    # JMP pin is VMA U7 GPIO#11
    sm_CatchVMA_U7 = rp2.StateMachine(10, CatchVMA_U7, freq=150000000, jmp_pin=machine.Pin(11) ) 

    # passes catch VMA U7 or U8 to next PIO
    # receive IRQ5
    # JMP pin is 2ph clock
    # diag-> 
    #sm_Pass_VMA = rp2.StateMachine(11, Pass_VMA, freq=150000000, sideset_base=machine.Pin(22), jmp_pin=machine.Pin(1))
    sm_Pass_VMA = rp2.StateMachine(11, Pass_VMA, freq=150000000, jmp_pin=machine.Pin(1))
    
    


    print("PIO Start")

    #
    #Trigger and Detection PIO (#2)
    #
    #PIO2 - three state machine in use (fourth used by system for wifi)
    sm_CatchVMA_U7.active(1)
    sm_CatchVMA_U8.active(1)
    sm_Pass_VMA.active(1)
    sm_Pass_VMA.exec("irq(clear,5)")
        
    #
    #Ram access part (shadowram) PIO (#0)
    #
    #PIO0_SM0
    sm_ReadAddress.active(1)
    #preloads    
    sm_ReadAddress.put(RamDef.SRAM_DATA_BASE_23)   
    sm_ReadAddress.exec("pull()")
    sm_ReadAddress.exec("out(y,32)")
    #sm_ReadAddress.put(0x0FF)
    #sm_ReadAddress.exec("pull()")
    #sm_ReadAddress.exec("out(x,8)")

    #PIO0_SM1
    sm_GetWriteAddress.active(1)   
    #preloads
    sm_GetWriteAddress.put(RamDef.SRAM_DATA_BASE_23)  
    sm_GetWriteAddress.exec("pull()")
    sm_GetWriteAddress.exec("out(y,32)")
    
    #PIO_SM2
    sm_WriteRam.active(1)
    #clear IRQs for clean start up
    sm_WriteRam.exec("irq(clear,4)")
    sm_WriteRam.exec("irq(clear,5)")
    sm_WriteRam.exec("irq(clear,6)")

    #PIO0_SM3 - low-nibble forcer for 0x100+
    sm_set_lsn_data.active(1)
    sm_set_lsn_data.exec("set(x, 0x0F)")   #preload X = 0x0F, the value driven onto D0-D3
    sm_set_lsn_data.exec("irq(clear,7)")   #clean start
  


def dma_start():
    #**************************************************
    # DMA Setup for bus memory access, read and writes
    #**************************************************
    a=rp2.DMA()
    b=rp2.DMA()
    c=rp2.DMA()
    d=rp2.DMA()        

    dma_channels = f"MEM: {a},{b},{c},{d}"
    print(dma_channels," <-MUST be 2-3-4-5 !")
    if not all(str(i) in dma_channels for i in range(2, 6)):  #2,3,4,5
        return "fault"
 
    #DMA channel assignments
    DMA_ADDRESS = 2
    DMA_READ_DATA = 3     
    DMA_ADDRESS_COPY = 4
    DMA_WRITE_DATA = 5

    #uctypes structs for each channel
    dma_address = dma_d.DMA_CHANS[DMA_ADDRESS]   
    dma_read_data = dma_d.DMA_CHANS[DMA_READ_DATA]    
    dma_address_copy = dma_d.DMA_CHANS[DMA_ADDRESS_COPY]                     
    dma_write_data = dma_d.DMA_CHANS[DMA_WRITE_DATA]                   

    #------------------------
    # DMA 2 for address   DMA_ADDRESS
    #------------------------
    dma_address.READ_ADDR_REG =   0x50200000 + 0x020        # PIO0_SM0 RX buffer
    dma_address.WRITE_ADDR_REG =   0x50000000 + 0x0FC       # DMA3 SRC register  & trigger of DMA3
    dma_address.CTRL_REG.CHAIN_TO = DMA_ADDRESS             # no chain trigger
    dma_address.CTRL_REG.INCR_WRITE = 0
    dma_address.CTRL_REG.INCR_READ = 0
    dma_address.CTRL_REG.IRQ_QUIET = 1
    dma_address.CTRL_REG.TREQ_SEL =  4                    #dma_d.DREQ_PIO0_RX0  
    dma_address.CTRL_REG.DATA_SIZE = 2                    #32 bit move (address)
    dma_address.CTRL_REG.EN = 1
    dma_address.CTRL_REG.HIGH_PRIORITY = 1
    dma_address.TRANS_COUNT_REG_TRIG = 1                  #pre-trigger this DMA (will wait on DREQ)

    #-------------------------
    # DMA 3  read data
    #-------------------------
    dma_read_data.READ_ADDR_REG =  0x20042000           # written by DMA2  
    dma_read_data.WRITE_ADDR_REG = 0x50200000 + 0x010   # PIO0_SM0 TX Buffer
    dma_read_data.TRANS_COUNT_REG = 1
    dma_read_data.CTRL_REG.CHAIN_TO = DMA_ADDRESS       # retrigger DMA2 via chain
    dma_read_data.CTRL_REG.INCR_WRITE = 0
    dma_read_data.CTRL_REG.INCR_READ = 0
    dma_read_data.CTRL_REG.IRQ_QUIET = 1
    dma_read_data.CTRL_REG.TREQ_SEL =  0x3F    #none
    dma_read_data.CTRL_REG.DATA_SIZE = 0       #byte
    dma_read_data.CTRL_REG.HIGH_PRIORITY = 1
    dma_read_data.CTRL_REG.EN = 1

    #-------------------------
    # DMA 4 Address Copy DMA_ADDRESS_COPY
    #-------------------------
    dma_address_copy.READ_ADDR_REG =  0x50200000 + 0x024    #PIO0_SM1 RX Buffer  (write address)
    dma_address_copy.WRITE_ADDR_REG =  0x50000000 + 0x16C    #DMA5 Destination Reg & trigger 
    #dma_address_copy.TRANS_COUNT_REG = 1
    dma_address_copy.CTRL_REG.CHAIN_TO = DMA_ADDRESS_COPY     #none
    dma_address_copy.CTRL_REG.INCR_WRITE = 0
    dma_address_copy.CTRL_REG.INCR_READ = 0
    dma_address_copy.CTRL_REG.IRQ_QUIET = 1
    dma_address_copy.CTRL_REG.TREQ_SEL = 5       #PIO0_SM1 Rx 
    dma_address_copy.CTRL_REG.DATA_SIZE = 2      #32 bit address
    dma_address_copy.CTRL_REG.HIGH_PRIORITY = 1
    dma_address_copy.CTRL_REG.EN = 1
    dma_address_copy.TRANS_COUNT_REG_TRIG = 1    #pre trigger at start

    #----------------------
    # DMA 5 for write data
    #----------------------    
    dma_write_data.READ_ADDR_REG =  0x50200000 + 0x028    # data out of PIO0-SM2  RX (data pio) 
    dma_write_data.WRITE_ADDR_REG = 0x20040000  #uctypes.addressof(shadowRam)    # written by other dmas to point into sram
    dma_write_data.TRANS_COUNT_REG = 1 
    dma_write_data.CTRL_REG.CHAIN_TO = DMA_ADDRESS_COPY 
    dma_write_data.CTRL_REG.INCR_WRITE = 0
    dma_write_data.CTRL_REG.INCR_READ = 0
    dma_write_data.CTRL_REG.IRQ_QUIET = 1
    dma_write_data.CTRL_REG.TREQ_SEL = 6  #DREQ_PIO0_RX2  
    dma_write_data.CTRL_REG.DATA_SIZE = 0
    dma_write_data.CTRL_REG.HIGH_PRIORITY = 1
    dma_write_data.CTRL_REG.EN = 1
   
    return "ok"




def configure():
  
    if dma_start() != "ok":
        print("MEM: DMA setup failed")
        return "fault"

    pio_start()
    return "ok"


   
    
    