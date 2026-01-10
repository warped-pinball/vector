import os

import BoardLED as L
import machine
import rp2
import SharedState as S
from micropython import const

# Hardware Faults
HDWR00 = const("HDWR00: Unknown Hardware Error")
HDWR01 = const("HDWR01: Early Bus Activity")
HDWR02 = const("HDWR02: No Bus Activity")

ALL_HDWR = [HDWR00[:6], HDWR01[:6], HDWR02[:6]]

# Software Faults
SFWR00 = const("SFWR00: Unknown Software Error")
SFTW01 = const("SFTW01: Drop Through")
SFTW02 = const("SFTW02: async loop interrupted")

ALL_SFWR = [SFWR00[:6], SFTW01[:6], SFTW02[:6]]

# Configuration Faults
CONF00 = const("CONF00: Unknown Configuration Error")
CONF01 = const("CONF01: Invalid Configuration")

ALL_CONF = [CONF00[:6], CONF01[:6]]

# WiFi Faults
WIFI00 = const("WIFI00: Unknown Wifi Error")
WIFI01 = const("WIFI01: Invalid Wifi Credentials")
WIFI02 = const("WIFI02: No Wifi Signal")

ALL_WIFI = [WIFI00[:6], WIFI01[:6], WIFI02[:6]]

DUNO00 = const("DUNO00: Unknown Error")
ALL = ALL_HDWR + ALL_SFWR + ALL_CONF + ALL_WIFI + [DUNO00]


def raise_fault(fault, msg=None):
    if msg is not None and not isinstance(msg, str):
        msg = str(msg)

    # If the fault is already raised, don't raise it again
    if fault_is_raised(fault):
        return

    if S.faults is None or not isinstance(S.faults, list):
        S.faults = []

    full_fault = f"{fault} - {msg}" if msg else fault
    S.faults.append(full_fault)

    from logger import logger_instance as Log

    Log.log(f"Fault raised: {full_fault}")

    # get the LED sequence for this fault
    update_led_sequence()


def fault_is_raised(fault):
    if isinstance(fault, str):
        faults = [fault]
    elif isinstance(fault, list):
        faults = fault
    else:
        raise ValueError("fault must be a string or a list of strings")

    for f in faults:
        fault_code = f.split(":")[0]
        if fault_code in [x.split(":")[0] for x in S.faults]:
            return True
    return False


def clear_fault(fault):
    for f in S.faults:
        fault_code = f.split(":")[0]
        S.faults = [x for x in S.faults if x.split(":")[0] != fault_code]

    from logger import logger_instance as Log

    Log.log(f"Fault cleared: {fault}")


#
# LED functions
#

timer = machine.Timer()
enableWS2812led = None
LED_Out = None
sequence = [L.BLACK]
index = 0
update_sequence_continuous=True


def isChip2350():
    """
    Determine if we are running on 2350 with PIO support for new ws2812 LED
    """
    chip_id = os.uname().machine

    if "RP2350" in chip_id and rp2 is not None:
        print("FLTS: Pico 2 (RP2350) detected")
        return True
    return False


def init_led():
    """
    start up fault indicator once
    """
    global LED_Out, timer, enableWS2812led
    enableWS2812led = isChip2350()
   
    if not enableWS2812led:
        LED_Out = machine.Pin(26, machine.Pin.OUT)
    else:
        L.startUp()
        L.ledOff()
        L.ledColor(L.BLACK)
        timer.init(period=790, mode=machine.Timer.PERIODIC, callback=_timerCallBack)



def _timerCallBack(_):
    """
    Timer callback to update LED color based on fault sequence
    """
    global index, sequence, update_sequence_continuous

    # If the sequence has shortened or we reached the end, reset the index
    index = index if index < len(sequence) else 0
    L.ledColor(sequence[index])
    index = index + 1

    if update_sequence_continuous is True:
        update_led_sequence()


def get_fault_led_sequence(fault):
    seq = []

    if fault in ALL_HDWR:
        seq.append(L.RED)  # Red blink
        seq.append({HDWR00: L.PURPLE, HDWR01: L.YELLOW, HDWR02: L.WHITE}[fault])
    elif fault in ALL_SFWR:
        seq.append(L.YELLOW)  # Yellow blink
        seq.append({SFWR00: L.PURPLE, SFTW01: L.RED, SFTW02: L.WHITE}[fault])
    elif fault in ALL_WIFI:
        seq.append(L.BLUE)  # Blue blink
        seq.append({WIFI00[:6]: L.PURPLE, WIFI01[:6]: L.YELLOW, WIFI02[:6]: L.RED}[fault])
    elif fault in ALL_CONF:
        seq.append(L.WHITE)  # Cyan blink
        seq.append({CONF00: L.PURPLE, CONF01: L.YELLOW}[fault])
    elif fault == DUNO00:
        seq.append(L.PURPLE) 

    return seq if seq else [L.PURPLE]  # Magenta for unknown fault


def update_led_sequence():  
    global update_sequence_continuous

    fault_codes = [f.split(":")[0] for f in S.faults]
    led_sequences = [get_fault_led_sequence(fault) for fault in fault_codes]

    # Separate each fault code sequence with OFF states
    code_sep = [L.BLACK, L.BLACK, L.BLACK]
    combined_sequence = []
    for seq in led_sequences:
        combined_sequence.extend(seq)
        combined_sequence.extend(code_sep)

    #if no fault then report state on LED (single color, with DIM blinks)
    if not combined_sequence:        
        if getattr(S, "wifi_connected", False) is True:
            combined_sequence = [L.GREEN, L.GREEN_DIM]        # All OK
            update_sequence_continuous=False
        else:
            if getattr(S, "wifi_AP_mode", False) is True:
                combined_sequence = [L.PURPLE,L.PURPLE_DIM]   # AP mode
            else:
                combined_sequence = [L.YELLOW,L.YELLOW_DIM,L.YELLOW_DIM]   # trying to connect (at powerup)
    else:
        update_sequence_continuous=False

    global sequence
    sequence = combined_sequence





init_led()






def toggleBoardLED(buttonHeld=False):
    """
    Legacy interface to led function
      -works if we are on a PICO1 without BoardLED running
      -works on PICO2 with BoardLED and only single color LED installed
      -runs with no effect on PICO2 with only ws2812 led installed

      -button held for power up AP mode without timer resources running yet
    """

    global enableWS2812led
    if enableWS2812led is True:
        # ws2812 driver - control of RGB LED
        print("Faults: toggle Board LED ws2812")
        L.ledtoggle(buttonHeld)

    if LED_Out is not None:
        # old single color led only
        print("Faults: toggle Board LED single color")
        LED_Out.toggle()
