# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
User buttons ->  (+/-)
    Sensor sensitivity sdjustment
    
    EM version

"""

import micropython
from machine import Pin, Timer
import time

import sensorRead

# GPIO assignments
UP_PIN = 28     # button UP (active low)
DOWN_PIN = 27   # button DOWN (active low)
LED_PIN = 16    # LED (driven LOW to light)

# internal state
_processing = False      # debounce/in-flight flag
_pending_event = 0       # 0 = none, 1 = UP, 2 = DOWN

# hardware objects (initialized in init_buttons)
up_pin = None
down_pin = None
led_pin = None
_debounce_timer = Timer()  # single Timer instance


# --- internal handlers ---
def _scheduled_handler(event_code):
    """Runs in VM context (scheduled from IRQ) after debounce timer expires."""
    global _processing, _pending_event, up_pin, down_pin, led_pin

    code = int(event_code)
    try:
        if code == 1:
           sensorRead.sensitivityChange(1)
           print("UP")
        elif code == 2:
           sensorRead.sensitivityChange(-1)
           print("DOWN")
    finally:
        # turn LED off (active low -> set HIGH)
        led_pin.value(1)
        _pending_event = 0
        _processing = False
        # re-enable interrupts
        up_pin.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)
        down_pin.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)


def _timer_cb(t):
    """Timer callback (IRQ context) — schedule main handler to run in VM."""
    # pass the pending event code to scheduled handler (must be int)
    try:
        micropython.schedule(_scheduled_handler, _pending_event)
    except Exception:
        # If scheduling fails for any reason, try to call handler directly as fallback
        _scheduled_handler(_pending_event)


def _button_irq(pin):
    """Very small IRQ handler for both buttons."""
    global _processing, _pending_event, led_pin, _debounce_timer

    # Ignore if a press is already being processed
    if _processing:
        return

    _processing = True

    # determine which button (use pin identity)
    if pin is up_pin:
        _pending_event = 1
    else:
        _pending_event = 2

    # light LED (active low)
    led_pin.value(0)

    # disable both IRQs until processing completes
    up_pin.irq(handler=None)
    down_pin.irq(handler=None)

    # start one-shot debounce timer (500 ms)
    try:
        _debounce_timer.init(period=500, mode=Timer.ONE_SHOT, callback=_timer_cb)
    except Exception:
        # if timer init fails in this environment, schedule immediately
        micropython.schedule(_scheduled_handler, _pending_event)


# --- public init/enable/disable ---
def init_buttons():
    """Initialize pins, LED and attach interrupts. Call once at startup."""
    global up_pin, down_pin, led_pin, _processing, _pending_event

    led_pin = Pin(LED_PIN, Pin.OUT, value=1)       # default OFF (HIGH -> off)
    up_pin = Pin(UP_PIN, Pin.IN, Pin.PULL_UP)
    down_pin = Pin(DOWN_PIN, Pin.IN, Pin.PULL_UP)

    _processing = False
    _pending_event = 0

    up_pin.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)
    down_pin.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)


def enable_buttons():
    """Re-enable button interrupts (if previously disabled)."""
    up_pin.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)
    down_pin.irq(trigger=Pin.IRQ_FALLING, handler=_button_irq)


def disable_buttons():
    """Disable button interrupts."""
    up_pin.irq(handler=None)
    down_pin.irq(handler=None)






if __name__ == "__main__":

    init_buttons()
    enable_buttons()

    while 1:
        print(".", end="")
        time.sleep(1)
