from  ujson import dumps as json_dumps 
from hashlib import sha256 as hashlib_sha256
from binascii import hexlify
from time import time, sleep
from gc import collect as gc_collect, threshold as gc_threshold
from uctypes import bytearray_at
from machine import RTC

from phew import server

from SPI_DataStore import (
    writeIP, 
    read_record as ds_read_record, 
    write_record as ds_write_record, 
    memory_map as ds_memory_map
)
from random_bytes import random_hex
from ls import ls
from Memory_Main import save_ram, blank_ram
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH, SRAM_COUNT_BASE
import Pico_Led
import faults

#
# Constants
#
rtc = RTC()
ram_access = bytearray_at(SRAM_DATA_BASE,SRAM_DATA_LENGTH)
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
        gc_collect()
        try:
            response = func(request)

            default_headers = {
                "Content-Type": "application/json",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache"
            }

            if response is None:
                response = "ok", 200
            
            if isinstance(response, str):
                response = response, 200

            if isinstance(response, tuple):
                if len(response) == 2:
                    response = response[0], response[1], default_headers

                if len(response) == 3:
                    body, status, headers = response
                    if isinstance(headers, str):
                        headers = {"Content-Type": headers}

                    if isinstance(headers, dict):
                        # Merge the default headers with the custom headers
                        headers = default_headers | headers
                    return body, status, headers
            else:
                raise ValueError(f"Invalid response type: {type(response)}")
                    
        except Exception as e:
            msg = f"Error in {func.__name__}: {e}"
            print(msg)
            print(request)
            print(request.query)
            return msg, 500

        finally:
            gc_collect()
    return wrapped_route

def add_route(path, method="GET", auth=False, cool_down_seconds=0, single_instance=False):
    '''Decorator to add a route to the server with gc_collect() and error handling'''
    # If auth is True only allow a single instance of the route to run at a time
    if auth:
        single_instance = True

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
    # Compute ETag incrementally to save memory
    try:
        hasher = hashlib_sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(1024):  # Read in 1KB chunks
                hasher.update(chunk)
        etag = hexlify(hasher.digest()[:8]).decode()
    except Exception as e:
        print(f"Failed to calculate ETag for {file_path}: {e}")
        etag = random_hex(8)  # Fallback to a random ETag

    def file_stream_generator():
        gc_collect()
        with open(file_path, 'rb') as f:
            while chunk := f.read(1024):  # Read in 1KB chunks
                yield chunk
        gc_collect()

    def file_handler(request):
        # Check for conditional request
        if request.headers.get('if-none-match') == etag:
            return "", 304, {"ETag": etag}  # Tell the browser to use it's cached copy

        headers = {
            'Content-Type': get_content_type(file_path),
            'Connection': 'close',
            'Cache-Control': 'public, max-age=31536000, immutable',  # Cache for 1 year, immutable
            'ETag': etag
        }
        return file_stream_generator(), 200, headers

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

            if (time() - last_call) < cool_down_seconds:
                return "Cooling down", 429

            running = True
            last_call = time()
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
        h = hashlib_sha256()
        h.update(key)
        key = h.digest()

    # Pad the key
    if len(key) < BLOCK_SIZE:
        key = key + b'\x00' * (BLOCK_SIZE - len(key))

    # Create inner and outer pads
    o_key_pad = bytes([b ^ 0x5c for b in key])
    i_key_pad = bytes([b ^ 0x36 for b in key])

    # Inner hash
    h_inner = hashlib_sha256()
    h_inner.update(i_key_pad + message)
    inner_hash = h_inner.digest()

    # Outer hash
    h_outer = hashlib_sha256()
    h_outer.update(o_key_pad + inner_hash)
    return h_outer.digest()

def require_auth(handler):
    '''Decorator to require authentication using HMAC-SHA256'''
    def auth_wrapper(request, *args, **kwargs):
        global current_challenge, challenge_timestamp

        if not current_challenge or not challenge_timestamp:
            msg = json_dumps({"error": "Challenge not set"}), 401, 'application/json'
            print(msg)
            return msg

        if (time() - challenge_timestamp) > CHALLENGE_EXPIRATION_SECONDS:
            msg = json_dumps({"error": "Challenge expired"}), 401, 'application/json'
            print(msg)
            return msg

        # Get the HMAC from the request headers
        client_hmac = request.headers.get('x-auth-hmac')
        if not client_hmac:
            msg = json_dumps({"error": "Missing authentication HMAC"}), 401, 'application/json'
            print(msg)
            print(request.headers)
            return msg

        # Retrieve stored password (the key)
        credentials = ds_read_record("configuration", 0)
        stored_password = credentials["Gpassword"].encode('utf-8')

        # Construct the message string
        path = request.path
        query_string = request.query_string or ""
        body_str = request.raw_data or ""
        message_str = current_challenge + path + query_string + body_str
        message_bytes = message_str.encode('utf-8')

        # Compute expected HMAC
        expected_digest = hmac_sha256(stored_password, message_bytes)
        expected_hmac = hexlify(expected_digest).decode()

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
            return json_dumps({"error": "Authentication failed"}), 401, 'application/json'

    return auth_wrapper



@add_route("/api/auth/challenge")
def get_challenge(request):
    global current_challenge, challenge_timestamp
    # Generate a random nonce (challenge)
    current_challenge = random_hex(64)
    challenge_timestamp = time()
    # Return the nonce to the client
    return json_dumps({"challenge": current_challenge}), 200

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
    import reset_control
    reset_control.reset()
    sleep(2)
    reset_control.release(True)         
    server.reset_bootup_counters()

@add_route("/api/game/name")
def app_game_name(request):
    import SharedState
    return SharedState.gdata["GameInfo"]["GameName"], 200

@add_route("/api/game/active_config")
def app_game_config_filename(request):
    return json_dumps({
        "active_config":ds_read_record("configuration", 0)["gamename"]
    }), 200

@add_route("/api/game/configs_list")
def app_game_configs_list(request):
    from GameDefsLoad import list_game_configs
    return json_dumps(list_game_configs()), 200
        

#
# Memory
#
@add_route("/api/memory/reset", auth=True)
def app_reset_memory(request):
    import reset_control
    reset_control.reset()
    sleep(2)
    blank_ram()
    sleep(1)
    reset_control.release(True)
    server.reset_bootup_counters()
    

@add_route("/api/memory-snapshot")
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
    for i in range(ds_memory_map[key]["count"]):
        row = ds_read_record(key, i)
        if row.get("score", 0) > 0:
            rows.append(row)
    
    # sort the rows by score
    rows.sort(key=lambda x: x["score"], reverse=True)
    
    # add the rank to each row
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    return json_dumps(rows), 200

@add_route("/api/leaders")
def app_leaderBoardRead(request):
    return get_scoreboard("leaders")

@add_route("/api/tournament")
def app_tournamentRead(request):
    return get_scoreboard("tournament")

@add_route("/api/leaders/reset", auth=True)
def app_resetScores(request):
    from SPI_DataStore import blankStruct
    blankStruct("leaders")

@add_route("/api/tournament/reset", auth=True)
def app_tournamentClear(request):
    from SPI_DataStore import blankStruct
    import SharedState
    blankStruct("tournament")
    SharedState.gameCounter=0

#
# Players
#
@add_route("/api/players")
def app_getPlayers(request):
    players = {}
    count = ds_memory_map["names"]["count"]
    # Iterate through the player records
    for i in range(count):
        record = ds_read_record("names", i)
        initials = record['initials'].replace('\x00', ' ').strip('\0')
        full_name = record['full_name'].replace('\x00', ' ').strip('\0')
        if initials or full_name: # ensure that at least one field is not empty
            players[str(i)] = {"initials": initials, "name": full_name}             
    return json_dumps(players), 200

    
@add_route("/api/player/update", method="POST", auth=True)
def app_updatePlayer(request):    
    #TODO this correctly deletes the player and unlinks their scores, but should it remove their name from leaderbaord scores? (currently it does not)
    body = request.data
    
    index = int(body['id'])  
    if index < 0 or index > ds_memory_map["names"]["count"]:
        raise ValueError(f"Invalid index: {index}")

    initials = body['initials'].upper()[:3]
    name = body['full_name'][:16]

    # if name and initials are empty, delete the record
    if len(initials) == 0 and len(name) == 0:
        print("Deleting record")
        from SPI_DataStore import blankIndPlayerScores
        blankIndPlayerScores(int(body['id']))
    
    print(f"Updating record {index} with {initials} and {name}")

    ds_write_record("names",{"initials":initials,"full_name":name},index)


@add_route("/api/player/scores")
def app_getScores(request):
    player_id = int(request.query.get("id"))
    scores = []                      
    numberOfScores = ds_memory_map["individual"]["count"]
    for i in range(numberOfScores):
        record = ds_read_record("individual", i, player_id)  
        score = record['score']
        date = record['date'].strip().replace('\x00', ' ')          
        if score > 0:
            scores.append({
                "score": score,
                "date": date
            })                           
    return json_dumps(scores), 200


@add_route("/api/player/scores/reset", auth=True)
def app_resetIndScores(request):
    from SPI_DataStore import blankIndPlayerScores
    index = int(request.args.get("id"))
    blankIndPlayerScores(index)


#
# Settings
#
@add_route("/api/settings/score_claim_methods")
def app_getScoreCap(request):
    raw_data = ds_read_record("extras", 0)["other"]
    print(f"raw_data: {raw_data}")
    score_cap = bool(raw_data)
    return json_dumps({"on-machine": score_cap}), 200


@add_route("/api/settings/score_claim_methods", method="POST", auth=True)
def app_setScoreCap(request):
    json_data = request.data
    if "on-machine" in json_data:        
        info = ds_read_record("extras", 0)
        info["other"] = json_data['on-machine']
        ds_write_record("extras", info, 0)



@add_route("/api/settings/tournament_mode", method="POST", auth=True)
def app_setTournamentMode(request):    
    import SharedState
    SharedState.tournamentModeOn = int(request.json['tournament_mode'])


@add_route("/api/settings/factory_reset", auth=True)
def app_factoryReset(request):
    # TODO confirm with this is an ok way to reset the device
    from SPI_DataStore import blankAll
    from machine import reset
    import reset_control

    reset_control.reset() # turn off pinbal machine
    blankAll()
    reset()

#
# Networking
#
@add_route("/api/last_ip")
def app_getLastIP(request):
    ip_address = ds_read_record("extras", 0)["lastIP"]
    return json_dumps({"ip": ip_address}), 200


@add_route("/api/available_ssids")
def app_getAvailableSSIDs(request):
    import scanwifi
    available_networks=scanwifi.scan_wifi2()
    ssid = ds_read_record("configuration", 0)["ssid"]

    for network in available_networks:
        if network['ssid'] == ssid:
            network['configured'] = True
            break

    return json_dumps(available_networks), 200


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
#     y, m, d, _,_,_,_,_= localtime()
#     return f"{y:04d}-{m:02d}-{d:02d}", 200


#
# Miscellaneous
#
@add_route("/api/version")
def app_version(request):
    import SharedState
    return json_dumps({'version':SharedState.WarpedVersion}), 200

@add_route("/api/fault")
def app_install_fault(request):
    import SharedState
    return json_dumps(SharedState.faults), 200

#
# File IO
#
@add_route("/api/memory-snapshot")
def app_memory_snapshot(request):
    return save_ram(), 200

@add_route("/api/logs", cool_down_seconds=10, single_instance=True)
def app_getLogs(request):
    from FileIO import download_log
    return download_log()

# cool down needs to be set to 0 to keep updates moving quickly/error free
@add_route("/api/upload_file", method="POST", auth=True, cool_down_seconds=0, single_instance=True)
def app_upload_file_json(request):
    """
    Receives a JSON body representing a single "file update" dictionary, e.g.:
        {
          "FileType": "SomeFile.py" or "SomeFile.json",
          "contents": "...",
          "Checksum": "1234ABCD",
          ...
        }

    Then it creates a fake form-based request to call the existing process_incoming_file,
    which expects request.form and does:
        for key in request.form:
            value = request.form[key]
        data = json.loads(value)

    Returns:
      200 on success,
      500 on error (with a JSON body containing the error).
    """
    from FileIO import process_incoming_file

    class FakeRequest:
        def __init__(self, dict_value):
            # The form in your code is accessed by request.form
            self.form = {
                "dictionary": dict_value
            }

    try:
        # request.data should be a single dictionary
        # If it’s not, that’s an error
        if not isinstance(request.data, dict):
            raise ValueError("Expected a JSON dictionary (single file), but got something else.")

        # Convert the dict to a JSON string, 
        # because process_incoming_file does `json.loads(value)`
        item_json_str = json_dumps(request.data)

        # Build a fake request object
        fake_request = FakeRequest(item_json_str)

        # Call your existing function
        result = process_incoming_file(fake_request)

        # Return success
        return json_dumps({
            "status": "ok",
            "result": result
        }), 200, "application/json"

    except Exception as e:
        # Return an error with status code 500
        error_message = f"Error uploading file: {e}"
        print(error_message)
        return json_dumps({
            "status": "error",
            "message": error_message
        }), 500, "application/json"

# kinda logs for update
# TODO server.add_route('/upload_results',handler = FileIO.incoming_file_results, methods=['GET'])


def add_app_mode_routes():
    '''Routes only available in app mode'''
    @add_route("/api/in_ap_mode")
    def app_inAPMode(request):
        return json_dumps({"in_ap_mode": False}), 200

#
# AP mode routes
#
def add_ap_mode_routes():
    '''Routes only available in AP mode'''

    @add_route("/api/in_ap_mode")
    def app_inAPMode(request):
        return json_dumps({"in_ap_mode": True}), 200

    @add_route("/api/settings/set_vector_config", method="POST")
    def app_setWifi(request):
        '''Set the wifi SSID and password'''
        from GameDefsLoad import list_game_configs
        all_game_configs = list_game_configs().keys()
        
        data = request.data
        if data['game_config_filename'] not in all_game_configs:
            return f"Invalid game config filename {data['game_config_filename']}", 400
        

        ds_write_record("configuration",
            {
                "ssid": data['ssid'],
                "password": data['wifi_password'],
                "Gpassword": data['vector_password'],
                "gamename": data['game_config_filename'],
            }
        )

        Pico_Led.off()

def connect_to_wifi():
    from phew import connect_to_wifi as phew_connect, is_connected_to_wifi as phew_is_connected
    wifi_credentials = ds_read_record("configuration", 0)
    ssid = wifi_credentials["ssid"]
    password = wifi_credentials["password"]
    
    if not ssid:
        return False

    # Try a few times before raising a fault
    for i in range(WIFI_MAX_ATTEMPTS):
        ip_address = phew_connect(ssid, password, timeout_seconds=10) 
        if phew_is_connected():
            print(f"Connected to wifi with IP address: {ip_address}")
            writeIP(ip_address)
            from displayMessage import init
            init(ip_address)
            return True
    
    
    # If there's signal that means the credentials are wrong
    import scanwifi
    networks = scanwifi.scan_wifi2()
    for network in networks:
        if network['ssid'] == ssid:
            faults.raise_fault(faults.WIFI01, f"Invalid wifi credentials for ssid: {ssid}")
            return False
    
    faults.raise_fault(faults.WIFI02, f"No wifi signal for ssid: {ssid}")
    return False

def go(ap_mode):
    '''Start the server and run the main loop'''
    
    #TODO this was earlier in the code, might need moved to the top of this file OG comments:
    #Allocate PICO led early - this grabs DMA0&1 and PIO1_SM0 before memory interfaces setup
    #wifi uses PICO LED to indicate status (since it is on wifi chip via spi also)   
    Pico_Led.off()
    gc_threshold(2048 * 6) 

    # check if configuration is valid
    wifi_credentials = ds_read_record("configuration", 0)
    if not wifi_credentials["ssid"]:
        print("No wifi credentials configured")
        ap_mode = True

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
        while not connect_to_wifi():
            print("Failed to connect to wifi, retrying in 2 seconds")
            sleep(2)
        Pico_Led.on()
        add_app_mode_routes()
        server.set_callback(four_oh_four)

    print("-"*10)
    print("Starting server")
    print("-"*10)
    server.run()
    
    

#TODO roller games and police force need rom versions