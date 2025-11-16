"""USB API client utilities for communicating with the device over serial.

This module exposes a small helper class, :class:`UsbApiClient`, that wraps a
serial connection and handles the wire protocol used by the device firmware.

USB connections are treated as trusted physical links, so authentication is
disabled by default when constructing a client with :meth:`UsbApiClient.from_device`.
If your firmware still expects HMAC headers, enable authentication explicitly.

The flow for authenticated requests is:
    1. Ask the device for a challenge via ``/api/auth/challenge``.
    2. Combine the challenge, route, and request body and sign with the device
       password using HMAC-SHA256.
    3. Send the request with the resulting headers.

The password is provided by the caller (for example, the demo script hard-codes
one for simplicity). In production environments this value should come from a
secure secret store or environment variable rather than a checked-in constant.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Dict, Iterable, Union

import serial


def headers_to_text(headers: Union[str, Dict[str, str]]) -> str:
    """Render a header mapping as a newline-delimited string.

    The device expects headers to be sent as ``name: value`` pairs joined by
    newlines. If ``headers`` is already a string it is returned unchanged.
    """

    if isinstance(headers, str):
        return headers

    header_lines: Iterable[str] = (f"{name}: {value}" for name, value in headers.items())
    return "\n".join(header_lines)


def build_auth_headers(challenge: str, route: str, body_text: str, password: str) -> Dict[str, str]:
    """Build headers required for the firmware's HMAC-based authentication.

    The HMAC digest is calculated over ``challenge + route + body`` using the
    device password. The returned headers include ``Content-Type`` and the
    challenge/HMAC pair that the device validates.
    """

    message = f"{challenge}{route}{body_text}".encode("utf-8")
    digest = hmac.new(password.encode("utf-8"), message, hashlib.sha256).hexdigest()

    return {
        "Content-Type": "application/json",
        "x-auth-challenge": challenge,
        "x-auth-hmac": digest,
    }


class UsbApiClient:
    """High-level client for the USB API protocol used by the device."""

    def __init__(
        self,
        ser,
        device_password: str | None = None,
        authentication_enabled: bool = True,
    ):
        """Initialize the client with an open serial connection.

        Args:
            ser: An object implementing the subset of the :mod:`serial.Serial`
                interface used by this client.
            device_password: Optional password used for authenticated requests.
            authentication_enabled: Whether to perform challenge/HMAC
                authentication for protected routes. USB links can safely use
                ``False`` because the transport is a trusted physical cable.
        """

        self.ser = ser
        self.device_password = device_password
        self.authentication_enabled = authentication_enabled

    @classmethod
    def from_device(
        cls,
        port: str = "/dev/ttyACM0",
        baudrate: int = 115200,
        timeout: int = 10,
        device_password: str | None = None,
        authentication_enabled: bool = False,
    ) -> "UsbApiClient":
        """Create a client with a real serial connection.

        A short delay is added after opening the port to give the device time to
        boot, matching the behavior of the previous utility script.
        """

        ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        time.sleep(2)
        return cls(
            ser,
            device_password=device_password,
            authentication_enabled=authentication_enabled,
        )

    def close(self) -> None:
        """Close the underlying serial connection."""

        self.ser.close()

    def send_and_receive(
        self,
        route: str,
        payload: Union[Dict, str, None],
        headers: Union[str, Dict[str, str]] | None = None,
        body_text: str | None = None,
        timeout: int = 10,
    ):
        """Send a request to the device and return the parsed response.

        Requests are formatted as ``<route>|<headers>|<body>`` with ``|``
        characters escaped. The method waits for a ``USB API RESPONSE-->`` line
        and parses the JSON payload into a Python dictionary.
        """

        if headers is None:
            headers = {"Content-Type": "application/json"}

        header_text = headers_to_text(headers)
        if payload is None:
            payload = {}
        if body_text is None:
            body_text = json.dumps(payload)

        sections = [route, header_text, body_text]
        escaped_sections = [section.replace("|", "\\|") for section in sections]
        request = "|".join(escaped_sections) + "\n"

        self.ser.write(request.encode())
        self.ser.flush()

        prefix = "USB API RESPONSE-->"
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if self.ser.in_waiting:
                line = self.ser.readline()
                if not line:
                    continue
                text = line.decode(errors="replace").rstrip("\r\n")
                if not text.startswith(prefix):
                    continue
                payload_text = text[len(prefix) :].strip()
                data = json.loads(payload_text)

                body_raw = data.get("body")
                if isinstance(body_raw, str):
                    try:
                        data["body"] = json.loads(body_raw)
                    except json.JSONDecodeError:
                        pass
                return data
            time.sleep(0.05)

        raise TimeoutError("No response received within timeout period.")

    def fetch_challenge(self, timeout: int = 5) -> str | None:
        """Request an authentication challenge from the device."""

        response = self.send_and_receive(
            route="/api/auth/challenge",
            payload={},
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        if not response or response.get("status") != 200:
            return None

        body = response.get("body") or {}
        if isinstance(body, dict):
            return body.get("challenge")
        return None

    def send_authenticated_request(
        self,
        route: str,
        payload: Dict,
        timeout: int = 10,
        require_authentication: bool | None = None,
    ):
        """Send a request, optionally using the HMAC-based authentication headers.

        Args:
            route: API route to call.
            payload: JSON-serializable request body.
            timeout: Maximum seconds to wait for a response.
            require_authentication: Force authentication on or off. ``None``
                defers to :pyattr:`authentication_enabled`, which defaults to
                ``False`` for USB connections.
        """

        auth_required = self.authentication_enabled if require_authentication is None else require_authentication

        if not auth_required:
            return self.send_and_receive(
                route=route,
                payload=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )

        if not self.device_password:
            print("Device password is not configured for authenticated requests.")
            return None

        body_text = json.dumps(payload)
        challenge = self.fetch_challenge(timeout=timeout)
        if not challenge:
            print("Could not fetch authentication challenge.")
            return None

        auth_headers = build_auth_headers(challenge, route, body_text, password=self.device_password)
        return self.send_and_receive(
            route=route,
            payload=payload,
            headers=auth_headers,
            body_text=body_text,
            timeout=timeout,
        )
