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

    def is_game_active(self) -> bool:
        """Check if the game is active by sending a request to the device."""
        try:
            resp = self.send_and_receive(route="/api/game/status", payload=None)
            return bool(resp["body"].get("GameActive", False))
        except Exception:
            return False


def main():
    # The port will probably need to be changed here
    client = UsbApiClient.from_device(port="/dev/ttyACM0", timeout=10)

    try:
        print("Listening for responses. Press Ctrl+C to stop.")
        while True:
            # print out the game status
            resp = client.send_and_receive(route="/api/game/status", payload=None)
            print("Status:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # print out the leaderboard
            resp = client.send_and_receive(route="/api/leaders", payload=None)
            print("Leaderboard:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # list out all registered players
            resp = client.send_and_receive(route="/api/players", payload=None)
            print("Players:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # Add a new player
            resp = client.send_and_receive(route="/api/player/update", payload={"id": 1, "full_name": "Tim Crowley", "initials": "TIM"})
            print("Player Update:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # check if a game is active
            print("Checking if game is active...")
            if client.is_game_active():
                print("\tGame is active!")
            else:
                print("\tGame is not active.")
            time.sleep(0.5)

            # --- Address Read/Write/Listener API examples (admin-only routes) ---

            # Read 4 bytes starting at SRAM offset 0
            resp = client.send_and_receive(route="/api/address/read", payload={"offset": 0, "count": 4})
            print("Address Read:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # Write two bytes at SRAM offset 0
            resp = client.send_and_receive(route="/api/address/write", payload={"offset": 0, "values": [0xAA, 0xBB]})
            print("Address Write:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # Set up address listeners on offsets 0, 1, and 2
            resp = client.send_and_receive(route="/api/address/listeners", payload={"offsets": [0, 1, 2]})
            print("Set Listeners:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # Query current listener list (omit offsets)
            resp = client.send_and_receive(route="/api/address/listeners", payload={})
            print("Current Listeners:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # Enable the address listener broadcast (UDP on port 2041, 10 Hz)
            resp = client.send_and_receive(route="/api/address/toggle-broadcast", payload={"enable": True})
            print("Broadcast Enabled:" + json.dumps(resp["body"]))
            time.sleep(2)  # let a few broadcast cycles run

            # Disable the address listener broadcast
            resp = client.send_and_receive(route="/api/address/toggle-broadcast", payload={"enable": False})
            print("Broadcast Disabled:" + json.dumps(resp["body"]))
            time.sleep(0.5)

            # Clear all listeners
            resp = client.send_and_receive(route="/api/address/listeners", payload={"offsets": []})
            print("Cleared Listeners:" + json.dumps(resp["body"]))
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Stopped listening.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
