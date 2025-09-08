from asyncio import sleep

import ubinascii
import ujson
from backend import hmac_sha256
from curve25519 import generate_x25519_keypair
from rsa.key import PublicKey
from rsa.pkcs1 import verify
from SPI_DataStore import read_record as ds_read_record
from mqtt_client import connect

MAX_CHALLENGES = 10
ORIGIN_URL = "https://origin-beta.doze.dev"
ORIGIN_MQTT_URL = f"mqtt://{ORIGIN_URL}:1883/origin".replace("https://", "").replace("http://", "")
ORIGIN_PUBLIC_KEY = PublicKey(
    n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
    e=65537,
)

mqtt = None
metadata = {}


def _b64decode(s: str) -> bytes:
    return ubinascii.a2b_base64(s)


def _b64encode(b: bytes) -> str:
    return ubinascii.b2a_base64(b).decode().strip()


def get_config():
    # First check if we have a pending claim
    if metadata.get("pending_claim"):
        pending_claim = metadata["pending_claim"]
        if pending_claim.get("id") and pending_claim.get("secret"):
            return pending_claim

    cloud_config = ds_read_record("cloud", 0)

    if not cloud_config.get("id"):
        raise Exception("No ID set in cloud config")
    if not cloud_config.get("secret"):
        raise Exception("No secret set in cloud config")

    # Check if id is all zeros
    if cloud_config["id"] == [0] * len(cloud_config["id"]):
        raise Exception("ID cannot be all zeros")

    # Check if secret is all zeros
    if cloud_config["secret"] == [0] * len(cloud_config["secret"]):
        raise Exception("Secret cannot be all zeros")

    # Convert id and secret from list of bytes to base64 encoded string
    if isinstance(cloud_config["id"], list):
        cloud_config["id"] = _b64encode(bytes(cloud_config["id"]))
    if isinstance(cloud_config["secret"], list):
        cloud_config["secret"] = _b64encode(bytes(cloud_config["secret"]))

    return cloud_config


def is_claimed() -> bool:
    config = ds_read_record("cloud", 0)
    return config.get("id") and config.get("secret")


def open_mqtt():
    global mqtt

    if mqtt is None:
        mqtt = connect(ORIGIN_MQTT_URL)

    if mqtt is None:
        raise Exception("Failed to open MQTT connection")

    return mqtt


def close_mqtt():
    """Close the persistent MQTT connection."""
    global mqtt
    if mqtt is not None:
        try:
            mqtt.close()
        except Exception:
            pass
        mqtt = None


def send(route: str, msg: str, sign: bool = True):
    print("Sending", route, msg, "sign=" + str(sign))
    global metadata, mqtt
    if len(route) == 0 or "|" in route:
        raise Exception("Invalid route:", route)

    open_mqtt()

    msg = route + "|" + msg

    if sign:
        next_challenge = metadata.get("challenges", [None]).pop(0)
        if not next_challenge:
            send_request_challenges()

        while next_challenge := metadata.get("challenges", [None]).pop(0):
            sleep(0.5)  # wait a moment for challenges to arrive
            recv()

        config = get_config()

        # Append HMAC fields if signing
        msg += "|" + str(config["id"])
        msg += "|" + str(next_challenge)
        msg += "|" + str(hmac_sha256(config["secret"], msg))

    mqtt.send(msg)

    if sign and len(metadata.get("challenges", [])) < MAX_CHALLENGES / 4:
        send_request_challenges()


def recv():
    global mqtt
    open_mqtt()

    try:
        resp = mqtt.recv()
        print("Received", resp)
    except OSError:
        mqtt = None
        open_mqtt()
        return  # no message to process

    if not resp:
        mqtt = None
        open_mqtt()
        return

    if b"|" not in resp:
        print("Response missing signature: " + resp.decode())
        return

    body, signature = resp.rsplit(b"|", 1)
    result = verify(body, ubinascii.a2b_base64(signature.strip()), ORIGIN_PUBLIC_KEY)

    if result != "SHA-256":
        print("Origin server response signature invalid!")
        return

    if not body:
        print("Response Route missing")
        return

    route, body = body.decode().split("|", 1)

    routes = {"handshake": handle_handshake, "claimed": handle_claimed, "challenges": handle_challenges}

    if route in routes:
        routes[route](body)
    else:
        print("Received unknown route:", route)


def send_handshake_request():
    # Generate X25519 keys
    priv, pub = generate_x25519_keypair()

    # Send client key + game title as JSON
    game_title = ds_read_record("configuration", 0)["gamename"]
    client_key_b64 = _b64encode(pub)
    msg = ujson.dumps({"client_key": client_key_b64, "game_title": game_title})

    send("handshake", msg, sign=False)

    global metadata

    metadata["pending_handshake"] = {"private_key": priv}


def send_request_challenges():
    # request the max challenges number of challenges
    send("request_challenges", f'{{"num": {MAX_CHALLENGES}}}', sign=False)


def send_acknowledgment():
    send("ack", "")


def handle_handshake(data):
    global metadata

    if "pending_handshake" not in metadata:
        raise Exception("No pending handshake")

    data = ujson.loads(data)
    machine_id = _b64decode(data.get("machine_id"))
    server_public_key = _b64decode(data.get("server_key"))  # 32 bytes
    shared_secret = metadata["pending_handshake"].get("private_key").exchange(server_public_key)
    claim_url = data.get("claim_url")

    # make sure machine ID is bytes and 16 bytes long
    if not isinstance(machine_id, bytes) and len(machine_id) != 16:
        raise Exception("Invalid machine ID")

    # make sure secret is bytes and 32 bytes long
    if not isinstance(shared_secret, bytes) or len(shared_secret) != 32:
        raise Exception("Invalid secret")

    if not isinstance(claim_url, str):
        raise Exception("Invalid claim URL")

    # Stash in SharedState for your app logic
    record = {"id": machine_id, "secret": shared_secret, "claim_url": claim_url}
    metadata["pending_claim"] = record

    # remove the pending_handshake from metadata
    del metadata["pending_handshake"]


def handle_claimed(data):
    from SPI_DataStore import write_record as ds_write_record

    if "pending_claim" not in metadata:
        raise Exception("No pending claim")

    claim_data = metadata["pending_claim"]
    ds_write_record("cloud", 0, {"id": claim_data["id"], "secret": claim_data["secret"]})

    del metadata["pending_claim"]


def handle_challenges(data):
    global metadata
    challenges = [c for c in ujson.loads(data) if c]

    current_challenges = metadata.get("challenges", [])

    num_new_challenges = MAX_CHALLENGES - len(challenges)
    kept_challenges = MAX_CHALLENGES - num_new_challenges

    # trim down current challenges
    current_challenges = current_challenges[:kept_challenges]
    current_challenges.extend(challenges)
    metadata["challenges"] = current_challenges


def status():
    if metadata.get("pending_claim"):
        return {"linked": False, "claim_url": metadata["pending_claim"].get("claim_url", "claim_url_missing")}

    try:
        get_config()
        return {"linked": True}
    except Exception:
        pass

    return {"linked": False}
