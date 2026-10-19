#!/usr/bin/env python3
"""Local HTTPS receiver for testing Vector webhooks.

Listens on 0.0.0.0:8443 with a throwaway self-signed certificate (the board
does not check certificates), verifies X-Vector-Signature, and prints each
event.

    python dev/webhook_test/receiver.py --secret test-secret
"""

import argparse
import datetime
import hashlib
import hmac
import ipaddress
import json
import ssl
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def write_self_signed_cert(directory):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "vector-webhook-test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = Path(directory) / "cert.pem"
    key_path = Path(directory) / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_path, key_path


def make_handler(secret):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            valid = hmac.compare_digest(expected, self.headers.get("X-Vector-Signature", ""))

            stamp = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{stamp}] {self.client_address[0]} signature={'OK' if valid else 'BAD'}")
            try:
                print(json.dumps(json.loads(body), indent=2))
            except ValueError:
                print(body)

            self.send_response(200 if valid else 401)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--secret", required=True, help="Same secret you register on the board")
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()
    # Print each event the moment it lands
    sys.stdout.reconfigure(line_buffering=True)

    with tempfile.TemporaryDirectory() as tmp:
        cert_path, key_path = write_self_signed_cert(tmp)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)

        server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(args.secret))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        print(f"Listening on https://0.0.0.0:{args.port}/ (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
