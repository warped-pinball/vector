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
ORIGIN_WS_URL = f"ws://{ORIGIN_URL}:8002/ws/setup".replace("https://", "").replace("http://", "")
ORIGIN_PUBLIC_KEY = PublicKey(
    n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
    e=65537,
)

ws = None
metadata = {}


def open_ws():
    global ws

    if ws is None:
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
        cloud_config = ds_read_record("cloud", 0)
        if not cloud_config["id"]:
            raise Exception("No ID set in cloud config")
        if not S.origin_next_challenge:
            raise Exception("No next challenge set in SharedState")
        if not cloud_config["secret"]:
            raise Exception("No secret set in cloud config")

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

    # TODO implement response handling instead of returning body

    return body


def send_handshake_request():
    open_ws()

    # Generate X25519 keys
    priv, pub = generate_x25519_keypair()

    # Send client key + game title as JSON
    game_title = ds_read_record("configuration", 0)["gamename"]
    client_key_b64 = _b64encode(pub)
    msg = ujson.dumps({"client_key": client_key_b64, "game_title": game_title})

    send(msg, sign=False)

    metadata["pending_handshake"] = {"private_key": priv}


def handle_handshake(data):
    if "pending_handshake" not in metadata:
        raise Exception("No pending handshake")

    data = ujson.loads(data)
    server_public_key = _b64decode(data["server_key"])  # 32 bytes

    # Stash in SharedState for your app logic
    record = {"id": _b64decode(data["machine_id"]), "secret": metadata["pending_handshake"]["private_key"].exchange(server_public_key), "claim_url": data["claim_url"]}
    # TODO validate data and write to data store

    metadata["claim_url"] = data["claim_url"]

    # remove the pending_handshake from metadata
    del metadata["pending_handshake"]


def handle_claimed():
    # TODO implement me
    return


def _b64decode(s: str) -> bytes:
    return ubinascii.a2b_base64(s)


def _b64encode(b: bytes) -> str:
    return ubinascii.b2a_base64(b).decode().strip()


def origin_connect():
    """
    Open a persistent WebSocket to the Origin server and perform the setup handshake.
    Leaves the connection open globally for send/receive.

    Returns a dict with claim_url on success.
    """
    global _ws, _shared_secret, _machine_id_hex

    import SharedState as S

    if _ws is not None:
        # Already connected
        return {"connected": True, "claim_url": S.origin_pending_claim["claim_url"]} if S.origin_pending_claim else {"connected": True}

    # Generate X25519 keys
    priv, pub = generate_x25519_keypair()

    # Send client key + game title as JSON
    game_title = ds_read_record("configuration", 0)["gamename"]
    client_key_b64 = _b64encode(pub)
    msg = ujson.dumps({"client_key": client_key_b64, "game_title": game_title})

    # Open socket and send (unsigned handshake)
    ws = connect(ORIGIN_WS_URL)
    ws.send(msg)

    # Initial handshake response (text frame)
    resp_text = ws.recv().decode("utf-8")
    print("Origin handshake response:", resp_text)

    # Split "<json>|<base64(signature)>"
    try:
        data_text, sig_b64 = resp_text.rsplit("|", 1)
    except ValueError:
        ws.close()
        raise Exception("Handshake response missing signature separator '|'")

    try:
        signature = ubinascii.a2b_base64(sig_b64.strip())
    except Exception as e:
        ws.close()
        raise Exception("Handshake signature not valid base64: {}".format(e))

    # Verify RSA PKCS#1 v1.5 / SHA-256 over EXACT JSON bytes
    result = verify(data_text.encode("utf-8"), signature, _ORIGIN_PUBLIC_KEY)
    if result != "SHA-256":
        ws.close()
        raise Exception("Handshake signature invalid! {}".format(result))

    # Parse the signed JSON
    data = ujson.loads(data_text)
    server_key = _b64decode(data["server_key"])  # 32 bytes
    claim_code = data["claim_code"]
    machine_id_b64 = data["machine_id"]

    # Compute shared secret (raw 32 bytes)
    _shared_secret = priv.exchange(server_key)
    print("Shared secret established (hex):", ubinascii.hexlify(_shared_secret).decode())

    # machine_id is base64(UUID bytes); keep local hex for storage/compat
    try:
        mid_bytes = _b64decode(machine_id_b64)
        _machine_id_hex = ubinascii.hexlify(mid_bytes).decode()
    except Exception:
        _machine_id_hex = machine_id_b64  # fallback: keep as b64

    claim_url = "%s/claim?code=%s" % (ORIGIN_URL, claim_code)

    # Stash in SharedState for your app logic
    S.origin_pending_claim = {"id": _machine_id_hex, "secret": _shared_secret, "claim_url": claim_url}

    # Save socket globally for persistent use
    _ws = ws

    # Optional: make socket non-blocking-ish (depends on your client)
    try:
        # Some MicroPython websocket clients expose .settimeout()
        _ws.settimeout(0)
    except Exception:
        # If not supported, recv() will block; your cadence caller should tolerate that or you can wrap with try/except
        pass

    return {"claim_url": claim_url}


def msg_origin(msg: str, sign: bool = True):
    """
    Kept for compatibility with your existing code paths that expect a request/response.
    If the connection is not open, it will open and perform handshake (unsigned).
    If sign=True, append your HMAC fields as before.
    This sends a single message and waits once for a reply.
    """
    import SharedState as S
    import SPI_DataStore as ds
    from backend import hmac_sha256

    if _ws is None:
        origin_connect()

    to_send = msg
    if sign:
        cloud_config = ds.read_record("cloud", 0)
        if not cloud_config["id"]:
            raise Exception("No ID set in cloud config")
        if not S.origin_next_challenge:
            raise Exception("No next challenge set in SharedState")
        if not cloud_config["secret"]:
            raise Exception("No secret set in cloud config")

        to_send = to_send + "|" + str(cloud_config["id"])
        to_send = to_send + "|" + str(S.origin_next_challenge)
        to_send_hmac = hmac_sha256(cloud_config["secret"], to_send)
        to_send = to_send + "|" + str(to_send_hmac)

    _ws.send(to_send)

    resp_text = _ws.recv().decode("utf-8")
    print("response from Origin server:", resp_text)

    try:
        data_text, sig_b64 = resp_text.rsplit("|", 1)
    except ValueError:
        raise Exception("Response missing signature separator '|'")

    try:
        signature = ubinascii.a2b_base64(sig_b64.strip())
    except Exception as e:
        raise Exception("Signature was not valid base64: {}".format(e))

    result = verify(data_text.encode("utf-8"), signature, _ORIGIN_PUBLIC_KEY)
    if result != "SHA-256":
        raise Exception("Signature invalid! {}".format(result))

    return data_text


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


# TODO parse / handle response commands like "finalize claim" which should move the pending claim from shared state to the fram
# TODO add a timeout handler
# TODO keep web socket open?
# TODO update port to 8001 for prod
