#  Data East



# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
display message handling (custom message shown on the pinball machine display)

Data East - optionally shows IP address in high score display
"""

from Shadow_Ram_Definitions import shadowRam
import SharedState as S
import SPI_DataStore as DataStore
import DataMapper
from logger import logger_instance
log = logger_instance

localCopyIp = 0
show_ip_last_state = False


def fixAdjustmentChecksum():
    pass
    return
  

def _set(ipAddress):
    """
        put ip address values in shadow ram
    """
    if not isinstance(ipAddress, str):
        ipAddress = "000.000.000.000"

    ipAddress = "WARPED PINBALL " + ipAddress
    print("MSG: set display message ", ipAddress)
    DataMapper.set_message(ipAddress)


def _blank():
    """
        clear the display message
    """
    str = " " * 48
    DataMapper.set_message(str)
    DataMapper.enable_message(False)
    


def init(ipAddress):
    """
        call to set the ip address to be displayed at powerup
    """
    global localCopyIp, show_ip_last_state
    localCopyIp = ipAddress
    show_ip_last_state = DataStore.read_record("extras", 0)["show_ip_address"]
    log.log(f"MSG: init ip address {ipAddress}")

    if DataStore.read_record("extras", 0)["show_ip_address"] == 1:
        _set(localCopyIp)
        print("MSG: refreshed ", localCopyIp)
   


def refresh():
    """refresh IP address display
    call from schduler and any time config for "show ip address" changes
    """
    global localCopyIp, show_ip_last_state
    
    #just turned off 
    if show_ip_last_state==1 and DataStore.read_record("extras", 0)["show_ip_address"]==0:
        # turn off custom message                
        _blank()        
        print("MSG: turned off")
        
    #refresh message    
    if DataStore.read_record("extras", 0)["show_ip_address"] == 1:
        _set(localCopyIp)
        print("MSG: refreshed ", localCopyIp)
        
    show_ip_last_state = DataStore.read_record("extras", 0)["show_ip_address"]

