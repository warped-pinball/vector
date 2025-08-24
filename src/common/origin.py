import SharedState as S
import ubinascii
import ujson
from backend import hmac_sha256
from curve25519 import generate_x25519_keypair
from rsa.key import PublicKey
from rsa.pkcs1 import verify
from SPI_DataStore import read_record as ds_read_record
from websocket_client import connect

ORIGIN_URL = "https://origin-beta.doze.dev"
ORIGIN_WS_URL = f"ws://{ORIGIN_URL}:8002/ws/setup".replace("https://", "").replace("http://", "")  # TODO update port to 8001 for prod
ORIGIN_PUBLIC_KEY = PublicKey(
    n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
    e=65537,
)

ws = None
metadata = {}


def _b64decode(s: str) -> bytes:
    return ubinascii.a2b_base64(s)


def _b64encode(b: bytes) -> str:
    return ubinascii.b2a_base64(b).decode().strip()


def get_config():
    cloud_config = ds_read_record("cloud", 0)
    if not cloud_config.get("id"):
        raise Exception("No ID set in cloud config")
    if not cloud_config.get("secret"):
        raise Exception("No secret set in cloud config")
    return cloud_config


def open_ws(if_configured=True):
    global ws

    if ws is None:
        if if_configured:
            # check if we have an id & secret in datastore
            try:
                get_config()
            except Exception:
                # with the exception of when there's a pending claim or handshake, don't open WS
                if not metadata.get("pending_handshake") and not metadata.get("pending_claim"):
                    return None

        ws = connect(ORIGIN_WS_URL)

    if ws is None:
        raise Exception("Failed to open WebSocket connection")

    return ws


def close_ws():
    """
    Close the persistent websocket.
    """
    global ws
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass
        ws = None


def send(msg: str, sign: bool = True):
    ws = open_ws()

    if sign:
        cloud_config = get_config()
        if not S.origin_next_challenge:
            raise Exception("No next challenge set in SharedState")

        # Append HMAC fields if signing
        msg += "|" + str(cloud_config["id"])
        msg += "|" + str(S.origin_next_challenge)
        msg += "|" + str(hmac_sha256(cloud_config["secret"], msg))

    ws.send(msg)


def recv():
    ws = open_ws()
    resp = ws.recv()

    if resp is None:
        return

    body, signature = resp.rsplit("|", 1)

    result = verify(body.encode("utf-8"), ubinascii.a2b_base64(signature.strip()), ORIGIN_PUBLIC_KEY)
    if result != "SHA-256":
        raise Exception("Origin server response signature invalid!")

    route, body = body.split("|", 1)

    routes = {"handshake": handle_handshake, "claimed": handle_claimed}

    if route in routes:
        routes[route](body)
    else:
        print("Received unknown route:", route)


def send_handshake_request():
    open_ws(if_configured=False)

    # Generate X25519 keys
    priv, pub = generate_x25519_keypair()

    # Send client key + game title as JSON
    game_title = ds_read_record("configuration", 0)["gamename"]
    client_key_b64 = _b64encode(pub)
    msg = ujson.dumps({"client_key": client_key_b64, "game_title": game_title})

    send(msg, sign=False)

    global metadata

    metadata["pending_handshake"] = {"private_key": priv}


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


def handle_claimed():
    from SPI_DataStore import write_record as ds_write_record

    if "pending_claim" not in metadata:
        raise Exception("No pending claim")

    claim_data = metadata["pending_claim"]
    ds_write_record("cloud", 0, {"id": claim_data["id"], "secret": claim_data["secret"]})

    del metadata["pending_claim"]


def app_origin_status(request):
    """Return linking status with Origin server."""
    import SharedState as S

    if S.origin_pending_claim:
        return {"linked": False, "claim_url": S.origin_pending_claim["claim_url"]}

    import SPI_DataStore as ds

    cloud_config = ds.read_record("cloud", 0)
    if cloud_config["secret"] and cloud_config["id"]:
        return {"linked": True}
    return {"linked": False}
