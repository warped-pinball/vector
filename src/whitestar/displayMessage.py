#  Whitestar

# This file is part of the Warped Pinball Vector (Whitestar) Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
display message handling (custom message shown on the pinball machine display)

Whitestar - optionally shows the IP address in the game's custom message
(DisplayMessage Type 40 = 3 lines x 12, Type 41 = 2 lines x 24, both at
$1F41). The message is shown in attract mode while the CustomMessageOn
adjustment is 1; that byte lives in the summed main adjustment block, so
every change goes through DataMapper, which fixes the checksum.
"""

import SharedState as S
import SPI_DataStore as DataStore
import DataMapper
from logger import logger_instance
log = logger_instance

localCopyIp = 0
show_ip_last_state = False


def fixAdjustmentChecksum():
    """
    Re-sum the main adjustment block (Adjustments Type 40).
    Called by Memory_Main at boot, before the game CPU is released.
    Returns True when the stored checksum already matched.
    """
    try:
        return DataMapper.fix_adjustment_checksum()
    except Exception as e:
        log.log(f"MSG: adjustment checksum fix failed {e}")
        return True


def _set(ipAddress):
    """
    put ip address values in shadow ram
    """
    if not isinstance(ipAddress, str):
        ipAddress = "000.000.000.000"

    # the run of spaces makes the text longer than one line, so the title and
    # the IP address land on separate lines on the 2 x 24 displays too
    message = "WARPED PINBALL" + " " * 10 + ipAddress
    print("MSG: set display message ", message.strip())
    DataMapper.set_message(message)


def _blank():
    """
    clear the display message and turn it off
    """
    DataMapper.blank_message()


def init(ipAddress):
    """
    call to set the ip address to be displayed at powerup
    """
    global localCopyIp, show_ip_last_state
    localCopyIp = ipAddress
    show_ip_last_state = DataStore.read_record("extras", 0)["show_ip_address"]
    log.log(f"MSG: init ip address {ipAddress}")

    if S.gdata.get("DisplayMessage", {}).get("Type", 0) not in DataMapper.DISPLAY_MESSAGE_TYPES:
        return

    if show_ip_last_state == 1:
        _set(localCopyIp)
        print("MSG: refreshed ", localCopyIp)


def refresh():
    """refresh IP address display
    call from scheduler and any time config for "show ip address" changes
    """
    global localCopyIp, show_ip_last_state

    if S.gdata.get("DisplayMessage", {}).get("Type", 0) not in DataMapper.DISPLAY_MESSAGE_TYPES:
        return

    show_now = DataStore.read_record("extras", 0)["show_ip_address"]

    # just turned off
    if show_ip_last_state == 1 and show_now == 0:
        _blank()
        print("MSG: turned off")

    # refresh message
    if show_now == 1:
        _set(localCopyIp)
        print("MSG: refreshed ", localCopyIp)

    show_ip_last_state = show_now
