# reset pin control
import machine
from machine import Pin
import time
from logger import logger_instance

Log = logger_instance

usb_power_state = False
reset_output = None 

def init():
    global reset_output,usb_power_state
    reset_output = machine.Pin(0, machine.Pin.OUT, value=1) #hold in reset   
    print("RST: Reset control init")
  
    usb_power_pin = Pin('WL_GPIO2', Pin.IN)        
    if usb_power_pin.value() == 1:
        usb_power_state = True
        Log.log("RST: USB power ON")
        return "USB Power"
    return "Norm"

# Release reset line
def release(override=False):
    global usb_power_state, reset_output
    if reset_output is None:
        Log.log("RST: Error")
        return

    # Check for USB power
    usb_power_pin = Pin('WL_GPIO2', Pin.IN)        
    if usb_power_pin.value() == 1:
        usb_power_state = True
        Log.log("RST: _USB power ON")

    if not usb_power_state or override:
        reset_output.value(0)
        Log.log("RST: Release")

def reset():
    global reset_output
    if reset_output is None:
        print("RST: _Error")
        return
    reset_output.value(1)
    Log.log("RST: Admin Reset Cycle")
    
