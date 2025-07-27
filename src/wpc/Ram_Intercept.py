# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
"""
Ram intercept module - REVISION 5 - CADR version

    PIO0,1,2  and  DMA 2,3,4,5

    This module intercepts all read operations and sources the data from internal RP2350 ram
    All write operations are decoded and stored to internal RP2350 ram (writes are allowed to
    propagate on the main board to the standard ram also)

    Clock addresses (CADR in hardware) are also decoded and special clock PIO handles
    read and write operations to shadow the RTC registers in RP2350 ram


    PIO#0:  Clock read a write operations, uses SMs 0,1,2,3
    PIO#1:  Ram read and write operations,  uses SMs 4,5,6
    PIO#2:  Triggering for RAM and CLOCK, uses SMs: 9,10,11
    SM#8 reserved for use by micopython Wifi chip interface

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





#
#Catch the memory VMA signal
#   SM#9, PIO2
#   JMP Pin is VMA_ADR (GPIO#13) 
#    
#@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))  
@rp2.asm_pio()  
def CatchVMA():
    wrap_target()
    label("start_adr")
    
    wait(0, gpio, 13)         #wait for VMA+ADR to go active(low), assumme this hardware is set for total address validation   
    jmp (pin,"start_adr")     #check again - debounce

    irq(5)                     #this will keep sending irq5 while gpio is low, but thats ok. handled later in Pass_VMA_CADR
    wrap()

#
#CLOCK ADRESS (CADR)
#   SM#10,  PIO2
#   JMP Pin is CADR (GPIO#11)
#
#@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))  
@rp2.asm_pio()  
def CatchCADR():
    wrap_target()
    label("start_cadr")
    
    wait(0, gpio, 11)           #wait for CADR to go active(low)
    jmp (pin,"start_cadr")      #confirm still active (debounce)
             
    irq(5)   
    wrap()


#
#Pass VMA or CADR on to next pio module
#   SM#11, PIO2
#
#   pass irq signal to correct VMA OR CADR
#   and wait for clock cycle ignoring future IRQs that can be false
#
#   this needs to happen in one place to lock out CADR when VMA is in process and vice versa
#
#   pin for JMP is CADR (GPIO#11)
#
#@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW))  
@rp2.asm_pio()  
def Pass_VMA_CADR():
    wrap_target()
    
    wait(1, irq, 5)           #wait for signal from CADR or VMA (both use irq5)   
    jmp(pin, "not_cadr_trigger")   

    #send trigger IRQ (new style for RP2350) - CADR 
    word(0xC40C)  #.side(1)     # (1100 0100 0000 1100 ) = ( 0xC40C)   IRQ4 to PIO minus one (we are in PIO2 so back one is PIO1)   
    jmp ("vma_cadr_done")      


    label("not_cadr_trigger") 
    nop()    
    #send trigger IRQ (new stlye for rp2350) - VMA
    word(0xC41C)      # (1100 0100 0001 1100 ) = ( 0xC41C)   IRQ4 to PIO plus one (we are in PIO2 so up one goes to PIO0)   
    #word(0xC40C) 

    label("vma_cadr_done")
    wait(1,gpio,1)  [6]   #wait for eClock HIGH
    wait(0,gpio,1)  [1]   #wait for eClock LOW
    irq(clear, 5)  # .side(0)   #clear IRQ5 before looping back, will have been spammed
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
@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_HIGH,rp2.PIO.OUT_LOW), out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT) 
def ReadAddress():

    nop() .side(0)  #why is this required!!! crazy town

    label("start_adr")    
    wrap_target()
    
    wait(1,irq,4)                       #new way for rp2350 - wait for IRQ4, this is the signal from PIO2  
    jmp(pin,"do_write")                 #pin is W/R (not R/W, has been inverted) 

    #READ Process, Get Address  
    mov(isr,y)             .side(0)     #copy 21 bit address msb to isr,ready to shift in 11 lsb from pins    
    in_(pins,5)            .side(0)     #read A8/9/10/11/12, set A_Select to 1  (WPC)
    nop()           [3]    .side(1)     #side set happens at begining of instruction      
    #nop()           [3]    .side(1)
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
@rp2.asm_pio (out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT  ) 
def WriteRam():
    
    wrap_target()    
    wait(1,irq,6)           #wait for IRQ6 and reset it    

    wait(0, gpio, 13)  [10]  #wait for qclock to go Low      7->9
    nop()              [9]      

    in_(pins,8)             #read all 8 data in one go      
    push(noblock)           #push out data byte, picked up by DMA    

    wrap()
    
 










# CLOCK step 1 - signaled from PIO2
#
# SM#4, PIO1
#  JMP pin = W/R  gpio12
#  in pin - address line 0
#
# side set is LED:Aselect
#
#@rp2.asm_pio( sideset_init=(rp2.PIO.OUT_LOW) ) 
@rp2.asm_pio( )
def CLOCK_DetectOperation():

    label("clk_start")    
    #wrap_target()
  
    wait(1,irq,4)           #this is the signal from PIO1

    nop() [3]       #.side(1)      #set A_Select

    mov (isr,null)
    in_ (pins,1)            #read address line 0
    mov (x,isr) [3] #.side(0)    #store address line 0 in X  <<need at least 3 delay for A_Select, one more would probably be good!

    #mov (x,null)  #alternate to 3 lines above - untested
    #mov (x,pins)    

    jmp(pin, "clk_do_write")    # jump based on W/R - jump on 1 which is WRITE
 
    jmp(not_x,"clk_start") #read offset, do nothing

    #trigger data read
    irq(5)  
    jmp("clk_start")

    #write section
    label("clk_do_write")
    jmp (not_x,"write_offset")
    
    #trigger write to Data
    irq(7)  
    jmp("clk_start")
  
    label("write_offset")
    irq(6)      #trigger write to address offset(index)
    
    #wrap()

    #write data    (adr=1  r/w=0)        
    #write offsets (adr=0  r/w=0)
    #read data     (adr=1, r/w=1)



#CLOCK write the address offset (index)
#
# SM#5, PIO1
#
@rp2.asm_pio() 
def CLOCK_WriteIndex():
    wrap_target()
    wait(1,irq,6)

    #READ Process, Get Address  
    mov(isr,y)                          #copy 26 bit address msb to isr,ready to shift in 6 lsb from DATA pins    
    wait(1, gpio, 11)  [2]              #wait for CADR to go Low    

    in_(pins,6)                         #read 6 data pins as addresses (CLOCK WPC)          
    push(noblock)                       #push out entire address, picked up by DMA6  

    wrap()


#CLOCK Write Data
#
# SM#6, PIO1
#
@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW)) 
def CLOCK_WriteData():

    wrap_target()
    wait(1,irq,7)

    wait(1, gpio, 11)  [2]          #wait for CADR (Qclock) to go Low    
    in_(pins,8)                     #read all 8 data in one go      
    push(noblock)                   #push out data byte, picked up by DMA8    

    wrap()


#CLOCK Read Data
#
# SM#7, PIO1
#
@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_LOW), out_init= (rp2.PIO.IN_HIGH,)*8,  out_shiftdir=rp2.PIO.SHIFT_RIGHT) 
def CLOCK_ReadData():
    wrap_target()

    wait(1,irq,5)
    push(noblock)   [3]                 #trigger DMA with push (data does not matter)
  
    nop()           [7]     .side(0)  

    #READ Process, send data out to pins
    mov(osr,x)      [7]     .side(0)     #load all ones to osr from x   
    out(pindirs,8)  [7]     .side(1)     #pins to outputs (1=output), side set is data_dir output      
    #mov(pindirs,~null)     .side(1)      #new for rp2350 (save an instruction?)
      
    pull(noblock)           .side(1) 
    #pull(block)            .side(1)     #TX fifo -> OSR, getting 8 bits data from DMA transfer    
                                         #change to block to give DMA thim eit need dynamically instead of wait states in previous lines...
    out(pins,8)             .side(1)     #OSR -> Pins   

    #READ data, wrap up   
   
    wait(0, gpio, 1)    [2]  .side(1)    #wait for E clock to go low
    mov(osr,invert(x))       .side(1)    #invert to all zeroes
    out(pindirs,8)           .side(0)    #pins to inputs, and return data_dir to normal    OSR->pindirs    
    #mov(pindirs,null)  [1]  .side(0)   #new for rp2350

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
       
    #   PRELOAD: Y with 21 bit shadow ram base address
    #   SIDESET: A_Select
    #   IN: Address Pins
    sm_GetWriteAddress = rp2.StateMachine(1, GetWriteAddress, freq=150000000, sideset_base=machine.Pin(27) ,in_base=machine.Pin(FIRST_ADR_PIN))
    
    #   IN: Data Pins
    sm_WriteRam = rp2.StateMachine(2, WriteRam, freq=150000000, in_base=machine.Pin(FIRST_DATA_PIN), out_base=machine.Pin(FIRST_DATA_PIN)  )
    #sm_WriteRam = rp2.StateMachine(2, WriteRam, freq=125000000, in_base=machine.Pin(FIRST_DATA_PIN), out_base=machine.Pin(FIRST_DATA_PIN) , sideset_base=machine.Pin(26) )   #side set for testing    





    #VMA Catch SM
    sm_CatchVma = rp2.StateMachine(9, CatchVMA, freq=150000000, jmp_pin=machine.Pin(13) )  
    #sm_CatchVma = rp2.StateMachine(9, CatchVMA, freq=150000000, jmp_pin=machine.Pin(13),  sideset_base=machine.Pin(26)  )  #side set for test
  
    # CADR Catch (rtc clock address dedcode)
    # JMP pin is CADR GPIO#11
    sm_CatchCADR = rp2.StateMachine(10, CatchCADR, freq=150000000, jmp_pin=machine.Pin(11) ) 
    #sm_CatchCADR = rp2.StateMachine(10, CatchCADR, freq=150000000, jmp_pin=machine.Pin(11),  sideset_base=machine.Pin(26) )  #side set for test

    # passes catch VMA or Catch CADR to next PIO module
    # JMP pin is CADR GPIO#11
    # receive IRQ5
    sm_Pass_VMA_CADR = rp2.StateMachine(11, Pass_VMA_CADR, freq=150000000, jmp_pin=machine.Pin(11))#, sideset_base=machine.Pin(27) )  
    #sm_Pass_VMA_CADR = rp2.StateMachine(11, Pass_VMA_CADR, freq=150000000, jmp_pin=machine.Pin(11), sideset_base=machine.Pin(26)  )  #side set for test
    
    

    #
    # Start up all CLOCK dedicated SMs in PIO1
    #
    
    # aselect is side set
    # jmp pin is W/R
    #sm_Clock_DetectOperation = rp2.StateMachine(4, CLOCK_DetectOperation, freq=150000000, jmp_pin=machine.Pin(WR_PIN), in_base=machine.Pin(6), sideset_base=machine.Pin(27) )   
    sm_Clock_DetectOperation = rp2.StateMachine(4, CLOCK_DetectOperation, freq=150000000, jmp_pin=machine.Pin(WR_PIN), in_base=machine.Pin(6) )   


    '''
    
    #CLOCK_DetectOperation
    #in base is data lines
    #side set for test only
    #jmp pin on CADR (11)
    #diag   sm_Clock_WriteIndex = rp2.StateMachine(5, CLOCK_WriteIndex, freq=150000000, jmp_pin=machine.Pin(11) ,sideset_base=machine.Pin(26), in_base=machine.Pin(14) )   
    sm_Clock_WriteIndex = rp2.StateMachine(5, CLOCK_WriteIndex, freq=150000000, jmp_pin=machine.Pin(11), in_base=machine.Pin(14) )   
    

    #diag  sm_Clock_WriteData = rp2.StateMachine(6, CLOCK_WriteData, freq=150000000, jmp_pin=machine.Pin(11) ,sideset_base=machine.Pin(26), in_base=machine.Pin(14)  )   
    sm_Clock_WriteData = rp2.StateMachine(6, CLOCK_WriteData, freq=150000000, jmp_pin=machine.Pin(11) ,in_base=machine.Pin(14)  )   
    
    #diag??    sm_Clock_ReadData = rp2.StateMachine(7, CLOCK_ReadData, freq=150000000, sideset_base=machine.Pin(28) , out_base=machine.Pin(FIRST_DATA_PIN)) 
    sm_Clock_ReadData = rp2.StateMachine(7, CLOCK_ReadData, freq=150000000, sideset_base=machine.Pin(28) , out_base=machine.Pin(FIRST_DATA_PIN))   
    '''
    

    

    print("PIO Start")

    #
    #Trigger and Detection PIO (#2)
    #
    #PIO2 - three state machine in use (fourth used by system for wifi)
    sm_CatchCADR.active(1)
    sm_CatchVma.active(1)
    sm_Pass_VMA_CADR.active(1)
    #sm_Pass_VMA_CADR.exec("irq(clear,5)")

        
    #
    #Ram access part (shadowram) PIO (#0)
    #
    #PIO0_SM0
    sm_ReadAddress.active(1)
    #preloads    
    sm_ReadAddress.put(RamDef.SRAM_DATA_BASE_19)   #wpc
    sm_ReadAddress.exec("pull()")
    sm_ReadAddress.exec("out(y,32)")
    sm_ReadAddress.put(0x0FF)
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
       
    
    #
    #Clock (CADR) section PIO (#1)
    #

    reg_addr = 0x504000CC
    current_value = machine.mem32[reg_addr]
    machine.mem32[reg_addr] = current_value | (1 << 30)
    print(f"Set bit 30: 0x{reg_addr:08X} = {hex(machine.mem32[reg_addr])}")


    sm_Clock_DetectOperation.active(1)



    '''
    sm_Clock_WriteIndex.active(1)
    sm_Clock_WriteIndex.put(RamDef.CLOCKRAM_DATA_BASE_26)     #clock storage in pico ram (26bits) room for 64 locations, 6 more address bits
    sm_Clock_WriteIndex.exec("pull()")
    sm_Clock_WriteIndex.exec("out(y,32)")

    sm_Clock_WriteData.active(1)

    sm_Clock_ReadData.active(1)
    sm_Clock_ReadData.put(0x0FF )
    sm_Clock_ReadData.exec("pull()")
    sm_Clock_ReadData.exec("out(x,8)")

    '''


    PIO0_BASE = 0x50200000
    PIO1_BASE = 0x50300000
    PIO2_BASE = 0x50400000  

    #SM0_SHIFTCTRL_OFFSET = 0xD0 
    #machine.mem32[PIO1_BASE + SM0_SHIFTCTRL_OFFSET] =  machine.mem32[PIO1_BASE + SM0_SHIFTCTRL_OFFSET] |0x01






def dma_start_clock():
    #************************************************
    # DMA Setup for RTC   access, read and writes
    #************************************************
    a=rp2.DMA()
    b=rp2.DMA()
    c=rp2.DMA()
    d=rp2.DMA()        
    e=rp2.DMA()

    dma_channels = f"MEM: {a},{b},{c},{d},{e}"
    print(dma_channels," <-MUST be 6-7-8-9-10 !")
    if not all(str(i) in dma_channels for i in range(6, 11)):  #6,7,8,9,10
        return "fault"
 
    #DMA channel assignments
    DMA_WRITEOFFS_1 = 6
    DMA_WRITEOFFS_2 = 7     
    DMA_WRITEDATA = 8
    DMA_TRIGREAD = 9
    DMA_READDATA = 10
   
    #uctypes structs for each channel
    dma_writeoff_1 = dma_d.DMA_CHANS[DMA_WRITEOFFS_1]   
    dma_writeoff_2 = dma_d.DMA_CHANS[DMA_WRITEOFFS_2]    
    dma_writedata = dma_d.DMA_CHANS[DMA_WRITEDATA]         
    dma_triggerread = dma_d.DMA_CHANS[DMA_TRIGREAD]
    dma_readdata = dma_d.DMA_CHANS[DMA_READDATA]                     
             

    #------------------------
    # DMA 6   DMA_WRITEOFFS_1
    #------------------------
    dma_writeoff_1.READ_ADDR_REG =    0x50300000 + 0x024    # PIO1_SM1 RX buffer
    dma_writeoff_1.WRITE_ADDR_REG =   0x50000000 + 0x204    # DMA8 write address
    dma_writeoff_1.CTRL_REG.CHAIN_TO = DMA_WRITEOFFS_2      # chain on to copy the address on with DMA 7
    dma_writeoff_1.CTRL_REG.INCR_WRITE = 0
    dma_writeoff_1.CTRL_REG.INCR_READ = 0
    dma_writeoff_1.CTRL_REG.IRQ_QUIET = 1
    dma_writeoff_1.CTRL_REG.TREQ_SEL =  13                  #dma_d.DREQ   PIO1_RX1   
    dma_writeoff_1.CTRL_REG.DATA_SIZE = 2                   #32 bit move (address)
    dma_writeoff_1.CTRL_REG.EN = 1
    dma_writeoff_1.CTRL_REG.HIGH_PRIORITY = 1
    dma_writeoff_1.TRANS_COUNT_REG_TRIG = 0x10000001        #pre-trigger this DMA (will wait on DREQ), turn on auto trigger

    #------------------------
    # DMA 7   DMA_WRITEOFFS_2
    #------------------------
    dma_writeoff_2.READ_ADDR_REG =    0x50000000 + 0x204    # read from DMA8 write address
    dma_writeoff_2.WRITE_ADDR_REG =   0x50000000 + 0x280    # write to DMA10 read address   
    dma_writeoff_2.CTRL_REG.CHAIN_TO = DMA_WRITEOFFS_2            
    dma_writeoff_2.CTRL_REG.INCR_WRITE = 0
    dma_writeoff_2.CTRL_REG.INCR_READ = 0
    dma_writeoff_2.CTRL_REG.IRQ_QUIET = 1
    dma_writeoff_2.CTRL_REG.TREQ_SEL =  0x3F
    dma_writeoff_2.CTRL_REG.DATA_SIZE = 2                  
    dma_writeoff_2.CTRL_REG.EN = 1
    dma_writeoff_2.CTRL_REG.HIGH_PRIORITY = 1
    dma_writeoff_2.TRANS_COUNT_REG = 0x0000001 

    #------------------------
    # DMA 8   DMA_WRITEDATA
    #------------------------
    dma_writedata.READ_ADDR_REG =    0x50300000 + 0x028    # read from PIO1_SM2 Rx buffer
    dma_writedata.WRITE_ADDR_REG =   0x2007ffff            # write to register is written by DMA6
    dma_writedata.CTRL_REG.CHAIN_TO = DMA_WRITEDATA            
    dma_writedata.CTRL_REG.INCR_WRITE = 0
    dma_writedata.CTRL_REG.INCR_READ = 0
    dma_writedata.CTRL_REG.IRQ_QUIET = 1
    dma_writedata.CTRL_REG.TREQ_SEL =  14
    dma_writedata.CTRL_REG.DATA_SIZE = 0    #byte only                  
    dma_writedata.CTRL_REG.EN = 1
    dma_writedata.CTRL_REG.HIGH_PRIORITY = 1
    dma_writedata.TRANS_COUNT_REG_TRIG =  0x10000001    # auto trigger every DREQ (output from PIO1_sm2)

    #--------------------------
    # DMA 9   DMA_READDATATRIG
    #--------------------------
    #take the dummy byte from PIO1_SM3 and throw away. Trigger DMA10 to move Ram data byte into PIO1_SM3
    dma_triggerread.READ_ADDR_REG =    0x50300000 + 0x02C    # PIO1_SM3 RX buffer
    dma_triggerread.WRITE_ADDR_REG =   0x50000000 + 0x3C0    # write this to harmless place - - -   DMA channel 15 read address
    dma_triggerread.CTRL_REG.CHAIN_TO = DMA_READDATA      # chain on to DMA 10
    dma_triggerread.CTRL_REG.INCR_WRITE = 0
    dma_triggerread.CTRL_REG.INCR_READ = 0
    dma_triggerread.CTRL_REG.IRQ_QUIET = 1
    dma_triggerread.CTRL_REG.TREQ_SEL =  15                  #dma_d.DREQ   PIO1_RX1   
    dma_triggerread.CTRL_REG.DATA_SIZE = 2                   #32 bit move
    dma_triggerread.CTRL_REG.EN = 1
    dma_triggerread.CTRL_REG.HIGH_PRIORITY = 1
    dma_triggerread.TRANS_COUNT_REG_TRIG = 0x10000001        #pre-trigger this DMA (will wait on DREQ), turn on auto trigger

    #--------------------------
    # DMA 10   DMA_READDATA
    #--------------------------
    dma_readdata.READ_ADDR_REG =    0x2007ffff          # filled in from writeoffset_2, start with harmless address
    dma_readdata.WRITE_ADDR_REG =   0x50300000 + 0x1C   # PIO1_SM3 Tx
    dma_readdata.CTRL_REG.CHAIN_TO = DMA_READDATA            
    dma_readdata.CTRL_REG.INCR_WRITE = 0
    dma_readdata.CTRL_REG.INCR_READ = 0
    dma_readdata.CTRL_REG.IRQ_QUIET = 1
    dma_readdata.CTRL_REG.TREQ_SEL =  0x3F
    dma_readdata.CTRL_REG.DATA_SIZE = 0        #byte only                  
    dma_readdata.CTRL_REG.EN = 1
    dma_readdata.CTRL_REG.HIGH_PRIORITY = 1
    dma_readdata.TRANS_COUNT_REG =  0x00000001    # auto trigger every DREQ (output from PIO1_sm2)












    return "ok"






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
    if not all(str(i) in dma_channels for i in range(2, 6)):  #2,3,4,5,6
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
    
    if dma_start() != "ok":
        print("MEM: DMA setup failed")
        return "fault"
    
    if dma_start_clock() != "ok":
        print("MEM: DMA for RTC setup failed")
        return "fault"
    
    pio_start()   
    return "ok"


   
    
    