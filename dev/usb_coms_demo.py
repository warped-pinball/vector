#!/usr/bin/env python3
"""USB API client utilities for communicating with the device over serial.

This module exposes a small helper class, :class:`UsbApiClient`, that wraps a
serial connection and handles the wire protocol used by the device firmware.
"""

from __future__ import annotations

import json
import time
from typing import Dict, Iterable, Union

import serial


def headers_to_text(headers: Union[str, Dict[str, str]]) -> str:
    """Render a header mapping as a newline-delimited string."""
    if isinstance(headers, str):
        return headers
    header_lines: Iterable[str] = (f"{name}: {value}" for name, value in headers.items())
    return "\n".join(header_lines)


class UsbApiClient:
    """High-level client for the USB API protocol used by the device."""

    def __init__(self, ser):
        self.ser = ser

    @classmethod
    def from_device(
        cls,
        port: str = "/dev/ttyACM0",
        baudrate: int = 115200,
        timeout: int = 10,
    ) -> "UsbApiClient":
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        time.sleep(2)
        return cls(ser)

    def close(self) -> None:
        self.ser.close()

    def send_and_receive(
        self,
        route: str,
        payload: Union[Dict, str, None],
        headers: Union[str, Dict[str, str]] | None = None,
        body_text: str | None = None,
        timeout: int = 10,
    ):
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
                try:
                    data = json.loads(payload_text)
                except json.JSONDecodeError:
                    print(f"Failed to parse JSON: {payload_text}")
                    continue

                body_raw = data.get("body")
                if isinstance(body_raw, str):
                    try:
                        data["body"] = json.loads(body_raw)
                    except json.JSONDecodeError:
                        # If body is not valid JSON, leave as string (expected for some responses)
                        pass
                return data
            time.sleep(0.05)

        raise TimeoutError("No response received within timeout period.")


def is_game_active(client: UsbApiClient) -> bool:
    """Check if the game is active by sending a request to the device."""
    try:
        resp = client.send_and_receive(route="/api/game/status", payload=None)
        return bool(resp["body"].get("GameActive", False))
    except Exception:
        return False


def main():
    # The port will probably need to be changed here
    client = UsbApiClient.from_device(port="/dev/ttyACM0", timeout=10)

    try:
        print("Listening for responses. Press Ctrl+C to stop.")
        while True:
            resp = client.send_and_receive(route="/api/game/status", payload=None)
            print("Received response:" + json.dumps(resp["body"]))
            time.sleep(0.5)
            resp = client.send_and_receive(route="/api/leaders", payload=None)
            print("Received response:" + json.dumps(resp["body"]))
            time.sleep(0.5)
            resp = client.send_and_receive(route="/api/players", payload=None)
            print("Received response:" + json.dumps(resp["body"]))
            time.sleep(0.5)
            resp = client.send_and_receive(route="/api/player/update", payload={"id": 1, "full_name": "Tim Crowley", "initials": "TIM"})
            print("Received response:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            print("Checking if game is active...")
            if is_game_active(client):
                print("\tGame is active!")
            else:
                print("\tGame is not active.")
            now = time.perf_counter()
            last = getattr(main, "_last_check_time", None)
            if last is not None:
                interval = now - last
                rate = 1.0 / interval if interval else float("inf")
                print(f"\tLast check {interval:.3f}s ago (~{rate:.2f} Hz)")
            main._last_check_time = now
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Stopped listening.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
