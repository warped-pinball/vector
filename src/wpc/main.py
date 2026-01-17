# WPC

# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    Warped Pinball - WPC.Wifi
    fault check updated for early sys11 game compatability
"""

import resource
import time

import faults
import GameDefsLoad
import machine
import Memory_Main as MemoryMain
import reset_control
from logger import logger_instance
from systemConfig import SystemVersion
from machine import Pin

import Formats

Log = logger_instance
# other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)

timer = machine.Timer()
led_board = None

faults.initialize_board_LED()

def error_toggle(timer):
    faults.toggle_board_LED()


def set_error_led():
    timer.init(freq=3, mode=machine.Timer.PERIODIC, callback=error_toggle)


def bus_activity_fault_check():
    # Looking for bus activity via transitions - reset hold is not working?
    pins = [machine.Pin(i, machine.Pin.IN) for i in range(6, 11)]  # changes made here specific to WPC hardware
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
            faults.toggle_board_LED(button_held=True)
            time.sleep(0.1)
        time.sleep(3)
        return True  # AP mode
    else:
        return False  # Normal boot mode, no button press


reset_control.init()

print("\n\n")
print("  Warped Pinball :: System WPC.Wifi")
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

usb_power_pin = Pin("WL_GPIO2", Pin.IN)
if usb_power_pin.value() == 1:
    usb_power_state = True
    bus_activity_fault=False
else:    
    bus_activity_fault = bus_activity_fault_check()
    if bus_activity_fault:
        set_error_led()
        faults.raise_fault(faults.HDWR01)
        print("Main: Bus Activity fault detected !!")
        # Log.log("Main: Reset Circuit fault detected !!")


# load up Game Definitions
if not bus_activity_fault and not ap_mode:
    GameDefsLoad.go()
else:
    GameDefsLoad.go(safe_mode=True)

if not bus_activity_fault:
    MemoryMain.go()


import Time
Time.initialize()

time.sleep(0.5)
reset_control.release(True)
time.sleep(1)

resource.go(True)


Formats.test()

# launch wifi, and server. Should not return
from backend import go  # noqa: E402

print("MAIN: Launching Wifi AP mode=", ap_mode)
go(ap_mode)
Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)
