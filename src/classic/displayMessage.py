# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
display message handling (custom message shown on the pinball machine display)

classics - stub implementation (functions are empty but callable)
"""

import SharedState as S
from Shadow_Ram_Definitions import shadowRam

from logger import logger_instance
log = logger_instance

ip=""

def fixAdjustmentChecksum():
    pass


def _write_reversed_digit_number(base_adr, num_digits, number):
    """
    Encode number into shadow RAM in the same format InPlay.Type 30 scores
    use: one decimal digit per byte, upper nibble, least-significant digit
    first (base_adr is the ones digit, base_adr+1 the tens digit, etc).
    """
    for i in range(num_digits):
        digit = number % 10
        number //= 10
        shadowRam[base_adr + i] = digit << 4


def init(ipAddress):
    """
    Write the IP address into shadow RAM for display (classics)

    DisplayMessage.Type 30: the IP address's 4 octets are written one per
    "score area", Spacing bytes apart starting at Address - matching the
    layout DataMapper.get_live_scores() reads player scores from.
    """
    global ip
    
    try:
        ip=ipAddress

        disp = S.gdata["DisplayMessage"]
        if disp["Type"] != 30:
            return

        octets = ipAddress.split(".")
        if len(octets) != 4:
            return

        for idx, octet in enumerate(octets):
            base_adr = disp["Address"] + idx * disp["Spacing"]
            _write_reversed_digit_number(base_adr, disp["Length"], int(octet))
    except Exception as e:
        log.log(f"MSG: error in init: {e}")


def refresh():
    global ip
    init(ip)
    pass


def refresh_9():
    pass
