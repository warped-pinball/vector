# Accessing the API over USB

The USB transport reuses the same route handlers via `src/common/usb_comms.py`. Requests are read from the serial console as `route|headers|body` lines and responded to with JSON.

Host-side scripts cannot import the MicroPython modules. Use the standalone client below based on `dev/usb_coms_demo.py` to talk to the board over serial.

## Frame format

Each request line contains three pipe-delimited fields. Escape literal pipes in headers or body as `\|`. Headers are provided as raw HTTP-style text (e.g. `Content-Type: application/json` on separate lines) and the body is optional.

## Host demo snippet

Save the following as `usb_client.py` (adapted from `dev/usb_coms_demo.py`) and run it locally:

```
#!/usr/bin/env python3
import json
import time

import serial


def send_and_receive(port: str, route: str, headers=None, body_text=""):
    ser = serial.Serial(port=port, baudrate=115200, timeout=10)
    time.sleep(2)  # allow the device to reset
    headers = headers or {"Content-Type": "application/json"}
    header_text = "\n".join(f"{k}: {v}" for k, v in headers.items())
    frame = f"{route}|{header_text}|{body_text}\n"
    ser.write(frame.encode())
    prefix = "USB API RESPONSE-->"
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if not line.startswith(prefix):
            continue
        payload = json.loads(line[len(prefix) :])
        body_raw = payload.get("body")
        if isinstance(body_raw, str):
            try:
                payload["body"] = json.loads(body_raw)
            except json.JSONDecodeError:
                pass
        return payload


if __name__ == "__main__":
    port = "/dev/ttyACM0"  # adjust for your platform
    print(send_and_receive(port, "/api/version"))
    # Authenticated call: fetch challenge then include headers
    challenge_resp = send_and_receive(port, "/api/auth/challenge")
    print("challenge", challenge_resp.get("body"))
```

The helper opens the serial connection, writes a framed request, and parses the JSON response emitted by the firmware. Expand it with additional routes as needed.
