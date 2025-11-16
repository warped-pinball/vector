from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
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
    password = "local-device-password"

    headers = usb_coms.build_auth_headers(challenge, route, body_text, password)

    expected_message = f"{challenge}{route}{body_text}".encode("utf-8")
    expected_hmac = usb_coms.hmac.new(
        password.encode("utf-8"),
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


def test_demo_bootstraps_repo_root_into_sys_path(monkeypatch):
    demo_path = Path(__file__).resolve().parent.parent / "usb_coms_demo.py"

    repo_root = demo_path.parent.parent

    # Simulate running the script directly: the script directory is first on
    # sys.path and the repository root is not present yet, but the standard
    # library entries remain.
    sanitized_path = [p for p in sys.path if p not in {"", str(repo_root)}]
    monkeypatch.setattr(sys, "path", [str(demo_path.parent), *sanitized_path])

    namespace = runpy.run_path(str(demo_path), run_name="usb_coms_demo_test")

    # The helper import succeeds when the script adds the repository root to
    # sys.path at runtime.
    assert "UsbApiClient" in namespace


def test_send_authenticated_request_requires_password():
    fake_serial = FakeSerial([])
    client = usb_coms.UsbApiClient(fake_serial)

    result = client.send_authenticated_request("/api/test", {"ok": True})

    assert result is None
    assert fake_serial.write_buffer == b""


def test_send_authenticated_request_uses_provided_password():
    challenge_response = {
        "url": "/api/auth/challenge",
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"challenge": "demo-challenge"}),
    }
    success_response = {
        "url": "/api/test",
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"result": "ok"}),
    }

    fake_serial = FakeSerial(
        [
            f"USB API RESPONSE-->{json.dumps(challenge_response)}\n".encode(),
            f"USB API RESPONSE-->{json.dumps(success_response)}\n".encode(),
        ]
    )

    password = "demo-pass"
    client = usb_coms.UsbApiClient(fake_serial, device_password=password)
    response = client.send_authenticated_request("/api/test", {"ok": True})

    assert response["body"]["result"] == "ok"

    expected_body = json.dumps({"ok": True})
    expected_auth = usb_coms.build_auth_headers(
        "demo-challenge", "/api/test", expected_body, password
    )
    expected_headers = usb_coms.headers_to_text(expected_auth)

    assert b"/api/auth/challenge|Content-Type: application/json|{}\n" in fake_serial.write_buffer
    assert expected_headers.encode("utf-8") in fake_serial.write_buffer
