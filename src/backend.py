#TODO change all of these to more specific imports to save memory
#TODO organize these imports between 3rd party and local imports
import SPI_DataStore as DataStore
from SPI_DataStore import writeIP
import ujson as json
import uhashlib as hashlib
import binascii
import time
import gc
import os
from Utilities.random_bytes import random_hex
from phew import server
import reset_control
import SharedState
from Memory_Main import save_ram, blank_ram
import uctypes
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH, SRAM_COUNT_BASE
from GameStatus import report as game_status_report
import FileIO
from machine import RTC
from Utilities.ls import ls
import Pico_Led
import displayMessage
import ujson as json
import uhashlib as hashlib
import binascii
import time
import faults
import GameDefsLoad
#
# Constants
#
rtc = RTC()
ram_access = uctypes.bytearray_at(SRAM_DATA_BASE,SRAM_DATA_LENGTH)
WIFI_MAX_ATTEMPTS = 12
AP_NAME = "Warped Pinball"
# Authentication variables
current_challenge = None
challenge_timestamp = None
CHALLENGE_EXPIRATION_SECONDS = 60


#
# Standardized Route Functions
#
def route_wrapper(func):
    def wrapped_route(request):
        gc.collect()
        try:
            response = func(request)

            if response is None:
                return "ok", 200
            return response

        except Exception as e:
            msg = f"Error in {func.__name__}: {e}"
            print(msg)
            print(request)
            print(request.query)
            return msg, 500

        finally:
            gc.collect()
    return wrapped_route

def add_route(path, method="GET", auth=False, cool_down_seconds=0, single_instance=False):
    '''Decorator to add a route to the server with gc.collect() and error handling'''
    # If auth is True only allow a single instance of the route to run at a time
    if auth:
        single_instance = True
        cool_down_seconds = 2

    def decorator(func):
        if cool_down_seconds > 0 or single_instance:
            func = cool_down(cool_down_seconds, single_instance)(func)

        if auth:
            func = require_auth(func)

        wrapped = route_wrapper(func)

        @server.route(path, methods=[method])
        def route(request):
            return wrapped(request)
        
        return route
    return decorator

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

def create_file_handler(file_path):
    def file_stream_generator():
        gc.collect()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(1024)  # Read in chunks of 1KB
                if not chunk:
                    break
                yield chunk
        gc.collect()

    def file_handler(request):
        headers = {
            'Content-Type': get_content_type(file_path),
            'Connection': 'close'
        }
        # TODO add 'Cache-Control': 'max-age=86400'  #to headers  in order to cache for a day
        # not sure how we would clear this cache, we might want to consider options first
        return file_stream_generator(), 200, headers

    # Wrap the file_handler with the same error/memory logic
    return route_wrapper(file_handler)

def cool_down(cool_down_seconds=0, single_instance=False):
    '''Decorator to prevent a route from being called more than once within a given time period and optionally ensuring the previous call has completed before another can be made'''
    def decorator(func):
        last_call = 0
        running = False

        def wrapped_route(request):
            nonlocal last_call, running
            if running and single_instance:
                return "Already running", 409

            if (time.time() - last_call) < cool_down_seconds:
                return "Cooling down", 429

            running = True
            last_call = time.time()
            try:
                return func(request)
            finally:
                running = False

        return wrapped_route
    return decorator

def four_oh_four(request):
    print("--- 404 ---")
    print(request)
    print(request.query)
    print()
    return "Not found", 404

def redirect(request):
    from phew.server import redirect
    #TODO check that the route is a valid one for the server, else 404
    return redirect(f"/index.html", status=303)
#
# Authentication
#
def hmac_sha256(key, message):
    """
    Compute HMAC-SHA256 using the given key and message.
    key and message should be bytes.
    """
    BLOCK_SIZE = 64  # block size for SHA-256

    # If key longer than block size, hash it
    if len(key) > BLOCK_SIZE:
        h = hashlib.sha256()
        h.update(key)
        key = h.digest()

    # Pad the key
    if len(key) < BLOCK_SIZE:
        key = key + b'\x00' * (BLOCK_SIZE - len(key))

    # Create inner and outer pads
    o_key_pad = bytes([b ^ 0x5c for b in key])
    i_key_pad = bytes([b ^ 0x36 for b in key])

    # Inner hash
    h_inner = hashlib.sha256()
    h_inner.update(i_key_pad + message)
    inner_hash = h_inner.digest()

    # Outer hash
    h_outer = hashlib.sha256()
    h_outer.update(o_key_pad + inner_hash)
    return h_outer.digest()

def require_auth(handler):
    '''Decorator to require authentication using HMAC-SHA256'''
    def auth_wrapper(request, *args, **kwargs):
        global current_challenge, challenge_timestamp

        if not current_challenge or not challenge_timestamp:
            msg = json.dumps({"error": "Challenge missing"}), 401, 'application/json'
            print(msg)
            return msg

        if (time.time() - challenge_timestamp) > CHALLENGE_EXPIRATION_SECONDS:
            msg = json.dumps({"error": "Challenge expired"}), 401, 'application/json'
            print(msg)
            return msg

        # Get the HMAC from the request headers
        client_hmac = request.headers.get('X-Auth-HMAC') or request.headers.get('x-auth-hmac')
        if not client_hmac:
            msg = json.dumps({"error": "Missing authentication HMAC"}), 401, 'application/json'
            print(msg)
            print(request.headers)
            return msg

        # Retrieve stored password (the key)
        credentials = DataStore.read_record("configuration", 0)
        stored_password = credentials["Gpassword"].encode('utf-8')

        # Construct the message string
        path = request.path
        query_string = request.query_string or ""
        body_str = request.raw_data or ""
        message_str = current_challenge + path + query_string + body_str
        message_bytes = message_str.encode('utf-8')

        # Compute expected HMAC
        expected_digest = hmac_sha256(stored_password, message_bytes)
        expected_hmac = binascii.hexlify(expected_digest).decode()

        if client_hmac == expected_hmac:
            # Authentication successful
            current_challenge = None
            challenge_timestamp = None
            print("Authentication successful")
            return handler(request, *args, **kwargs)
        else:
            # Authentication failed
            print("Authentication failed")
            print(f"Expected HMAC: {expected_hmac}")
            print(f"Client HMAC: {client_hmac}")
            print(message_bytes)
            return json.dumps({"error": "Authentication failed"}), 401, 'application/json'

    return auth_wrapper



@add_route("/api/auth/challenge", cool_down_seconds=2)
def get_challenge(request):
    global current_challenge, challenge_timestamp
    # Generate a random nonce (challenge)
    current_challenge = random_hex(64)
    challenge_timestamp = time.time()
    # Return the nonce to the client
    return json.dumps({"challenge": current_challenge}), 200, 'application/json'

@add_route("api/auth/password_check", method="POST", auth=True)
def check_password(request):
    return "ok", 200

#
# Static File Server
#
for file_path in ls('web'):
    route = file_path[3:]  # This should give '/index.html' for 'web/index.html'
    server.add_route(route, create_file_handler(file_path), methods=['GET'])
    if route == "/index.html":
        server.add_route("/", create_file_handler(file_path), methods=['GET'])

#
# Game
#
@add_route("/api/game/reboot", auth=True)
def app_reboot_game(request):              
    reset_control.reset()
    time.sleep(2)
    reset_control.release(True)         
    server.reset_bootup_counters()

@add_route("/api/game/name")
def app_game_name(request):
    return SharedState.gdata["GameInfo"]["GameName"], 200

@add_route("/api/game/status")
def app_gameStatus(request):
    return game_status_report(request)

@add_route("/api/game/active_config")
def app_game_config_filename(request):
    return json.dumps({
        "active_config":DataStore.read_record("configuration", 0)["gamename"]
    }), 200

@add_route("/api/game/configs_list")
def app_game_configs_list(request):
    return json.dumps(GameDefsLoad.list_game_configs()), 200
        

#
# Memory
#
@add_route("/api/memory/reset", auth=True)
def app_reset_memory(request):
    reset_control.reset()
    time.sleep(2)
    blank_ram()
    time.sleep(1)
    reset_control.release(True)
    server.reset_bootup_counters()
    

@add_route("/api/memory/save")
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
def get_scoreboard(key):
    '''Get the leaderboard from memory'''
    rows = []
    for i in range(DataStore.memory_map[key]["count"]):
        row = DataStore.read_record(key, i)
        if row.get("score", 0) > 0:
            rows.append(row)
    
    # sort the rows by score
    rows.sort(key=lambda x: x["score"], reverse=True)
    
    # add the rank to each row
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    return json.dumps(rows), 200

@add_route("/api/leaders")
def app_leaderBoardRead(request):
    return get_scoreboard("leaders")

@add_route("/api/tournament")
def app_tournamentRead(request):
    return get_scoreboard("tournament")

@add_route("/api/leaders/reset", auth=True)
def app_resetScores(request):
    DataStore.blankStruct("leaders")

@add_route("/api/tournament/reset", auth=True)
def app_tournamentClear(request):
    DataStore.blankStruct("tournament")
    SharedState.gameCounter=0

#
# Players
#
@add_route("/api/players")
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

    
@add_route("/api/player/update", method="POST", auth=True)
def app_updatePlayer(request):
    #TODO if initials and name are empty, we need to delete the scores
    
    body = request.data
    initials = body['initials'].upper()[:3]
    name = body['full_name'][:16]
    index = int(body['id'])  
    if index < 0 or index > DataStore.memory_map["names"]["count"]:
        raise ValueError(f"Invalid index: {index}")
            
    DataStore.write_record("names",{"initials":initials,"full_name":name},index)


@add_route("/api/player/scores")
def app_getScores(request):
    player_id = int(request.query.get("id"))
    scores = []                      
    numberOfScores = DataStore.memory_map["individual"]["count"]
    for i in range(numberOfScores):
        record = DataStore.read_record("individual", i, player_id)  
        score = record['score']
        date = record['date'].strip().replace('\x00', ' ')          
        if score > 0:
            scores.append({
                "score": score,
                "date": date
            })                           
    return json.dumps(scores), 200


@add_route("/api/player/scores/reset", auth=True)
def app_resetIndScores(request):
    index = int(request.args.get("id"))
    DataStore.blankIndPlayerScores(index)


#
# Settings
#
@add_route("/api/settings/score_claim_methods")
def app_getScoreCap(request):
    raw_data = DataStore.read_record("extras", 0)["other"]
    print(f"raw_data: {raw_data}")
    score_cap = bool(raw_data)
    return json.dumps({"on-machine": score_cap}), 200


@add_route("/api/settings/score_claim_methods", method="POST", auth=True)
def app_setScoreCap(request):
    #TODO this should only update the methods in the json, the others should be left as is
    json_data = request.data
    print(type(json_data))
    print(f"json_data: {json_data}")
    new_state = json_data['on-machine']
    info = DataStore.read_record("extras", 0)
    info["other"] = new_state
    DataStore.write_record("extras", info, 0)


# @add_route("/api/settings/tournament_mode")

@add_route("/api/settings/tournament_mode", method="POST", auth=True)
def app_setTournamentMode(request):    
    SharedState.tournamentModeOn = int(request.json['tournament_mode'])


@add_route("/api/settings/factory_reset", auth=True)
def app_factoryReset(request):
    # TODO confirm with this is an ok way to reset the device
    import machine
    reset_control.reset() # turn off pinbal machine
    DataStore.blankAll()
    machine.reset()

#
# Networking
#
@add_route("/api/last_ip")
def app_getLastIP(request):
    return DataStore.read_record("extras", 0)["lastIP"], 200

@add_route("/api/available_ssids")
def app_getAvailableSSIDs(request):
    import scanwifi
    available_networks=scanwifi.scan_wifi2()
    ssid = DataStore.read_record("configuration", 0)["ssid"]

    for network in available_networks:
        if network['ssid'] == ssid:
            network['configured'] = True
            break

    return json.dumps(available_networks), 200


#TODO setup domain name

#
# Time
#
@add_route("/api/date_time", method="POST", auth=True)
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
    

@add_route("/api/date_time")
def app_getDateTime(request):
    return rtc.datetime(), 200

#TODO not sure we need this anymore
# @add_route("/api/date")
# def app_getDate(request):
#     y, m, d, _,_,_,_,_= time.localtime()
#     return f"{y:04d}-{m:02d}-{d:02d}", 200


#
# Miscellaneous
#

#TODO version number

@add_route("/api/fault")
def app_install_fault(request):
    return json.dumps(SharedState.faults), 200

#
# File IO
#
#TODO probably not required if we can enable downloading files form score boards in javascript
# server.add_route('/download_leaders',handler = FileIO.download_leaders, methods=['GET'])
# server.add_route('/download_tournament',handler = FileIO.download_tournament, methods=['GET'])
# server.add_route('/download_names',handler = FileIO.download_names, methods=['GET'])
server.add_route('/download_log',handler = FileIO.download_log, methods=['GET'])

#
server.add_route('/upload_file',handler = FileIO.process_incoming_file, methods=['POST'])

# kinda logs for update
server.add_route('/upload_results',handler = FileIO.incoming_file_results, methods=['GET'])


def add_app_mode_routes():
    '''Routes only available in app mode'''
    @add_route("/api/in_ap_mode")
    def app_inAPMode(request):
        return json.dumps({"in_ap_mode": False}), 200

#
# AP mode routes
#
def add_ap_mode_routes():
    '''Routes only available in AP mode'''

    @add_route("/api/in_ap_mode")
    def app_inAPMode(request):
        return json.dumps({"in_ap_mode": True}), 200

    @add_route("/api/settings/set_vector_config", method="POST")
    def app_setWifi(request):
        '''Set the wifi SSID and password'''
        data = request.data
        
        # confirm that the game config exists
        all_game_configs = GameDefsLoad.list_game_configs().keys()
        if data['game_config_filename'] not in all_game_configs:
            return f"Invalid game config filename {data['game_config_filename']}", 400
        

        DataStore.write_record("configuration",
            {
                "ssid": data['ssid'],
                "password": data['wifi_password'],
                "Gpassword": data['vector_password'],
                "gamename": data['game_config_filename'],
            }
        )
        print(request.data)
        Pico_Led.off()

def connect_to_wifi():
    from phew import connect_to_wifi as phew_connect, is_connected_to_wifi as phew_is_connected
    wifi_credentials = DataStore.read_record("configuration", 0)
    ssid = wifi_credentials["ssid"]
    password = wifi_credentials["password"]

    if not ssid:
        return False # Wifi not configured
    
    for i in range(WIFI_MAX_ATTEMPTS):
        print(f"Attempt {i+1} to connect to wifi ssid:{ssid}")
        ip_address = phew_connect(ssid, password, timeout_seconds=10) 
        if phew_is_connected():
            print(f"Connected to wifi with IP address {ip_address}")
            writeIP(ip_address)
            Pico_Led.on()
            displayMessage.init(ip_address)
            return True
    
    # check that we get signal form the ssid
    import scanwifi
    networks = scanwifi.scan_wifi2()
    for network in networks:
        if network['ssid'] == ssid:
            faults.raise_fault(faults.WIFI01, f"Invalid wifi credentials for ssid: {ssid}")
            return False
    
    # We have credentials but no signal so raise a fault
    faults.raise_fault(faults.WIFI02, f"No wifi signal for ssid: {ssid}")
    return False

def go(ap_mode):
    '''Start the server and run the main loop'''
    
    #TODO this was earlier in the code, might need moved to the top of this file OG comments:
    #Allocate PICO led early - this grabs DMA0&1 and PIO1_SM0 before memory interfaces setup
    #wifi uses PICO LED to indicate status (since it is on wifi chip via spi also)   
    Pico_Led.off()
    gc.threshold(2048 * 6) 

    if not ap_mode:
        # try to connect to WiFi
        try:
            if not connect_to_wifi():
                ap_mode = True # If we can't connect to wifi, start in AP mode
        except Exception as e:
            ap_mode = True
            faults.raise_fault(faults.WIFI00, e)

    # check if we are in AP mode again incase we failed to connect to wifi 
    if ap_mode:
        from phew import access_point, dns
        print("Starting in AP mode")
        Pico_Led.start_fast_blink()    
        add_ap_mode_routes()
        # send clients to the configure page
        server.set_callback(redirect)
        ap = access_point(AP_NAME)
        ip = ap.ifconfig()[0]
        dns.run_catchall(ip)
    else:
        add_app_mode_routes()
        server.set_callback(four_oh_four)

    print("-"*10)
    print("Starting server")
    print("-"*10)
    server.run()
    
    

#TODO roller games and police force need rom versions