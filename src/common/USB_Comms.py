"""
    serial data via USB handler

    IRQ for incoming data
    call handler from system scheduler
    to send data - just print!

"""
import io
import json
import sys

import GameStatus
import uselect
from phew.server import _handle_request as server_handle_request

incoming_data = []  # complete lines only
buffer = ""  # partial input line
poller = uselect.poll()
poller.register(sys.stdin, uselect.POLLIN)


def usb_request_handler():
    """Non-blocking USB request handler - processes complete request lines"""
    global buffer, incoming_data

    # First, read any available data into buffer (non-blocking)
    loop_count = 0
    while poller.poll(0) and loop_count < 100:
        data = sys.stdin.read(1)
        if not data:
            break
        if data in ("\n", "\r"):
            if buffer:  # if buffer is not empty and string has been terminated
                incoming_data.append(buffer)
                buffer = ""
        else:
            buffer += data
            if len(buffer) > 1000:  # prevent buffer overflow
                buffer = ""
        loop_count += 1

    # Process any complete requests from the buffer
    request_count = 0
    while incoming_data and request_count < 10:
        request_count += 1
        request = incoming_data.pop(0)

        print(f"USB REQ: processing request: {request}")
        parts = request.split("|", 2)
        if len(parts) != 3:
            print(f"USB REQ: invalid request format: {request}")
            continue

        route_url, headers, data = parts
        print(f"USB REQ: URL: {route_url} HEADERS: {headers} DATA: {data}")

        try:
            # build a reader / writer pair to feed to the server handler
            request_line = f"GET {route_url} HTTP/1.1".encode()
            reader = b"\r\n".join([request_line, headers.encode(), b"", data.encode()])

            # make reader into a stream
            reader_stream = io.BytesIO(reader)
            writer = sys.stdout

            # call the server handler (this might still block, but at least we're not blocking on I/O)
            server_handle_request(reader_stream, writer)
        except Exception as e:
            print(f"USB REQ: error processing request: {e}")
            # Continue processing other requests even if one fails


def send_game_status():
    gs = GameStatus.game_report()
    # gs['zoom_initials'] = S.zoom_initials
    gs_json = json.dumps(gs)
    print(f"ZOOM: GAME: {gs_json}")
