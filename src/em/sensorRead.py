# This file is part of the Warped Pinball SYS_EM_Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Sensor Read
    setup analog threshold PWMs
    PIO to gather sensor data on SPI
    DMA to copy sensor data to bulk ram store (8k)
    sample rate 1mS
"""

import rp2
import machine
import Dma_Registers_RP2350 as dma_d
from machine import Pin
import time
import SharedState as S

import uctypes
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH

from logger import logger_instance
log = logger_instance

# Pin assignments
PIO_MISO_PIN = 12  
PIO_SCK_PIN  = 10  
PIO_CS_PIN   = 13  # CS (or Load...)
ANALOG_HI_GPIO = 19
ANALOG_LOW_GPIO = 18

#MISO data pin init
machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_DOWN)

#analog thresholds PWMs
hiPwm = machine.PWM(machine.Pin(19))
lowPwm = machine.PWM(machine.Pin(18))


@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, set_init=rp2.PIO.OUT_HIGH) 
def spi_master_16bit():
    set(x, 15)                          #init first transfer bit length

    wrap_target()
    set(pins, 1)             [7]        #set load pin high

    label("bitloop")         

    nop()                    .side(0)  [1]
    in_(pins, 1)             .side(0)  [1]  #data in pin changes on rising edge of clock
    nop()                    .side(1)   
    nop()                    .side(1)  [1]
    
    jmp(x_dec, "bitloop")    .side(0)

    set(pins, 0)             .side(0)
    set(x, 15)               .side(0) #bit length (-1)

    push(noblock)

    #Delay loop for pause between reads - set up for 1mS cycle
    set(y, 2)   # set(y, 19)
    label("delay")
    nop()                   [1]
    jmp(y_dec, "delay")     [7]

    #nop()                   .side(0)   [3]
    wrap()








@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, set_init=rp2.PIO.OUT_HIGH) 
def spi_master_16bit_invert():
   
    wrap_target()

    mov(isr,invert(null))

    set(x, 7)                          #init first transfer bit length
    set(pins, 1)             [7]        #set load pin high

    label("MSbitloop")         
    nop()                    .side(0)  [1]
    in_(pins, 1)             .side(0)  [1]  #data in pin changes on rising edge of clock
    nop()                    .side(1)   
    nop()                    .side(1)  [1]    
    jmp(x_dec, "MSbitloop")    .side(0)

    mov(isr,invert(isr))
    set(x, 7) 

    label("LSbitloop")         
    nop()                    .side(0)  [1]
    in_(pins, 1)             .side(0)  [1]  #data in pin changes on rising edge of clock
    nop()                    .side(1)   
    nop()                    .side(1)  [1]    
    jmp(x_dec, "LSbitloop")    .side(0)

    set(pins, 0)             .side(0)
    
    push(noblock)

    #Delay loop for pause between reads - set up for 0.775mS cycle
    set(y, 11)     # set(y, 19)
    label("delay")
    nop()                   [1]
    jmp(y_dec, "delay")     [7]

    wrap()







# GAME active detector - - - first level filering
INPUT_PIN = 21  # Input to sample  <- changed to gpio21 for version 2 pcb (switched with Aux input)
OUTPUT_PIN = 17 # Output to set/clear
machine.Pin(INPUT_PIN, machine.Pin.IN)
@rp2.asm_pio(set_init=rp2.PIO.OUT_HIGH)
def sample_and_count():
    wrap_target()
    label("top")

    set(y, 31)         # number of readings
    set(x, 10)         # number that need to be low for game over

    label("next_sample")

    jmp(pin,"high")         # jmp pin is the game over lamp input, low=lamp on
    jmp(x_dec,"confirmed_low")       # decrement, if 0 then we have low for sure
    label("high")

    #delay between readings
    nop()                   [7]    
    jmp(y_dec,"next_sample")        

    #sampling done here
    set(pins,1)
    jmp("top")

    label("confirmed_low")
    set(pins,0)
    wrap()


# GAME active detector - - second level filtering
OUTPUT_GAME_ACTIVE_PIN = 15    #output on pin#15 to be picked up in mpython
@rp2.asm_pio(set_init=rp2.PIO.OUT_HIGH)
def drive_game_active_pin():

    wrap_target()
   
    label("topg")       
    set(x, 30) 

    label("loopg")
    jmp(pin,"highb")  [31] 
    #pin is low, set output low and start again
    set(pins,0) 
    jmp("topg")
    
    label("highb") 
    jmp(x_dec,"loopg")   [31]  #non zero take the branch

    set(pins,1) 
    wrap()
   

smSpi = None

def initialize():
    global smSpi,lowPwm,hiPwm

    print("SENSOR: setup sensor read DMA / PIO")

    ram_bytes = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
    for i in range(SRAM_DATA_LENGTH):
        ram_bytes[i] = 0

    import ScoreTrack
    ScoreTrack.reset_sensor_buffer_pointer()

    dma_start()

    #state machine - for SPI read of coil sensors
    smSpi = rp2.StateMachine(4, spi_master_16bit_invert, freq=340000,
        in_base=machine.Pin(PIO_MISO_PIN),
        sideset_base=machine.Pin(PIO_SCK_PIN),
        set_base=machine.Pin(PIO_CS_PIN)
    )
    smSpi.active(1)

    #give the analog PWM outputs a default
    hiPwm.freq(1000)
    lowPwm.freq(1000)
    hiPwm.duty_u16(int(65535 * 0.55))   # 80% duty cycle
    lowPwm.duty_u16(int(65535 * 0.45))  # 20% duty cycle

    # Set up state machine for the game active detection
    sma = rp2.StateMachine(
        1, sample_and_count, freq=100000,  
        set_base=machine.Pin(OUTPUT_PIN),
        jmp_pin=machine.Pin(INPUT_PIN)           
    )
    sma.active(1)
    
    # Set up state machine - game active filter
    smb = rp2.StateMachine(
        2, drive_game_active_pin, freq=40000,  
        set_base=machine.Pin(OUTPUT_GAME_ACTIVE_PIN),
        jmp_pin=machine.Pin(OUTPUT_PIN),
        sideset_base=machine.Pin(0)
    )
    smb.active(1)
    

dma_sensor = None

def dma_diag():
    global dma_sensor
    if dma_sensor is not None:
        print("SENSOR: DMA write address =", hex(dma_sensor.WRITE_ADDR_REG))
        print("SENSOR: DMA transfer count =", hex(dma_sensor.TRANS_COUNT_REG))


def dma_start():
    global dma_sensor    
    #**************************************************
    # DMA Setup for bus memory access, read and writes
    #**************************************************
    a=rp2.DMA()
   
    # DMA channel assignment (we can use any channel in this case)
    DMA_SENSOR = a.channel 
    log.log(f"SENSOR: using DMA channel: {DMA_SENSOR}")

    #uctypes struct for registers
    dma_sensor = dma_d.DMA_CHANS[DMA_SENSOR]   
                
    #-------------------------------------------------------
    # DMA - copy from sensor PIO to reserved Ram - circular
    #-------------------------------------------------------
    dma_sensor.READ_ADDR_REG =      0x50300000 + 0x020      # PIO1_SM0 (4) RX buffer
    dma_sensor.WRITE_ADDR_REG =     SRAM_DATA_BASE
    dma_sensor.CTRL_REG.CHAIN_TO =  DMA_SENSOR # <<only triggerws at the end of 0x0800              # no chain trigger

    dma_sensor.CTRL_REG.INCR_WRITE =    1       #enable increment to write address
    dma_sensor.CTRL_REG.INCR_READ =     0
    dma_sensor.CTRL_REG.RING_SEL=       1       #ring is appllied to write addresses
    dma_sensor.CTRL_REG.RING_SIZE =     13      #13 bits in ring (8k)

    dma_sensor.CTRL_REG.IRQ_QUIET =     1
    dma_sensor.CTRL_REG.TREQ_SEL =      12      #dma_d.DREQ_PIO1_RX0 - wait on data from spi_master_16bit
    dma_sensor.CTRL_REG.DATA_SIZE =     2       #32 bit move (only 16 used now, planning on four player board)
    dma_sensor.CTRL_REG.EN =            1
    dma_sensor.CTRL_REG.HIGH_PRIORITY = 1

    dma_sensor.TRANS_COUNT_REG =        0xF0000008 #wrap forever 0x0800     #pre-trigger this DMA (will wait on DREQ)
    dma_sensor.READ_ADDR_REG_TRIG =     0x50300000 + 0x020  

    print("SENSOR: DMA setup complete")

def clearSensorRx():
    global smSpi    
    while smSpi.rx_fifo() > 0:
        x=smSpi.get()

def readSensorRx():
    global smSpi
    return (smSpi.get())

def depthSensorRx():
    return (smSpi.rx_fifo())

     
def reverse_bits_16(x):
    x = ((x & 0xAAAA) >> 1) | ((x & 0x5555) << 1)
    x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2)
    x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4)
    x = ((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)
    #x = x & 0x0F
    return x


#this pin is the output from the PIO game active filter
game_active_pin = Pin(15, Pin.OUT)   
def gameActive():
    return game_active_pin.value()


lowCalThres=32000
highCalThres=32000

def calibrate():
    '''calibrate the analog output pwms - sensors need to be idleing for this'''
    global smSpi,lowPwm,hiPwm,lowCalThres,highCalThres

    #check existing cal from spi datastore
    cal_high = S.gdata.get("sensorlevels")[1]
    cal_low = S.gdata.get("sensorlevels")[0]
    if (cal_high>20000  and   cal_low<(65535-20000) ):
        log.log(f"SENSOR: sensor calibration restored:  cal_low={cal_low}, cal_high={cal_high}")
        lowPwm.duty_u16(cal_low)
        lowCalThres=cal_low
        hiPwm.duty_u16(cal_high)
        highCalThres=cal_high
        return

    print("SENSOR: Calibrate sensor circuit")
    lowPwm.duty_u16(20000)
    hiPwm.duty_u16(65535-20000)
    time.sleep(0.4)  
    clearSensorRx()
    time.sleep(0.1)  
    v = readSensorRx()   
    if (v&0x03) != 0:
        log.log("SENSOR: sensor cal fault")

    for duty in range(20000, 65536-20000, 256):  # Ramp in steps of 256 for speed        
        print(".",end="")
        lowPwm.duty_u16(duty)
        clearSensorRx()
        time.sleep(0.1)  
      
        lowCal=0
        highCal=0

        # Check buffer for two LSBs clear
        v = readSensorRx()               
        if v is not None:
            if (v & 3) == 3:  # Two LSBs
                print(f"\nSENSOR: Low PWM calibration found at duty: {duty} ({duty/65535:.2%})")  
                lowCal=duty
                break        


    lowPwm.duty_u16(int(0))
    time.sleep(0.1)
    for duty in range(65535-20000, 19999, -256):
        print(".",end="")
        hiPwm.duty_u16(duty)
        clearSensorRx()        
        time.sleep(0.08)  

        # Check buffer for two LSBs clear
        v = readSensorRx()   
        if v is not None:        
            if (v & 3) == 3:  # Two LSBs               
                print(f"\nSENSOR: High PWM calibration found at duty: {duty} ({duty/65535:.2%})")                
                highCal=duty
                break


    #print("\nSENSOR: calibration complete:",lowCal,highCal)
    lowCalThres = int(lowCal*0.88)   #0.9
    lowPwm.duty_u16(lowCalThres)
    highCalThres = int(highCal*1.12)  #1.1
    hiPwm.duty_u16(highCalThres)
    log.log(f"SENSOR: calibration thresholds, low={lowCalThres} high={highCalThres}")
    print("SENSOR: thresholds as percentage: Low = {:.2%}, High = {:.2%}".format(lowCalThres/65535, highCalThres/65535))



def sensitivityChange(dir):
    '''sensitivy adjust - up=1 so more sensitive'''
    global lowCalThres,highCalThres
    if dir==1:
        if int(highCalThres*0.98) > int(lowCalThres*1.02):
            highCalThres=int(highCalThres*0.98)
            lowCalThres=int(lowCalThres*1.02)
    else:
        if int(highCalThres*1.02) < 55000 :
            highCalThres=int(highCalThres*1.02)
            lowCalThres=int(lowCalThres*0.98)

    lowPwm.duty_u16(lowCalThres)
    hiPwm.duty_u16(highCalThres)
    log.log(f"SENSOR: set thresholds low={lowCalThres} high={highCalThres}")

    import SPI_DataStore as DataStore
    S.gdata.get("sensorlevels")[1] = highCalThres
    S.gdata.get("sensorlevels")[0] = lowCalThres
    DataStore.write_record("EMData", S.gdata)



#test
if __name__ == "__main__":

    initialize()

    import ScoreTrack

    while True:
        v = ScoreTrack.pullWithDelete()
        print("V: 0x{:04X}".format(v) if v is not None else "V: None")
        #print("ggggggggggggggggg")
        time.sleep(0.5)




