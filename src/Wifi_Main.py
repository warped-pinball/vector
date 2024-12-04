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

#Allocate PICO led early - this grabs DMA0&1 and PIO1_SM0 before memory interfaces setup
#wifi uses PICO LED to indicate status (since it is on wifi chip via spi also)   
Pico_Led.off()

#print("thres----  ",gc.threshold())
gc.threshold(2048 * 6) 

def get_content_type(file_path):
    content_type_mapping = {
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.html': 'text/html',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.gz': 'application/gzip'
    }
    for extension, content_type in content_type_mapping.items():
        if file_path.endswith(extension):
            return content_type
    return 'application/octet-stream'


# define streaming file service route
def serve_file(file_path):
    def route(request):
        print(f"Attempting to serve file @ {file_path}")
        try:
            headers = {
                'Content-Type': get_content_type(file_path),
                'Connection': 'close'
            }

            def file_stream_generator():
                gc.collect()
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(1024)  # Read in chunks of 1KB
                        if not chunk:
                            break
                        yield chunk
                gc.collect() 

            print("File opened successfully")
            return file_stream_generator(), 200, headers

        except OSError as e:
            error_message = "File Not Found" if e.errno == 2 else "Internal Server Error"
            print(f"Error: {error_message} - {e}")
            gc.collect()
            return f"<html><body><h1>{error_message}</h1></body></html>", 404 if e.errno == 2 else 500, {'Content-Type': 'text/html', 'Connection': 'close'}

        except Exception as e:
            print(f"Unexpected Error: {e}")
            gc.collect()
            return "<html><body><h1>Internal Server Error</h1></body></html>", 500, {'Content-Type': 'text/html', 'Connection': 'close'}
    return route

# find all files in the web directory
def list_files(top):
    try:
        entries = os.listdir(top)
    except OSError:
        return
    for entry in entries:
        path = top + "/" + entry if top != "/" else "/" + entry
        try:
            mode = os.stat(path)[0]
        except OSError:
            continue
        # 0x4000 is the S_IFDIR flag indicating a directory
        if mode & 0x4000:
            yield from list_files(path)
        else:
            yield path

def serve_static_files():
    for file_path in list_files('web'):        
        route = file_path[3:]
        print(f"Adding route for {route}")
        server.add_route(route, serve_file(file_path), methods=['GET'])
        if route == "/index.html":
            server.add_route("/", serve_file(file_path), methods=['GET'])


def setup_mode(fault_msg):
    Pico_Led.start_fast_blink()    
    print("WIFI: Entering setup mode")
    available_networks = None
    
    def ap_index(request):
        cfg=DataStore.read_record("configuration",0)
        s=cfg["ssid"].strip('\0')
        p=cfg["password"].strip('\0')
        extradat=DataStore.read_record("extras",0)
        ip=extradat["lastIP"]
                        
        if request.headers.get("host").lower() != AP_DOMAIN.lower():            
            return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain = AP_DOMAIN.lower())
        return render_template(f"{AP_TEMPLATE_PATH}/index.html",ssid=s,password=p,lastip=ip,warning_message=fault_msg)

    def ap_configure(request):
        print("WIFI: Saving credentials")
        data=request.form
        data['enable']=1
        data['other']=1
        #print("request ",data," END")       
        DataStore.write_record("configuration",request.form,0)
        Pico_Led.off()
        return render_template(f"{AP_TEMPLATE_PATH}/configured.html", ssid = request.form["ssid"])
        
    def ap_catch_all(request):    
        if request.headers.get("host") != AP_DOMAIN:
            return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain = AP_DOMAIN)
        return "Not found.", 404

    def app_listNetworks(request):
        ssid_list = [ssid for ssid, rssi in available_networks]
        networks_dict = {"networks": ssid_list}
        networks_json = json.dumps(networks_dict)
        print(" NETWRK to ->  ",networks_json)
        return networks_json

    def app_initData(request):    
        dat = DataStore.read_record("configuration")
        print("SETUP MODE: init data,",dat)
        return json.dumps(dat)

    import scanwifi
    available_networks=scanwifi.scan_wifi2()
    print(available_networks)

          
    server.add_route("/listnetworks", handler = app_listNetworks, methods = ["GET"])        
    server.add_route("/initdata", handler = app_initData, methods = ["GET"])    
    server.add_route("/", handler = ap_index, methods = ["GET"])
    server.add_route("/configure", handler = ap_configure, methods = ["POST"])

    # add static files
    serve_static_files()

    server.set_callback(ap_catch_all)

    ap = access_point(AP_NAME)
    ip = ap.ifconfig()[0]
    dns.run_catchall(ip)
   

#main application wifi mode
def application_mode(fault_msg):
    print("WIFI: Entering application mode.")       

    def app_catch_all(request):
        return "Not found.", 404
      
    
  
    # add static files
    serve_static_files()

    print("WIFI: end application mode callback")
    server.set_callback(app_catch_all)
 

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
