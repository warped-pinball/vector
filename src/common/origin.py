import ubinascii
import ujson
from curve25519 import generate_x25519_keypair
from rsa.key import PublicKey
from rsa.pkcs1 import verify
from SPI_DataStore import read_record as ds_read_record
from websocket_client import connect


def setup_origin(request):
    """Establish a shared secret with the Origin server and return a claim link."""

    print("Enabling Origin...")
    ORIGIN_URL = "https://origin-beta.doze.dev"
    ORIGIN_PUBLIC_KEY = PublicKey(
        n=28614654558060418822124381284684831254240478555015789120214464642901890987895680763405283269470147887303926250817244523625615064384265979999971160712325590195185400773415418587665620878814790592993312154170130272487068858777781318039028994811713368525780667651253262629854713152229058045735971916702945553321024064700665927316038594874406926206882462124681757469297186287685022784316136293905948058639312054312972513412949216100630192514723261366098654269262605755873336924648017315943877734167140790946157752127646335353231314390105352972464257397958038844584017889131801645980590812612518452889053859829545934839273,  # noqa
        e=65537,
    )
    print("Connecting to Origin server...")
    # Use port 8001 for the websocket connection
    host = ORIGIN_URL.replace("https://", "").replace("http://", "")
    ws_url = f"ws://{host}:8001/ws/claim"
    try:
        ws = connect(ws_url)
    except Exception as e:
        print(f"Origin server connection failed: {e}")
        return {"error": "unreachable"}, 503

    try:
        priv, pub = generate_x25519_keypair()
        print("Sending public key to Origin server...")
        ws.send(ujson.dumps({"client_key": ubinascii.b2a_base64(pub).decode(), "game_title": ds_read_record("configuration", 0)["gamename"]}))
        print("Waiting for response from Origin server...")
        resp = ws.recv()
        print("Received response from Origin server")
        data = ujson.loads(resp)
        server_key = ubinascii.a2b_base64(data["server_key"])
        claim_code = data["claim_code"]
        machine_id = data["machine_id"]
        signature = ubinascii.unhexlify(data["signature"])
    except Exception as e:
        print(f"Error during Origin handshake: {e}")
        print("Received response:", resp)
        return {"error": "handshake"}, 502
    finally:
        ws.close()

    shared_secret = priv.exchange(server_key)
    print("Shared secret established")

    try:
        result = verify(shared_secret, signature, ORIGIN_PUBLIC_KEY)
        if result != "SHA-256":
            raise Exception(f"Signature invalid! {result}")
    except Exception:
        return {"error": "signature"}, 400
    print("Signature verified")

    # TODO store the shared secret in a secure way
    import SharedState

    SharedState.origin_shared_secret = shared_secret
    SharedState.origin_machine_id = machine_id

    claim_url = "%s/claim?code=%s" % (ORIGIN_URL, claim_code)
    print(f"Claim URL: {claim_url}")
    return {"claim_url": claim_url}


def app_origin_status(request):
    """Return linking status with Origin server."""
    return {"linked": False}
