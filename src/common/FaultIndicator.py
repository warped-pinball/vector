
# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

"""
    Warped Pinball
    
    Fault indicator 
    Supports Ws2812 multi color LED for enhanced fault reporting via BoardLED.py driver
"""

import time,utime
import machine
import SharedState
import BoardLED as L
import faults
try:
    import rp2
except:
    rp2 = None


# Map each fault type to a list of colors for LED indication
#     first in list has priority  
FAULT_COLOR_SEQUENCES = {
    "ALL_OK":  [L.GREEN, L.GREENDIM, L.GREEN, L.GREENDIMM],
    "GEN_FLT": [L.RED, L.RED,L.RED,L.RED,L.RED,L.RED, L.BLACK],
    "WIFI00":  [L.RED, L.BLUE, L.YELLOW, L.BLACK],
    "WIFI01":  [L.RED, L.RED, L.BLUE, L.BLACK],
    "HDWR01":  [L.RED, L.MAGENTA, L.BLACK],
    "SFTW01":  [L.MAGENTA, L.WHITE, L.BLACK],

}

enableWS2812led = False
timer = machine.Timer()
LED_Out = None
sequence = [L.BLACK, L.BLACK]
index = 0

def isChip2350():
    """
        Determine if we are running on 2350 with PIO support for new ws2812 LED
    """
    import os
    chip_id = os.uname().machine
  
    if "RP2350" in chip_id and rp2 != None:
        print("FLT_IND: Pico 2 (RP2350) detected")       
        return True
    return False



def toggleBoardLED():
    """
        Legacy interface to led function
          -works if we are on a PICO1 without BoardLED running
          -works on PICO2 with BoardLED and only single color LED installed
          -runs with no effect on PICO2 with only ws2812 led installed
    """
    global enableWS2812led
    if enableWS2812led is True:
        #ws2812 driver - control of single color LED
        L.ledtoggle()
    else:
        #old single color led only
        LED_Out.toggle()


def start():
    """
        start up fault indicator once
    """
    global LED_Out, timer, enableWS2812led
    enableWS2812led = isChip2350()
    if enableWS2812led is True:
        L.startUp()
        L.ledOff()
        L.ledColor(L.BLACK)
        timer.init(period=790, mode=machine.Timer.PERIODIC, callback=_timerCallBack)
    else:
        LED_Out = machine.Pin(26, machine.Pin.OUT)

  

def _getNewFaults():
    global x, sequence
    """
        Check SharedState for faults and update LED sequence accordingly
    """
    # Extract fault codes from SharedState.faults
    fault_codes = [f.split(":")[0].split()[0] for f in SharedState.faults]

    # Find the first matching fault code in FAULT_COLOR_SEQUENCES
    selected_seq = None
    if fault_codes:
        for key in FAULT_COLOR_SEQUENCES:
            if key in fault_codes:
                selected_seq = FAULT_COLOR_SEQUENCES[key]
                break
        if selected_seq is None:
            selected_seq = FAULT_COLOR_SEQUENCES.get("GEN_FLT")
    else:
        selected_seq = FAULT_COLOR_SEQUENCES.get("ALL_OK")

    # Copy the selected color sequence into seq
    sequence = list(selected_seq)



def _timerCallBack(_):
    """
        timer to drive LED blinky blink - and get new FAULTS periodically
    """
    global index,sequence
    L.ledColor(sequence[index])
    index = (index + 1) % (len(sequence)) 
    if index==0:
        _getNewFaults()
    





#  TEST - - 
if __name__ == "__main__":
    start()

    #generic fault
    #faults.raise_fault(faults.WIFI02, f"Invalid wifi credentials ")

   
    time.sleep(2)
    L.ledtoggle()
    time.sleep(5)
    #known fault
    faults.raise_fault(faults.WIFI00, f"Invalid wifi credentials ")
    faults.raise_fault(faults.WIFI01, f"Invalid wifi credentials ")
    L.ledtoggle()
    time.sleep(2)
