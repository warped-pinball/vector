# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
"""
  Wifi Main
  SYS11Wifi Project from Warped Pinball
  Components from Phew library included here 
  https://github.com/pimoroni/phew/blob/main/LICENSE
"""
from phew import access_point, connect_to_wifi, is_connected_to_wifi, dns, server 
from phew.template import render_template
import json
import machine
import os
import utime
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH, SRAM_COUNT_BASE
import uctypes
import gc
import micropython
import displayMessage
from Memory_Main import save_ram,blank_ram
import time
import Pico_Led
import SharedState
import SPI_DataStore as DataStore
import FileIO
from SPI_DataStore import writeIP
import GameStatus
import reset_control

ip_address=0
cycle_count = 1
ram_access = uctypes.bytearray_at(SRAM_DATA_BASE,SRAM_DATA_LENGTH)
count_access = uctypes.bytearray_at(SRAM_COUNT_BASE,SRAM_DATA_LENGTH)            
adr_display = 0

PassWordFail = False

IndividualActivePlayerInit = ""
IndividualActivePlayerNum = 0

AP_NAME = "WarpedPinball"
AP_DOMAIN = "system11.net"
AP_TEMPLATE_PATH = "ap_templates"
APP_TEMPLATE_PATH = "app_templates"
WIFI_FILE = "wifi.json"
WIFI_MAX_ATTEMPTS = 12

#run WIFI - gets connected and starts the web server
#  timed functions are spawned in server.py, event driven stuff in wifi_main.py
#  This call DOES NOT RETURN unless there is a fault
def go(configWifi,fault_msg): 
 global ip_address
 try:
    Pico_Led.start_slow_blink()

    #load credentials here - if blank go to AP mode
    wifi_credentials = DataStore.read_record("configuration",0) 
    print("WIFI: Credentials:",wifi_credentials)
    if wifi_credentials["ssid"] is None or len(wifi_credentials["ssid"])<4:
        configWifi = True

    if configWifi:  #setup (AP mode)
        print("WIFI: go to setup mode - open AP")    
        setup_mode(fault_msg)        
    else:           #normal run
        wifi_current_attempt = 1
       
        while (wifi_current_attempt < WIFI_MAX_ATTEMPTS):
            ssid = wifi_credentials["ssid"].strip()
            password = wifi_credentials["password"].strip()
            print(f"WIFI: Attempt Join with:@{ssid}@{password}@") 
            ip_address = connect_to_wifi(ssid,password) 
            print("WIFI: returned from connect function")            
            if is_connected_to_wifi():
                print(f"WIFI: Connected to wifi-> IP address {ip_address}")
                #send ip address to storage for setup screen
                writeIP(ip_address)
                break            
            else:
                print("WIFI: no good, try again")
                wifi_current_attempt += 1
                        
        if is_connected_to_wifi():            
            #Some module inits here, but watch out for faults - will cause wifi exception
            Pico_Led.on()
            try:
                displayMessage.init(ip_address)                 
            except Exception as e:
                print("WIFI: Fault after connection in init sequence")
                print("WIFI: Error details", str(e)) 
            application_mode(fault_msg)    
            
        else:            
            # WIFI fail - not much to do here, issue warning and go ahead without wifi connection
            print("WIFI: Connection Fail!")
            print("WIFI: ",wifi_credentials)
            application_mode(fault_msg)
            
 except Exception:
    print("WIFI: go to setup mode - from fault")    
    setup_mode(fault_msg)

 # Start the web server...
 print("WIFI: Run Server ") 
 server.run()
 print("WIFI: Back From Run Server Fault")
 

 
if __name__ == "__main__":
    print("test call applicaiton mode")
    application_mode(None)
