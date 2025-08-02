# WPC

# This file is part of the Warped Pinball WOC - Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Time Module
    Manipulate the Hour and Minute to cause midnightmadness
        "Extras":"MM_Always"
    Set minute and hour to pico time when enabeled    
    Disable clock PIO function when disabeled (in case this breaks some machines in the future)
        "Extras":"WPCTimeOn"
    One time trigger of midnight maddess - call trigger_midnight_madness
"""
import machine
import SPI_DataStore as DataStore
from logger import logger_instance
log = logger_instance

from Shadow_Ram_Definitions import SRAM_CLOCK_MINUTES, SRAM_CLOCK_HOURS
from Ram_Intercept import DISABLE_CLOCK_ADDRESS, DISABLE_CLOCK_DATA, ENABLE_CLOCK_DATA

#this is the power up state
Time_Enabeled = True

def _midnight_now():
    machine.mem8[SRAM_CLOCK_HOURS] = 0x18
    machine.mem8[SRAM_CLOCK_MINUTES] = 0x01

def trigger_midnight_madness():
    """ call this from midnight madness now button """
    if  DataStore.read_record("extras", 0)["WPCTimeOn"] == True:
        _midnight_now()
        # trigger and then let update_game_time set back to normal      
        log.log("TIME: trigger Midnight Madness")

def update_game_time():
    print("YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY")
    """setup phew timer to call this once every minute.  handle config changes and time updates"""
    if  DataStore.read_record("extras", 0)["WPCTimeOn"] == True:
        import time
        t = time.localtime() 
        machine.mem8[SRAM_CLOCK_HOURS] = t[3]  # Hour (0-23)
        machine.mem8[SRAM_CLOCK_MINUTES] = t[4]  # Minute (0-59)

        if DataStore.read_record("extras", 0)["MM_Always"] == True:
            _midnight_now()            

    if (DataStore.read_record("extras", 0)["WPCTimeOn"] == False) and (Time_Enabeled==True):
        log.log("TIME: enable off")
        #special code to turn off the PIO TIME Function
        machine.mem32[DISABLE_CLOCK_ADDRESS] = DISABLE_CLOCK_DATA   
        Time_Enabeled=False
    
    if (DataStore.read_record("extras", 0)["WPCTimeOn"] == True) and (Time_Enabeled==False):
        log.log("TIME: enable on")
        #special code to turn off the PIO TIME Function
        machine.mem32[DISABLE_CLOCK_ADDRESS] = ENABLE_CLOCK_DATA   
        Time_Enabeled=True

   
