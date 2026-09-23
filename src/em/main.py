# EM

# This file is part of the Warped Pinball SYS-EM Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    Warped Pinball - WPC.Wifi
    fault check updated for early sys11 game compatability
"""

import nonblocking_print  # noqa: F401  -- must be first; installs non-blocking print()
import resource
import time

import sensorRead

import faults
import GameDefsLoad
import machine
import uctypes
import adjustButtons

from logger import logger_instance
from systemConfig import SystemVersion

import ScoreTrack
import SharedState as S

# EM hardware variant, detected at boot from GPIO14: "2player" or "4player"
hardware_version = None


Log = logger_instance
# other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)
LED_Out = machine.Pin(26, machine.Pin.OUT)
HW_version_pin = machine.Pin(14, machine.Pin.IN)

timer = machine.Timer()
led_board = None


def detect_hardware_version(pin, checks=10, interval_ms=5):
    """Read pin until its value is stable across `checks` consecutive reads,
    then classify the board: LOW = 2player, HIGH = 4player."""
    last = pin.value()
    stable_count = 1
    while stable_count < checks:
        time.sleep_ms(interval_ms)
        current = pin.value()
        if current == last:
            stable_count += 1
        else:
            last = current
            stable_count = 1
    return "4player" if last else "2player"

adjustButtons.init_buttons()



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
Log.log(f"          Version EM {SystemVersion}")
print("Contact Paul -> Paul@WarpedPinball.com")

print(
    """
 EM.Wifi (Vector) from Warped Pinball
This work is licensed under CC BY-NC 4.0
"""
)


S.hardware_version = detect_hardware_version(HW_version_pin)
Log.log(f"MAIN: Hardware version = {S.hardware_version}")

ap_mode = check_ap_button()
print("Main: AP mode = ", ap_mode)


# load up Game Definitions
if not ap_mode:
    GameDefsLoad.go()
else:
    GameDefsLoad.go(safe_mode=True)


#initialization order is important
ScoreTrack.initialize()
sensorRead.initialize()
resource.go(True)

# launch wifi, and server. Should not return
from backend import go  

# EM has no use for the periodic shadow-RAM -> FRAM mirror that other game
# systems rely on (SRAM_DATA_BASE here is a transient sensor sample buffer,
# not persistent score/game state), so it's pure wasted FRAM bus time every
# 100ms. Patched out here rather than in the shared phew/server.py scheduler
# so wpc/sys11/etc. keep running it unchanged.
import phew.server as _phew_server
_phew_server.copy_to_fram = lambda: None

print("MAIN: Launching Wifi AP mode=", ap_mode)
try:
    go(ap_mode)
finally:
    # freeze the display (stop its periodic update) rather than let it
    # keep scrolling/blinking once main has stopped driving it - covers
    # both a normal fall-through and an unhandled exception dropping to REPL
    import displayMessage
    displayMessage.stop()

Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)
