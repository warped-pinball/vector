import SPI_DataStore as DataStore
import ujson as json
import uhashlib as hashlib
import urandom
import binascii
import time
import gc
from Utilities.random_bytes import random_hex
from phew import server 

# Authentication variables
current_challenge = None
challenge_timestamp = None
CHALLENGE_EXPIRATION_SECONDS = 60

def require_auth(handler):
    def wrapper(request, *args, **kwargs):
        global current_challenge, challenge_timestamp
        # Check if the challenge exists and is valid
        if not current_challenge or not challenge_timestamp:
            return json.dumps({"error": "Challenge missing"}), 401, {'Content-Type': 'application/json'}
        
        if (time.time() - challenge_timestamp) > CHALLENGE_EXPIRATION_SECONDS:
            return json.dumps({"error": "Challenge expired"}), 401, {'Content-Type': 'application/json'}
        
        # Get the HMAC from the request headers
        client_hmac = request.headers.get('X-Auth-HMAC')
        if not client_hmac:
            return json.dumps({"error": "Missing authentication HMAC"}), 401, {'Content-Type': 'application/json'}
        
        # Reconstruct the message used for HMAC: challenge + request path + request body
        credentials = DataStore.read_record("configuration", 0)
        stored_password = credentials["Gpassword"]
        key = stored_password.encode('utf-8')
        msg = (
            current_challenge +           # Challenge
            request.path +                # Request path
            request.query_string +        # Query string (if any)
            request.data_string           # Request body (if any)
        ).encode('utf-8')
        
        # Compute expected HMAC
        hasher = hashlib.sha256()
        hasher.update(key + msg)
        expected_hmac = binascii.hexlify(hasher.digest()).decode()
        
        # Compare HMACs
        if client_hmac == expected_hmac:
            # Authentication successful
            current_challenge = None
            challenge_timestamp = None
            return handler(request, *args, **kwargs)
        else:
            # Authentication failed
            return json.dumps({"error": "Authentication failed"}), 401, {'Content-Type': 'application/json'}
    return wrapper


@server.route("/get_challenge", methods=["GET"])
def get_challenge(request):
    global current_challenge, challenge_timestamp
    # Generate a random nonce (challenge)
    current_challenge = random_hex(64)
    challenge_timestamp = time.time()
    # Return the nonce to the client
    return json.dumps({"challenge": current_challenge}), 200, {'Content-Type': 'application/json'}

