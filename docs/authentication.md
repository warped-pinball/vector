# Authentication

Authenticated routes require an HMAC signature tied to a one-time challenge token. Use this flow for any route marked as requiring authentication.

## Flow

1. Call `/api/auth/challenge` to receive a hexadecimal `challenge` string.
2. Build the message string by concatenating `challenge + request_path + raw_body`. If the request has no body, use an empty string for `raw_body`.
3. Compute the HMAC-SHA256 digest of the message using the configured password as the key.
4. Send the protected request with headers `x-auth-challenge` (the issued token) and `x-auth-hmac` (the hexadecimal digest).
5. Challenges expire after 60 seconds and are removed once successfully used. Request a new challenge if you receive an expiration or invalid challenge error.

## Examples

Example message construction for `/api/settings/set_show_ip` without a request body:

```
challenge = "deadbeef..."  # obtained from /api/auth/challenge
path = "/api/settings/set_show_ip"
body = ""  # no payload for this route
message = challenge + path + body
```

Include the generated `x-auth-challenge` and `x-auth-hmac` headers in the subsequent request.

## Ready-to-run Python example

This script retrieves a challenge, signs a protected request, and prints the response. Save it locally and run with `python auth_demo.py`.

```
#!/usr/bin/env python3
import hashlib
import hmac
import requests

BASE_URL = "http://192.168.1.42"  # replace with your board IP
PASSWORD = "your-password"         # the device password used for HMAC


def signed_get(path: str):
    challenge = requests.get(f"{BASE_URL}/api/auth/challenge", timeout=5).json()["challenge"]
    message = (challenge + path).encode()
    signature = hmac.new(PASSWORD.encode(), message, hashlib.sha256).hexdigest()

    return requests.get(
        f"{BASE_URL}{path}",
        headers={
            "x-auth-challenge": challenge,
            "x-auth-hmac": signature,
        },
        timeout=5,
    )


if __name__ == "__main__":
    print("Version:", requests.get(f"{BASE_URL}/api/version", timeout=5).json())
    resp = signed_get("/api/settings/set_show_ip")
    print("Authenticated response:", resp.status_code, resp.text)
```

Swap `BASE_URL` and `PASSWORD` for your device. Reuse `signed_get` for any authenticated route.
