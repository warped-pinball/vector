# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
'''
    Warped Pinball - SYS11.Wifi
    fault check updated for early sys11 game compatability
'''

# import Wifi_Main as Wifi
import Memory_Main as MemoryMain
import machine
from machine import Pin
from time import sleep
from uctypes import BF_POS, BF_LEN, UINT32, BFUINT32, struct
import displayMessage
import time
import resource
import reset_control
import GameDefsLoad
import SharedState as S
from Shadow_Ram_Definitions import shadowRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
from logger import logger_instance
Log = logger_instance

#other gen I/O pin inits
SW_pin = machine.Pin(22, machine.Pin.IN)
AS_output = machine.Pin(27, machine.Pin.OUT, value=0)
DD_output = machine.Pin(28, machine.Pin.OUT, value=0)
LED_Out = machine.Pin(26, machine.Pin.OUT)

timer = machine.Timer()
led_board=None

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
        return True   # Fault
    else:
        return False  # All ok


def adr_activity_check():
    initial_values = [shadowRam[i] for i in range(0x10, 0x18)]

    for _ in range(20):
        #shadowRam locs 0x10 to 0x18 (lamp columns)
        current_values = [shadowRam[i] for i in range(0x10, 0x18)]
        # Changing?
        if current_values != initial_values:
            Log.log("Main: Acitivy Check OK")
            return "Pass"  
        time.sleep_ms(100)
    
    Log.log("Main: Acitivy Check FAIL")
    return "Fail"


def check_ap_button():
    #holding down AP setup button?
    zero_count = 0
    num_Checks = 5
    for _ in range(num_Checks):    
        pin_state = SW_pin.value()
        if pin_state == 0:
            zero_count += 1

    if (zero_count == num_Checks):        
        Log.log("Main: Button press-wifi config")
        #now blink LED for a bit
        start_time = time.time()
        while time.time() - start_time < 3:
            LED_Out.toggle()        
            time.sleep(0.1)      
        time.sleep(3)
        return(True)  # AP mode
    else:
        return(False)  # Normal boot mode, no button press
     
reset_control.init()

print("\n\n")
print("  Warped Pinball :: System11.Wifi")
Log.log(f"          Version {S.WarpedVersion}")
print("Contact Paul -> Inventingfun@gmail.com")

print("""
SYS11.Wifi from Warped Pinball 
This work is licensed under CC BY-NC 4.0     
""")

ap_mode = check_ap_button()
bus_activity_fault = bus_activity_fault_check() 
if bus_activity_fault == True:
    set_error_led()
    S.installation_fault = True
    fault_msg = "Installation Fault Detected"
    Log.log("Main: Reset Circuit fault detected !!")
else:
    fault_msg = None

#load up Game Definitions
if bus_activity_fault==False and ap_mode==False:
    GameDefsLoad.go() 
else:
    GameDefsLoad.go(safe_mode=True)

if bus_activity_fault == False:
    MemoryMain.go()     

time.sleep(0.5) 
reset_control.release(True)
time.sleep(4) 

if bus_activity_fault == False:
    if "Fail"==adr_activity_check():
        reset_control.reset()
        time.sleep(2)
        reset_control.release(True)

#launch wifi, and server. Should not return
from backend import go
go(ap_mode,fault_msg)   #ap mode / bus fault
# Wifi.go(ap_mode,fault_msg)   #ap mode / bus fault

Log.log("MAIN: drop through fault")
