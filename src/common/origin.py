import ubinascii
import ujson
from backend import hmac_sha256
from curve25519 import generate_x25519_keypair
from rsa.key import PublicKey
from rsa.pkcs1 import verify
from SPI_DataStore import read_record as ds_read_record
import urequests as requests

MAX_CHALLENGES = 10
ORIGIN_URL = "https://origin-beta.doze.dev/api/v1/"
ORIGIN_PUBLIC_KEY = PublicKey(
    n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
    e=65537,
)
metadata = {}

class Config():
    def __init__(self):
        self._loaded = False
        self._id = None
        self._secret = None
        self._claim_url = None
        self._claimed = None
        
    @property
    def id(self):
        if not self._loaded:
            self.load_from_fram()
        return self._id

    @property
    def secret(self):
        if not self._loaded:
            self.load_from_fram()
        return self._secret

    @property
    def claim_url(self):
        if not self._loaded:
            self.load_from_fram()
        return self._claim_url

    #setter that ensures we have loaded first
    @id.setter
    def id(self, value):
        if not self._loaded:
            self.load_from_fram()
        self._id = value
    
    @secret.setter
    def secret(self, value):
        if not self._loaded:
            self.load_from_fram()
        self._secret = value
    
    @claim_url.setter
    def claim_url(self, value):
        if not self._loaded:
            self.load_from_fram()
        self._claim_url = value

    def read_from_fram(self):
        record = ds_read_record("cloud", 0)
        if record.get("id"):
            record["id"] = _b64encode(bytes(record["id"])) if isinstance(record["id"], list) else record["id"]
        if record.get("secret"):
            record["secret"] = _b64encode(bytes(record["secret"])) if isinstance(record["secret"], list) else record["secret"]
        self.validate(record)
        return record

    def load_from_fram(self):
        record = self.read_from_fram()
        
        try:
            self.validate(record)
        except Exception as e:
            print("Invalid config in fram, resetting:", e)
            return
        
        self._id = record.get("id", None)
        self._secret = record.get("secret", None)
        self._loaded = True

    def save_to_fram(self):
        from SPI_DataStore import write_record as ds_write_record
        self.validate({"id": self._id, "secret": self._secret})
        ds_write_record("cloud", 0, {
            "id": _b64decode(self._id),
            "secret": _b64decode(self._secret)
        })

    def validate(self, data):
        if not data.get("id") or not data.get("secret"):
            raise Exception("ID and secret must be set")
        if data["id"] == _b64encode(bytes([0]*32)):
            raise Exception("ID cannot be all zeros")
        if data["secret"] == _b64encode(bytes([0]*32)):
            raise Exception("Secret cannot be all zeros")
    
    def claimed(self):
        self._claimed = True
        self._claim_url = None
        self._loaded = True
        self.save_to_fram()

    def is_claimed(self):
        if self._claimed is None:
            if self._claim_url is not None:
                self._claimed = False
            else:
                try:
                    self.read_from_fram()
                except Exception:
                    self._claimed = False
        return self._claimed

config = Config()


def _b64decode(s: str) -> bytes:
    return ubinascii.a2b_base64(s)


def _b64encode(b: bytes) -> str:
    return ubinascii.b2a_base64(b).decode().strip()

def get_next_challenge() -> bytes:
    next_challenge = metadata.get("challenges", [None]).pop(0)
    if not next_challenge:
        challenges = make_request("challenges", {"num": MAX_CHALLENGES}, sign=False)
        if not challenges or "challenges" not in challenges:
            raise Exception("Invalid challenges response")
        encoded = challenges["challenges"]
        if not isinstance(encoded, list):
            raise Exception("Invalid challenges format")
        metadata["challenges"] = [_b64decode(c) for c in encoded[:MAX_CHALLENGES] if c]
        next_challenge = metadata.get("challenges", [None]).pop(0)
    return next_challenge

def random_bytes(n: int) -> bytes:
    from urandom import getrandbits

    output = getrandbits(8).to_bytes(1, "big")
    for i in range(n - 1):
        output += getrandbits(8).to_bytes(1, "big")
    return output

def make_request(path: str, body: dict=None, sign: bool = True, validate: bool = True) -> dict:    
    url = ORIGIN_URL.rstrip("/") + "/" + path.lstrip("/")
    
    if body is None:
        body = {}
    
    # generate a random 32 byte challenge for the server if we need it
    client_challenge = None
    if sign or validate:
        client_challenge = random_bytes(32)

    response = send_request(url, ujson.dumps(body).encode("utf-8"), sign=sign, client_challenge=client_challenge)

    if validate:
        validate_response(response, client_challenge)
    
    return response.json()

def send_request(url: str, body_bytes: bytes, sign: bool=True, client_challenge: bytes=None) -> dict:
    headers = {
        "Content-Type": "application/json",
    }

    if config.id is not None:
        headers["X-Machine-ID"] = config.id

    if client_challenge is not None:
        headers["X-Client-Challenge"] = _b64encode(client_challenge)

    if sign:
        global config
        shared_secret = config.secret
        next_challenge = get_next_challenge()
        headers["X-Signature"] = "v1=" + hmac_sha256(shared_secret, url.encode("utf-8") + next_challenge + body_bytes)

    return requests.post(url, data=body_bytes, headers=headers)

def validate_response(response, client_challenge: bytes) -> None:
    if not response:
        raise Exception("Empty response is not valid")
    
    signature = response.headers.get("X-Signature", False)
    if not signature:
        raise Exception("Response missing signature")
    
    body = response.content

    if not body:
        raise Exception("Response body is missing")

    global config
    shared_secret = config.secret
    result = verify(shared_secret + client_challenge + body, ubinascii.a2b_base64(signature.strip()), ORIGIN_PUBLIC_KEY)

    if result != "SHA-256":
        raise Exception("Response signature invalid")

    return





def send_handshake_request():
    # Generate X25519 keys
    priv, pub = generate_x25519_keypair()

    # Send client key + game title as JSON
    game_title = ds_read_record("configuration", 0)["gamename"]
    client_key_b64 = _b64encode(pub)

    data = make_request("machines/handshake", {"client_public_key_b64": client_key_b64, "game_title": game_title}, sign=False)

    config.id = _b64decode(data.get("machine_id"))
    config.secret = priv.exchange(_b64decode(data.get("server_key")))
    config.claim_url = data.get("claim_url")

    return status()

def check_in():
    global config

    if not config.is_claimed():
        return
    
    data = make_request("machines/checkin")
    for msg in data.get("messages", []):
        msg_type = msg.get("type", None)
        if msg_type is None:
            print("Invalid message from origin, missing type")
            continue
        if msg_type == "claimed":
            config.claimed()

def status():
    global config

    try:
        if config.is_claimed():
            return {"linked": True}    
        if config.claim_url is not None:
            return {"linked": False, "claim_url": config.claim_url}
        else:
            return {"linked": False}
    except Exception as e:
        print("Error checking origin status:", e)
        return {"linked": False}