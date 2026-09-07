# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    Warped Pinball - Vector :: Classic
"""
import nonblocking_print  # noqa: F401  -- must be first; installs non-blocking print()

#allocate DMA - wifi chip channel now
import Pico_Led
Pico_Led.on()

import resource
import time

import faults
import GameDefsLoad
import machine
import Memory_Main as MemoryMain
import Ram_Intercept_classics as RamInt
import reset_control
import SharedState
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

def bus_activity_fault_check():
    # Looking for bus activity via transitions - reset hold is not working?
    # Classics: only watch the address lines A0-A8. These are the address-bus
    # GPIO (FIRST_ADR_PIN..FIRST_DATA_PIN, i.e. 6..13), muxed via A_Select.
    # Data lines (GPIO 14+) are intentionally ignored.
    pins = [machine.Pin(i, machine.Pin.IN) for i in range(6, 14)]  # A0-A8, classics hardware
    transitions = 0
    total_reads = 0
    start_time = time.ticks_us()
    previous_states = [pin.value() for pin in pins]

    while time.ticks_diff(time.ticks_us(), start_time) < 800000:
        for i, pin in enumerate(pins):
            current_state = pin.value()
            if current_state != previous_states[i]:
                transitions += 1
                previous_states[i] = current_state
        total_reads += 1

    Log.log(f"Total reads: {total_reads}")
    Log.log(f"Total transitions: {transitions}")

    if transitions > 250:
        return True  # Fault
    else:
        return False  # All ok


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

# check for early bus activity (reset hold not working) on address lines A0-A8
bus_activity_fault = bus_activity_fault_check()
if bus_activity_fault:
    faults.raise_fault(faults.HDWR01)
    print("Main: Bus Activity fault detected !!")
    Log.log("Main: Early bus activity - reset hold fault")

# load up Game Definitions
if not bus_activity_fault and not ap_mode:
    GameDefsLoad.go()
else:
    GameDefsLoad.go(safe_mode=True)

if not bus_activity_fault:
    MemoryMain.go()

    # MPU-200 boards have full-byte RAM at 0x100-0x200
    # so the low-nibble forcer state machine needs to be disabled for them.
    is_mpu200 = SharedState.gdata.get("GameInfo", {}).get("System") == "MPU200"
    RamInt.enableMPU200Mode(is_mpu200)


time.sleep(1)
reset_control.release(True)
time.sleep(1)

resource.go(True)
Switches.initialize()
Formats.initialize()

# launch wifi, and server. Should not return
from backend import go  # noqa

Log.log("MAIN: Launching Wifi")
go(ap_mode)
Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)
