'''
seven segment diagnostic display on the data lines

-cannot use inside a pinball machine
-intended for network, memeory tests etc..  not machine testing

'''
from machine import Pin
import time

pins = []

segment_map = {
    '0': 0b00111111, '1': 0b00000110, '2': 0b01011011, '3': 0b01001111,
    '4': 0b01100110, '5': 0b01101101, '6': 0b01111101, '7': 0b00000111,
    '8': 0b01111111, '9': 0b01101111, 'A': 0b01110111, 'B': 0b01111100,
    'C': 0b00111001, 'D': 0b01011110, 'E': 0b01111001, 'F': 0b01110001,
    'G': 0b00111101, 'H': 0b01110110, 'I': 0b00000110, 'J': 0b00011110,
    'L': 0b00111000, 'N': 0b01010100, 'O': 0b01011100, 'P': 0b01110011,
    'q': 0b01100111, 'R': 0b01010000, 'S': 0b01101101, 'T': 0b01111000,
    'U': 0b00111110, 'U': 0b00011100, 'Y': 0b01101110, '.': 0b10000000,
    ' ': 0b00000000
}


def initialize():
    #turn off PIO state machine?
    #  should already be off with the board not in a machine (fault detected)

    #set data to l
    for i in range(14, 22):
        pin = Pin(i, Pin.OUT)
        pins.append(pin)

    #set direciton controls
    pin28 = Pin(28, Pin.OUT)
    pin28.value(1)

def display_string(s):
    for c in s:
        write_char(c)
        time.sleep(0.5) 

def write_char(c):
    c = c.upper()
    if c in segment_map:
        value = segment_map[c]
        print(value)
        for i in range(8):
            pins[i].value((value >> i) & 0x01)
    else:
        print(c," :Character not in lookup table")


if __name__ == "__main__":
    initialize()

    display_string(" 192.168.12.12444 Abcdefghijklmnopqrstuvwxyz ")

    