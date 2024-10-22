'''
   on-board PICO LED driver
   
   note: This LED is actually driven by the wifi chip and requires SPI
   access. so initing this allocated SPI and DMA for Wifi chip  
'''

import machine
import utime


pico_onboard_led = machine.Pin("LED", machine.Pin.OUT)
timer = machine.Timer()

def toggle_led(timer):
    pico_onboard_led.toggle()

#functions set LED mode
def start_fast_blink():
    timer.init(freq=10, mode=machine.Timer.PERIODIC, callback=toggle_led)

def start_slow_blink():
    timer.init(freq=1, mode=machine.Timer.PERIODIC, callback=toggle_led)

def start_long_short_blink():
    timer.init(freq=1/3, mode=machine.Timer.PERIODIC, callback=toggle_led)

def off():
    timer.deinit()
    pico_onboard_led.off()

def on():
    timer.deinit()
    pico_onboard_led.on()


