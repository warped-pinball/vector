# WPC

# This file is part of the Warped Pinball WOC - Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Time Module
    Manipulate the Hour and Minute to cause midnight madness
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
import SharedState as S

from Shadow_Ram_Definitions import SRAM_CLOCK_MINUTES, SRAM_CLOCK_HOURS
from Ram_Intercept import enableClockCapture, disableClockCapture 

#this is the power up state
Time_Enabeled = True
MM_Trigger_Active_Count = 0

def initialize():
    #set schedule call back
    from phew import server
    server.schedule(update_game_time, 25000, 30000)

def _midnight_now():
    machine.mem8[SRAM_CLOCK_HOURS] = 0x18
    machine.mem8[SRAM_CLOCK_MINUTES] = 0x01

def trigger_midnight_madness():
    """ call this from midnight madness now button """
    global MM_Trigger_Active_Count
    if  DataStore.read_record("extras", 0)["WPCTimeOn"] == True:
        _midnight_now()
        # trigger and then let update_game_time set back to normal      
        log.log("TIME: trigger Midnight Madness")
        MM_Trigger_Active_Count = 3

def update_game_time():    
    """setup phew timer to call this once every minute.  handle config changes and time updates"""
    global Time_Enabeled,MM_Trigger_Active_Count   

    if S.gdata.get("GameInfo", {}).get("Clock") != "MM":
        return

    if MM_Trigger_Active_Count == 0:
        if  DataStore.read_record("extras", 0)["WPCTimeOn"] == True:
            if DataStore.read_record("extras", 0)["MM_Always"] == True:
                _midnight_now()    
            else:
                import time
                t = time.localtime() 
                machine.mem8[SRAM_CLOCK_HOURS] = 0x17     #t[3]  # Hour (0-23) might go back to this with twilight zone
                machine.mem8[SRAM_CLOCK_MINUTES] = 0x20   #t[4]  # Minute (0-59)                   

        if (DataStore.read_record("extras", 0)["WPCTimeOn"] == False) and (Time_Enabeled==True):        
            log.log("TIME: enable off")          
            disableClockCapture()
            Time_Enabeled=False
        
        if (DataStore.read_record("extras", 0)["WPCTimeOn"] == True) and (Time_Enabeled==False):
            log.log("TIME: enable on")          
            disableClockCapture()
            Time_Enabeled=True
    else:
        MM_Trigger_Active_Count=MM_Trigger_Active_Count-1
   
