import gc

from backend import hmac_sha256
from discovery import send_sock
from micropython import const
from ujson import dumps
from urandom import getrandbits
from urequests import post
from utime import ticks_diff, ticks_ms

_MAX_CHALLENGES = const(10)
_ORIGIN_PUBLIC_KEY_N = const(
    28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273  # noqa
)
_ORIGIN_PUBLIC_KEY_E = const(65537)
challenges = []  # queue of server-provided challenges
previous_state = None  # last gamestate string sent to server


def _b64decode(s: str):
    from ubinascii import a2b_base64

    return a2b_base64(s)


def _b64encode(b: bytes):
    from ubinascii import b2a_base64

    return b2a_base64(b).decode().strip()


class Config:
    def __init__(self):
        self.cache = None

    @property
    def id_bytes(self):
        if self.cache is None:
            self.load_config()
        return self.cache.get("id", None) if self.cache else None

    @property
    def secret_bytes(self):
        if self.cache is None:
            self.load_config()
        return self.cache.get("secret", None) if self.cache else None

    @property
    def id_b64(self):
        return _b64encode(self.id_bytes) if self.id_bytes else None

    @property
    def secret_b64(self):
        return _b64encode(self.secret_bytes) if self.secret_bytes else None

    def load_config(self):
        from SPI_DataStore import read_record as ds_read_record

        if self.cache is not None:
            return self.cache

        record = ds_read_record("cloud", 0)

        # id is 16 bytes; secret is 32 bytes in the FRAM layout
        if record.get("id") == [0] * 16 or record.get("secret") == [0] * 32:
            self.cache = None
            return

        record["id"] = bytes(record["id"])
        record["secret"] = bytes(record["secret"])

        self.cache = record

    def set_config(self, id, secret):
        from SPI_DataStore import write_record as ds_write_record

        if isinstance(id, str):
            id_bytes = _b64decode(id)
        elif isinstance(id, bytes):
            id_bytes = id
        else:
            raise ValueError("Invalid ID type")

        if isinstance(secret, str):
            secret_bytes = _b64decode(secret)
        elif isinstance(secret, bytes):
            secret_bytes = secret
        else:
            raise ValueError("Invalid Secret type")

        # Internally store raw bytes for consistency; expose base64 via properties
        self.cache = {
            "id": id_bytes,
            "secret": secret_bytes,
        }

        # Correct argument order: write_record(structure_name, record, index=0, set=0)
        # Previous call passed 0 as the record (int) and the dict as the index, leading to
        # a TypeError in SPI_DataStore.write_record when attempting dict * int.
        ds_write_record(
            "cloud",
            {
                "id": id_bytes,
                "secret": secret_bytes,
            },
        )

    def is_enabled(self):
        return self.id_bytes is not None and self.secret_bytes is not None


config = Config()


def get_next_challenge():
    global challenges
    if len(challenges) < 1:
        data = make_request("api/v1/machines/challenges", {"n": _MAX_CHALLENGES}, sign=False)
        if not data or "challenges" not in data:
            raise Exception("Invalid challenges response")
        encoded = data["challenges"]
        if not isinstance(encoded, list):
            raise Exception("Invalid challenges format")
        challenges = [_b64decode(c) for c in encoded[:_MAX_CHALLENGES] if c]
    return challenges.pop(0)


def random_bytes(n: int):
    from urandom import getrandbits

    output = getrandbits(8).to_bytes(1, "big")
    for i in range(n - 1):
        output += getrandbits(8).to_bytes(1, "big")
    return output


def make_request(path: str, body: dict = None, sign: bool = True, validate: bool = True):
    if body is None:
        body = b""

    if isinstance(body, dict):
        from ujson import dumps

        body = dumps(body).encode("utf-8")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    elif isinstance(body, bytes):
        pass
    else:
        raise ValueError("Invalid body type: {}".format(type(body)))

    print("Making request:", path, body, sign, validate)
    # generate a random 32 byte challenge for the server if we need it
    client_challenge = random_bytes(32)

    print("Client challenge:", client_challenge)

    gc.collect()
    response = send_request(path, body, sign=sign, client_challenge=client_challenge)

    if validate:
        print("Validating response...")
        validate_response(response, client_challenge)

    print("getting response json...")
    data = response.json()
    print("Response data:", data)
    return data


def send_request(path: str, body_bytes: bytes, sign: bool = True, client_challenge: bytes = None):
    if path.startswith("/"):
        raise ValueError("Path must not start with /")

    print("Preparing request:", path, body_bytes)
    headers = {
        "Content-Type": "application/json",
    }

    if client_challenge is not None:
        headers["X-Client-Challenge"] = _b64encode(client_challenge)

    if config.id_b64 is not None:
        headers["X-Machine-ID"] = config.id_b64

    if sign:
        print("Signing request:", path, body_bytes)
        next_challenge = get_next_challenge()
        headers["X-Server-Challenge"] = _b64encode(next_challenge)
        msg = path.encode("utf-8") + next_challenge + body_bytes
        print("Signing message:", msg)
        hmac_b64 = _b64encode(hmac_sha256(config.secret_bytes, msg))
        headers["X-Signature"] = "v1=" + hmac_b64

    print("Sending request:", path, body_bytes, headers)
    gc.collect()

    return post("https://origin-beta.doze.dev/" + path, data=body_bytes, headers=headers)


def validate_response(response, client_challenge: bytes):
    from rsa.key import PublicKey
    from rsa.pkcs1 import verify

    if not response:
        raise Exception("Empty response is not valid")

    signature = response.headers.get("X-Signature", False)
    if not signature:
        raise Exception("Response missing signature")

    body = response.content

    if not body:
        raise Exception("Response body is missing")

    shared_secret = config.secret_bytes
    print("Validating response:", body, signature)

    gc.collect()
    origin_public_key = PublicKey(n=_ORIGIN_PUBLIC_KEY_N, e=_ORIGIN_PUBLIC_KEY_E)
    result = verify(shared_secret + client_challenge + body, _b64decode(signature), origin_public_key)

    if result != "SHA-256":
        raise Exception("Response signature invalid")

    return


def send_handshake_request():
    import SharedState as S
    from curve25519 import generate_x25519_keypair

    # Generate X25519 keys
    priv, pub = generate_x25519_keypair()

    # Send client key + game title as JSON
    game_title = S.gdata.get("GameInfo", {}).get("GameName", "Unknown Title")
    client_key_b64 = _b64encode(pub)

    data = make_request("api/v1/machines/handshake", {"client_public_key_b64": client_key_b64, "game_title": game_title}, sign=False, validate=False)

    print("handshake response:", data)

    machine_id = data.get("machine_id") or data.get("id")
    if not machine_id:
        raise Exception("Handshake response missing machine_id/id")
    server_key_b64 = data.get("server_key") or data.get("server_public_key")
    if not server_key_b64:
        raise Exception("Handshake response missing server_key/server_public_key")

    config.set_config(
        id=machine_id,
        secret=priv.exchange(_b64decode(server_key_b64)),
    )
    print("config set:", config.cache)

    return status()


# def check_in():
#     global config

#     # TODO figure out the right logic to use here
#     # if not config.is_claimed() and config.claim_url is None:
#     #     return

#     data = make_request("api/v1/machines/checkin")
#     for msg in data.get("messages", []):
#         msg_type = msg.get("type", None)
#         if msg_type is None:
#             print("Invalid message from origin, missing type")
#             continue


def status():
    if not config.is_enabled():
        return {"is_claimed": None, "claim_url": None, "username": None}

    return make_request("api/v1/machines/claim_status", sign=True, validate=True)


# Simulated gameplay state (can be disabled by commenting out a single line in push_game_state)
_sim_initialized = False
_sim_scores = [0, 0, 0, 0]
_sim_ball_in_play = 1
_sim_current_player = 0  # 0..3 for players 1..4
_sim_plays_remaining = 0
_sim_game_start_ms = None


def _randint(a, b):
    span = b - a + 1
    return a + (getrandbits(16) % span)


def _reset_new_game():
    global _sim_scores, _sim_ball_in_play, _sim_current_player, _sim_plays_remaining, _sim_game_start_ms

    _sim_scores = [0, 0, 0, 0]
    _sim_ball_in_play = 1
    _sim_current_player = 0
    _sim_plays_remaining = _randint(3, 12)
    _sim_game_start_ms = ticks_ms()


def _push_game_state_sim(game_time, scores, ball_in_play, game_active):
    global previous_state
    global _sim_initialized, _sim_scores, _sim_ball_in_play, _sim_current_player, _sim_plays_remaining, _sim_game_start_ms

    try:
        # One-time init
        if not _sim_initialized:
            _sim_initialized = True
            _reset_new_game()

        # If last ball ended (ball 0), start a new game
        if _sim_ball_in_play == 0:
            _reset_new_game()

        # If this player is done, advance player (and maybe ball)
        if _sim_plays_remaining <= 0:
            _sim_current_player = (_sim_current_player + 1) % 4
            _sim_plays_remaining = _randint(30, 100)
            if _sim_current_player == 0:
                _sim_ball_in_play += 1
                if _sim_ball_in_play > 5:
                    # Game over: reset ball to 0 and scores to 0 (visible "reset" frame)
                    _sim_ball_in_play = 0
                    _sim_scores = [0, 0, 0, 0]

        # If a ball is active, add some score to the active player
        if _sim_ball_in_play > 0:
            inc = _randint(1000, 50000)
            _sim_scores[_sim_current_player] += inc
            _sim_plays_remaining -= 1

        # Compute game time
        now = ticks_ms()
        game_time_ms = ticks_diff(now, _sim_game_start_ms) if _sim_game_start_ms is not None else 0

        # Deduplicate same state
        state_tail = "{},{},{},{},{}".format(_sim_scores[0], _sim_scores[1], _sim_scores[2], _sim_scores[3], _sim_ball_in_play)
        if previous_state == state_tail:
            return

    except Exception as e:
        print("Error pushing game state (sim):", e)

    _push_game_state_real(game_time_ms, _sim_scores, _sim_ball_in_play, game_active=_sim_ball_in_play > 0)


def _push_game_state_real(game_time, scores, ball_in_play, game_active):
    global previous_state
    try:
        # Deduplicate same state
        state_tail = "{},{},{},{},{}".format(
            scores[0] if len(scores) > 0 else 0,
            scores[1] if len(scores) > 1 else 0,
            scores[2] if len(scores) > 2 else 0,
            scores[3] if len(scores) > 3 else 0,
            ball_in_play,
        )
        if previous_state == state_tail:
            return

        packet = dumps({"machine_id_b64": config.id_b64, "gameTimeMs": game_time if game_time is not None else 0, "scores": scores, "ball_in_play": ball_in_play, "game_active": game_active})
        send_sock.sendto(packet.encode(), ("255.255.255.255", 6809))
        previous_state = state_tail
    except Exception as e:
        print("Error pushing game state (real):", e)


def push_game_state(game_time, scores, ball_in_play, game_active):
    # Toggle simulation: comment the next line to disable simulated gameplay.
    return _push_game_state_sim(game_time, scores, ball_in_play, game_active)

    # Normal behavior: uncomment the next line to use real game state.
    # return _push_game_state_real(game_time, scores, ball_in_play, game_active)
