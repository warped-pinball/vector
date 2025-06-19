# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
"""
Ram intercept module - REVISION 4

    PIO0,1 and DMA 2,3,4,5

    This module intercepts all read operations and sources the data from internal RP2040 ram
    All write operations are decoded and stored to internal RP2040 ram (writes are allowed to
    propagate on the main board to the standard ram also)
"""
import machine
import rp2
import Dma_Registers_RP2350 as dma_d
import Shadow_Ram_Definitions as RamDef
   
# I/O Defs, PCB Rev2
DATA_DIR_PIN = 28
A_SELECT_PIN = 27
LED_PIN = 26
SWITCH_PIN = 22
WR_PIN = 12
VMA_ADR_PIN = 13
FIRST_ADR_PIN = 6
FIRST_DATA_PIN = 14



#PIO-PRG: CatchCADR - - this one designed to be in PIO#1,  real time clock interface in PIO#2
#
#   JMP Pin Must be CADR (#11)
#       
@rp2.asm_pio()  
def CatchCADR():
    wrap_target()
    label("start_cadr")
    
    wait(0, gpio, 11)           #wait for CADR to go active(low)
    jmp (pin,"start_cadr")      #confirm still active (debounce)
             
    # word(0xC41C)                # (1100 0100 0001 1100 ) = ( 0xC41C)   IRQ4 to PIO plus one (to pio 2) 

    wait(1,gpio,1)              #wait for eClock HIGH
    wait(0,gpio,1)              #wait for eClock LOW
    wrap()




#PIO-PRG: CatchVMA - - this one designed to be in PIO#1, ram memory interface in PIO#0, and now real time clock interface in PIO#2
#
#   JMP Pin Must be VMA_ADR (#13)
#   Set Base #22 (switch, used to signal PIO0_SM0)
#    
@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)  
def CatchVMA():
    wrap_target()
    label("start_adr")
    
    wait(0, gpio, 13)       #wait for VMA+ADR to go active(low), assumme this hardware is set for total address validation   
    jmp (pin,"start_adr")   #confirm still active (debounce)

    # in the past used a gpio to singal pio1 - now can use IRQ in RP2350?
    set(pins,1)    [4]     #rpio22 signal other pio to start - delay happens after pin state changes
    set(pins,0)    [4]        
    #word(0xC40C)     # (1100 0100 0000 1100 ) = ( 0xC40C)   IRQ4 to PIO back one (to pio 0)   irq(4)[4]relative index=-1

    wait(1,gpio,1)  [6]    #wait for eClock HIGH
    wait(0,gpio,1)  [4]    #wait for eClock LOW
    wrap()





    
# PIO_PRG: Read Address
#
#   wait for valid adr / Vma signal
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
#   <<19>>
@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_HIGH,rp2.PIO.OUT_LOW), out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT) 
def ReadAddress():
       
    label("start_adr")    
    wrap_target()
    wait(1,gpio,22)                     #wait for signal from PIO1, dont loop back here until eclock is high
    #wait(1,irq,4) [2]
  
    jmp(pin,"do_write")                 #pin is W/R (not R/W, has been inverted) 

    #READ Process, Get Address  
    mov(isr,y)             .side(0)     #copy 21 bit address msb to isr,ready to shift in 11 lsb from pins    
    #in_(pins,3)            .side(0)    #read A8/9/10, set A_Select to 1
    in_(pins,5)            .side(0)     #read A8/9/10/11/12, set A_Select to 1  (WPC)
    nop()           [3]    .side(1)     #side set happens at begining of instruction                <<< -add delay here   
    nop()           [3]    .side(1)
    in_(pins,8)            .side(1)     #read A0-7, set A_Select back to 0        
    push(noblock)   [3]    .side(0)     #send out address result for DMA   

    #delays @push and mov and out required to give DMAx2 time?  why is it so slow... ?
  
    #READ Process, send data out to pins
    mov(osr,x)      [3]     .side(0)     #load all ones to osr from x   
    out(pindirs,8)  [3]     .side(2)     #pins to outputs (1=output), side set is data_dir output      
    #mov(pindirs,~null)    .side(2)   #new for rp2350

    nop() [3]              .side(2)  
   

    pull(noblock)          .side(2) 
    #pull(block)          .side(2)     #TX fifo -> OSR, getting 8 bits data from DMA transfer    
                                      #change to block to give DMA thim eit need dynamically instead of wait states in previous lines...
    out(pins,8)          .side(2)     #OSR -> Pins   


    #READ Process, wrap up   
    mov(osr,invert(x)) [3]   .side(2)     #invert to all zeroes
    wait(0, gpio, 1)   [3] .side(2)     #wait for eclock to go LOW   
    out(pindirs,8)         .side(0)     #pins to inputs, and return data_dir to normal    OSR->pindirs    
    #mov(pindirs,null)  [1]  .side(0)      #new for rp2350

    jmp("start_adr")       .side(0)     #read done, back to the top

    #WRITE process
    label("do_write")    
    irq(5)      [3]             
    wait(1,gpio,1)  [3]                 #when eClock goes high
    wait(0,gpio,1)  [3]                 #wait for eClock to go low
    wrap() 
    

    
# PIO_PRG: Get Address for Write Cycle
#
#     read in address (with fixed 21 bits)
#     push address out and launch next pio prg via IRQ
#
#     PRELOAD: Y with 21 bit shadow ram base address
#
#     SIDESET: A_Select
#     IN: Address Pins
#
#     <<7>>
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW)
def GetWriteAddress():
    wrap_target()
    wait (1,irq,5)         
    
    #WRITE Process, Get Address  
    mov(isr,y)             .side(0)     #copy 21 bit address msb to isr,ready to shift in 11 lsb from pins    
    in_(pins,5)            .side(0)     #read A8/9/10/11/12, set A_Select to 1  (WPC)
    nop()              [7] .side(1)    
    in_(pins,8)            .side(1)     #read A0-7, set A_Select back to 0        
    push(noblock)          .side(0)     #send out address result for DMA    
    irq(6)                              #start write ram pio
    wrap()
  
  
# PIO_PRG : Data write
#
#   read data from pins
#   write data (to internal rp2 memory) 
#
#   OUT: Data Pins
#
#  <<4>>
@rp2.asm_pio (out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT  ) 
def WriteRam():
    
    wrap_target()    
    wait(1,irq,6)           #wait for IRQ6 and reset it    

    wait(0, gpio, 13)  [10]  #wait for qclock to go Low      7->9
    nop()              [9]      

    in_(pins,8)             #read all 8 data in one go      
    push(noblock)           #push out data byte, picked up by DMA    

    wrap()
    
 
 
def pio_start():

    gpio_1 = machine.Pin(1, machine.Pin.IN)
    gpio_13 = machine.Pin(13, machine.Pin.IN)
    gpio_22 = machine.Pin(22, machine.Pin.OUT)
    gpio_rw = machine.Pin(WR_PIN, machine.Pin.IN)  

    gpio_led = machine.Pin(26, machine.Pin.OUT)

    for pin_num in range(6, 14):  # range goes from 6 to 13
        machine.Pin(pin_num, machine.Pin.IN)

    #   PRELOAD: y with 21 bit shadow ram base address
    #   PRELOAD: x with all ones for use in pin data direction
    #   SIDESET: A_select and Data_Dir
    #   IN: Address Pins
    #   OUT: Data Pins
    sm_ReadAddress = rp2.StateMachine(0, ReadAddress, freq=150000000, set_base=machine.Pin(22), sideset_base=machine.Pin(27), out_base=machine.Pin(FIRST_DATA_PIN) ,in_base=machine.Pin(FIRST_ADR_PIN), jmp_pin=machine.Pin(WR_PIN))  
   
    #   PRELOAD: Y with 21 bit shadow ram base addres
    #   SIDESET: A_Select
    #   IN: Address Pins
    sm_GetWriteAddress = rp2.StateMachine(1, GetWriteAddress, freq=150000000, sideset_base=machine.Pin(27) ,in_base=machine.Pin(FIRST_ADR_PIN))
    
    #   IN: Data Pins
    sm_WriteRam = rp2.StateMachine(2, WriteRam, freq=150000000, in_base=machine.Pin(FIRST_DATA_PIN), out_base=machine.Pin(FIRST_DATA_PIN)  )
    #sm_WriteRam = rp2.StateMachine(2, WriteRam, freq=125000000, in_base=machine.Pin(FIRST_DATA_PIN), out_base=machine.Pin(FIRST_DATA_PIN) , sideset_base=machine.Pin(26) )   #side set for testing

    #   IN: Data Pins
    sm_CatchVma = rp2.StateMachine(6, CatchVMA, freq=150000000, jmp_pin=machine.Pin(13), set_base=machine.Pin(22)  )
    #sm_CatchVma = rp2.StateMachine(6, CatchVMA, freq=150000000, jmp_pin=machine.Pin(13), set_base=machine.Pin(22), sideset_base=26  )  #side set for testing

    #   catch CADR the rtc clock address dedcode
    #sm_CatchCADR = rp2.StateMachine(9, CatchCADR, freq=125000000, jmp_pin=machine.Pin(11) )


    print("PIO Start")
    #sm_CatchCADR.active(1)
    sm_CatchVma.active(1)

    #PIO0_SM0
    sm_ReadAddress.active(1)

    #preloads    
    sm_ReadAddress.put(RamDef.SRAM_DATA_BASE_19)   #wpc
    sm_ReadAddress.exec("pull()")
    sm_ReadAddress.exec("out(y,32)")
    sm_ReadAddress.put(0x0FF )
    sm_ReadAddress.exec("pull()")
    sm_ReadAddress.exec("out(x,8)")

    
    #PIO0_SM1
    sm_GetWriteAddress.active(1)   

    #preloads
    sm_GetWriteAddress.put(RamDef.SRAM_DATA_BASE_19)  #wpc
    sm_GetWriteAddress.exec("pull()")
    sm_GetWriteAddress.exec("out(y,32)")
    
    #PIO_SM2
    sm_WriteRam.active(1)

    #clear IRQs for clean start up
    sm_WriteRam.exec("irq(clear,4)")
    sm_WriteRam.exec("irq(clear,5)")
    sm_WriteRam.exec("irq(clear,6)")
       

def dma_start():
    #**************************************************
    # DMA Setup for bus memory access, read and writes
    #**************************************************
    a=rp2.DMA()
    b=rp2.DMA()
    c=rp2.DMA()
    d=rp2.DMA()
    e=rp2.DMA()    

    dma_channels = f"MEM: {a},{b},{c},{d},{e}"
    print(dma_channels," <-MUST be 2-3-4-5-6 !")
    if not all(str(i) in dma_channels for i in range(2, 7)):  #2,3,4,5,6
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
    dma_address.READ_ADDR_REG =   0x50200000 + 0x020      # PIO0_SM0 RX buffer
    dma_address.WRITE_ADDR_REG =   0x50000000 + 0x0FC      # DMA3 SRC register  & trigger of DMA3
    dma_address.CTRL_REG.CHAIN_TO = DMA_ADDRESS           # no chain trigger
    dma_address.CTRL_REG.INCR_WRITE = 0
    dma_address.CTRL_REG.INCR_READ = 0
    dma_address.CTRL_REG.IRQ_QUIET = 1
    dma_address.CTRL_REG.TREQ_SEL =  4           #dma_d.DREQ_PIO0_RX0  #wait on PIO0-SM1 RX
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
    
    if dma_start() is not "ok":
        print("MEM: DMA setup failed")
        return "fault"
    
    pio_start()   
    return "ok"


   
    
    