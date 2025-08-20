import ubinascii
import ujson
from curve25519 import generate_x25519_keypair
from rsa.key import PublicKey
from rsa.pkcs1 import verify
from SPI_DataStore import read_record as ds_read_record
from websocket_client import connect

ORIGIN_URL = "https://origin-beta.doze.dev"
ORIGIN_WS_URL = f"ws://{ORIGIN_URL}:8002/ws/claim".replace("https://", "").replace("http://", "")
# TODO make this port 8001 for production


def setup_origin(request):
    """Establish a shared secret with the Origin server and return a claim link."""
    import SharedState as S

    priv, pub = generate_x25519_keypair()
    print("Sending public key to Origin server...")
    msg = ujson.dumps({"client_key": ubinascii.b2a_base64(pub).decode(), "game_title": ds_read_record("configuration", 0)["gamename"]})

    resp = msg_origin(msg, sign=False)

    print("Received response from Origin server")
    data = ujson.loads(resp)
    server_key = ubinascii.a2b_base64(data["server_key"])
    claim_code = data["claim_code"]
    machine_id = data["machine_id"]
    shared_secret = priv.exchange(server_key)
    claim_url = "%s/claim?code=%s" % (ORIGIN_URL, claim_code)
    S.origin_pending_claim = {"id": machine_id, "secret": shared_secret, "claim_url": claim_url}
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

            msg += "|" + str(cloud_config["id"])

            if not S.origin_next_challenge:
                raise Exception("No next challenge set in SharedState")

            msg += "|" + str(S.origin_next_challenge)

            if not cloud_config["secret"]:
                raise Exception("No secret set in cloud config")

            msg += "|" + str(hmac_sha256(cloud_config["secret"], msg))

        ws = connect(ORIGIN_WS_URL)
        ws.send(msg)
        resp = ws.recv()
        sig = resp.split("|")[-1]
        data = resp[: -len(sig) - 1]

        signature = ubinascii.unhexlify(sig)
        ORIGIN_PUBLIC_KEY = PublicKey(
            n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
            e=65537,
        )
        result = verify(data, signature, ORIGIN_PUBLIC_KEY)
        if result != "SHA-256":
            raise Exception(f"Signature invalid! {result}")

    except Exception as e:
        raise Exception(f"Error during Origin message exchange: {e}")
    finally:
        if ws is not None:
            ws.close()

    # TODO parse / handle response commands like "finalize claim" which should move the pending claim from shared state to the fram

    return data


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
