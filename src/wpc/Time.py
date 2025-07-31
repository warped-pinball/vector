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
from Ram_Intercept import DISABLE_CLOCK_ADDRESS, DISABLE_CLOCK_DATA



def _midnight_now():
    machine.mem8[SRAM_CLOCK_HOURS] = 0x18
    machine.mem8[SRAM_CLOCK_MINUTES] = 0x01

def intiialize():
    """ call anytime to configure module to new switch settings
        reads switches out of SPI_DataStore!
        enable/disable clock
        enable/disalbe midnightmadness always on"""        
    
    if DataStore.read_record("extras", 0)["WPCTimeOn"] == False:
        log.log("TIME: enable off")
        #special code to turn off the PIO TIME Function
        machine.mem32[DISABLE_CLOCK_ADDRESS] = DISABLE_CLOCK_DATA   
    
    if DataStore.read_record("extras", 0)["MM_Always"] == True:
        _midnight_now()            
            

def trigger_midnight_madness():
    if  DataStore.read_record("extras", 0)["WPCTimeOn"] == True:
        _midnight_now()
        # Schedule trigger_end to run in 10 seconds
        global _midnight_timer
        _midnight_timer = machine.Timer(-1)
        _midnight_timer.init(mode=machine.Timer.ONE_SHOT, period=10000, callback=lambda t: _trigger_end())
        log.log("TIME: trigger MM")

def _trigger_end():
    machine.mem8[SRAM_CLOCK_HOURS] = 0
    machine.mem8[SRAM_CLOCK_MINUTES] = 0

def update_game_time():
    if  DataStore.read_record("extras", 0)["WPCTimeOn"] == True:
        import time
        t = time.localtime() 
        machine.mem8[SRAM_CLOCK_HOURS] = t[3]  # Hour (0-23)
        machine.mem8[SRAM_CLOCK_MINUTES] = t[4]  # Minute (0-59)


