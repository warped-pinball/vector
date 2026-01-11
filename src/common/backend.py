from binascii import hexlify
from gc import collect as gc_collect
from gc import threshold as gc_threshold
from hashlib import sha256 as hashlib_sha256
from time import sleep, time

import faults
import Pico_Led
import SharedState as S
import uctypes
from ls import ls
from machine import RTC
from phew.server import add_route as phew_add_route
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH
from SPI_DataStore import memory_map as ds_memory_map
from SPI_DataStore import read_record as ds_read_record
from SPI_DataStore import write_record as ds_write_record
from ujson import dumps as json_dumps

#
# Constants
#
rtc = RTC()
WIFI_MAX_ATTEMPTS = 2
AP_NAME = "Warped Pinball"
# Authentication variables
challenges = {}
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
                "Pragma": "no-cache",
            }

            if response is None:
                response = "ok", 200

            if type(response).__name__ == "generator":
                return response

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


def add_route(path, auth=False, cool_down_seconds=0, single_instance=False):
    """Decorator to add a route to the server with gc_collect() and error handling"""
    # If auth is True only allow a single instance of the route to run at a time
    if auth:
        single_instance = True

    def decorator(func):
        if cool_down_seconds > 0 or single_instance:
            func = cool_down(cool_down_seconds, single_instance)(func)

        if auth:
            func = require_auth(func)

        wrapped = route_wrapper(func)

        from phew.server import add_route as phew_add_route

        phew_add_route(path, wrapped)

        # return route

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
        ".svg": "image/svg+xml",
        ".gz": "application/gzip",
    }
    for extension, content_type in content_type_mapping.items():
        if file_path.endswith(extension):
            return content_type
    return "application/octet-stream"


def create_file_handler(file_path):
    is_gz = file_path.endswith(".gz")
    served_path = file_path[:-3] if is_gz else file_path

    try:
        hasher = hashlib_sha256()
        with open(file_path, "rb") as f:
            buff = bytearray(1024)
            while True:
                buff[0:] = f.read(1024)
                if not buff:
                    break
                hasher.update(buff)
        etag = hexlify(hasher.digest()[:8]).decode()
    except Exception as e:
        print(f"Failed to calculate ETag for {file_path}: {e}")
        etag = random_hex(8)

    def file_stream_generator():
        gc_collect()
        with open(file_path, "rb") as f:
            buff = bytearray(1024)
            while True:
                buff[0:] = f.read(1024)
                if not buff:
                    break
                yield buff
        gc_collect()

    def file_handler(request):
        if request.headers.get("if-none-match") == etag:
            return "", 304, {"ETag": etag}

        headers = {
            "Content-Type": get_content_type(served_path),
            "Connection": "close",
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag,
        }
        if is_gz:
            if served_path.endswith(".svg"):
                headers["Content-Type"] = "application/gzip"
            else:
                headers["Content-Encoding"] = "gzip"
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

        # USB transport is explicitly tagged by the USB bridge. Only those
        # requests bypass authentication; HTTP callers cannot skip HMAC by
        # spoofing the protocol string.
        try:
            if request.is_usb_transport and request.method == "USB" and request.protocol.startswith("USB"):
                return handler(request, *args, **kwargs)
        except Exception:
            pass

        def deny_access(reason):
            msg = json_dumps({"error": reason}), 401, "application/json"
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
    """
    @api
    summary: Request a new authentication challenge
    request:
    response:
      status_codes:
        - code: 200
          description: Challenge issued
        - code: 429
          description: Too many active challenges
      body:
        description: JSON containing a single challenge token.
        example:
            {
                "challenge": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
            }
    @end
    """
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


@add_route("/api/auth/password_check", auth=True)
def check_password(request):
    """
    @api
    summary: Convenience method to verify credentials without side effects
    auth: true
    response:
      status_codes:
        - code: 200
          description: Credentials accepted
        - code: 401
          description: Credentials rejected
      body:
        description: Acknowledgement string
        example: "ok"
    @end
    """
    return "ok", 200


#
# Static File Server
#
for file_path in ls("web"):
    route = file_path[3:]
    if file_path.endswith(".gz"):
        route = route[:-3]
    handler = create_file_handler(file_path)
    phew_add_route(route, handler)
    if route == "/index.html":
        phew_add_route("/", handler)


#
# Game
#
@add_route("/api/game/reboot", auth=True)
def app_reboot_game(request):
    """
    @api
    summary: Power-cycle the pinball machine and restart the scheduled tasks
    auth: true
    response:
      status_codes:
        - code: 200
          description: Reboot triggered
      body:
        description: Empty body; returns OK on success
        example: "ok"
    @end
    """
    import reset_control
    from phew.server import restart_schedule as phew_restart_schedule

    reset_control.reset()
    sleep(2)
    reset_control.release(True)
    phew_restart_schedule()


@add_route("/api/game/name")
def app_game_name(request):
    """
    @api
    summary: Get the human-friendly title of the active game configuration
    response:
      status_codes:
        - code: 200
          description: Active game returned
      body:
        description: Plain-text game name
        example: "Attack from Mars"
    @end
    """
    import SharedState

    return SharedState.gdata["GameInfo"]["GameName"], 200


@add_route("/api/game/active_config")
def app_game_config_filename(request):
    """
    @api
    summary: Get the filename of the active game configuration. Note that on EM systems this is the same as the game name.
    response:
      status_codes:
        - code: 200
          description: Active configuration returned
      body:
        description: JSON object identifying the configuration file in use
        example:
            {
                "active_config": "AttackMars_11"
            }
    @end
    """
    import SharedState

    if SharedState.gdata["GameInfo"]["System"] == "EM":
        return {"active_config": SharedState.gdata["GameInfo"]["GameName"]}

    return {"active_config": ds_read_record("configuration", 0)["gamename"]}
    # TODO make this use configured game name on EM


@add_route("/api/game/configs_list")
def app_game_configs_list(request):
    """
    @api
    summary: List all available game configuration files
    response:
      status_codes:
        - code: 200
          description: Configurations listed
      body:
        description: Mapping of configuration filenames to human-readable titles
        example: {"F14_L1": {"name": "F14 Tomcat", "rom": "L1"}, "Taxi_L4": {"name": "Taxi", "rom": "L4"}}
            {
                "F14_L1": {
                    "name": "F14 Tomcat",
                    "rom": "L1"
                },
                "Taxi_L4": {
                    "name": "Taxi",
                    "rom": "L4"
                }
            }
    @end
    """
    from GameDefsLoad import list_game_configs

    return list_game_configs()


@add_route("/api/game/status")
def app_game_status(request):
    """
    @api
    summary: Retrieve the current game status such as ball in play, scores, and anything else the configured game supports
    response:
      status_codes:
        - code: 200
          description: Status returned
      body:
        description: JSON object describing current play state, score, and timers
        example:
            {
                "GameActive": true,
                "BallInPlay": 2,
                "Scores": [1000, 0, 0, 0]
            }
    @end
    """
    # TODO cache me
    from GameStatus import game_report

    return game_report()


#
# Leaderboard
#
def get_scoreboard(key, sort_by="score", reverse=False):
    rows = []
    for i in range(ds_memory_map[key]["count"]):
        row = ds_read_record(key, i)
        if row.get("score", 0) > 0:
            rows.append(row)

    # sort the rows by score
    rows.sort(key=lambda x: x[sort_by], reverse=reverse)

    from time import time

    from phew.ntp import time_ago

    now_seconds = time()

    # add the rank to each row
    for i, row in enumerate(rows):
        row["rank"] = i + 1
        if "date" in row:
            row["ago"] = time_ago(row["date"], now_seconds)

    return rows


@add_route("/api/leaders")
def app_leaderBoardRead(request):
    """
    @api
    summary: Fetch the main leaderboard
    response:
      status_codes:
        - code: 200
          description: Leaderboard returned
      body:
        description: Sorted list of leaderboard entries with rank and relative times
        example:
            [
                {
                    "initials": "ABC",
                    "score": 123456,
                    "rank": 1,
                    "ago": "2h"
                }
            ]
    @end
    """
    return get_scoreboard("leaders", reverse=True)


@add_route("/api/score/delete", auth=True)
def app_scoreDelete(request):
    """
    @api
    summary: Delete one or more score entries from a leaderboard
    auth: true
    request:
      body:
        - name: delete
          type: list
          required: true
          description: Collection of score objects containing ``score`` and ``initials``.
        - name: list
          type: string
          required: true
          description: Target list name (e.g. leaders or tournament)
    response:
      status_codes:
        - code: 200
          description: Scores removed
      body:
        description: Confirmation indicator
        example: {"success": true}
    @end
    """
    from ScoreTrackCommon import remove_score_entry

    body = request.data
    requested_to_delete = body["delete"]
    delete_from = body["list"]
    scores_to_delete = dict()
    for requested in requested_to_delete:
        scores_to_delete[requested["score"]] = requested["initials"]

    for score in scores_to_delete:
        remove_score_entry(initials=scores_to_delete[score], score=score, list=delete_from)

    # If this was the leaders list, set top_scores global var and update machine scores.
    if delete_from == "leaders":
        from ScoreTrack import initialize_leaderboard, place_machine_scores

        initialize_leaderboard()
        # Write the top 4 scores to machine memory again, so they don't re-sync to vector.
        place_machine_scores()

    return {"success": True}


@add_route("/api/tournament")
def app_tournamentRead(request):
    """
    @api
    summary: Read the tournament leaderboard
    response:
      status_codes:
        - code: 200
          description: Tournament leaderboard returned
      body:
        description: List of tournament scores sorted by game order
        example:
            [
                {
                    "initials": "ABC",
                    "score": 123456,
                    "game": 1
                }
            ]
    @end
    """
    return get_scoreboard("tournament", sort_by="game")


@add_route("/api/leaders/reset", auth=True)
def app_resetScores(request):
    """
    @api
    summary: Clear the main leaderboard
    auth: true
    response:
      status_codes:
        - code: 200
          description: Scores cleared
      body:
        example: "ok"
    @end
    """
    from ScoreTrack import reset_scores

    reset_scores()


@add_route("/api/tournament/reset", auth=True)
def app_tournamentClear(request):
    """
    @api
    summary: Clear tournament standings and resets the game counter
    auth: true
    response:
      status_codes:
        - code: 200
          description: Tournament data cleared
      body:
        example: "ok"
    @end
    """
    import SharedState
    from SPI_DataStore import blankStruct

    blankStruct("tournament")
    SharedState.gameCounter = 0


@add_route("/api/scores/claimable")
def app_getClaimableScores(request):
    """
    @api
    summary: List recent claimable plays
    response:
      status_codes:
        - code: 200
          description: Claimable scores returned
      body:
        description: Collection of unclaimed score records
        example:
            [
                {
                    "score": 12345,
                    "player_index": 0,
                    "game": 1
                }
            ]
    @end
    """
    from ScoreTrack import get_claim_score_list

    return get_claim_score_list()


@add_route("/api/scores/claim")
def app_claimScore(request):
    """
    @api
    summary: Apply initials to an unclaimed score
    request:
      body:
        - name: initials
          type: string
          required: true
          description: Player initials to record
        - name: player_index
          type: int
          required: true
          description: Player slot or position associated with the score
        - name: score
          type: int
          required: true
          description: Score value to claim
    response:
      status_codes:
        - code: 200
          description: Score claimed
      body:
        example: "ok"
    @end
    """
    from ScoreTrack import claim_score

    data = request.data
    claim_score(initials=data["initials"], player_index=data["player_index"], score=data["score"])


#
# Players
#
@add_route("/api/players")
def app_getPlayers(request):
    """
    @api
    summary: List registered players
    response:
      status_codes:
        - code: 200
          description: Player list returned
      body:
        description: Mapping of player IDs to initials and names
        example:
            {
                "0": {
                    "initials": "ABC",
                    "name": "Alice"
                }
            }
    @end
    """
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
    """
    @api
    summary: Update a stored player record
    auth: true
    request:
      body:
        - name: id
          type: int
          required: true
          description: Player ID to update
        - name: initials
          type: string
          required: true
          description: Up to three alphabetic characters
        - name: full_name
          type: string
          required: false
          description: Player display name (truncated to 16 characters)
    response:
      status_codes:
        - code: 200
          description: Record updated
      body:
        example: "ok"
    @end
    """
    body = request.data

    index = int(body["id"])
    if index < 0 or index > ds_memory_map["names"]["count"]:
        raise ValueError(f"Invalid index: {index}")

    initials = body["initials"].upper()  # very particular intials conditioning
    i_intials = ""
    for c in initials:
        if "A" <= c <= "Z":
            i_intials += c
    initials = (i_intials + "   ")[:3]

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
    """
    @api
    summary: Fetch all scores for a specific player
    request:
      body:
        - name: id
          type: int
          required: true
          description: Player index to inspect
    response:
      status_codes:
        - code: 200
          description: Player scores returned
      body:
        description: Sorted list of score entries with rank, initials, and timestamps
        example:
            [
                {
                    "score": 10000,
                    "rank": 1,
                    "initials": "ABC",
                    "date": "2024-01-01",
                    "ago": "1d"
                }
            ]
    @end
    """
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


@add_route("/api/personal/bests")
def app_personal_bests(request):
    """
    @api
    summary: Return the best score for each registered player
    response:
      status_codes:
        - code: 200
          description: Personal bests returned
      body:
        description: Leaderboard of each player's highest score
        example:
            [
                {
                    "player_id": 0,
                    "initials": "ABC",
                    "score": 12345,
                    "rank": 1
                }
            ]
    @end
    """
    from time import time

    from phew.ntp import time_ago

    now_seconds = time()

    bests = {}
    # total players and individual scores
    total_players = ds_memory_map["names"]["count"]
    total_scores = ds_memory_map["individual"]["count"]

    for player_id in range(total_players):
        player = ds_read_record("names", player_id)
        if not player["initials"].strip():
            continue

        for score_idx in range(total_scores):
            record = ds_read_record("individual", score_idx, player_id)
            if record["score"] > 0:
                if player_id not in bests or record["score"] > bests[player_id]["score"]:
                    bests[player_id] = {
                        "initials": player["initials"],
                        "full_name": player["full_name"],
                        "score": record["score"],
                        "date": record["date"].strip().replace("\x00", " "),
                        "ago": time_ago(record["date"].strip().replace("\x00", " "), now_seconds),
                    }

    records = sorted(
        ({"player_id": pid, "initials": d["initials"], "full_name": d["full_name"], "score": d["score"], "date": d["date"], "ago": d["ago"]} for pid, d in bests.items()),
        key=lambda x: x["score"],
        reverse=True,
    )
    for idx, rec in enumerate(records, start=1):
        rec["rank"] = idx
    return records


@add_route("/api/player/scores/reset", auth=True)
def app_resetIndScores(request):
    """
    @api
    summary: Clear all scores for a single player
    auth: true
    request:
      query:
        - name: id
          type: int
          required: true
          description: Player index whose scores should be erased
    response:
      status_codes:
        - code: 200
          description: Scores cleared
      body:
        example: "ok"
    @end
    """
    from SPI_DataStore import blankIndPlayerScores

    index = int(request.args.get("id"))
    blankIndPlayerScores(index)


#
# Adjustments
#
@add_route("/api/adjustments/status")
def app_getAdjustmentStatus(request):
    """
    @api
    summary: Get the status of each adjustment bank
    response:
      status_codes:
        - code: 200
          description: Adjustment metadata returned
      body:
        description: List of adjustment profiles with [Name, Active, Exists], along with a flag indicating overall support
        example:
            {
                "profiles": [
                    ["Free Play", false, true],
                    ["Arcade", true, true],
                    ["", false, false],
                    ["", false, false]
                ],
                "adjustments_support": true
            }
    @end
    """
    from Adjustments import get_adjustments_status

    return get_adjustments_status()


@add_route("/api/adjustments/name", auth=True)
def app_setAdjustmentName(request):
    """
    @api
    summary: Set the name of an adjustment profile
    auth: true
    request:
      body:
        - name: index
          type: int
          required: true
          description: Adjustment slot to rename
        - name: name
          type: string
          required: true
          description: New name for the slot
    response:
      status_codes:
        - code: 200
          description: Name updated
      body:
        example: "ok"
    @end
    """
    from Adjustments import set_name

    data = request.data
    index = int(data["index"])
    name = data["name"]
    set_name(index, name)


@add_route("/api/adjustments/capture", auth=True)
def app_captureAdjustments(request):
    """
    @api
    summary: Capture current adjustments into a profile
    auth: true
    request:
      body:
        - name: index
          type: int
          required: true
          description: Destination profile for captured adjustments
    response:
      status_codes:
        - code: 200
          description: Adjustments stored
      body:
        example: "ok"
    @end
    """
    from Adjustments import store_adjustments

    store_adjustments(int(request.data["index"]))


@add_route("/api/adjustments/restore", auth=True, cool_down_seconds=5)
def app_restoreAdjustments(request):
    """
    @api
    summary: Restore adjustments from a saved profile
    auth: true
    request:
      body:
        - name: index
          type: int
          required: true
          description: Adjustment profile to restore
    response:
      status_codes:
        - code: 200
          description: Adjustments restored
      body:
        example: "ok"
    @end
    """
    from Adjustments import restore_adjustments

    restore_adjustments(int(request.data["index"]))


#
# Settings
#
@add_route("/api/settings/get_claim_methods")
def app_getScoreCap(request):
    """
    @api
    summary: Read score entry methods
    response:
      status_codes:
        - code: 200
          description: Claim methods returned
      body:
        description: All keys are available methods for entering initials, only enabled methods are true
        example:
            {
                "on-machine": true,
                "web-ui": false
            }
    @end
    """
    record = ds_read_record("extras", 0)
    return {
        "on-machine": record["enter_initials_on_game"],
        "web-ui": record["claim_scores"],
    }


@add_route("/api/settings/set_claim_methods", auth=True)
def app_setScoreCap(request):
    """
    @api
    summary: Configure which score claim methods are enabled
    auth: true
    request:
      body:
        - name: on-machine
          type: bool
          required: false
          description: Allow initials entry on the physical game
        - name: web-ui
          type: bool
          required: false
          description: Allow initials entry via the web interface
    response:
      status_codes:
        - code: 200
          description: Preferences updated
      body:
        example: "ok"
    @end
    """
    json_data = request.data
    record = ds_read_record("extras", 0)
    if "on-machine" in json_data:
        record["enter_initials_on_game"] = bool(json_data["on-machine"])
    if "web-ui" in json_data:
        record["claim_scores"] = bool(json_data["web-ui"])
    ds_write_record("extras", record, 0)


@add_route("/api/settings/get_tournament_mode")
def app_getTournamentMode(request):
    """
    @api
    summary: Get whether tournament mode is enabled
    response:
      status_codes:
        - code: 200
          description: Tournament mode returned
      body:
        description: Flag indicating tournament mode state
        example: {"tournament_mode": true}
    @end
    """
    tournament_mode = ds_read_record("extras", 0)["tournament_mode"]
    return {"tournament_mode": tournament_mode}


@add_route("/api/settings/set_tournament_mode", auth=True)
def app_setTournamentMode(request):
    """
    @api
    summary: Enable or disable tournament mode
    auth: true
    request:
      body:
        - name: tournament_mode
          type: bool
          required: true
          description: New tournament mode setting
    response:
      status_codes:
        - code: 200
          description: Setting saved
      body:
        example: "ok"
    @end
    """
    json_data = request.data
    if "tournament_mode" in json_data:
        info = ds_read_record("extras", 0)
        info["tournament_mode"] = bool(json_data["tournament_mode"])
        ds_write_record("extras", info, 0)


@add_route("/api/settings/get_show_ip")
def app_getShowIP(request):
    """
    @api
    summary: Check whether the IP address is shown on the display
    response:
      status_codes:
        - code: 200
          description: Preference returned
      body:
        description: Flag indicating whether the IP is displayed
        example: {"show_ip": true}
    @end
    """
    return {"show_ip": ds_read_record("extras", 0)["show_ip_address"]}


@add_route("/api/settings/set_show_ip", auth=True)
def app_setShowIP(request):
    """
    @api
    summary: Set whether the IP address should be shown on the display
    auth: true
    request:
      body:
        - name: show_ip
          type: bool
          required: true
          description: Whether to show the IP address on screen
    response:
      status_codes:
        - code: 200
          description: Preference updated
      body:
        example: "ok"
    @end
    """
    data = request.data
    info = ds_read_record("extras", 0)
    info["show_ip_address"] = bool(data["show_ip"])
    ds_write_record("extras", info, 0)
    import displayMessage

    displayMessage.refresh()


@add_route("/api/time/midnight_madness_available")
def app_midnightMadnessAvailable(request):
    """
    @api
    summary: Report if Midnight Madness mode is supported
    response:
      status_codes:
        - code: 200
          description: Availability returned
      body:
        description: Flag indicating if the game supports Midnight Madness
        example: {"available": true}
    @end
    """
    if S.gdata["GameInfo"].get("Clock") == "MM":
        return {"available": True}
    else:
        return {"available": False}


@add_route("/api/time/get_midnight_madness")
def app_getMidnightMadness(request):
    """
    @api
    summary: Read Midnight Madness configuration
    response:
      status_codes:
        - code: 200
          description: Configuration returned
      body:
        description: Flags describing whether Midnight Madness is enabled and always on
        example:
            {
                "enabled": true,
                "always": false
            }
    @end
    """
    record = ds_read_record("extras", 0)
    return {
        "enabled": record.get("WPCTimeOn", False),
        "always": record.get("MM_Always", False),
    }


@add_route("/api/time/set_midnight_madness", auth=True)
def app_setMidnightMadness(request):
    """
    @api
    summary: Set Midnight Madness configuration
    auth: true
    request:
      body:
        - name: always
          type: bool
          required: true
          description: Keep Midnight Madness enabled for all games
        - name: enabled
          type: bool
          required: true
          description: Enable timed Midnight Madness events
    response:
      status_codes:
        - code: 200
          description: Configuration saved
      body:
        example: "ok"
    @end
    """
    data = request.data
    info = ds_read_record("extras", 0)
    info["MM_Always"] = bool(data["always"])
    info["WPCTimeOn"] = bool(data["enabled"])
    ds_write_record("extras", info, 0)


@add_route("/api/time/trigger_midnight_madness")
def app_triggerMidnightMadness(request):
    """
    @api
    summary: Immediately trigger Midnight Madness
    response:
      status_codes:
        - code: 200
          description: Event triggered
      body:
        example: "ok"
    @end
    """
    import Time

    Time.trigger_midnight_madness()


@add_route("/api/settings/factory_reset", auth=True)
def app_factoryReset(request):
    """
    @api
    summary: Perform a full factory reset of Vector and the pinball machine
    auth: true
    response:
      status_codes:
        - code: 200
          description: Reset initiated
      body:
        example: "ok"
    @end
    """
    import reset_control
    from Adjustments import blank_all as A_blank
    from logger import logger_instance
    from machine import reset
    from SPI_DataStore import blankAll as D_blank
    from SPI_Store import write_16_fram

    Log = logger_instance

    reset_control.reset()  # turn off pinbal machine
    ram_access = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
    Log.delete_log()
    D_blank()
    A_blank()
    Log.log("BKD: Factory Reset")

    # corrupt adjustments to force game factory reset on next boot
    for i in range(1930, 1970):
        ram_access[i] = 0
    write_16_fram(SRAM_DATA_BASE + 1930, 1930)
    write_16_fram(SRAM_DATA_BASE + 1950, 1950)

    reset()  # reset PICO


@add_route("/api/settings/reboot", auth=True)
def app_reboot(request):
    """
    @api
    summary: Reboot the Pinball machine
    auth: true
    response:
      status_codes:
        - code: 200
          description: Reboot initiated
      body:
        example: "ok"
    @end
    """
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
    """
    @api
    summary: Get the last known IP address
    response:
      status_codes:
        - code: 200
          description: IP returned
      body:
        description: Last recorded IP address
        example: {"ip": "192.168.0.10"}
    @end
    """
    ip_address = ds_read_record("extras", 0)["lastIP"]
    return {"ip": ip_address}


@add_route("/api/available_ssids")
def app_getAvailableSSIDs(request):
    """
    @api
    summary: Scan for nearby Wi-Fi networks
    response:
      status_codes:
        - code: 200
          description: Networks listed
      body:
        description: Array of SSID records with signal quality and configuration flag
        example:
            [
                {
                    "ssid": "MyNetwork",
                    "rssi": -40,
                    "configured": true
                }
            ]
    @end
    """
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
    """
    @api
    summary: List other vector devices discovered on the local network
    response:
      status_codes:
        - code: 200
          description: Peer map returned
      body:
        description: Mapping of peer identifiers to network information
        example:
            {
                "192.168.4.243": {
                    "name": "Pinbot",
                    "self": true
                }
            }
    @end
    """
    from discovery import get_peer_map

    return get_peer_map()


#
# Time
#
@add_route("/api/set_date", auth=True)
def app_setDateTime(request):
    """
    @api
    summary: Set Vector's date and time
    auth: true
    request:
      body:
        - name: date
          type: list
          required: true
          description: RTC tuple [year, month, day, hour, minute, second]
    response:
      status_codes:
        - code: 200
          description: Clock updated
      body:
        example: "ok"
    @end
    """
    date = [int(e) for e in request.json["date"]]

    # rtc will calculate the day of the week for us
    rtc.datetime((date[0], date[1], date[2], 0, date[3], date[4], date[5], 0))


@add_route("/api/get_date")
def app_getDateTime(request):
    """
    @api
    summary: Read the current time according to Vector
    response:
      status_codes:
        - code: 200
          description: RTC timestamp returned
      body:
        description: Tuple containing RTC date/time fields
        example: {"date": [2024, 1, 1, 0, 12, 0, 0]}
    @end
    """
    return {"date": list(rtc.datetime())}


#
# Miscellaneous
#
@add_route("/api/version")
def app_version(request):
    """
    @api
    summary: Get the software version. Note: this is the version for the target hardware (what the user sees) and not the release version.
    response:
      status_codes:
        - code: 200
          description: Version returned
      body:
        description: Current firmware version string
        example: {"version": "1.0.0"}
    @end
    """
    from systemConfig import SystemVersion

    return {"version": SystemVersion}


@add_route("/api/fault")
def app_install_fault(request):
    """
    @api
    summary: Get the list of currently active faults
    response:
      status_codes:
        - code: 200
          description: Faults returned
      body:
        description: Collection of fault flags and details
        example: {"faults": []}
    @end
    """
    import SharedState

    return SharedState.faults


#
# File IO
#
@add_route("/api/export/scores")
def app_export_leaderboard(request):
    """
    @api
    summary: Export all leaderboard data
    response:
      status_codes:
        - code: 200
        description: Leaderboard export file returned
      body:
        example: {
            "scores": {"tournament": [{"initials": "AAA", "score": 938479, "index": 2, "game": 0}],
            "leaders": [{"initials": "MSM", "date": "02/04/2025", "full_name": "Maxwell Mullin", "score": 2817420816}]},
            "version": 1
        }
    @end
    """
    from FileIO import download_scores

    return download_scores()


@add_route("/api/import/scores", auth=True)
def app_import_leaderboard(request):
    """
    @api
    summary: Import leaderboard data from an uploaded file
    auth: true
    request:
      body:
        - name: file
          type: bytes
          required: true
          description: Score export file content
    response:
      status_codes:
        - code: 200
          description: Import completed
      body:
        description: Success indicator
        example: {"success": true}
    @end
    """
    from FileIO import import_scores

    data = request.data
    return {"success": import_scores(data)}


@add_route("/api/memory-snapshot")
def app_memory_snapshot(request):
    """
    @api
    summary: Stream a snapshot of memory contents
    response:
      status_codes:
        - code: 200
          description: Snapshot streaming
      body:
        description: Text stream of byte values
    @end
    """
    ram_access = bytes(uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH))
    for value in ram_access:
        yield f"{value}\n".encode("utf-8")


@add_route("/api/logs", cool_down_seconds=10, single_instance=True, auth=True)
def app_getLogs(request):
    """
    @api
    summary: Download the system log file
    auth: true
    response:
      status_codes:
        - code: 200
          description: Log download streaming
      body:
        description: Log file content
    @end
    """
    from FileIO import download_log

    return download_log()


#
# Special Formats
#


# list format options
def get_available_formats():
    return [
        {"id": 0, "name": "Arcade", "description": "Manufacturer standard game play", "enable_function": None},
        {"id": 1, "name": "Practice", "description": "Practice mode with unlimited balls and no score tracking", "enable_function": None},
        {
            "id": 2,
            "name": "Golf",
            "description": "Hit a specific target in the least number of balls",
            "options": {
                "target": {
                    "type": "select",
                    "options": {
                        "11": "Crazy Bobs",
                        "12": "Spinner",
                        "13": "Left Outlane",
                    },
                    "default": "11",
                }
            },
            "enable_function": None,
        },
    ]


# 0 will always be default
@add_route("/api/formats/available")
def app_list_available_formats(request):
    """
    @api
    summary: Get the list of available game formats
    response:
      status_codes:
        - code: 200
          description: Formats returned
      body:
        description: Collection of available game formats with metadata and configuration options
        example:
            [
                {
                    "id": 0,
                    "name": "Arcade",
                    "description": "Manufacturer standard game play"
                }
            ]
    @end
    """
    return [{k: v for k, v in fmt.items() if k != "enable_function"} for fmt in get_available_formats()]


# set current format
@add_route("/api/formats/set", auth=True)
def app_set_current_format(request):
    """
    @api
    summary: Set the active game format
    auth: true
    request:
        body:
            - name: format_id
                type: int
                required: true
                description: Format identifier to activate
            - name: options
                type: dict
                required: false
                description: Configuration options for the selected format
    response:
      status_codes:
        - code: 200
          description: Format set successfully
    @end
    """
    data = request.data
    if not isinstance(data, dict) or "format_id" not in data:
        return {"error": "Missing required field: format_id"}, 400
    format_id = data["format_id"]
    available_formats = get_available_formats()
    format_dict = next((fmt for fmt in available_formats if fmt["id"] == format_id), None)
    if not format_dict:
        return {"error": f"Invalid format id: {format_id}"}, 400

    # Call enable function if it exists
    enable_function = format_dict.get("enable_function", None)
    if not enable_function:
        raise NotImplementedError("Format enable function not implemented yet")

    # Enable the format
    enable_function(data.get("options", {}))

    S.game_status["format"] = {"format_id": format_id}
    if "options" in data:
        S.game_status["format"]["options"] = data["options"]

    return


# get active format(s)
@add_route("/api/formats/active")
def app_get_active_formats(request):
    """
    @api
    summary: Get the currently active game format
    response:
        status_codes:
        - code: 200
          description: Active format returned
      body:
        description: Current game format identifier and options
        example:
            {
                "format_id": 1,
                "options": {"target": "11"}
            }
    @end
    """

    return S.game_status.get("format", {"format_id": 0})


# get switch diagnostics
@add_route("/api/diagnostics/switches")
def app_get_switch_diagnostics(request):
    """
    @api
    summary: Get diagnostic information for all switches
    response:
        status_codes:
        - code: 200
          description: Switch diagnostics returned
        body:
        description: Collection of switch records with row, column, value, and optional label
        example:
            [
                {
                    "row": 1,
                    "col": 1,
                    "val": 100,
                    "label": "Left Flipper"
                }
            ]
    @end
    """
    switches = [
        (1, 1, 100, "Left Flipper"),
        (1, 2, 100, "Right Flipper"),
        (1, 3, 90),
        (1, 4, 100),
        (1, 5, 80),
        (1, 6, 100),
        (1, 7, 100, "Start Button"),
        (2, 2, 100),
        (2, 4, 50),
        (2, 5, 100),
        (2, 8, 100),
        (3, 1, 10),
        (3, 3, 100, "Shooter Lane"),
        (3, 6, 100),
        (4, 2, 0, "Tilt"),
        (4, 5, 100),
        (4, 7, 100),
        (5, 4, 100),
        (5, 6, 5),
        (5, 8, 100),
    ]

    return [
        {
            "row": switch[0],
            "col": switch[1],
            "val": switch[2],
            "label": switch[3] if len(switch) > 3 else "",
        }
        for switch in switches
    ]



#
# Updates
#
@add_route("/api/update/check", cool_down_seconds=10)
def app_updates_available(request):
    """
    @api
    summary: Get the metadata for the latest available software version. This does not download or apply the update.
        Compare the returned version to the current version to determine if an update is available.
    response:
      status_codes:
        - code: 200
          description: Update metadata returned
      body:
        description: JSON payload describing available updates
        example:
            {
                "release_page": "https://github.com/...",
                "notes": "Another Great Release! Here's what we changed",
                "published_at": "2025-12-30T17:54:49+00:00",
                "url": "https://github.com/...",
                "version": "1.9.0"
            }
    @end
    """
    from mrequests.mrequests import get
    from systemConfig import updatesURL

    resp = get(updatesURL, timeout=10)

    try:
        data = resp.json()
    finally:
        resp.close()

    return data


@add_route("/api/update/apply", auth=True)
def app_apply_update(request):
    """
    @api
    summary: Download and apply a software update from the provided URL.
    auth: true
    request:
      body:
        - name: url
          type: string
          required: true
          description: Signed update package URL
        - name: skip_signature_check
          type: bool
          required: false
          description: Bypass signature validation (for developer builds)
    response:
      status_codes:
        - code: 200
          description: Streaming progress updates
      body:
        description: Sequence of JSON log entries with ``log`` and ``percent`` fields
        example:
            {
                "log": "Starting update",
                "percent": 0
            }
    @end
    """
    from logger import logger_instance as Log
    from update import apply_update

    yield json_dumps({"log": "Starting update", "percent": 0})
    data = request.data
    try:
        for response in apply_update(data["url"], skip_signature_check=data.get("skip_signature_check", False)):
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
        """
        @api
        summary: Indicates if Vector is running in AP or app mode
        response:
          status_codes:
            - code: 200
              description: Mode reported
          body:
            description: Flag showing AP mode status
            example: {"in_ap_mode": false}
        @end
        """
        return {"in_ap_mode": False}


#
# AP mode routes
#
def add_ap_mode_routes():
    """Routes only available in AP mode"""

    @add_route("/api/in_ap_mode")
    def app_inAPMode(request):
        # This replaces the app mode version when in AP mode
        return {"in_ap_mode": True}

    @add_route("/api/settings/set_vector_config")
    def app_setWifi(request):
        """
        @api
        summary: [AP Mode Only] Configure Wi-Fi credentials and default game
        request:
          body:
            - name: ssid
              type: string
              required: true
              description: Wi-Fi network name
            - name: wifi_password
              type: string
              required: true
              description: Wi-Fi network password
            - name: vector_password
              type: string
              required: true
              description: Password for authenticated API access
            - name: game_config_filename
              type: string
              required: true
              description: Game configuration filename to load
        response:
          status_codes:
            - code: 200
              description: Configuration saved
          body:
            example: "ok"
        @end
        """
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


def connect_to_wifi(initialize=False):
    from phew import is_connected_to_wifi as phew_is_connected
    from phew.server import initialize_timedate, schedule

    if phew_is_connected() and not initialize:
        schedule(initialize_timedate, 5000, log="Server: Initialize time /date")
        return True

    Pico_Led.start_slow_blink()

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
            print(f"Connected to wifi with IP address: {ip_address}")

            # clear any wifi related faults
            if faults.fault_is_raised(faults.ALL_WIFI):
                faults.clear_fault(faults.ALL_WIFI)

            schedule(initialize_timedate, 5000, log="Server: Initialize time & date")
            Pico_Led.on()
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


try:
    # This import must be after the add_route function is defined at minimum
    import em_routes  # noqa: F401
except Exception:
    pass
    # print(f"Error importing em_routes: {e}")  this will run on all boards - so not really fault?


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
        connect_to_wifi(True)
        add_app_mode_routes()
        from phew.server import set_callback

        set_callback(four_oh_four)

    print("-" * 10)
    print("Starting server")
    print("-" * 10)
    from phew.server import run

    run(ap_mode)
