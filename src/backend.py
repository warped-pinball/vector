from binascii import hexlify
from gc import collect as gc_collect
from gc import threshold as gc_threshold
from hashlib import sha256 as hashlib_sha256
from time import sleep, time

import Pico_Led
from ls import ls
from machine import RTC
from Memory_Main import blank_ram, save_ram
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH
from uctypes import bytearray_at
from ujson import dumps as json_dumps

import faults
from phew.server import add_route as phew_add_route
from SPI_DataStore import memory_map as ds_memory_map
from SPI_DataStore import read_record as ds_read_record
from SPI_DataStore import write_record as ds_write_record

#
# Constants
#
rtc = RTC()
ram_access = bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
WIFI_MAX_ATTEMPTS = 2
AP_NAME = "Warped Pinball"
# Authentication variables
challenges = {}
CHALLENGE_EXPIRATION_SECONDS = 60
# route etag cache
route_cache = {}


#
# Standardized Route Functions
#
def route_wrapper(func):
    def wrapped_route(request):
        gc_collect()
        try:
            response = func(request)

            if response is None:
                response = "ok", 200

            if type(response).__name__ == "generator":
                return response

            default_headers = {
                "Content-Type": "application/json",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            }

            if isinstance(response, str):
                response = response, 200

            if isinstance(response, dict) or isinstance(response, list):
                response = json_dumps(response), 200

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
                    if status not in [200, 304]:
                        print(f"Status: {status}, Body: {body}")
                    return body, status, headers
            else:
                raise ValueError(f"Invalid response type: {type(response)}")

        except Exception as e:
            msg = f"Error in {func.__name__}: {e}"
            print(msg)
            print(request)
            return msg, 500

        finally:
            gc_collect()

    return wrapped_route


def invalidate_cache(path):
    # Aproximately a 1 in 4.2 billion chance of a collision
    # Probably closer to 1 2^16 in practice because we don't have a good source of entropy
    route_cache[path] = random_hex(4)


def add_cache(path):
    # we should only need to initialize the cache once
    if path in route_cache:
        raise ValueError(f"Route {path} already has a cache entry")

    # "invalidating" is really just making a new random tag
    invalidate_cache(path)

    def decorator(func):
        def cached_route(request):
            # we trust that there is an entry since we initialized it at boot
            etag = route_cache[path]

            # Return 304 if client has current version
            if request.headers.get("if-none-match") == etag:
                return "", 304, {"ETag": etag}

            # Add ETag to response headers
            # This will fail for generators, but we want that since we can't cache them
            body, status, headers = func(request)
            headers["Cache-Control"] = "no-cache, must-revalidate"
            headers["Pragma"] = "no-cache"
            headers["ETag"] = etag
            return body, status, headers

        return cached_route

    return decorator


def add_route(path, auth=False, cool_down_seconds=0, single_instance=False, cache=False):
    """Decorator to add a route to the server with gc_collect() and error handling"""
    # If auth is True only allow a single instance of the route to run at a time
    if auth:
        single_instance = True

    def decorator(func):
        if cool_down_seconds > 0 or single_instance:
            func = cool_down(cool_down_seconds, single_instance)(func)

        func = route_wrapper(func)

        # TODO maybe we could put the cache around the auth decorator
        # But we would need to be careful about how the headers were handled
        if cache:
            func = add_cache(path)(func)

        if auth:
            func = require_auth(func)

        from phew.server import add_route as phew_add_route

        phew_add_route(path, func)

    return decorator


def get_content_type(file_path):
    content_type_mapping = {
        ".css": "text/css",
        ".js": "application/javascript",
        ".html": "text/html",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".gz": "application/gzip",
    }
    for extension, content_type in content_type_mapping.items():
        if file_path.endswith(extension):
            return content_type
    return "application/octet-stream"


def create_file_handler(file_path):
    # Compute ETag incrementally to save memory
    try:
        hasher = hashlib_sha256()
        with open(file_path, "rb") as f:
            buff = bytearray(1024)
            while True:
                buff[0:] = f.read(1024)  # Read in 1KB chunks
                if not buff:
                    break
                hasher.update(buff)
        etag = hexlify(hasher.digest()[:8]).decode()
    except Exception as e:
        print(f"Failed to calculate ETag for {file_path}: {e}")
        etag = random_hex(8)  # Fallback to a random ETag

    def file_stream_generator():
        gc_collect()
        with open(file_path, "rb") as f:
            buff = bytearray(1024)
            while True:
                buff[0:] = f.read(1024)  # Read in 1KB chunks
                if not buff:
                    break
                yield buff
        gc_collect()

    def file_handler(request):
        # Check for conditional request
        if request.headers.get("if-none-match") == etag:
            return "", 304, {"ETag": etag}  # Tell the browser to use it's cached copy

        headers = {
            "Content-Type": get_content_type(file_path),
            "Connection": "close",
            "Cache-Control": "public, max-age=31536000, immutable",  # Cache for 1 year, immutable
            "ETag": etag,
        }
        return file_stream_generator(), 200, headers

    return route_wrapper(file_handler)


def cool_down(cool_down_seconds=0, single_instance=False):
    """Decorator to prevent a route from being called more than once within a given time period and optionally ensuring the previous call has completed before another can be made"""

    def decorator(func):
        last_call = 0
        running = False

        def wrapped_route(request):
            nonlocal last_call, running
            if running and single_instance:
                return "Already running", 409

            if (time() - last_call) < cool_down_seconds:
                return json_dumps({"msg": "cooling down"}), 429

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
    print()
    return "Not found", 404


def redirect(request):
    from phew.server import redirect

    return redirect("/index.html", status=303)


#
# Authentication
#
def random_hex(n):
    from urandom import getrandbits

    output = getrandbits(8).to_bytes(1, "big")
    for i in range(n - 1):
        output += getrandbits(8).to_bytes(1, "big")
    return hexlify(output).decode()


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
        key = key + b"\x00" * (BLOCK_SIZE - len(key))

    # Create inner and outer pads
    o_key_pad = bytes([b ^ 0x5C for b in key])
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
    """Decorator to require authentication using HMAC-SHA256"""

    def auth_wrapper(request, *args, **kwargs):
        global challenges

        def deny_access(reason):
            msg = json_dumps({"error": "reason"}), 401, "application/json"
            print(msg)
            print(request.headers)
            return msg

        # Get the HMAC from the request headers
        client_hmac = request.headers.get("x-auth-hmac")
        if not client_hmac:
            return deny_access("Missing authentication HMAC")

        # Get the challenge from the request headers
        client_challenge = request.headers.get("x-auth-challenge")
        if not client_challenge:
            return deny_access("Missing authentication challenge")

        # confirm that the challenge is valid
        if client_challenge not in challenges:
            return deny_access("Invalid challenge")

        # confirm that the challenge has not expired
        if (time() - challenges[client_challenge]) > CHALLENGE_EXPIRATION_SECONDS:
            del challenges[client_challenge]
            return deny_access("Challenge expired")

        # Retrieve stored password
        credentials = ds_read_record("configuration", 0)
        stored_password = credentials["Gpassword"].encode("utf-8")

        # Construct the message string
        path = request.path
        body_str = request.raw_data or ""
        message_str = client_challenge + path + body_str
        message_bytes = message_str.encode("utf-8")

        # Compute expected HMAC
        expected_digest = hmac_sha256(stored_password, message_bytes)
        expected_hmac = hexlify(expected_digest).decode()

        # If authentication is successful
        if client_hmac == expected_hmac:
            # remove the challenge from the challenges dict
            del challenges[client_challenge]
            return handler(request, *args, **kwargs)
        else:
            return deny_access("Bad Credentials")

    return auth_wrapper


@add_route("/api/auth/challenge")
def get_challenge(request):
    global challenges

    # remove expired challenges
    for challenge, timestamp in list(challenges.items()):
        if (time() - timestamp) > CHALLENGE_EXPIRATION_SECONDS:
            del challenges[challenge]

    # make sure there are no more than 10 challenges
    if len(challenges) > 10:
        return json_dumps({"error": "Too many challenges"}), 429

    # Generate a random nonce (challenge)
    new_challenge = random_hex(64)
    challenge_timestamp = time()

    # add the challenge to the challenges dict
    challenges[new_challenge] = challenge_timestamp

    # Return the nonce to the client
    return json_dumps({"challenge": new_challenge}), 200


@add_route("api/auth/password_check", auth=True)
def check_password(request):
    return "ok", 200


#
# Static File Server
#
for file_path in ls("web"):
    route = file_path[3:]  # This should give '/index.html' for 'web/index.html'
    phew_add_route(route, create_file_handler(file_path))
    if route == "/index.html":
        phew_add_route("/", create_file_handler(file_path))


#
# Game
#
@add_route("/api/game/reboot", auth=True)
def app_reboot_game(request):
    import reset_control

    from phew.server import restart_schedule as phew_restart_schedule

    reset_control.reset()
    sleep(2)
    reset_control.release(True)
    phew_restart_schedule()


@add_route("/api/game/name")
def app_game_name(request):
    import SharedState

    return SharedState.gdata["GameInfo"]["GameName"], 200


@add_route("/api/game/active_config")
def app_game_config_filename(request):
    return {"active_config": ds_read_record("configuration", 0)["gamename"]}


@add_route("/api/game/configs_list")
def app_game_configs_list(request):
    from GameDefsLoad import list_game_configs

    return list_game_configs()


game_status = {"GameActive": True, "BallInPlay": 2, "Scores": [0, 0, 0, 0], "GameTime": 213}


@add_route("/api/game/status")
def app_game_status(request):
    # TODO cache me
    from GameStatus import game_report

    return game_report()


#
# Memory
#
@add_route("/api/memory/reset", auth=True)
def app_reset_memory(request):
    import reset_control

    from phew.server import restart_schedule as phew_restart_schedule

    reset_control.reset()
    sleep(2)
    blank_ram()
    sleep(1)
    reset_control.release(True)
    phew_restart_schedule()


#
# Leaderboard
#
@add_route("/api/scores_page_data")  # TODO , cache=True)
def app_getScoresPageData(request):
    from ScoreTrack import get_claim_score_list, top_scores

    def get_scoreboard(key):
        rows = []
        for i in range(ds_memory_map[key]["count"]):
            row = ds_read_record(key, i)
            if row.get("score", 0) > 0:
                rows.append(row)
            else:
                break
        return rows

    def format_scores(scores):
        print(scores)
        # filter out negative scores
        scores = [score for score in scores if score["score"] > 0]
        # sort the rows by score
        scores.sort(key=lambda x: x["score"], reverse=True)

        from time import time

        from phew.ntp import time_ago

        now_seconds = time()

        # add the rank to each row
        for i, score in enumerate(scores):
            score["rank"] = i + 1
            if "date" in score:
                print(score["date"])
                score["ago"] = time_ago(score["date"], now_seconds)

        return scores

    # TODO make sure to invalidate cache when any of these are updated
    return {"leaders": format_scores(top_scores), "tournament": format_scores(get_scoreboard("tournament")), "claimable": get_claim_score_list()}


@add_route("/api/top_scores")
def app_getTopScores(request):
    from ScoreTrack import top_scores

    return top_scores


@add_route("/api/leaders/reset", auth=True)
def app_resetScores(request):
    from SPI_DataStore import blankStruct

    blankStruct("leaders")


@add_route("/api/tournament/reset", auth=True)
def app_tournamentClear(request):
    import SharedState
    from SPI_DataStore import blankStruct

    blankStruct("tournament")
    SharedState.gameCounter = 0


@add_route("/api/scores/claim")
def app_claimScore(request):
    from ScoreTrack import claim_score

    data = request.data
    claim_score(initials=data["initials"], player_index=data["player_index"], score=data["score"])


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
        initials = record["initials"].replace("\x00", " ").strip("\0")
        full_name = record["full_name"].replace("\x00", " ").strip("\0")
        if initials or full_name:  # ensure that at least one field is not empty
            players[str(i)] = {"initials": initials, "name": full_name}
    return players


@add_route("/api/player/update", auth=True)
def app_updatePlayer(request):
    body = request.data

    index = int(body["id"])
    if index < 0 or index > ds_memory_map["names"]["count"]:
        raise ValueError(f"Invalid index: {index}")

    initials = body["initials"].upper()[:3]
    name = body["full_name"][:16]

    # if name and initials are empty, delete the record
    if len(initials) == 0 and len(name) == 0:
        print("Deleting record")
        from SPI_DataStore import blankIndPlayerScores

        blankIndPlayerScores(int(body["id"]))

    print(f"Updating record {index} with {initials} and {name}")

    ds_write_record("names", {"initials": initials, "full_name": name}, index)


@add_route("/api/player/scores")
def app_getScores(request):
    from time import time

    from phew.ntp import time_ago

    now_seconds = time()
    data = request.data
    player_id = int(data["id"])

    # get player initials and name
    player_record = ds_read_record("names", player_id)

    scores = []
    numberOfScores = ds_memory_map["individual"]["count"]
    for i in range(numberOfScores):
        record = ds_read_record("individual", i, player_id)
        score = record["score"]
        date = record["date"].strip().replace("\x00", " ")
        if score > 0:
            scores.append({"score": score, "date": date})

    # sort the scores by score and add the rank, initials, and name
    scores.sort(key=lambda x: x["score"], reverse=True)
    for i, score in enumerate(scores):
        score["rank"] = i + 1
        score["initials"] = player_record["initials"]
        score["full_name"] = player_record["full_name"]
        score["ago"] = time_ago(score["date"], now_seconds)

    return json_dumps(scores), 200


@add_route("/api/player/scores/reset", auth=True)
def app_resetIndScores(request):
    from SPI_DataStore import blankIndPlayerScores

    index = int(request.args.get("id"))
    blankIndPlayerScores(index)


#
# Adjustments
#
@add_route("/api/adjustments/status")
def app_getAdjustmentStatus(request):
    """
    Get the status of the adjustments as a list of tuples (name, active, populated)
    """
    from Adjustments import get_adjustments_status

    return get_adjustments_status()


@add_route("/api/adjustments/name", auth=True)
def app_setAdjustmentName(request):
    from Adjustments import set_name

    data = request.data
    index = int(data["index"])
    name = data["name"]
    set_name(index, name)


@add_route("/api/adjustments/capture", auth=True)
def app_captureAdjustments(request):
    from Adjustments import store_adjustments

    store_adjustments(int(request.data["index"]))


@add_route("/api/adjustments/restore", auth=True, cool_down_seconds=5)
def app_restoreAdjustments(request):
    from Adjustments import restore_adjustments

    restore_adjustments(int(request.data["index"]))


#
# Settings
#
@add_route("/api/settings/get_claim_methods")
def app_getScoreCap(request):
    record = ds_read_record("extras", 0)
    return {
        "on-machine": record["enter_initials_on_game"],
        "web-ui": record["claim_scores"],
    }


@add_route("/api/settings/set_claim_methods", auth=True)
def app_setScoreCap(request):
    json_data = request.data
    record = ds_read_record("extras", 0)
    if "on-machine" in json_data:
        record["enter_initials_on_game"] = bool(json_data["on-machine"])
    if "web-ui" in json_data:
        record["claim_scores"] = bool(json_data["web-ui"])
    ds_write_record("extras", record, 0)


@add_route("/api/settings/get_tournament_mode")
def app_getTournamentMode(request):
    tournament_mode = ds_read_record("extras", 0)["tournament_mode"]
    return {"tournament_mode": tournament_mode}


@add_route("/api/settings/set_tournament_mode", auth=True)
def app_setTournamentMode(request):
    json_data = request.data
    if "tournament_mode" in json_data:
        info = ds_read_record("extras", 0)
        info["tournament_mode"] = bool(json_data["tournament_mode"])
        ds_write_record("extras", info, 0)


@add_route("/api/settings/get_show_ip")
def app_getShowIP(request):
    return {"show_ip": ds_read_record("extras", 0)["show_ip_address"]}


@add_route("/api/settings/set_show_ip", auth=True)
def app_setShowIP(request):
    data = request.data
    info = ds_read_record("extras", 0)
    info["show_ip_address"] = bool(data["show_ip"])
    ds_write_record("extras", info, 0)


@add_route("/api/settings/factory_reset", auth=True)
def app_factoryReset(request):
    import reset_control
    from machine import reset

    from Adjustments import blank_all as A_blank
    from logger import logger_instance
    from SPI_DataStore import blankAll as D_blank

    Log = logger_instance

    reset_control.reset()  # turn off pinbal machine
    Log.delete_log()
    D_blank()
    A_blank()
    Log.log("BKD: Factory Reset")
    reset()  # reset PICO


@add_route("/api/settings/reboot", auth=True)
def app_reboot(request):
    import reset_control
    from machine import reset

    reset_control.reset()
    sleep(2)
    reset()


#
# Networking
#
@add_route("/api/last_ip")
def app_getLastIP(request):
    ip_address = ds_read_record("extras", 0)["lastIP"]
    return {"ip": ip_address}


@add_route("/api/available_ssids")
def app_getAvailableSSIDs(request):
    import scanwifi

    available_networks = scanwifi.scan_wifi2()
    ssid = ds_read_record("configuration", 0)["ssid"]

    for network in available_networks:
        if network["ssid"] == ssid:
            network["configured"] = True
            break

    return available_networks


@add_route("/api/network/peers")
def app_getPeers(request):
    from discovery import known_devices

    return known_devices


#
# Time
#
@add_route("/api/set_date", auth=True)
def app_setDateTime(request):
    """Set the date and time on the device"""
    date = [int(e) for e in request.json["date"]]

    # rtc will calculate the day of the week for us
    rtc.datetime((date[0], date[1], date[2], 0, date[3], date[4], date[5], 0))


@add_route("/api/get_date")
def app_getDateTime(request):
    return rtc.datetime(), 200


#
# Miscellaneous
#
@add_route("/api/version")
def app_version(request):
    import SharedState

    return {"version": SharedState.WarpedVersion}


@add_route("/api/fault")
def app_install_fault(request):
    import SharedState

    return SharedState.faults


#
# File IO
#
@add_route("/api/export/scores")
def app_export_leaderboard(request):
    from FileIO import download_scores

    return download_scores()


@add_route("/api/memory-snapshot")
def app_memory_snapshot(request):
    return save_ram(), 200


@add_route("/api/logs", cool_down_seconds=10, single_instance=True, auth=True)
def app_getLogs(request):
    from FileIO import download_log

    return download_log()


#
# Updates
#
@add_route("/api/update/check", cool_down_seconds=10)
def app_updates_available(request):
    from mrequests.mrequests import get

    # from urequests import get as urequests_get

    url = "https://api.github.com/repos/warped-pinball/vector/releases/latest"
    headers = {
        "User-Agent": "MicroPython-Device",
        "Accept": "application/vnd.github+json",
    }

    resp = get(url, headers=headers)
    buff = bytearray(1024)
    while True:
        buff[0:] = resp.read(1024)
        if not buff:
            break
        yield buff


@add_route("/api/update/apply", auth=True)
def app_apply_update(request):
    from logger import logger_instance as Log
    from update import apply_update

    yield json_dumps({"log": "Starting update", "percent": 0})
    data = request.data
    try:
        for response in apply_update(data["url"]):
            log = response.get("log", None)
            if log:
                Log.log(f"BKD: {log}")
            yield json_dumps(response)
            gc_collect()
    except Exception as e:
        Log.log(f"BKD: Error applying update: {e}")
        yield json_dumps({"log": f"Error applying update: {e}", "percent": 100})
        yield json_dumps({"log": "Try again in a moment", "percent": 100})


#
# APP mode route of AP mode only routes
#
def add_app_mode_routes():
    """Routes only available in app mode"""

    @add_route("/api/in_ap_mode")
    def app_inAPMode(request):
        return {"in_ap_mode": False}


#
# AP mode routes
#
def add_ap_mode_routes():
    """Routes only available in AP mode"""

    @add_route("/api/in_ap_mode")
    def app_inAPMode(request):
        return {"in_ap_mode": True}

    @add_route("/api/settings/set_vector_config")
    def app_setWifi(request):
        """Set the wifi SSID and password"""
        from GameDefsLoad import list_game_configs

        all_game_configs = list_game_configs().keys()

        data = request.data
        if data["game_config_filename"] not in all_game_configs:
            return f"Invalid game config filename {data['game_config_filename']}", 400

        ds_write_record(
            "configuration",
            {
                "ssid": data["ssid"],
                "password": data["wifi_password"],
                "Gpassword": data["vector_password"],
                "gamename": data["game_config_filename"],
            },
        )

        Pico_Led.off()


def connect_to_wifi():
    from phew import is_connected_to_wifi as phew_is_connected

    if phew_is_connected():
        return True

    from discovery import setup as discovery_setup
    from displayMessage import init as init_display
    from phew import connect_to_wifi as phew_connect
    from SPI_DataStore import writeIP

    wifi_credentials = ds_read_record("configuration", 0)
    ssid = wifi_credentials["ssid"]
    password = wifi_credentials["password"]

    if not ssid:
        return False

    # Try a few times before raising a fault
    for i in range(WIFI_MAX_ATTEMPTS):
        ip_address = phew_connect(ssid, password, timeout_seconds=10)
        if phew_is_connected():
            # TODO remove ip address args and move to scheduler
            writeIP(ip_address)
            init_display(ip_address)
            discovery_setup()
            print(f"Connected to wifi with IP address: {ip_address}")

            # clear any wifi related faults
            if faults.fault_is_raised(faults.ALL_WIFI):
                faults.clear_fault(faults.ALL_WIFI)

            return True

    # If there's signal that means the credentials are wrong
    import scanwifi

    networks = scanwifi.scan_wifi2()
    for network in networks:
        if network["ssid"] == ssid:
            faults.raise_fault(faults.WIFI01, f"Invalid wifi credentials for ssid: {ssid}")
            return False

    faults.raise_fault(faults.WIFI02, f"No wifi signal for ssid: {ssid}")
    return False


def go(ap_mode):
    """Start the server and run the main loop"""
    # Allocate PICO led early - this grabs DMA0&1 and PIO1_SM0 before memory interfaces setup
    # wifi uses PICO LED to indicate status (since it is on wifi chip via spi also)
    Pico_Led.off()
    gc_threshold(2048 * 6)

    # check if configuration is valid
    wifi_credentials = ds_read_record("configuration", 0)
    if not wifi_credentials["ssid"]:
        print("No wifi credentials configured")
        ap_mode = True

    if ap_mode:
        from phew import access_point, dns
        from phew.server import set_callback

        print("Starting in AP mode")
        from displayMessage import init as init_display

        init_display("000.000.000.000")
        Pico_Led.start_fast_blink()
        add_ap_mode_routes()
        # send clients to the configure page
        set_callback(redirect)
        ap = access_point(AP_NAME)
        ip = ap.ifconfig()[0]
        dns.run_catchall(ip)
    else:
        while not connect_to_wifi():
            print("retrying wifi")
            sleep(1)
        Pico_Led.on()
        add_app_mode_routes()
        from phew.server import set_callback

        set_callback(four_oh_four)

    print("-" * 10)
    print("Starting server")
    print("-" * 10)
    from phew.server import run

    run(ap_mode)
