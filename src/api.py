#TODO change all of these to more specific imports to save memory
import SPI_DataStore as DataStore
from SPI_DataStore import writeIP
import ujson as json
import uhashlib as hashlib
import binascii
import time
import gc
import os
from Utilities.random_bytes import random_hex
from phew import server, connect_to_wifi, is_connected_to_wifi, access_point, dns
import reset_control
import SharedState
from Memory_Main import save_ram,blank_ram
import uctypes
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH, SRAM_COUNT_BASE
from GameStatus import report as game_status_report
import FileIO
from machine import RTC
from Utilities.ls import ls
import Pico_Led
import displayMessage
#
# Constants
#
rtc = RTC()
ram_access = uctypes.bytearray_at(SRAM_DATA_BASE,SRAM_DATA_LENGTH)
WIFI_MAX_ATTEMPTS = 12
AP_NAME = "WarpedPinball"

# Authentication variables
current_challenge = None
challenge_timestamp = None
CHALLENGE_EXPIRATION_SECONDS = 60


#
# Standard Route Decorator
#
def add_route(path, methods=["GET"], auth=False):
    '''Decorator to add a route to the server with gc.collect() and error handling'''
    if isinstance(methods, str):
            methods = [methods]

    def route_adder(func):
        if auth:
            func = require_auth(func)

        # @server.route(path, methods=methods)
        def handle_errors(request):
            gc.collect()
            try:
                response = func(request)
            
                if response is None:
                    return "ok", 200
                else:
                    return response
            
            except Exception as e:
                msg = f"Error in {func.__name__}: {e}"
                print(msg)
                return msg, 500
            
            finally:
                gc.collect()

        server.add_route(path, handle_errors, methods=methods)
    return route_adder

#
# Authentication
#
def require_auth(handler):
    '''decorator to require authentication'''
    def wrapper(request, *args, **kwargs):
        global current_challenge, challenge_timestamp
        # Check if the challenge exists and is valid
        if not current_challenge or not challenge_timestamp:
            return json.dumps({"error": "Challenge missing"}), 401, {'Content-Type': 'application/json'}
        
        if (time.time() - challenge_timestamp) > CHALLENGE_EXPIRATION_SECONDS:
            return json.dumps({"error": "Challenge expired"}), 401, {'Content-Type': 'application/json'}
        
        # Get the HMAC from the request headers
        client_hmac = request.headers.get('X-Auth-HMAC')
        if not client_hmac:
            return json.dumps({"error": "Missing authentication HMAC"}), 401, {'Content-Type': 'application/json'}
        
        # Reconstruct the message used for HMAC: challenge + request path + request body
        credentials = DataStore.read_record("configuration", 0)
        stored_password = credentials["Gpassword"]
        key = stored_password.encode('utf-8')
        msg = (
            current_challenge +           # Challenge
            request.path +                # Request path
            request.query_string +        # Query string (if any)
            request.data_string           # Request body (if any)
        ).encode('utf-8')
        
        # Compute expected HMAC
        hasher = hashlib.sha256()
        hasher.update(key + msg)
        expected_hmac = binascii.hexlify(hasher.digest()).decode()
        
        # Compare HMACs
        if client_hmac == expected_hmac:
            # Authentication successful
            current_challenge = None
            challenge_timestamp = None
            return handler(request, *args, **kwargs)
        else:
            # Authentication failed
            return json.dumps({"error": "Authentication failed"}), 401, {'Content-Type': 'application/json'}
    return wrapper


@add_route("/api/auth/challenge", methods=["GET"])
def get_challenge(request):
    global current_challenge, challenge_timestamp
    # Generate a random nonce (challenge)
    current_challenge = random_hex(64)
    challenge_timestamp = time.time()
    # Return the nonce to the client
    return json.dumps({"challenge": current_challenge}), 200, {'Content-Type': 'application/json'}

#
# Static File Server
#

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

def serve_file(file_path, url=None):
    '''Serve a static file from the filesystem'''
    if url is None:
        url = file_path
    @add_route(url, methods=["GET"])
    def route(request):
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

        return file_stream_generator(), 200, headers
    return route

# Automatically serve all files in the 'web' directory
for file_path in ls('web'):        
    route = file_path[3:]
    print(f"Adding route for {route}")
    serve_file(file_path)
    if route == "/index.html":
        serve_file(file_path, url="/")

#
# Game
#
@add_route("/api/game/reset", methods=["GET"], auth=True)
def app_resetGame(request):              
    reset_control.reset()
    time.sleep(2)
    reset_control.release(True)         
    server.reset_bootup_counters()


@add_route("/api/game/list_names", methods=["GET"])
def app_listgames(request):
    files = os.listdir("GameDefs")
    games = [f[:-5] for f in files]
    response = json.dumps(games)
    return response

@add_route("/api/game/name", methods=["GET"])
def app_gameName(request):
    return json.dumps(SharedState.gdata["GameInfo"]["GameName"]), 200

@add_route("/api/game/status", methods=["GET"])
def app_gameStatus(request):
    return game_status_report(request)

#
# Memory
#
@add_route("/api/memory/reset", methods=["GET"], auth=True)
def app_resetMemory(request):
    reset_control.reset()
    time.sleep(2)
    blank_ram()
    time.sleep(1)
    reset_control.release(True)
    server.reset_bootup_counters()
    

@add_route("/api/memory/save", methods=["GET"])
def download_memory(request):
    # Stream memory values directly to the response to save RAM
    def memory_values_generator():
        for value in ram_access:
            yield f"{value}\n".encode('utf-8')               

    headers = {
        'Content-Type': 'text/plain',
        'Content-Disposition': 'attachment; filename=memory.txt',
        'Connection': 'close'
    }
    
    return memory_values_generator(), 200, headers

   
#
# Leaderboard
#
@add_route("/api/leaders", methods=["GET"])
def app_leaderBoardRead(request):
    leaders = []
    try:
        for i in range(DataStore.memory_map["leaders"]["count"]):
            leaders.append(DataStore.read_record("leaders", i))
    except Exception as e:
        return json.dumps([]), 500
    return json.dumps(leaders), 200


@add_route("/api/leaderboard/reset", methods=["GET"], auth=True)
def app_resetScores(request):
    DataStore.blankStruct("leaders")


#
# Tournament
#
@add_route("/api/tournament/reset", methods=["GET"], auth=True)
def app_tournamentClear(request):
    DataStore.blankStruct("tournament")
    SharedState.gameCounter=0


@add_route("/api/tournament", methods=["GET"], auth=True)
def app_tournamentRead(request):
    leaders = []
    try:
        for i in range(DataStore.memory_map["tournament"]["count"]):
            leaders.append(DataStore.read_record("tournament", i))
    except Exception as e:
        print(f"Error loading tournament: {e}")
        leaders = []
    return json.dumps(leaders)

#
# Players
#
@add_route("/api/players", methods=["GET"])
def app_getPlayers(request):
    players = {}
    count = DataStore.memory_map["names"]["count"]
    # Iterate through the player records
    for i in range(count):
        record = DataStore.read_record("names", i)
        initials = record['initials'].replace('\x00', ' ').strip('\0')
        full_name = record['full_name'].replace('\x00', ' ').strip('\0')
        if initials or full_name: # ensure that at least one field is not empty
            players[str(i)] = {"initials": initials, "name": full_name}             
    return json.dumps(players), 200

    
@add_route("/api/player/update", methods=["POST"], auth=True)
def app_updatePlayer(request):
    body = request.json                   
    initials = body['initials'].upper()[:3]
    name = body['full_name'][:16]
    index = int(body['id'])  
    if index < 0 or index > DataStore.memory_map["names"]["count"]:
        raise ValueError(f"Invalid index: {index}")
            
    DataStore.write_record("names",{"initials":initials,"full_name":name},index)


@add_route("/api/player/scores", methods=["GET"], auth=True)
def app_getScores(request):
    player_id = int(request.args.get("id"))
    scores = []                      
    name = DataStore.read_record("names", player_id)['full_name'].strip('\0')
    numberOfScores = DataStore.memory_map["individual"]["count"]
    for i in range(numberOfScores):
        record = DataStore.read_record("individual", i, player_id)  
        score = record['score']
        date = record['date'].strip().replace('\x00', ' ')          
        scores.append({
            "score": score,
            "full_name": name,
            "date": date
        })                       
    return json.dumps(scores), 200


@add_route("/api/player/scores/reset", methods=["GET"], auth=True)
def app_resetIndScores(request):
    index = int(request.args.get("id"))
    DataStore.blankIndPlayerScores(index)


#
# Settings
#
@add_route("/api/settings/score_capture_methods", methods=["GET"])
def app_getScoreCap(request):
    score_cap = bool(DataStore.read_record("extras", 0)["other"])
    return json.dumps({"on-machine": score_cap}), 200


@add_route("/api/settings/score_capture_methods", methods=["POST"], auth=True)
def app_setScoreCap(request):
    new_state = int(request.json['on-machine'])
    info = DataStore.read_record("extras", 0)
    info["other"] = new_state
    DataStore.write_record("extras", info, 0)


# @add_route("/api/settings/tournament_mode", methods=["GET"])

@add_route("/api/settings/tournament_mode", methods=["POST"], auth=True)
def app_setTournamentMode(request):    
    SharedState.tournamentModeOn = int(request.json['tournament_mode'])
        
@add_route("/api/settings/config_file", methods=["GET"])
def app_getConfig(request):
    return json.dumps(DataStore.read_record("configuration", 0)["gamename"]), 200    


#
# Networking
#
@add_route("/api/last_ip", methods=["GET"])
def app_getLastIP(request):
    return DataStore.read_record("extras", 0)["lastIP"], 200

@add_route("/api/available_ssids", methods=["GET"])
def app_getAvailableSSIDs(request):
    import scanwifi
    available_networks=scanwifi.scan_wifi2()
    return json.dumps(available_networks), 200

#TODO setup domain name

#
# Miscellaneous
#
@add_route("/api/fault", methods=["GET"])
def app_install_fault(request):
    if SharedState.installation_fault:
        return "fault", 500

@add_route("/api/date_time", methods=["POST"], auth=True)
def app_setDateTime(request):
    '''Set the date and time on the device'''
    date = [int(e) for e in request.json['date']]
    y = date[0]
    m = date[1]
    d = date[2]
    if len(date) == 6:
        h = date[3]
        mi = date[4]
        s = date[5]
    
    # rtc will calculate the day of the week for us
    rtc.datetime((date[0], date[1], date[2], 0, date[3], date[4], date[5], 0))
    

@add_route("/api/date_time", methods=["GET"])
def app_getDateTime(request):
    return rtc.datetime(), 200



#TODO not sure we need this anymore
# @add_route("/api/date", methods=["GET"])
# def app_getDate(request):
#     y, m, d, _,_,_,_,_= time.localtime()
#     return f"{y:04d}-{m:02d}-{d:02d}", 200

#
# File IO
#
#TODO probably not required if we can enable downloading files form score boards in javascript
# server.add_route('/download_leaders',handler = FileIO.download_leaders, methods=['GET'])
# server.add_route('/download_tournament',handler = FileIO.download_tournament, methods=['GET'])
# server.add_route('/download_names',handler = FileIO.download_names, methods=['GET'])
server.add_route('/download_log',handler = FileIO.download_log, methods=['GET'])
server.add_route('/upload_file',handler = FileIO.process_incoming_file, methods=['POST'])
server.add_route('/upload_results',handler = FileIO.incoming_file_results, methods=['GET'])

#
# Catch All
#
def four_oh_four(request):
    return "Not found", 404

def redirect(request):
#TODO old AP mode had this, not sure if we need it
#if request.headers.get("host") != AP_DOMAIN:
            #return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain = AP_DOMAIN)

    #TODO add page name query to direct to configuration page
    return "Redirecting...", 301, {"Location": "/index.html"}



#
# AP mode routes
#
def add_ap_mode_routes():
    '''Routes only available in AP mode'''

    @add_route("/api/settings/wifi", methods=["POST"])
    def app_setWifi(request):
        '''Set the wifi SSID and password'''
        data = request.json
        DataStore.write_record("configuration",
            {
                "ssid": data['ssid'],
                "password": data['password'],
                "Gpassword": data['gpassword'],
                "gamename": data['gamename'],

            }
        )
        Pico_Led.off()
        #TODO redirect to "configuration saved" page? possibly just have this baked into web page on 200
    


#TODO we dont really need the fault message since it can only be one message and it's already in the shared state as a bool
def go(ap_mode, fault_msg=None):
    '''Start the server and run the main loop'''
    
    #TODO this was earlier in the code, might need moved to the top of this file
    #Allocate PICO led early - this grabs DMA0&1 and PIO1_SM0 before memory interfaces setup
    #wifi uses PICO LED to indicate status (since it is on wifi chip via spi also)   
    Pico_Led.off()
    gc.threshold(2048 * 6) 

    if ap_mode:
        Pico_Led.start_fast_blink()    
        add_ap_mode_routes()
        # send clients to the configure page
        server.set_callback(redirect)
        ap = access_point(AP_NAME)
        ip = ap.ifconfig()[0]
        dns.run_catchall(ip)
    else:
        server.set_callback(four_oh_four)
        wifi_credentials = DataStore.read_record("configuration", 0)
        if not wifi_credentials:
            raise ValueError("No wifi credentials found in configuration")

        ssid = wifi_credentials["ssid"]
        password = wifi_credentials["password"]
        for i in range(WIFI_MAX_ATTEMPTS):
            print(f"Attempt {i+1} to connect to wifi ssid:{ssid}")
            ip_address = connect_to_wifi(ssid, password, timeout_seconds=10) 
            if is_connected_to_wifi():
                writeIP(ip_address)
                Pico_Led.on()
                displayMessage.init(ip_address)
                break
    
    server.run()
    
    

