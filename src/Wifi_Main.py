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
from machine import RTC
import SPI_DataStore as DataStore
import FileIO
from SPI_DataStore import writeIP
import GameStatus
import reset_control

rtc = RTC()
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

    def splitext(filename):
        dot_index = filename.rfind('.')
        if dot_index == -1:
            return filename, ''
        return filename[:dot_index], filename[dot_index:]

    def app_listgames(request):
        print("list games+++++++++++++")
        try:
            files = os.listdir("GameDefs")
            games = [splitext(f)[0] for f in files]
            print("Wifi: host games = ", games)            
        
            cfg=DataStore.read_record("configuration",0)
            gn=cfg["gamename"].strip('\0')

            if len(gn) < 4:
                print(f"game name '{gn}' detected, forcing to 'GenericSystem11'")
                gn = "GenericSystem11"

            response = json.dumps({"games": games, "current_selection": gn})
            #print(response)
            return response
        except Exception as e:
            print("Server: list games fault:", str(e))            
            return json.dumps({"error": "Server: list games fault"})

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

    server.add_route("/listgames", handler = app_listgames, methods = ["GET"])       
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

    def app_adr_plus(request):
        global adr_display
        if (adr_display<(2048-256)):
            adr_display =adr_display+128
        return "OK"
    
    def app_adr_minus(request):
        global adr_display
        if (adr_display>127):
            adr_display =adr_display-128
        return "OK"
    
    def bytes_to_hex_string(adr,ba):
        hex_string_dat = ' '.join(['0x{:02X}'.format(byte) for byte in ba])
        hex_string_loc = "0x{:04x}:  ".format(adr)                
        return hex_string_loc+hex_string_dat

    def build_json(count, mem_values):
        data = {
            "RCounter": count,
            "MemVal0": mem_values[0],
            "MemVal1": mem_values[1],
            "MemVal2": mem_values[2],
            "MemVal3": mem_values[3],
            "MemVal4": mem_values[4],
            "MemVal5": mem_values[5],
            "MemVal6": mem_values[6],
            "MemVal7": mem_values[7],
            "MemVal8": mem_values[8],            
            "MemVal9": mem_values[9],
            "MemVal10": mem_values[10],
            "MemVal11": mem_values[11],
            "MemVal12": mem_values[12],
            "MemVal13": mem_values[13],
            "MemVal14": mem_values[14],
            "MemVal15": mem_values[15]
        }        
        return json.dumps(data)

    #read memory data for admin page
    
   
    def app_get_mem_data(request):
        gc.collect()
        global cycle_count, ram_access, count_access
        cycle_count += 1
        ram_access_ba = bytearray(ram_access)

        def memory_data_generator():
            yield '{'
            yield f'"RCounter": {cycle_count}, '

            for i in range(16):
                start = i * 16 + adr_display
                end = (i + 1) * 16 + adr_display
                hex_values = " ".join(f"0x{byte:02X}" for byte in ram_access_ba[start:end])
                hex_string = f'0x{start:04X}:  {hex_values}'
                
                if i > 0:
                    yield ', '
                yield f'"MemVal{i}": "{hex_string}"'

            yield '}'

            gc.collect()  # Collect garbage after streaming is done

        # Set the appropriate headers for a JSON response
        headers = {
            'Content-Type': 'application/json',
            'Connection': 'close'
        }

        return memory_data_generator(), 200, headers

    


    #write value to memory location
    def app_write(request):            
        if request.method == "POST":
            try:            
                content_length = int(request.headers.get("content-length"))
                body = request.data            
                address = body['Address']
                data = body['Data']        
                # Convert hexadecimal strings to integers
                address_int = int(address, 16)
                data_int = int(data, 16)
                
                if address_int < SRAM_DATA_LENGTH:
                    ram_access[address_int]=data_int            
                    print("Writing data:", data_int, "to address:", address_int)                    
                return("ok")
            except:
                print("WIF: write memory execption")
                return("fail")
        else:
            return("fail")
      
    def app_updateDate(request):
        body = request.data
        data = body['newDate']
        #date_str = data['newDate']     
        year, month, day = map(int, data.split('-'))
        rtc.datetime((year, month, day, 0, 0, 0, 0, 0))
        return "OK"
       

    
    def app_set_IndPlayer(request):
        global IndividualActivePlayer
        global IndividualActivePlayerNum        
        try:
            body = request.data                        
            playa = body['player']
            #print("Set player - ", playa)            
            count = DataStore.memory_map["names"]["count"]
            found = False

            for i in range(count):
                record = DataStore.read_record("names", i)
                initials = record['initials']                                
                if initials == playa:
                    IndividualActivePlayer = initials
                    IndividualActivePlayerNum = i
                    found = True
                    break
            if not found:
                return json.dumps({"error": "Player not found"})            
            #print("index => ",IndividualActivePlayerNum)
            return ("ok")
        
        except Exception as e:
            print(f"Error setting player: {e}")
            return ("error")

    def app_get_IndScores(request):
        global IndividualActivePlayer
        global IndividualActivePlayerNum 
        gc.collect()
        scores = []
        name = DataStore.read_record("names",IndividualActivePlayerNum)['full_name'].strip('\0')
        try:                      
            numberOfScores = DataStore.memory_map["individual"]["count"]
            #print("num ",numberOfScores)
            for i in range(numberOfScores):
                record = DataStore.read_record("individual", i,IndividualActivePlayerNum)  
                score = record['score']
                date = record['date'].strip().replace('\x00', ' ')          
                #print(score,date)                  
                scores.append({
                    "score": score,
                    "full_name": name,
                    "date": date
                })                       
        except Exception as e:
            print("Error accessing DataStore:", str(e))
            return json.dumps({"error": str(e)}) 
        return json.dumps(scores)

    def app_deleteIndScores(request):
        global IndividualActivePlayerNum    
        global PassWordFail
        credentials = DataStore.read_record("configuration",0)             
        body = request.data     
        pw = body["password"]
        if pw ==  credentials["Gpassword"]:
                DataStore.blankIndPlayerScores(IndividualActivePlayerNum)   
                PassWordFail=False          
                print("del done")   
                return("ok")      
        PassWordFail=True  
        print("pass word fail set")
        time.sleep(1.5)
        return ("fail")

    

    

    #individual scores page
    server.add_route("/IndPlayers", handler = app_get_IndPlayers, methods = ["GET"])
    server.add_route("/IndPlayerSet", handler = app_set_IndPlayer, methods = ["POST"])
    server.add_route("/IndScores", handler = app_get_IndScores, methods = ["GET"])
    server.add_route("/deleteIndScores", handler = app_deleteIndScores, methods = ["POST"])
 
    #players NAMES page
    server.add_route("/players", handler = app_loadPlayers, methods = ["GET"])
    server.add_route("/updatePlayer", handler = app_updatePlayer, methods = ["POST"])              

    #admin page
    server.add_route("/password", handler = app_password, methods = ["POST"])   
    server.add_route("/updateDate", handler = app_updateDate, methods = ["POST"])   
    server.add_route("/data", handler = app_get_mem_data, methods = ["GET"])
    server.add_route("/AdrPlus", handler = app_adr_plus, methods = ["GET"])
    server.add_route("/AdrMinus", handler = app_adr_minus, methods = ["GET"])   
    server.add_route("/write", handler = app_write, methods=["POST"])    
    server.add_route("/ResetGame", handler = app_resetGame, methods=['GET'])
    server.add_route("/ResetGameMemory", handler = app_resetMemory, methods=['GET'])
    server.add_route('/download_memory', handler=download_memory ,methods=['GET'])    
    #admin page file IO operations
    server.add_route('/download_leaders',handler = FileIO.download_leaders, methods=['GET'])
    server.add_route('/download_tournament',handler = FileIO.download_tournament, methods=['GET'])
    server.add_route('/download_names',handler = FileIO.download_names, methods=['GET'])
    server.add_route('/download_log',handler = FileIO.download_log, methods=['GET'])
    server.add_route('/upload_file',handler = FileIO.process_incoming_file, methods=['POST'])
    server.add_route('/upload_results',handler = FileIO.incoming_file_results, methods=['GET'])
 

    @server.route("/leaderboardClear")
    def app_resetScores(request): 
        DataStore.blankStruct("leaders") 
        return("ok")

    #general
    server.add_route("/GameName", handler = app_getGameName, methods = ["GET"])
    server.add_route("/GameStatus", handler = GameStatus.report, methods = ["GET"])
  
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
