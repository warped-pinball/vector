# import dma_reg as dma_d
import time

import machine
from machine import Pin

# RESET_OUT pin initializtion
reset_out = Pin(0, Pin.OUT)
reset_out.value(1)  # hold main board in reset

# data direction
data_dir = Pin(28, Pin.OUT)
data_dir.low()

# on board LED
ledIndicator = machine.Pin(26, machine.Pin.OUT)
ledIndicator.low()  # low is ON

# A_Select pin initializtion
a_select = Pin(27, Pin.OUT)
a_select.low()


time.sleep(5)

reset_out.value(0)  # release main board reset
loopCount = 0

while True:
    print("------------ loop=", loopCount)
    loopCount = loopCount + 1

    ledIndicator.low()
    time.sleep(1)
    ledIndicator.high()
    time.sleep(1)
