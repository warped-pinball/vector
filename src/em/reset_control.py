# reset pin control
import machine
from machine import Pin
from logger import logger_instance
Log = logger_instance
usb_power_state = False

def init():
    global usb_power_state
    print("RST: Reset control init")

    usb_power_pin = Pin("WL_GPIO2", Pin.IN)
    if usb_power_pin.value() == 1:
        usb_power_state = True
        Log.log("RST: USB power ON")
        return "USB Power"
    return "Norm"


# Release reset line
def release(override=False):
    pass

def reset():    
    Log.log("RST: Admin Reset Cycle")
