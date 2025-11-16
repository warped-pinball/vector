from __future__ import annotations

import json
from typing import List

import dev.usb_coms as usb_coms


class FakeSerial:
    def __init__(self, responses: List[bytes]):
        self.responses = list(responses)
        self.write_buffer = b""

    @property
    def in_waiting(self):
        return len(self.responses)

    def write(self, data: bytes):
        self.write_buffer += data

    def flush(self):
        return None

    def readline(self) -> bytes:
        if self.responses:
            return self.responses.pop(0)
        return b""

    def close(self):
        return None


def test_headers_to_text_handles_dict_input():
    header_text = usb_coms.headers_to_text(
        {"Content-Type": "application/json", "X-Test": "true"}
    )

    assert "Content-Type: application/json" in header_text
    assert "X-Test: true" in header_text
    assert "\n" in header_text


def test_build_auth_headers_matches_backend_scheme():
    challenge = "abc123"
    route = "/api/auth/password_check"
    body_text = json.dumps({"payload": True})

    headers = usb_coms.build_auth_headers(challenge, route, body_text)

    expected_message = f"{challenge}{route}{body_text}".encode("utf-8")
    expected_hmac = usb_coms.hmac.new(
        usb_coms.DEVICE_PASSWORD.encode("utf-8"),
        expected_message,
        usb_coms.hashlib.sha256,
    ).hexdigest()

    assert headers["x-auth-challenge"] == challenge
    assert headers["x-auth-hmac"] == expected_hmac
    assert headers["Content-Type"] == "application/json"


def test_fetch_challenge_round_trip():
    response_payload = {
        "url": "/api/auth/challenge",
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"challenge": "expected-challenge"}),
    }
    response_line = f"USB API RESPONSE-->{json.dumps(response_payload)}\n".encode()
    fake_serial = FakeSerial([response_line])

    client = usb_coms.UsbApiClient(fake_serial)
    challenge = client.fetch_challenge()

    assert challenge == "expected-challenge"
    assert (
        fake_serial.write_buffer
        == b"/api/auth/challenge|Content-Type: application/json|{}\n"
    )
