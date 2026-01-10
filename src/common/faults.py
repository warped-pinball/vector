# faults.py
# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

import os
import BoardLED as L
import machine
import rp2
import SharedState as S
from micropython import const
from phew import is_connected_to_wifi

# Hardware Faults
HDWR00 = const("HDWR00: Unknown Hardware Error")
HDWR01 = const("HDWR01: Early Bus Activity")
HDWR02 = const("HDWR02: No Bus Activity")

ALL_HDWR = [code[:6] for code in [HDWR00, HDWR01, HDWR02]]
                  
# Software Faults
SFWR00 = const("SFWR00: Unknown Software Error")
SFTW01 = const("SFTW01: Drop Through")
SFTW02 = const("SFTW02: async loop interrupted")

ALL_SFWR =  [code[:6] for code in [SFWR00, SFTW01, SFTW02]]

# Configuration Faults
CONF00 = const("CONF00: Unknown Configuration Error")
CONF01 = const("CONF01: Invalid Configuration")

ALL_CONF =  [code[:6] for code in [CONF00, CONF01]]

# WiFi Faults
WIFI00 = const("WIFI00: Unknown Wifi Error")
WIFI01 = const("WIFI01: Invalid Wifi Credentials")
WIFI02 = const("WIFI02: No Wifi Signal")

ALL_WIFI =  [code[:6] for code in [WIFI00, WIFI01, WIFI02]]

DUNO00 = const("DUNO00: Unknown Error")
ALL = ALL_HDWR + ALL_SFWR + ALL_CONF + ALL_WIFI + [DUNO00[:6]]


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
    if isinstance(fault, list):
        for f in fault:
            clear_fault(f)
        return

    fault_code = fault.split(":", 1)[0]

    S.faults = [f for f in S.faults if f.split(":", 1)[0] != fault_code]

    from logger import logger_instance as Log
    Log.log(f"Fault cleared: {fault}")
    update_led_sequence()


#
# LED functions
#
timer = machine.Timer()
enableWS2812led = False
sequence = [L.BLACK]
index = 0
update_sequence_continuous = 75 #about 1 minute at timer period of 790ms
LED_Out = None


def initialize_board_LED():
    global LED_Out, enableWS2812led
    enableWS2812led = bool("RP2350" in os.uname().machine and rp2 is not None)

    if not enableWS2812led:
        LED_Out = machine.Pin(26, machine.Pin.OUT)
        print("FLTS: single color LED enabled")
    else:

        def _timerCallBack(_):
            """
            Timer callback to update LED color based on fault sequence
            """
            global index, sequence, update_sequence_continuous

            # If the sequence has shortened or we reached the end, reset the index
            index = index if index < len(sequence) else 0
            L.ledColor(sequence[index])
            index = index + 1
            
            if update_sequence_continuous > 0:
                update_led_sequence()
                update_sequence_continuous -= 1

        L.startUp()
        L.ledOff()
        L.ledColor(L.BLACK)
        timer.init(period=790, mode=machine.Timer.PERIODIC, callback=_timerCallBack)
        print("FLTS: ws2812 RGB LED enabled")


def get_fault_led_sequence(fault):
    seq = []
    fault = fault[:6]

    if fault in ALL_HDWR:
        seq.append(L.RED)  # Red blink
        seq.append({HDWR00[:6]: L.PURPLE, HDWR01[:6]: L.YELLOW, HDWR02[:6]: L.WHITE}[fault])
    elif fault in ALL_SFWR:
        seq.append(L.YELLOW)  # Yellow blink
        seq.append({SFWR00[:6]: L.PURPLE, SFTW01[:6]: L.RED, SFTW02[:6]: L.WHITE}[fault])
    elif fault in ALL_WIFI:
        seq.append(L.BLUE)  # Blue blink
        seq.append({WIFI00[:6]: L.PURPLE, WIFI01[:6]: L.YELLOW, WIFI02[:6]: L.RED}[fault])
    elif fault in ALL_CONF:
        seq.append(L.WHITE)  # Cyan blink
        seq.append({CONF00[:6]: L.PURPLE, CONF01[:6]: L.YELLOW}[fault])
    elif fault == DUNO00[:6]:
        seq.append(L.WHITE)

    return seq if seq else [L.WHITE]  # unknown fault


def update_led_sequence():
    global sequence

    led_sequences = [get_fault_led_sequence(fault) for fault in S.faults]

    # Separate each fault code sequence with OFF states
    code_sep = [L.BLACK, L.BLACK, L.BLACK]
    combined_sequence = []
    for seq in led_sequences:
        combined_sequence.extend(seq)
        combined_sequence.extend(code_sep)

    if combined_sequence:
        sequence = combined_sequence
        return

    #no faults - get and report normal status
    def in_ap_mode():
        """A lightly cursed way to determine if we are in AP mode without using global memory"""
        from json import loads
        from phew.server import _routes

        route = _routes.get("/api/in_ap_mode", None)
        if route is None:
            return False
        return loads(route(0)[0])["in_ap_mode"]

    if in_ap_mode():
        combined_sequence = [L.PURPLE, L.PURPLE_DIM]  # AP mode
    elif is_connected_to_wifi():
        combined_sequence = [L.GREEN, L.GREEN_DIM]  # All OK        
    else:
        combined_sequence = [L.YELLOW, L.YELLOW_DIM, L.YELLOW_DIM]  # trying to connect (at powerup)

    sequence = combined_sequence


def toggle_board_LED(button_held=False):
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
        L.ledtoggle(button_held)

    if LED_Out is not None:
        # old single color led only
        LED_Out.toggle()
