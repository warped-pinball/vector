# This file is part of the Warped Pinball SYSEM-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
display message for EM machines

handles on board displays only - LEDs for all the inputs
  and the single digit 7 segment for IP address, learn mode counts
"""
import time
from machine import Pin
from rp2 import asm_pio, PIO, StateMachine

from logger import logger_instance
log = logger_instance

from sensorRead import gameActive

localCopyIp = "0"

sensorPattern=0x0000   #green sensor LEDs
auxLED = False
gameOverLED = True

#alternate sources for 7 segment display
ipDigitDisplay="  "
ipDigitUpNext = 0
displayState = 0
captureModeCounter = -1
learnModeCounter = -1
faultNumber = -1

lastSendValue=0x0000

#SPI port for output only (no data in)
SPI_CLK_PIN = 6   # GP6 for SPI0 SCK
SPI_MOSI_PIN = 7  # GP7 for SPI0 MOSI
LOAD_PIN = 8      # GP8 for LOAD (GPIO)

# Initialize LOAD pin
load = Pin(LOAD_PIN, Pin.OUT)
load.value(0)

SEGMENTS = [
    0x3F,  # 0
    0x06,  # 1
    0x5B,  # 2
    0x4F,  # 3
    0x66,  # 4
    0x6D,  # 5
    0x7D,  # 6
    0x07,  # 7
    0x7F,  # 8
    0x6F,  # 9
    0x80,  # .
    0x00,  # _
    0x79   # E
]




def fixAdjustmentChecksum():   
    pass

def setipAddress(ipAddress):
    """call to set the ip address to be displayed
    at powerup
    """
    global ipDigitDisplay, ipDigitUpNext

    if not isinstance(ipAddress, str) or len(ipAddress) == 0:
        ipDigitDisplay = " "
    else:
        ipDigitDisplay = ipAddress + "    "

    log.log(f"MSG: init ip address {ipAddress}")
    return

def init(ipAddress=""):
    if isinstance(ipAddress, str) and len(ipAddress) > 3:
        setipAddress(ipAddress)

    from phew.server import schedule
    schedule(displayUpdate, 1000, 500)

#keep - compatiblewith server.py in common
def refresh():
    return

def setAuxLeds(aux,gameOver):
    '''add on special aux/go bits to sensor pattern leds'''
    global auxLED,gameOverLED
    auxLED = bool(aux)
    gameOverLED = bool(gameOver)

def setSensorLeds(pattern):
    '''add on bits to sensor pattern leds - will cause led to BLINK ONLY'''
    global sensorPattern
    sensorPattern = sensorPattern | pattern

def setLearnModeDigit(d):
    global learnModeCounter
    if isinstance(d, int) and 0 <= d <= 9:
        learnModeCounter = d
    else:
        learnModeCounter = -1

def setCaptureModeDigit(d):
    global captureModeCounter
    if isinstance(d, int) and 0 <= d <= 9:
        captureModeCounter = d
    else:
        captureModeCounter = -1


# PIO program: pull a 32-bit word, shift out the top 24 bits MSB-first
# out(pins, 1) writes the top bit of OSR to MOSI (out_base)
# sideset toggles SCK (sideset_base)
# set(pins, 1) toggles LOAD (set_base)
@asm_pio(out_shiftdir=PIO.SHIFT_LEFT, out_init=PIO.OUT_LOW,
         set_init=PIO.OUT_LOW, sideset_init=PIO.OUT_LOW)
def pio_spi_tx():
    pull()                 # load 32-bit OSR from TX FIFO
    set(pins, 0)           # ensure LOAD low (set_base)
    set(x, 23)             # 24 bits to shift (0..23)
    label("bitloop")
    out(pins, 1)  .side(0) [1]   # drive MOSI with OSR top bit
    nop()         .side(1) [1]   # clock high    nop()         .side(0) [0]   # clock low
    jmp(x_dec, "bitloop")
    # pulse LOAD high
    set(pins, 1)           [2]
    set(pins, 0)           [0]
    wrap()

# Initialize the PIO state machine (runs at import)
_sm_display = StateMachine(7, pio_spi_tx, freq=200000,
                          out_base=Pin(SPI_MOSI_PIN),
                          set_base=Pin(LOAD_PIN),
                          sideset_base=Pin(SPI_CLK_PIN))
_sm_display.active(1)

print("DISPLAY: initialized")

def _sendToHardware(tx32):
    '''sends data to hardware for immiidate update of led status'''
    global lastSendValue
    lastSendValue=tx32
    try:
        _sm_display.put(tx32)
    except Exception:
        pass


def displayUpdate():
    '''timer driven - build pattern and queue single 32-bit word to PIO state machine'''
    global sensorPattern, auxLED, gameOverLED, ipDigitDisplay, ipDigitUpNext, lastSendValue ,displayState

    displayState = (displayState + 1) % 4
    if displayState==2 or displayState==1:
        return
    if displayState==3:
        #shut off digit part?
        _sendToHardware(lastSendValue & 0x00FFFFFF)
        return
  
    # sensorPattern is 16-bit
    low_byte = sensorPattern & 0x1F
    mid_byte = (sensorPattern >> 8) & 0x1F
    sensorPattern=0

    # auxLED -> MSBit of byte #2 (bit7), gameover -> next lower bit (bit6)
    if auxLED:
        mid_byte |= 0x80

    gameOverLED = gameActive()
    if gameOverLED:
        mid_byte |= 0x40

    #deicde which input to put on digit display
    if 0 <= captureModeCounter <= 9:
        idx = captureModeCounter
    elif 0 <= learnModeCounter <= 9:
        idx= learnModeCounter
    else:
        ch = ipDigitDisplay[ipDigitUpNext]
        ipDigitUpNext = (ipDigitUpNext + 1) % len(ipDigitDisplay)
        if '0' <= ch <= '9':
            idx = ord(ch) - ord('0')     # 0..9
        elif ch == '.':
            idx = 10
        elif ch == ' ':
            idx = 11                      # blank / space
        else:
            idx = 11                      # unknown -> blank

    #convert ascii digit to 7 segment code
    top_byte = SEGMENTS[idx]

    # Compose 24-bit value in big-endian order and left-align into OSR
    # OSR shifts MSB first, so place 24-bit value at bits 31..8 by shifting left 8
    tx24 = ((top_byte << 16) | (mid_byte << 8) | low_byte) & 0xFFFFFF
    tx32 = (tx24 << 8) & 0xFFFFFFFF

    # Queue to PIO (non-blocking if FIFO has space)
    try:
        _sendToHardware(tx32)     
    except Exception:
        # If FIFO full, skip this update (or handle retry logic)
        pass

#power up clear the display to reduce power
displayUpdate()







#test
if __name__ == "__main__":   
    l=1
    ipDigitDisplay="012.789.345.567  "
    while True:
        displayUpdate()
        time.sleep(0.2)
        setSensorLeds(l)
        l=l*2
        if l>0x2000:
            l=1

