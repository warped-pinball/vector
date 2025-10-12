# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Ram intercept module - REVISION 5 - CADR version (Clock support)

    PIO0 and PIO2  and  DMA 2,3,4,5

    This module intercepts all read operations and sources the data from internal RP2350 ram
    All write operations are decoded and stored to internal RP2350 ram (writes are allowed to
    propagate on the main board to the standard ram also)

    Clock addresses (CADR in hardware) are also decoded and placed in prallele at the end of ram

    PIO#0:  Ram read and write operations,  uses SMs 4,5,6

    PIO#2:  Triggering for RAM and CLOCK, uses SMs: 9,10,11

    SM#8 reserved for use by micopython Wifi chip interface

"""
import Dma_Registers_RP2350 as dma_d
import machine
import rp2
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


# pointer and value to disable clock PIO (used in time.py)
PIO2_BASE = 0x50400000
INSTR_MEM_OFFSET = 0x048  # Offset to instruction memory in PIO
INSTR_INDEX = 5           # 6th instruction (0-based index)
DISABLE_CLOCK_DATA = 0xA042  #Mov y,y   1010 0000 0100 0010  = 0xA042
ENABLE_CLOCK_DATA = 0xC005   # IRQ(5)  1100 0000 0000 1001   = 0xC005
DISABLE_CLOCK_ADDRESS = PIO2_BASE + INSTR_MEM_OFFSET + (INSTR_INDEX * 4)


#
# Catch the memory VMA signal
#   SM#9, PIO2
#   JMP Pin is VMA_ADR (GPIO#13)
#
# @rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))
@rp2.asm_pio()
def CatchVMA():
    wrap_target()
    label("start_adr")
    
    wait(0, gpio, 13)         #wait for VMA+ADR to go active(low), assumme this hardware is set for total address validation   
    jmp(pin,"start_adr")      #check again - debounce

    irq(5)                     #this will keep sending irq5 while gpio is low, but thats ok. handled later in Pass_VMA_CADR
    wrap()


#
# CLOCK ADRESS (CADR)
#   SM#10,  PIO2
#   JMP Pin is CADR (GPIO#11)
#
# @rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))
@rp2.asm_pio()
def CatchCADR():
    wrap_target()
    label("start_cadr")
    
    wait(0, gpio, 11)           #wait for CADR to go active(low)
    jmp(pin,"start_cadr")       #confirm still active (debounce)
             
    irq(5)   #<<<<<<< point here for enable and disable clock interface <<<<<<<<<<
    wrap()


#
# Pass VMA or CADR on to next pio module
#   SM#11, PIO2
#
#   and wait for clock cycle ignoring future IRQs that can be false
#
#   this needs to happen in one place to lock out CADR when VMA is in process and vice versa
#
# @rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))
@rp2.asm_pio()
def Pass_VMA_CADR():
    wrap_target()
    
    wait(1, irq, 5)         #wait for signal from CADR or VMA (both use irq5)     
                            #send trigger IRQ (new stlye for rp2350) - VMA
    word(0xC41C)            #(1100 0100 0001 1100 ) = ( 0xC41C)   IRQ4 to PIO plus one (we are in PIO2 so up one goes to PIO0)   
    
    wait(1,gpio,1)  [6]     #wait for eClock HIGH
    wait(0,gpio,1)  [2]     #wait for eClock LOW
    irq(clear, 5)           #clear IRQ5 before looping back, will have been spammed
    wrap()


# PIO_PRG: Read Address
#
# SM#0, PIO0
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
@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.OUT_LOW), out_init=(rp2.PIO.IN_HIGH,) * 8, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def ReadAddress():
    label("start_adr")
    wrap_target()
    
    wait(1,irq,4)                       #new way for rp2350 - wait for IRQ4, this is the signal from PIO2  
    jmp(pin,"do_write")                 #pin is W/R (not R/W, has been inverted) 

    #READ Process, Get Address  
    mov(isr,y)             .side(0)     #copy 21 bit address msb to isr,ready to shift in 11 lsb from pins    
    in_(pins,5)            .side(0)     #read A8/9/10/11/12, set A_Select to 1  (WPC)
    nop()           [3]    .side(1)     #side set happens at begining of instruction      
    nop()           [3]    .side(1)
    in_(pins,8)            .side(1)     #read A0-7, set A_Select back to 0        
    push(noblock)   [3]    .side(0)     #send out address result for DMA   
    #delays @push and mov and out required to give DMAx2 time
  
    #READ Process, send data out to pins
    mov(osr,x)      [3]     .side(0)     #load all ones to osr from x   
    out(pindirs,8)  [3]     .side(2)     #pins to outputs (1=output), side set is data_dir output      
    #mov(pindirs,~null)     .side(2)      #new for rp2350 (save an instruction?)    

    nop() [3]               .side(2)  
    pull(noblock)           .side(2) 
    #pull(block)            .side(2)     #TX fifo -> OSR, getting 8 bits data from DMA transfer    
                                      #change to block to give DMA thim eit need dynamically instead of wait states in previous lines...
    out(pins,8)             .side(2)     #OSR -> Pins   


    #READ Process, wrap up   
    mov(osr,invert(x)) [3]  .side(2)   #invert to all zeroes
    wait(0, gpio, 1)   [3]  .side(2)     #wait for eclock to go LOW   
    out(pindirs,8)          .side(0)     #pins to inputs, and return data_dir to normal    OSR->pindirs    
    #mov(pindirs,null)  [1]  .side(0)   #new for rp2350

    jmp("start_adr")       .side(0)     #read done, back to the top

    #WRITE process
    label("do_write")    
    irq(5)          [3]             
    wait(1,gpio,1)  [3]                 #when eClock goes high
    wait(0,gpio,1)  [3]                 #wait for eClock to go low

    #jmp("start_adr")
    wrap() #for some reason wrap is not well behaved
    


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
# SM#2, PIO0
#
#   read data from pins
#   write data (to internal rp2 memory)
#
#   OUT: Data Pins
#
#  <<4>>
@rp2.asm_pio(out_init=(rp2.PIO.IN_HIGH,) * 8, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def WriteRam():
    
    wrap_target()    
    wait(1,irq,6)           #wait for IRQ6 and reset it    

    wait(0, gpio, 13)  [10] #wait for qclock to go Low      7->9
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
    sm_ReadAddress = rp2.StateMachine(
        0, ReadAddress, freq=150000000, set_base=machine.Pin(22), sideset_base=machine.Pin(27), out_base=machine.Pin(FIRST_DATA_PIN), in_base=machine.Pin(FIRST_ADR_PIN), jmp_pin=machine.Pin(WR_PIN)
    )

    #   PRELOAD: Y with 21 bit shadow ram base address
    #   SIDESET: A_Select
    #   IN: Address Pins
    sm_GetWriteAddress = rp2.StateMachine(1, GetWriteAddress, freq=150000000, sideset_base=machine.Pin(27), in_base=machine.Pin(FIRST_ADR_PIN))

    #   IN: Data Pins
    sm_WriteRam = rp2.StateMachine(2, WriteRam, freq=150000000, in_base=machine.Pin(FIRST_DATA_PIN), out_base=machine.Pin(FIRST_DATA_PIN))

    # VMA Catch
    sm_CatchVma = rp2.StateMachine(9, CatchVMA, freq=150000000, jmp_pin=machine.Pin(13))

    # CADR Catch (rtc clock address dedcode)
    # JMP pin is CADR GPIO#11
    sm_CatchCADR = rp2.StateMachine(10, CatchCADR, freq=150000000, jmp_pin=machine.Pin(11))

    # passes catch VMA or Catch CADR to next PIO module
    # JMP pin is CADR GPIO#11
    # receive IRQ5
    sm_Pass_VMA_CADR = rp2.StateMachine(11, Pass_VMA_CADR, freq=150000000, jmp_pin=machine.Pin(11))

    print("PIO Start")

    #
    # Trigger and Detection PIO (#2)
    #
    # PIO2 - three state machine in use (fourth used by system for wifi)
    sm_CatchCADR.active(1)
    sm_CatchVma.active(1)
    sm_Pass_VMA_CADR.active(1)
    sm_Pass_VMA_CADR.exec("irq(clear,5)")

    #
    # Ram access part (shadowram) PIO (#0)
    #
    # PIO0_SM0
    sm_ReadAddress.active(1)
    # preloads
    sm_ReadAddress.put(RamDef.SRAM_DATA_BASE_19)  # wpc
    sm_ReadAddress.exec("pull()")
    sm_ReadAddress.exec("out(y,32)")
    sm_ReadAddress.put(0x0FF)
    sm_ReadAddress.exec("pull()")
    sm_ReadAddress.exec("out(x,8)")

    # PIO0_SM1
    sm_GetWriteAddress.active(1)
    # preloads
    sm_GetWriteAddress.put(RamDef.SRAM_DATA_BASE_19)  # wpc
    sm_GetWriteAddress.exec("pull()")
    sm_GetWriteAddress.exec("out(y,32)")

    # PIO_SM2
    sm_WriteRam.active(1)
    # clear IRQs for clean start up
    sm_WriteRam.exec("irq(clear,4)")
    sm_WriteRam.exec("irq(clear,5)")
    sm_WriteRam.exec("irq(clear,6)")

    PIO0_BASE = 0x50200000
    PIO1_BASE = 0x50300000
    PIO2_BASE = 0x50400000


def dma_start():
    # **************************************************
    # DMA Setup for bus memory access, read and writes
    # **************************************************
    a = rp2.DMA()
    b = rp2.DMA()
    c = rp2.DMA()
    d = rp2.DMA()

    dma_channels = f"MEM: {a},{b},{c},{d}"
    print(dma_channels, " <-MUST be 2-3-4-5 !")
    if not all(str(i) in dma_channels for i in range(2, 6)):  # 2,3,4,5
        return "fault"

    # DMA channel assignments
    DMA_ADDRESS = 2
    DMA_READ_DATA = 3
    DMA_ADDRESS_COPY = 4
    DMA_WRITE_DATA = 5

    # uctypes structs for each channel
    dma_address = dma_d.DMA_CHANS[DMA_ADDRESS]
    dma_read_data = dma_d.DMA_CHANS[DMA_READ_DATA]
    dma_address_copy = dma_d.DMA_CHANS[DMA_ADDRESS_COPY]
    dma_write_data = dma_d.DMA_CHANS[DMA_WRITE_DATA]

    # ------------------------
    # DMA 2 for address   DMA_ADDRESS
    #------------------------
    dma_address.READ_ADDR_REG =   0x50200000 + 0x020        # PIO0_SM0 RX buffer
    dma_address.WRITE_ADDR_REG =   0x50000000 + 0x0FC       # DMA3 SRC register  & trigger of DMA3
    dma_address.CTRL_REG.CHAIN_TO = DMA_ADDRESS             # no chain trigger
    dma_address.CTRL_REG.INCR_WRITE = 0
    dma_address.CTRL_REG.INCR_READ = 0
    dma_address.CTRL_REG.IRQ_QUIET = 1
    dma_address.CTRL_REG.TREQ_SEL =  4           #dma_d.DREQ_PIO0_RX0  #wait on PIO0-SM1 RX
    dma_address.CTRL_REG.DATA_SIZE = 2                    #32 bit move (address)
    dma_address.CTRL_REG.EN = 1
    dma_address.CTRL_REG.HIGH_PRIORITY = 1
    dma_address.TRANS_COUNT_REG_TRIG = 1                  #pre-trigger this DMA (will wait on DREQ)

    # -------------------------
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

    # -------------------------
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

    # ----------------------
    # DMA 5 for write data
    #----------------------    
    dma_write_data.READ_ADDR_REG =  0x50200000 + 0x028    # data out of PIO0-SM2  RX (data pio) 
    dma_write_data.WRITE_ADDR_REG = 0x20040000  #uctypes.addressof(shadowRam)    # written by other dmas to point into sram
    dma_write_data.TRANS_COUNT_REG = 1 
    dma_write_data.CTRL_REG.CHAIN_TO = DMA_ADDRESS_COPY 
    dma_write_data.CTRL_REG.INCR_WRITE = 0
    dma_write_data.CTRL_REG.INCR_READ = 0
    dma_write_data.CTRL_REG.IRQ_QUIET = 1
    dma_write_data.CTRL_REG.TREQ_SEL = 6  # DREQ_PIO0_RX2
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
