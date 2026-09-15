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
import SharedState as S

localCopyIp = "0"

sensorPattern=0x0000   #green sensor LEDs, byte-per-player (P1..P4), low 5 bits significant
auxLED = False
gameOverLED = True

#alternate sources for 7 segment display
ipDigitDisplay="  "
ipDigitUpNext = 0
displayState = 0
captureModeCounter = -1
learnModeCounter = -1
faultNumber = -1

# words (32-bit each) last sent to the PIO, MSB-first: word[0]'s top byte is
# always the digit. 1 word for a 2player board, 2 words for 4player.
lastSendWords = (0,)

#SPI port for output only (no data in)
SPI_CLK_PIN = 6   # GP6 for SPI0 SCK
SPI_MOSI_PIN = 7  # GP7 for SPI0 MOSI
LOAD_PIN = 8      # GP8 for LOAD (GPIO)
LED_ENABLE_PIN = 9  # GP9 for LED driver output-enable (active low)

# Initialize LOAD pin
load = Pin(LOAD_PIN, Pin.OUT)
load.value(0)

# LED driver outputs start DISABLED (high). Stay disabled until init() has
# written a valid (blank) frame to the shift-register chain - otherwise the
# chain's power-on-reset contents are undefined and enabling first can light
# every segment/LED at once (a current surge as well as looking wrong).
led_enable = Pin(LED_ENABLE_PIN, Pin.OUT, value=1)

# backend.py passes this literal placeholder to displayMessage.init() while
# starting AP mode (before any real IP exists) - show "AP" instead on the
# single-digit display.
AP_MODE_IP_SENTINEL = "000.000.000.000"

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
    0x79,  # E
    0x77,  # A
    0x73   # P
]
IDX_A = 13
IDX_P = 14


def fixAdjustmentChecksum():
    pass

def setipAddress(ipAddress, pad=True):
    """call to set the ip address to be displayed
    at powerup. pad=False shows the text as a tight repeating
    cycle with no trailing blank gap (used for e.g. "AP" mode).
    """
    global ipDigitDisplay, ipDigitUpNext

    if not isinstance(ipAddress, str) or len(ipAddress) == 0:
        ipDigitDisplay = " "
    elif pad:
        ipDigitDisplay = ipAddress + "    "
    else:
        ipDigitDisplay = ipAddress

    log.log(f"MSG: init ip address {ipAddress}")
    return

_display_update_scheduled = False

def init(ipAddress=""):
    global NUM_PLAYERS, _sm_display, _display_update_scheduled

    # board variant must be known (set by main.py before ScoreTrack.initialize()
    # calls in here) to pick the right shift-register chain length/PIO program
    NUM_PLAYERS = 4 if getattr(S, "hardware_version", None) == "4player" else 2
    _sm_display = _build_state_machine(NUM_PLAYERS)
    _sm_display.active(1)

    # write an all-blank frame and give the PIO time to shift+latch it
    # BEFORE enabling the LED driver outputs, so the chain never shows
    # power-on-reset garbage / all-segments-on when first enabled
    blank_words = (0, 0) if NUM_PLAYERS == 4 else (0,)
    _sendToHardware(blank_words)
    time.sleep_ms(2)
    led_enable.value(0)

    if isinstance(ipAddress, str) and len(ipAddress) > 3:
        if ipAddress == AP_MODE_IP_SENTINEL:
            setipAddress("AP", pad=False)
        else:
            setipAddress(ipAddress)

    # backend.py calls init() again once wifi/AP actually comes up (to set
    # the real IP) - only schedule the timer once, or displayUpdate() runs
    # twice as fast out of phase with itself and the blink/blank never has
    # time to be visible on the display
    if not _display_update_scheduled:
        from phew.server import schedule
        schedule(displayUpdate, 1000, 300)
        _display_update_scheduled = True

def stop():
    '''halt periodic display updates so the display freezes at whatever it
    is currently showing - call this when main is about to exit (fault,
    unhandled exception, drop to REPL) so nothing keeps scrolling/blinking
    behind the scenes.'''
    global _display_update_scheduled
    if not _display_update_scheduled:
        return
    from phew.server import unschedule
    unschedule(displayUpdate)
    _display_update_scheduled = False

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
# Used for 2player boards: 3 shift-register bytes (digit, P2, P1) = 24 bits.
@asm_pio(out_shiftdir=PIO.SHIFT_LEFT, out_init=PIO.OUT_LOW,
         set_init=PIO.OUT_LOW, sideset_init=PIO.OUT_LOW)
def pio_spi_tx_24():
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

# Used for 4player boards: 5 shift-register bytes (digit, P4, P3, P2, P1) =
# 40 bits, more than fits in one 32-bit OSR pull, so this shifts a first
# 32-bit word then a second word (only its top 8 bits are used) before
# pulsing LOAD once at the very end.
@asm_pio(out_shiftdir=PIO.SHIFT_LEFT, out_init=PIO.OUT_LOW,
         set_init=PIO.OUT_LOW, sideset_init=PIO.OUT_LOW)
def pio_spi_tx_40():
    pull()                 # word A: digit,P4,P3,P2 (32 bits)
    set(pins, 0)
    set(x, 31)
    label("bitloopA")
    out(pins, 1)  .side(0) [1]
    nop()         .side(1) [1]
    jmp(x_dec, "bitloopA")
    pull()                 # word B: P1 in the top byte (8 bits used)
    set(x, 7)
    label("bitloopB")
    out(pins, 1)  .side(0) [1]
    nop()         .side(1) [1]
    jmp(x_dec, "bitloopB")
    # pulse LOAD high
    set(pins, 1)           [2]
    set(pins, 0)           [0]
    wrap()

# Uses SM0 (PIO0) rather than PIO1 (SM4-7) because on 4player boards
# spi_master_32bit_invert() in sensorRead.py fills PIO1's entire 32-instruction
# memory by itself; PIO0 has plenty of headroom alongside
# sample_and_count/drive_game_active_pin.
def _build_state_machine(num_players):
    program = pio_spi_tx_40 if num_players == 4 else pio_spi_tx_24
    return StateMachine(0, program, freq=200000,
                         out_base=Pin(SPI_MOSI_PIN),
                         set_base=Pin(LOAD_PIN),
                         sideset_base=Pin(SPI_CLK_PIN))

# resolved once, in init(), once S.hardware_version is known
NUM_PLAYERS = 2
_sm_display = None

print("DISPLAY: initialized")

def _sendToHardware(words):
    '''sends 1 or 2 32-bit words to hardware (MSB-first) for immediate update of led status'''
    global lastSendWords
    if _sm_display is None:
        return
    lastSendWords = tuple(words)
    try:
        for w in words:
            _sm_display.put(w)
    except Exception:
        pass


def displayUpdate():
    '''timer driven - build pattern and queue 1-2 32-bit words to PIO state machine'''
    global sensorPattern, auxLED, gameOverLED, ipDigitDisplay, ipDigitUpNext, displayState

    # 4-phase cycle per digit position: 3 ticks on, 1 tick off, before
    # moving to the next one - so two of the same digit in a row (e.g. the
    # "22" in 192.168.122.233) are visibly two separate digits rather than
    # one digit that never changed.
    displayState = (displayState + 1) % 4
    if displayState == 1 or displayState == 2:
        return
    if displayState == 3:
        # blank just the digit byte (top byte of word 0), leave the LED words as they were
        blanked = (lastSendWords[0] & 0x00FFFFFF,) + lastSendWords[1:]
        _sendToHardware(blanked)
        return

    # sensorPattern is byte-per-player, low 5 bits of each byte significant
    p1_byte = sensorPattern & 0x1F
    p2_byte = (sensorPattern >> 8) & 0x1F
    p3_byte = (sensorPattern >> 16) & 0x1F
    p4_byte = (sensorPattern >> 24) & 0x1F
    sensorPattern=0

    # auxLED -> MSBit of player2 byte (bit7), gameover -> next lower bit (bit6)
    if auxLED:
        p2_byte |= 0x80

    gameOverLED = gameActive()
    if gameOverLED:
        p2_byte |= 0x40

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
        elif ch == 'A':
            idx = IDX_A
        elif ch == 'P':
            idx = IDX_P
        else:
            idx = 11                      # unknown -> blank

    #convert ascii digit to 7 segment code
    top_byte = SEGMENTS[idx]

    # Chain order, MSB-first: digit, then players highest-to-lowest (Pn..P1)
    # - matches the physical chain (P1 register closest to MOSI, digit last).
    if NUM_PLAYERS == 4:
        wordA = ((top_byte << 24) | (p4_byte << 16) | (p3_byte << 8) | p2_byte) & 0xFFFFFFFF
        wordB = (p1_byte << 24) & 0xFFFFFFFF
        words = (wordA, wordB)
    else:
        tx24 = ((top_byte << 16) | (p2_byte << 8) | p1_byte) & 0xFFFFFF
        words = ((tx24 << 8) & 0xFFFFFFFF,)

    # Queue to PIO (non-blocking if FIFO has space)
    try:
        _sendToHardware(words)
    except Exception:
        # If FIFO full, skip this update (or handle retry logic)
        pass


#test
if __name__ == "__main__":
    init()
    l=1
    ipDigitDisplay="012.789.345.567  "
    while True:
        displayUpdate()
        time.sleep(0.2)
        setSensorLeds(l)
        l=l*2
        if l>0x2000:
            l=1
