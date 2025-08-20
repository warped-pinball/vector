import ubinascii
import ujson
from curve25519 import generate_x25519_keypair
from rsa.key import PublicKey
from rsa.pkcs1 import verify
from SPI_DataStore import read_record as ds_read_record
from websocket_client import connect

ORIGIN_URL = "https://origin-beta.doze.dev"
ORIGIN_WS_URL = f"ws://{ORIGIN_URL}:8002/ws/setup".replace("https://", "").replace("http://", "")
# TODO port 8001 for prod


def _b64decode(s: str) -> bytes:
    # MicroPython's ubinascii.a2b_base64 handles std b64
    return ubinascii.a2b_base64(s)


def _b64encode(b: bytes) -> str:
    return ubinascii.b2a_base64(b).decode().strip()


def setup_origin(request):
    """Establish a shared secret with the Origin server and return a claim link."""
    import SharedState as S

    priv, pub = generate_x25519_keypair()

    # client_key is base64 of our X25519 public key (raw 32 bytes)
    client_key_b64 = _b64encode(pub)

    game_title = ds_read_record("configuration", 0)["gamename"]
    msg = ujson.dumps({"client_key": client_key_b64, "game_title": game_title})

    resp = msg_origin(msg, sign=False)

    # Verify response is valid JSON, then compute shared secret
    data = ujson.loads(resp)
    server_key = _b64decode(data["server_key"])  # raw 32 bytes
    claim_code = data["claim_code"]
    machine_id_b64 = data["machine_id"]

    # X25519 shared secret
    shared_secret = priv.exchange(server_key)
    print("Shared secret established with Origin server:", ubinascii.hexlify(shared_secret).decode())

    # Decode machine_id (base64 UUID bytes) → hex string for local use
    try:
        machine_id_bytes = _b64decode(machine_id_b64)
        machine_id_hex = ubinascii.hexlify(machine_id_bytes).decode()
    except Exception:
        # Fallback: keep the b64 if decoding fails for any reason
        machine_id_hex = machine_id_b64

    claim_url = "%s/claim?code=%s" % (ORIGIN_URL, claim_code)
    S.origin_pending_claim = {"id": machine_id_hex, "secret": shared_secret, "claim_url": claim_url}
    return {"claim_url": claim_url}


def msg_origin(msg: str, sign: bool = True):
    import SharedState as S
    import SPI_DataStore as ds
    from backend import hmac_sha256

    ws = None
    try:
        if sign:
            cloud_config = ds.read_record("cloud", 0)
            if not cloud_config["id"]:
                raise Exception("No ID set in cloud config")

            msg = msg + "|" + str(cloud_config["id"])

            if not S.origin_next_challenge:
                raise Exception("No next challenge set in SharedState")

            msg = msg + "|" + str(S.origin_next_challenge)

            if not cloud_config["secret"]:
                raise Exception("No secret set in cloud config")

            msg_hmac = hmac_sha256(cloud_config["secret"], msg)
            msg = msg + "|" + str(msg_hmac)

        ws = connect(ORIGIN_WS_URL)
        ws.send(msg)

        resp_text = ws.recv().decode("utf-8")
        print("response from Origin server:", resp_text)

        try:
            data_text, sig_b64 = resp_text.rsplit("|", 1)
        except ValueError:
            raise Exception("Response missing signature separator '|'")

        sig_b64 = sig_b64.strip()

        try:
            signature = ubinascii.a2b_base64(sig_b64)
        except Exception as e:
            raise Exception("Signature was not valid base64: {}".format(e))

        # Verify signature length against modulus size (n.bit_length rounded up to bytes)
        ORIGIN_PUBLIC_KEY = PublicKey(
            n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
            e=65537,
        )

        if len(signature) != 256:
            raise Exception("Invalid signature length: {} (expected 256)".format(len(signature)))

        # Verify RSA PKCS#1 v1.5 SHA-256 signature over EXACT bytes the server signed
        result = verify(data_text.encode("utf-8"), signature, ORIGIN_PUBLIC_KEY)
        if result != "SHA-256":
            raise Exception("Signature invalid! {}".format(result))

    except Exception as e:
        raise Exception("Error during Origin message exchange: {}".format(e))
    finally:
        if ws is not None:
            ws.close()

    # Return only the signed JSON portion
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
