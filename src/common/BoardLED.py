# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

"""
    Warped Pinball
    
    Low level driver for WS2812 combined with single color led legacy support
"""
import machine
try:
    import rp2
except ImportError:
    rp2 = None


# Color definitions for board LEDs
RED     = 0x000C00
GREEN   = 0x0C0000
GREENDIM = 0x090000
GREENDIMM = 0x030000
BLUE    = 0x00000C
YELLOW  = 0x0C0C00
CYAN    = 0x000C0C
MAGENTA = 0x0C000C
WHITE   = 0x0C0C0C
BLACK   = 0x000000


# WS2812 serial driver with support for single color LED on same gpio
@rp2.asm_pio(
    sideset_init=rp2.PIO.OUT_LOW,
    out_shiftdir=rp2.PIO.SHIFT_LEFT,
    autopull=True,
    pull_thresh=24,     # 24 bits per pixel (GRB)
)
def ws2812():
    wrap_target()

    label("bitloop")
    out(x, 1)               .side(0)    [2]        
    jmp(not_x, "do_zero")   .side(1)    [1]          
    jmp("bitloop")          .side(1)    [3]         
    label("do_zero")
    nop()                   .side(0)    [3]        
    jmp(not_osre,"bitloop") #loop all data out (24 bits)

    set(x,14)               #delay with output low to set the data  
    label("after_loop")
    wait(1,irq,2)
    jmp(x_dec,"after_loop")

    jmp(not_y,"low_output") #set up the i/o pin output for single color led compatibility
    nop()   .side(1)
    label("low_output")

    label("wait")           #hold line high or low for simple LED, wait for data
    jmp(not_osre,"preplow")     
    jmp("wait")
    label("preplow")

    set(x,14)    .side(0)  #give some low time in prep for next bit string
    label("before_loop")
    wait(1,irq,2)
    jmp(x_dec,"before_loop")

    wrap()
    
#low speed clock source for delays required in  ws2812()
@rp2.asm_pio()
def irq_clock():
    wrap_target()
    irq(2)                
    set(x, 21)            
    label("delay")
    jmp(x_dec, "delay")
    wrap()


#main PIO state machine for control of LEDs
sm_led = None

def startUp():        
    """
        must call once at power up - only if running on PICO2
    """
    global sm_led

    clk_led = rp2.StateMachine(
        6,               # state machine index
        irq_clock,       
        freq=1_000_000,       
    )
    clk_led.active(1)

    sm_led = rp2.StateMachine(
        7,              # state machine index
        ws2812,         
        freq=8_000_000, 
        sideset_base=machine.Pin(26)
    )
    sm_led.active(1)

    print("BrdLED: start")


ledState = 0
lastColor = BLACK

def ledOn():
    global sm_led,ledState
    sm_led.exec("set(y, 0)") 
    ledState=1

def ledOff():
     global sm_led,ledState
     sm_led.exec("set(y, 1)") 
     ledState=0

def ledtoggle():
    # toggle also auto updates state!
    global ledState
    if ledState==0:
        ledOn()
    else:
        ledOff()
    ledColor(lastColor)

def ledColor(c):
    global lastColor
    #change in color updates led on/off status also
    lastColor = c
    sm_led.put(c<<8)  
