#!/usr/bin/env python3

import json
import time

import serial


def send_and_receive(ser, route, payload, headers="Content-Type: application/json", timeout=10):
    sections = [route, headers, json.dumps(payload)]

    # escape '|' in sections
    escaped_sections = [s.replace("|", "\\|") for s in sections]
    request = "|".join(escaped_sections) + "\n"

    ser.write(request.encode())
    ser.flush()
    print("Sent:", request.strip())

    prefix = "USB API RESPONSE-->"
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if ser.in_waiting:
            line = ser.readline()
            if not line:
                continue
            text = line.decode(errors="replace").rstrip("\r\n")
            if not text.startswith(prefix):
                continue
            payload_text = text[len(prefix) :].strip()
            try:
                data = json.loads(payload_text)
            except json.JSONDecodeError:
                print("Recv malformed:", payload_text)
                return None
            body_raw = data.get("body")
            if isinstance(body_raw, str):
                try:
                    data["body"] = json.loads(body_raw)
                except json.JSONDecodeError:
                    print("Recv body malformed:", body_raw)
            print(text)
            print("Recv:\n" + json.dumps(data, indent=2))
            return data
        time.sleep(0.05)

    print("Timed out waiting for response.")
    return None


def main():
    ser = serial.Serial(port="/dev/ttyACM0", baudrate=115200, timeout=10)
    time.sleep(2)

    try:
        print("Listening for responses. Press Ctrl+C to stop.")
        while True:
            send_and_receive(
                ser,
                route="/api/game/status",
                payload={"player": "AB|C", "score": 12345},
            )
            time.sleep(5)
            send_and_receive(
                ser,
                route="/api/leaders",
                payload={"player": "ABC", "score": 12345},
            )
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopped listening.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
