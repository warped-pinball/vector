# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
display message for EM machines

handles on board displays only - LEDs for all the inputs
  and the d=single digit 7 segment for IP address and fault codes

"""


import SharedState as S
import SPI_DataStore as DataStore
from logger import logger_instance
log = logger_instance

localCopyIp = 0

def fixAdjustmentChecksum():
    """
    fixes the CRC in the adjustments according to machine type
        not used on system 9
        system 11 with type 0 will only report check sum, not fix it
    """
    pass


def _set(ipAddress):
    """
    put ip address values in shadow ram
    """
    if not isinstance(ipAddress, str):
        ipAddress = "000.000.000.000"

   

def init(ipAddress):
    """call to set the ip address to be displayed
    at powerup
    """
    global localCopyIp, show_ip_last_state
    localCopyIp = ipAddress
    show_ip_last_state = DataStore.read_record("extras", 0)["show_ip_address"]

    log.log(f"MSG: init ip address {ipAddress}")

    return


def refresh():
    """refresh IP address display
    call from schduler and any time config for "show op address" changes
    """
    global localCopyIp, show_ip_last_state

    if show_ip_last_state and DataStore.read_record("extras", 0)["show_ip_address"]:
        if S.gdata["HighScores"]["Type"] in [1, 2, 3]:
            # turn off custom message
            shadowRam[S.gdata["DisplayMessage"]["EnableByteAddress"]] = 1
            fixAdjustmentChecksum()

    show_ip_last_state = DataStore.read_record("extras", 0)["show_ip_address"]

    if S.gdata["HighScores"]["Type"] in [1, 2, 3] and DataStore.read_record("extras", 0)["show_ip_address"]:
        _set(localCopyIp)
        print("MSG: refreshed ", localCopyIp)
        return

    if S.gdata["HighScores"]["Type"] == 9:
        pass

