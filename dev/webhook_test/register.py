#!/usr/bin/env python3
"""Register (or clear) a webhook on a Vector board and show its status.

    python dev/webhook_test/register.py --board 192.168.1.42 --password <board password> --url https://192.168.1.10:8443/hook --secret test-secret
    python dev/webhook_test/register.py --board 192.168.1.42 --password <board password> --status
    python dev/webhook_test/register.py --board 192.168.1.42 --password <board password> --clear
"""

import argparse
import hashlib
import hmac
import json
import urllib.request


def signed_request(board, password, path, body=""):
    with urllib.request.urlopen(f"http://{board}/api/auth/challenge", timeout=5) as resp:
        challenge = json.load(resp)["challenge"]
    signature = hmac.new(password.encode(), (challenge + path + body).encode(), hashlib.sha256).hexdigest()
    headers = {"x-auth-challenge": challenge, "x-auth-hmac": signature}
    data = None
    if body:
        headers["Content-Type"] = "application/json"
        data = body.encode()
    request = urllib.request.Request(f"http://{board}{path}", data=data, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(request, timeout=10) as resp:
        return resp.status, resp.read().decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--board", required=True, help="Board IP address")
    parser.add_argument("--password", required=True, help="Board password")
    parser.add_argument("--url", help="https URL to register")
    parser.add_argument("--secret", help="Shared secret to register")
    parser.add_argument("--clear", action="store_true", help="Stop sending and forget the webhook")
    parser.add_argument("--status", action="store_true", help="Only show the current status")
    args = parser.parse_args()

    if args.clear:
        print(signed_request(args.board, args.password, "/api/webhook/target", json.dumps({"enable": False})))
    elif not args.status:
        if not args.url or not args.secret:
            parser.error("--url and --secret are required to register")
        print(signed_request(args.board, args.password, "/api/webhook/target", json.dumps({"url": args.url, "secret": args.secret})))

    print(signed_request(args.board, args.password, "/api/webhook/status"))


if __name__ == "__main__":
    main()
