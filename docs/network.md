# Accessing the API over the network

Use regular HTTP requests against the board's IP address (e.g. `http://192.168.1.42`). All routes are GET endpoints unless otherwise documented.

For routes marked as authenticated, obtain an HMAC challenge token first and include the required headers; see [Authentication](authentication.md) for the signing flow.

## Quick demo script

The snippet below discovers the firmware version and, if needed, signs an authenticated request using the standard challenge flow.

```
import hashlib
import hmac
import requests

BASE_URL = "http://192.168.1.42"
PASSWORD = "your-password"

def get(path):
    return requests.get(BASE_URL + path, timeout=5)

print("Version:", get("/api/version").json())

# Authenticated example: toggle show_ip
challenge = get("/api/auth/challenge").json()["challenge"]
path = "/api/settings/set_show_ip"
body = ""  # no body for this GET route
message = (challenge + path + body).encode()
signature = hmac.new(PASSWORD.encode(), message, hashlib.sha256).hexdigest()

resp = requests.get(
    BASE_URL + path,
    headers={
        "x-auth-challenge": challenge,
        "x-auth-hmac": signature,
    },
    timeout=5,
)
print("show_ip response:", resp.text)
```

Swap `BASE_URL` for your board's address and reuse the helper to call other authenticated routes.
