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

Log = logger_instance
# other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)
LED_Out = machine.Pin(26, machine.Pin.OUT)

timer = machine.Timer()
led_board = None


def error_toggle(timer):
    led_board.toggle()


def set_error_led():
    global led_board
    led_board = machine.Pin(26, machine.Pin.OUT)
    timer.init(freq=3, mode=machine.Timer.PERIODIC, callback=error_toggle)


def bus_activity_fault_check():
    # Looking for bus activity via transitions - reset hold is not working?
    pins = [machine.Pin(i, machine.Pin.IN) for i in range(14, 22)]  # Data lines
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
            LED_Out.toggle()
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



PIO0_BASE = 0x50200000
PIO1_BASE = 0x50300000
PIO2_BASE = 0x50400000  # Hypothetical for RP2350, confirm in datasheet

# Define register offsets
CTRL_OFFSET = 0x00
FSTAT_OFFSET = 0x04
SM0_EXECCTRL_OFFSET = 0x0C
SM0_CLKDIV_OFFSET = 0x10
SM0_SHIFTCTRL_OFFSET = 0xD0  # Add SHIFTCTRL register offset

def read_pio_status(pio_base):
    """Read and print PIO status."""
    ctrl = machine.mem32[pio_base + CTRL_OFFSET]
    fstat = machine.mem32[pio_base + FSTAT_OFFSET]
    sm0_execctrl = machine.mem32[pio_base + SM0_EXECCTRL_OFFSET]
    sm0_clkdiv = machine.mem32[pio_base + SM0_CLKDIV_OFFSET]
    sm0_shiftctrl = machine.mem32[pio_base + SM0_SHIFTCTRL_OFFSET]  # Read SHIFTCTRL

    print(f"PIO Base: {hex(pio_base)}")
    print(f"  CTRL: {hex(ctrl)}")
    print(f"  FSTAT: {hex(fstat)}")
    print(f"  SM0_EXECCTRL: {hex(sm0_execctrl)}")
    print(f"  SM0_CLKDIV: {hex(sm0_clkdiv)}")
    print(f"  SM0_SHIFTCTRL: {hex(sm0_shiftctrl)}")  # Print SHIFTCTRL value




#machine.mem32[0x50000000 + 0x3C0] = 0x55

while 1:
    print("k")

    # Print 64 bytes of data starting from 0x2007FFC0
    #base_address = 0x2007FFC0
    length = 64

    base_address = 0x50400000 + 0x48


    bytes_per_row = 16

    print(f"Memory Dump (starting at 0x{base_address:08X}, length {length} bytes):")
    print("Address    | 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F")
    print("-----------+------------------------------------------------")

    for offset in range(0, length, bytes_per_row):
        # Print the starting address of the row
        row_address = base_address + offset
        print(f"0x{row_address:08X} | ", end="")

        # Print the 16 bytes in the row
        for i in range(bytes_per_row):
            byte_address = row_address + i
            byte_value = machine.mem8[byte_address]  # Read 8-bit value
            print(f"{byte_value:02X} ", end="")

        print("")  # Newline after each row

    print("")  # Extra newline for spacing


    ram_value = machine.mem32[0x50200000 + 0xCC]
    # Print the value in hexadecimal format
    print(f"RAM[0x50200000 + 0CC]: {hex(ram_value)}")

    ram_value = machine.mem32[0x50300000 + 0xCC]
    # Print the value in hexadecimal format
    print(f"RAM[0x50300000 + 0xCC]: {hex(ram_value)}")

    ram_value = machine.mem32[0x50000000 + 0x280]
    # Print the value in hexadecimal format
    print(f"RAM[0x50000000 + 0x280]: {hex(ram_value)}")


    ram_value = machine.mem32[0x50000000 + 0x3C0]
    # Print the value in hexadecimal format
    print(f"RAM[0x50000000 + 0x3C0]: {hex(ram_value)}")



    # Set bit 30 in the register at location 0x504000CC
    reg_addr = 0x504000CC
    current_value = machine.mem32[reg_addr]
    machine.mem32[reg_addr] = current_value | (1 << 30)
    print(f"Set bit 30: 0x{reg_addr:08X} = {hex(machine.mem32[reg_addr])}")




    #machine.mem32[0x2007ffc0]=0xA5




    time.sleep(4)


time.sleep(0.5)
reset_control.release(True)
time.sleep(1)

resource.go(True)

# launch wifi, and server. Should not return
from backend import go  # noqa: E402

print("MAIN: Launching Wifi AP mode=", ap_mode)
go(ap_mode)
Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)
