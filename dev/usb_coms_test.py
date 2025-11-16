#!/usr/bin/env python3

import json
import time

import serial

# from detect_boards import detect_boards

# boards = detect_boards()
# print("Detected boards:", boards)

# # pick the first key and the first port for that key
# board_types = list(boards.keys())
# if not board_types:
#     print("No boards detected.")
#     exit(1)
# first_board_type = board_types[0]
# first_port = boards[first_board_type][0]
# print(f"Using board type: {first_board_type} on port: {first_port}")

ser = serial.Serial(port="/dev/ttyACM0", baudrate=115200, timeout=10)
time.sleep(2)

try:

    def send_api_request():
        """Send a test API request to the USB handler"""
        route = "/game/status"
        headers = "Content-Type: application/json"
        data = json.dumps({"player": "ABC", "score": 12345})

        request = f"{route}|{headers}|{data}\n"
        ser.write(request.encode())
        ser.flush()
        print("Sent:", request.strip())

    last_send = time.monotonic() - 5

    print("Listening for responses. Press Ctrl+C to stop.")
    while True:
        now = time.monotonic()
        if now - last_send >= 5:
            send_api_request()
            last_send = now

        if ser.in_waiting:
            line = ser.readline()
            if line:
                text = line.decode(errors="replace").rstrip("\r\n")
                print("Recv:", text)
        else:
            time.sleep(0.05)

except KeyboardInterrupt:
    print("Stopped listening.")
finally:
    ser.close()
