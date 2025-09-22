# WPC

# This file is part of the Warped Pinball SYS-EM Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    Warped Pinball - WPC.Wifi
    fault check updated for early sys11 game compatability
"""

import resource
import time

import sensorRead
sensorRead.initialize()
sensorRead.calibrate()


import faults
import GameDefsLoad
import machine
import uctypes
import adjustButtons

from logger import logger_instance
from systemConfig import SystemVersion


import display
import GameStatus
import ScoreTrack
import SharedState as S

Log = logger_instance
# other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)
LED_Out = machine.Pin(26, machine.Pin.OUT)

timer = machine.Timer()
led_board = None

adjustButtons.init_buttons()

def error_toggle(timer):
    led_board.toggle()


def set_error_led():
    global led_board
    led_board = machine.Pin(26, machine.Pin.OUT)
    timer.init(freq=3, mode=machine.Timer.PERIODIC, callback=error_toggle)


def bus_activity_fault_check():
    pass
    return False


def check_ap_button():
    # holding down AP setup button?
    zero_count = 0
    num_Checks = 5
    for _ in range(num_Checks):
        pin_state = SW_pin.value()
        if pin_state == 0:
            zero_count += 1

    if zero_count == num_Checks:
        # Log.log("Main: Button press-wifi config")
        # now blink LED for a bit
        start_time = time.time()
        while time.time() - start_time < 3:
            LED_Out.toggle()
            time.sleep(0.1)
        time.sleep(3)
        return True  # AP mode
    else:
        return False  # Normal boot mode, no button press




def clear_ram_section(start_addr=0x20080000, length=0x20):
    """
    Clear (set to zero) a section of RAM from start_addr to start_addr+length.
    Default: 0x20080000 to 0x20088000 (32KB).
    """
    ram = uctypes.bytearray_at(start_addr, length)
    for i in range(length):
        ram[i] = 0




print("\n\n")
print("  Warped Pinball :: System EM")
Log.log(f"          Version WPC {SystemVersion}")
print("Contact Paul -> Inventingfun@gmail.com")

print(
    """
WPC.Wifi (Vector) from Warped Pinball
This work is licensed under CC BY-NC 4.0
"""
)


ap_mode = check_ap_button()
print("Main: AP mode = ", ap_mode)






'''
while True:
    time.sleep(4)
    print(ScoreTrack.plen())
    print("_")
'''




# load up Game Definitions
if not ap_mode:
    GameDefsLoad.go()
else:
    GameDefsLoad.go(safe_mode=True)


# Add these entries to S.gdata
S.gdata["numberOfPlayers"] = 2
S.gdata["digitsPerPlayer"] = 4
S.gdata["scoreMultiplier"] = 10

ScoreTrack.initialize()

resource.go(True)

# launch wifi, and server. Should not return
from backend import go  # noqa: E402

print("MAIN: Launching Wifi AP mode=", ap_mode)
go(ap_mode)
Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)
