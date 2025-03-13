# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
    Warped Pinball - SYS11.Wifi
    fault check updated for early sys11 game compatability
"""

import resource
import time
from time import sleep

import machine
import Memory_Main as MemoryMain
import reset_control
from Shadow_Ram_Definitions import shadowRam

import faults
import GameDefsLoad
import SharedState as S
from logger import logger_instance
Log = logger_instance

import uos
#from SPI_Store import initialize as initialize_spi_store
import uasyncio
import uselect
import sys


incoming_data = []


# other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)
LED_Out = machine.Pin(26, machine.Pin.OUT)

timer = machine.Timer()

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


def adr_activity_ok():
    initial_values = [shadowRam[i] for i in range(0x10, 0x18)]

    for _ in range(20):
        # shadowRam locs 0x10 to 0x18 (lamp columns)
        current_values = [shadowRam[i] for i in range(0x10, 0x18)]
        # Changing?
        if current_values != initial_values:
            Log.log("Main: Acitivy Check OK")
            return True
        time.sleep_ms(100)

    faults.raise_fault(faults.HDWR02)
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
        Log.log("Main: Button press-wifi config")
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
print("  Warped Pinball :: System11.Wifi")
Log.log(f"          Version {S.WarpedVersion}")
print("Contact Paul -> Inventingfun@gmail.com")

print(
    """
SYS11.Wifi from Warped Pinball
This work is licensed under CC BY-NC 4.0
"""
)

ap_mode = check_ap_button()
bus_activity_fault = bus_activity_fault_check()
if bus_activity_fault:
    set_error_led()
    faults.raise_fault(faults.HDWR01)
    print("Main: Bus Activity fault detected !!")
    Log.log("Main: Reset Circuit fault detected !!")

# load up Game Definitions
if not bus_activity_fault and not ap_mode:
    GameDefsLoad.go()
else:
    GameDefsLoad.go(safe_mode=True)

if not bus_activity_fault:
    MemoryMain.go()






async def main_task():
    global incoming_data

    for x in range(4):
        print("test line from vector bootup ", x)        
        await uasyncio.sleep(0.5)

    while True:
        #print("continue running")        
        if incoming_data:
            buffer = incoming_data.pop(0)  #pops a string from the list        
            #print(f"Processing buffer in main_task: {buffer}")
            #print("incomming st#ff ")
            search_str = "VECTOR: display "
            index = buffer.find(search_str)            
            if index != -1 and index + len(search_str) < len(buffer):
                char_to_send = buffer[index + len(search_str)]
                #print(f"Character to send to diagdisplay: {char_to_send}")
                disp.write_char(char_to_send)
        await uasyncio.sleep(1)

async def main():
    # Create tasks for both the usb_data_handler and main_task
    usb_task = uasyncio.create_task(usb_data_handler())
    main_task_instance = uasyncio.create_task(main_task())

    # Wait for both tasks to complete (they won't, because they run indefinitely)
    await usb_task
    await main_task_instance

async def usb_data_handler():
    """get serial data from the serial port"""
    global incoming_data
    poller = uselect.poll()
    poller.register(sys.stdin, uselect.POLLIN)
    buffer = ""
    
    while True:
        while poller.poll(0):
            data = sys.stdin.read(1)
            if data in ('\n','\r'):
                if buffer: #if buffer is not empty and string has been terminated by \n or \r
                    print(f"Data received at vector: {buffer}")
                    incoming_data.append(buffer)                    
                    buffer = ""
            else:
                buffer += data
                if len(buffer) > 500:
                    buffer = ""
        await uasyncio.sleep(0.1)




# Run the main coroutine
uasyncio.run(main())

print("PAST UASYNC MAIN CALL NOw")

time.sleep(0.5)
reset_control.release(True)
time.sleep(4)
resource.go(True)

# launch wifi, and server. Should not return
from backend import go  # noqa

Log.log("MAIN: Launching Wifi")
go(ap_mode)
Log.log("MAIN: drop through fault")
faults.raise_fault(faults.SFTW01)





