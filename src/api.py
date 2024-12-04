import SPI_DataStore as DataStore
import ujson as json
import uhashlib as hashlib
import binascii
import time
import gc
from Utilities.random_bytes import random_hex
from phew import server 
import reset_control
import SharedState
from Memory_Main import save_ram,blank_ram
import uctypes
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH, SRAM_COUNT_BASE

#
# Constants
#
ram_access = uctypes.bytearray_at(SRAM_DATA_BASE,SRAM_DATA_LENGTH)

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

    def decorator(func):
        if auth:
            func = require_auth(func)

        @server.route(path, methods=methods)
        def wrapper(request):
            gc.collect()
            try:
                response = func(request)
            except Exception as e:
                msg = f"Error in {func.__name__}: {e}"
                print(msg)
                gc.collect()
                return msg, 500
            
            if response is None:
                return "ok", 200
                    
            gc.collect()
            return response
        return wrapper
    return decorator

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
# Game
#
@add_route("/api/game/reset", methods=["GET"], auth=True)
def app_resetGame(request):              
    reset_control.reset()
    time.sleep(2)
    reset_control.release(True)         
    server.reset_bootup_counters()


@add_route("/api/game/name", methods=["GET"])
def app_gameName(request):
    try:            
        n=SharedState.gdata["GameInfo"]["GameName"]
        return json.dumps({"gamename": n}), 200    
    except Exception as e:            
        return json.dumps({"gamename":"BLANK"}), 500


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
    new_state = request.json['on-machine']
    info = DataStore.read_record("extras", 0)
    info["other"] = new_state
    DataStore.write_record("extras", info, 0)
    return "ok", 200

# @add_route("/api/settings/tournament_mode", methods=["GET"])

@add_route("/api/settings/tournament_mode", methods=["POST"], auth=True)
def app_setTournamentMode(request):    
    SharedState.tournamentModeOn = int(request.json['tournament_mode'])
        





#
# Miscellaneous
#
@add_route("/api/fault", methods=["GET"])
def app_install_fault(request):
    if SharedState.installation_fault:
        return "fault", 500


#TODO not sure we need this anymore
# @add_route("/api/date", methods=["GET"])
# def app_getDate(request):
#     y, m, d, _,_,_,_,_= time.localtime()
#     return f"{y:04d}-{m:02d}-{d:02d}", 200

