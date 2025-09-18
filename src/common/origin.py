import ubinascii
import ujson
import urequests as requests
from backend import hmac_sha256
from curve25519 import generate_x25519_keypair
from rsa.key import PublicKey
from rsa.pkcs1 import verify

MAX_CHALLENGES = 10
ORIGIN_URL = "https://origin-beta.doze.dev/"
ORIGIN_PUBLIC_KEY = PublicKey(
    n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
    e=65537,
)
challenges = []  # queue of server-provided challenges


def _b64decode(s: str):
    return ubinascii.a2b_base64(s)


def _b64encode(b: bytes):
    return ubinascii.b2a_base64(b).decode().strip()


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


config = Config()


def get_next_challenge():
    global challenges
    if len(challenges) < 1:
        data = make_request("api/v1/machines/challenges", {"n": MAX_CHALLENGES}, sign=False)
        if not data or "challenges" not in data:
            raise Exception("Invalid challenges response")
        encoded = data["challenges"]
        if not isinstance(encoded, list):
            raise Exception("Invalid challenges format")
        challenges = [_b64decode(c) for c in encoded[:MAX_CHALLENGES] if c]
    return challenges.pop(0)


def random_bytes(n: int):
    from urandom import getrandbits

    output = getrandbits(8).to_bytes(1, "big")
    for i in range(n - 1):
        output += getrandbits(8).to_bytes(1, "big")
    return output


def make_request(path: str, body: dict = None, sign: bool = True, validate: bool = True):
    if body is None:
        body = {}

    # generate a random 32 byte challenge for the server if we need it
    client_challenge = random_bytes(32)

    response = send_request(path, ujson.dumps(body).encode("utf-8"), sign=sign, client_challenge=client_challenge)

    if validate:
        validate_response(response, client_challenge)

    data = response.json()
    print("Response data:", data)
    return data


def send_request(path: str, body_bytes: bytes, sign: bool = True, client_challenge: bytes = None):
    url = ORIGIN_URL.rstrip("/") + "/" + path.lstrip("/")

    print("Preparing request:", url, body_bytes)
    headers = {
        "Content-Type": "application/json",
    }

    if client_challenge is not None:
        headers["X-Client-Challenge"] = _b64encode(client_challenge)

    if config.id_b64 is not None:
        headers["X-Machine-ID"] = config.id_b64

    if sign:
        next_challenge = get_next_challenge()
        headers["X-Server-Challenge"] = _b64encode(next_challenge)
        msg = path.lstrip("/").encode("utf-8") + next_challenge + body_bytes
        print("Signing message:", msg)
        hmac_b64 = _b64encode(hmac_sha256(config.secret_bytes, msg))
        headers["X-Signature"] = "v1=" + hmac_b64

    print("Sending request:", url, body_bytes, headers)

    return requests.post(url, data=body_bytes, headers=headers)


def validate_response(response, client_challenge: bytes):
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

    result = verify(shared_secret + client_challenge + body, _b64decode(signature), ORIGIN_PUBLIC_KEY)

    if result != "SHA-256":
        raise Exception("Response signature invalid")

    return


def send_handshake_request():
    from SPI_DataStore import read_record as ds_read_record

    # Generate X25519 keys
    priv, pub = generate_x25519_keypair()

    # Send client key + game title as JSON
    game_title = ds_read_record("configuration", 0)["gamename"]
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
    if config.id_bytes is None or config.secret_bytes is None:
        return {"is_claimed": None, "claim_url": None, "username": None}

    return make_request("api/v1/machines/claim_status", sign=True, validate=True)
