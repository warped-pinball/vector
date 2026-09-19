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
DIAG_OUTPUT_PIN = 1
GPIO11_OUTPUT_PIN = 11
PIO_CS_PIN   = 13  # CS (or Load...)
ANALOG_HI_GPIO = 19
ANALOG_LOW_GPIO = 18

#MISO data pin init
machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_DOWN)

#GPIO11 output init
machine.Pin(GPIO11_OUTPUT_PIN, machine.Pin.OUT, value=1)

#GPIO1 diagnostic output init
machine.Pin(DIAG_OUTPUT_PIN, machine.Pin.OUT, value=0)

#analog thresholds PWMs
hiPwm = machine.PWM(machine.Pin(19))
lowPwm = machine.PWM(machine.Pin(18))


#read sebsors
@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.OUT_HIGH), set_init=rp2.PIO.OUT_HIGH) 
def spi_master_16bit_invert():
   
    wrap_target()

    mov(isr,invert(null))   .side(0)

    set(pins, 1)                [3]     #set load pin (CS) high
    set(x, 7)                   [3]       #init first transfer bit length   
    nop()                       [3]

    label("MSbitloop")         
    nop()                       .side(0)  [1]
    in_(pins, 1)                .side(0)  [1]  #data in pin changes on rising edge of clock
    nop()                       .side(1)  [3]  #side set happnens and then delay cycles
    jmp(x_dec, "MSbitloop")     .side(0)

    mov(isr,invert(isr))
    set(x, 7) 

    label("LSbitloop")         
    nop()                    .side(0)  [1]
    in_(pins, 1)             .side(0)  [1]  #data in pin changes on rising edge of clock
    nop()                    .side(1)  [3]    
    jmp(x_dec, "LSbitloop")    .side(0)

    set(pins, 0)             .side(0)       #CS off (load pin)    
    push(noblock)

    #Delay loop for pause between reads - set up for 0.775mS cycle
    set(y, 11)    .side(2)   # set(y, 11)    
    label("delay2")
    nop()                   [3]
    nop()                   [2]
    jmp(y_dec, "delay2")    [3]

    wrap()





@rp2.asm_pio(sideset_init=(rp2.PIO.OUT_HIGH, rp2.PIO.OUT_HIGH), set_init=rp2.PIO.OUT_HIGH)
def spi_master_32bit_invert():
    """
    4-player variant of spi_master_16bit_invert(): clocks in 32 bits per
    sample as four 8-bit sensor-register groups, shifted in order
    P4,P3,P2,P1, and pushes the full 32-bit ISR to the RX FIFO.

    The real 4-player board hardware-inverts the 1st and 3rd bytes (P4,
    P2) but not the 2nd and 4th (P3, P1) -- an alternating pattern. A
    single mov(isr, invert(isr)) flips the *entire* ISR (every bit shifted
    in so far, not just the newest group), so it looks like one invert
    can't isolate just one group -- but applying it after EVERY group
    (not just once) works out correctly: each already-placed group picks
    up one more inversion for every later group's invert, and the
    resulting parity alternates exactly right. Verified by simulation:
    group 1 (P4) ends up inverted, group 2 (P3) ends up raw, group 3 (P2)
    inverted, group 4 (P1) raw -- matching the real hardware exactly, no
    software-side byte inversion needed for this board.
    """

    wrap_target()

    mov(isr, invert(null))   .side(0)

    set(pins, 1)                [3]     #set load pin (CS) high
    set(x, 7)                   [3]     #8 bits per group
    nop()                       [3]

    label("p4loop")                     # group 1: P4 -> ends up inverted
    nop()                       .side(0)  [1]
    in_(pins, 1)                .side(0)  [1]  #data in pin changes on rising edge of clock
    nop()                       .side(1)  [3]
    jmp(x_dec, "p4loop")        .side(0)

    mov(isr, invert(isr))
    set(x, 7)

    label("p3loop")                     # group 2: P3 -> ends up raw
    nop()                       .side(0)  [1]
    in_(pins, 1)                .side(0)  [1]
    nop()                       .side(1)  [3]
    jmp(x_dec, "p3loop")        .side(0)

    mov(isr, invert(isr))
    set(x, 7)

    label("p2loop")                     # group 3: P2 -> ends up inverted
    nop()                       .side(0)  [1]
    in_(pins, 1)                .side(0)  [1]
    nop()                       .side(1)  [3]
    jmp(x_dec, "p2loop")        .side(0)

    mov(isr, invert(isr))
    set(x, 7)

    label("p1loop")                     # group 4: P1 -> ends up raw
    nop()                       .side(0)  [1]
    in_(pins, 1)                .side(0)  [1]
    nop()                       .side(1)  [3]
    jmp(x_dec, "p1loop")        .side(0)

    set(pins, 0)             .side(0)       #CS off (load pin)
    push(noblock)

    #Delay loop for pause between reads
    set(y, 11)    .side(2)
    label("delay2")
    nop()                   [3]
    nop()                   [2]
    jmp(y_dec, "delay2")    [3]

    wrap()




# GAME active detector - - - first level filtering
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
    #  2player board: 16 bits/sample (P1,P2), alternating invert baked into the PIO.
    #  4player board: 32 bits/sample (P4,P3,P2,P1), same alternating invert
    #  baked in too (see spi_master_32bit_invert() for how).
    sensor_pio_program = spi_master_32bit_invert if S.hardware_version == "4player" else spi_master_16bit_invert
    smSpi = rp2.StateMachine(4, sensor_pio_program, freq=340000,
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

    # Restore persisted calibration/sensitivity thresholds on boot and write PWM regs.
    _restore_sensor_thresholds_from_store()

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
    dma_sensor.CTRL_REG.CHAIN_TO =  DMA_SENSOR # <<only triggers at the end of 0x0800              # no chain trigger

    dma_sensor.CTRL_REG.INCR_WRITE =    1       #enable increment to write address
    dma_sensor.CTRL_REG.INCR_READ =     0
    dma_sensor.CTRL_REG.RING_SEL=       1       #ring is applied to write addresses
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


# Calibration record - set only by calibrate() (or restored from flash on
# boot). Sensitivity is applied live, on top of this record, every time
# thresholds are written to the PWM registers - the record itself never
# changes just because sensitivity changes, so a recalibrate cycle always
# starts from a clean hardware reading.
calLow = 32000
calHigh = 32000
sensitivity = 0              # percent, SENSITIVITY_MIN..SENSITIVITY_MAX; 0 = as-calibrated

SENSITIVITY_MIN = -200
SENSITIVITY_MAX = 0
COUNTS_PER_PERCENT = 200     # total threshold spread change (both thresholds combined) per 1% sensitivity


def _setThresholds(pct, persist=True):
    """Single point of control for sensor thresholds: clamps/stores the
    sensitivity percent, computes (low, high) PWM counts live from the
    calibration record, writes them to the analog PWM registers, and
    (unless persist=False) saves the result to EMData.

    Every function that changes sensitivity or thresholds must go through
    here so the PWM outputs, S.gdata, and persisted state can never drift
    apart from one another."""
    global sensitivity

    pct = max(SENSITIVITY_MIN, min(SENSITIVITY_MAX, int(pct)))
    sensitivity = pct

    delta = (COUNTS_PER_PERCENT * pct)   # counts each threshold moves toward/away from midpoint
    low = max(0, min(65535, int(calLow + delta)))
    high = max(0, min(65535, int(calHigh - delta)))
    if high < low:
        low = high = (low + high) // 2

    lowPwm.duty_u16(low)
    hiPwm.duty_u16(high)
    print(f"SENSOR: PWM thresholds low={low} high={high} (cal low={calLow} high={calHigh}, sensitivity={sensitivity}%)")

    S.gdata["sensitivity"] = pct

    if persist:
        try:
            from ScoreTrack import saveState

            saveState()
        except Exception as e:
            log.log(f"SENSOR: failed to persist thresholds: {e}")

    return pct, low, high


def _restore_sensor_thresholds_from_store():
    """Restore the persisted calibration record + sensitivity and apply to PWM."""
    global calLow, calHigh

    sensor_levels = S.gdata.get("sensorlevels")
    if not isinstance(sensor_levels, (list, tuple)) or len(sensor_levels) < 2:
        return False

    try:
        cal_low = int(sensor_levels[0])
        cal_high = int(sensor_levels[1])
    except Exception:
        return False

    # Sanity checks: keep in valid register range and ensure a useful spread.
    # (calibrate() stores calLow/calHigh already margin-expanded - 0.6x/1.4x
    # of the raw sweep points - so they routinely fall outside the raw
    # 20000..45535 sweep window; that is expected, not a fault.)
    if cal_low < 0 or cal_low > 65535 or cal_high < 0 or cal_high > 65535:
        return False
    if (cal_high - cal_low) < 1000:
        return False

    calLow = cal_low
    calHigh = cal_high
    pct = int(S.gdata.get("sensitivity", 0))

    # Restoring reapplies exactly what was already persisted, so there's
    # nothing new to save back to EMData.
    pct, low, high = _setThresholds(pct, persist=False)
    log.log(f"SENSOR: sensor calibration restored: cal_low={cal_low}, cal_high={cal_high}, sensitivity={pct}%, applied low={low} high={high}")
    return True

def calibrate():
    '''calibrate the analog output pwms - sensors need to be idleing for this'''
    global smSpi,lowPwm,hiPwm,calLow,calHigh

    print("SENSOR: Calibrate sensor circuit start")

    # check existing cal from SPI datastore and apply as the starting point
    _restore_sensor_thresholds_from_store()

    print("SENSOR: Calibrate sensor circuit - run CAL")
    lowPwm.duty_u16(20000)
    hiPwm.duty_u16(65535-20000)
    time.sleep(0.4)  
    clearSensorRx()
    time.sleep(0.1)  
    v = readSensorRx()   
    if (v&0x03) != 0:
        log.log("SENSOR: sensor cal fault")

    lowCal = 0
    highCal = 0
    for duty in range(20000, 65536-20000, 256):  # Ramp in steps of 256 for speed
        print(".",end="")
        lowPwm.duty_u16(duty)
        clearSensorRx()
        time.sleep(0.1)

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


    print("\nSENSOR: calibration complete:",lowCal,highCal)
    # calLow/calHigh define the calibration record's threshold spread - pull
    # them in tight around the midpoint instead of scaling lowCal/highCal
    # outward, so they land close together regardless of how far apart the
    # sweep's found crossing points are. CAL_MIN_GAP is the smallest allowed
    # spread (raw PWM counts) and also guarantees calHigh > calLow.
    CAL_MIN_GAP = 40
    midpoint = (lowCal + highCal) // 2
    calLow = max(0, min(65535, midpoint - CAL_MIN_GAP // 2))
    calHigh = max(calLow + 1, min(65535, midpoint + CAL_MIN_GAP // 2))
    S.gdata["sensorlevels"] = [calLow, calHigh]
    log.log(f"SENSOR: calibration record, low={calLow} high={calHigh}")
    print("SENSOR: calibration record as percentage: Low = {:.2%}, High = {:.2%}".format(calLow/65535, calHigh/65535))

    # A fresh calibration applies this starting sensitivity on top of the
    # newly-calibrated record before returning.
    return _setThresholds(-10)


def setSensitivityPercent(percent):
    """Set sensitivity percent (SENSITIVITY_MIN..SENSITIVITY_MAX) and apply it
    live against the calibration record, writing the result to the PWM
    registers.

    0% keeps the full calibrated threshold spread (most sensitive).
    Negative % = less sensitive (thresholds move further apart), down to
    SENSITIVITY_MIN.
    """
    try:
        pct = int(percent)
    except Exception:
        pct = 0

    pct, low, high = _setThresholds(pct)
    log.log(f"SENSOR: sensitivity set to {pct}% -> low={low} high={high}")
    return pct, low, high


def sensitivityChange(dir):
    '''sensitivity adjust via physical buttons - dir=1 so more sensitive.

    Routes through setSensitivityPercent() (same path as the web admin
    +/- buttons) so thresholds are always derived live from the calibration
    record instead of drifting relative to themselves.
    '''
    pct = int(S.gdata.get("sensitivity", 0))
    step = 1 if dir == 1 else -1
    pct = max(SENSITIVITY_MIN, min(SENSITIVITY_MAX, pct + step))
    return setSensitivityPercent(pct)

#test
if __name__ == "__main__":

    initialize()

    import ScoreTrack

    while True:
        v = ScoreTrack.pullWithDelete()
        print("V: 0x{:04X}".format(v) if v is not None else "V: None")
        #print("ggggggggggggggggg")
        time.sleep(0.5)




