# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    Warped Pinball - SYS11.Wifi
    fault check updated for early sys11 game compatability
"""


import resource
import time

import machine
import Memory_Main as MemoryMain
import reset_control
from Shadow_Ram_Definitions import shadowRam

import faults
import GameDefsLoad
import SharedState as S
from logger import logger_instance

import uctypes  


#import transparent_mode


Log = logger_instance

# other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)

#LED_Out_diag = machine.Pin(26, machine.Pin.OUT)

#timer = machine.Timer()
#led_board = None


#def error_toggle(timer):
#    led_board.toggle()


def set_error_led():
    pass
    #global led_board
    #led_board = machine.Pin(26, machine.Pin.OUT)
    #timer.init(freq=3, mode=machine.Timer.PERIODIC, callback=error_toggle)


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
        #Log.log("Main: Button press-wifi config")
        # now blink LED for a bit
        start_time = time.time()
        while time.time() - start_time < 3:
            #LED_Out.toggle()
            time.sleep(0.1)
        time.sleep(3)
        return True  # AP mode
    else:
        return False  # Normal boot mode, no button press


reset_control.init()

print("\n\n")
print("  Warped Pinball :: System11.Wifi")
#Log.log(f"          Version {S.WarpedVersion}")
print("Contact Paul -> Inventingfun@gmail.com")

print(
    """
SYS11.Wifi from Warped Pinball
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
    #Log.log("Main: Reset Circuit fault detected !!")


# load up Game Definitions
if not bus_activity_fault and not ap_mode:
    GameDefsLoad.go()
else:
    GameDefsLoad.go(safe_mode=True)



#if not bus_activity_fault:

MemoryMain.go()



# Define the memory address
import Shadow_Ram_Definitions  as RamDefs
RAM_BASE = RamDefs.SRAM_DATA_BASE #0x20041800
LENGTH = 40  # 16 bytes (0x20080000 - 0x2008000F)

#RAM_BASE = 0x50200000 + 0x024

# Access memory directly
ram_contents = uctypes.bytearray_at(RAM_BASE, 0x2000)
#ram_contents[0] = 0xF0  # Set the first byte to 0xFF
#ram_contents[1] = 0xF3  # Set the second byte to 0xFF
#ram_contents[2] = 0x5  # Set the third byte to 0xFF
#ram_contents[3] = 0x77  # Set the fourth byte to 0xFF


for i in range(LENGTH):
    ram_contents[i]=1

time.sleep(2)
reset_control.release(True)




loopCount=0
#ledIndicator = machine.Pin(26,machine.Pin.OUT)
#while True:
while loopCount < 3:
    print("------------ loop=",loopCount)
    loopCount = loopCount+1
       
    #hexdump format
    print("\nHex dump:")
    for i in range(  0 , 0+LENGTH, 4):

        addr = RAM_BASE + i

        values = " ".join([f"{ram_contents[i+j]:02X}" for j in range(4) ])

        print(f"0x{addr:08X}: {values}")



    #ledIndicator.low()
    time.sleep(1)
    #ledIndicator.high()
    time.sleep(1)





    '''    
    print("\nDMA3 SRC Register contents:")
    dma_reg_addr = 0x50200000 + 0x010  #0x500000FC
    dma_reg_contents = uctypes.bytearray_at(dma_reg_addr, 4)
    # Fix the line below to properly format each byte
    print( f" {dma_reg_contents[0]:02X}, {dma_reg_contents[1]:02X},{dma_reg_contents[2]:02X},{dma_reg_contents[3]:02X}")
    '''


#resource.go(True)

# launch wifi, and server. Should not return
from backend import go  # noqa

print("MAIN: Launching Wifi molde=",ap_mode)
go(ap_mode)
Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)


