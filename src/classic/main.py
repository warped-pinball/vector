# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    Warped Pinball - Vector :: Classic
"""

import resource
import time

import faults
import GameDefsLoad
import machine
import Memory_Main as MemoryMain
import reset_control
from logger import logger_instance
from Shadow_Ram_Definitions import shadowRam
from systemConfig import SystemVersion
import Switches
import Formats

Log = logger_instance

# other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)

led_board = None

faults.initialize_board_LED()



def check_ap_button():
    # holding down AP setup button?
    zero_count = 0
    num_Checks = 5
    for _ in range(num_Checks):
        pin_state = SW_pin.value()
        if pin_state == 0:
            zero_count += 1

    if zero_count == num_Checks:
        Log.log("Main: Button press-wifi config")
        # now blink LED for a bit
        start_time = time.time()
        while time.time() - start_time < 3:
            faults.toggle_board_LED(button_held=True)
            time.sleep(0.1)
        time.sleep(3)
        return True  # AP mode
    else:
        return False  # Normal boot mode, no button press


reset_control.init()

print("\n\n")
print("  Warped Pinball :: Vector Classic")
Log.log(f"          Version {SystemVersion}")
print("Contact Paul -> Inventingfun@gmail.com")

print(
    """
Vector (Classic) from Warped Pinball
This work is licensed under CC BY-NC 4.0
"""
)


ap_mode = check_ap_button()
print("Main: AP mode = ", ap_mode)

# load up Game Definitions
if not ap_mode:
    GameDefsLoad.go()
else:
    GameDefsLoad.go(safe_mode=True)

MemoryMain.go()

time.sleep(0.5)
reset_control.release(True)
time.sleep(4)

resource.go(True)
Switches.initialize()
Formats.initialize()

# launch wifi, and server. Should not return
from backend import go  # noqa

Log.log("MAIN: Launching Wifi")
go(ap_mode)
Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)
