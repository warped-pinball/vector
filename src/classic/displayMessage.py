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

    Digits beyond the number's significant digits (leading zeros) are
    written with the 0xF blanking code so they display blank instead of 0,
    matching the convention read by DataMapper._reversed_digit_score.
    """
    for i in range(num_digits):
        if number == 0 and i > 0:
            shadowRam[base_adr + i] = 0xF0
            continue
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
        log.log(f"MSG: init ip address {ipAddress}")

        disp = S.gdata["DisplayMessage"]
        if disp["Type"] != 30:
            log.log(f"MSG: init skipped, DisplayMessage Type is {disp['Type']} not 30")
            return

        octets = ipAddress.split(".")
        if len(octets) != 4:
            log.log(f"MSG: init skipped, invalid ip address {ipAddress}")
            return

        for idx, octet in enumerate(octets):
            base_adr = disp["Address"] + idx * disp["Spacing"]
            log.log(f"MSG: init writing octet {octet} at address {base_adr}")
            _write_reversed_digit_number(base_adr, disp["Length"], int(octet))
    except Exception as e:
        log.log(f"MSG: error in init: {e}")


def refresh():
    global ip
    init(ip)
    pass


def refresh_9():
    pass
