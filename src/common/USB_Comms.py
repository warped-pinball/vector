"""
    serial data via USB handler

    IRQ for incoming data
    call handler from system scheduler
    to send data - just print!

"""
import json
import sys

import GameStatus
import uselect
from phew.server import Request, Response, _routes, catchall_handler

incoming_data = []  # complete lines only
buffer = ""  # partial input line
poller = uselect.poll()
poller.register(sys.stdin, uselect.POLLIN)


def _parse_headers(header_text):
    headers = {}
    for line in header_text.split("\n"):
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return headers


def _render_response(response):
    body = response.body
    if type(body).__name__ == "generator":
        body = b"".join(body)

    if isinstance(body, str):
        body_bytes = body.encode()
    else:
        body_bytes = body

    try:
        body_text = body_bytes.decode()
    except Exception:
        body_text = str(body_bytes)

    payload = {
        "status": response.status,
        "headers": response.headers,
        "body": body_text,
    }

    return json.dumps(payload)


def _normalize_response(response):
    if type(response).__name__ == "generator":
        return Response(response, status=200, headers={"Content-Type": "application/octet-stream"})

    if isinstance(response, str):
        response = (response,)

    if isinstance(response, tuple):
        body = response[0]
        status = response[1] if len(response) >= 2 else 200
        headers = response[2] if len(response) >= 3 else {"Content-Type": "text/html"}

        if isinstance(headers, str):
            headers = {"Content-Type": headers}

        response = Response(body, status=status)

        for key, value in headers.items():
            response.add_header(key, value)

        if hasattr(body, "__len__"):
            response.add_header("Content-Length", len(body))

    return response


def handle_usb_api_request(route_url, headers_text, data_text):
    request_headers = _parse_headers(headers_text)

    request = Request("USB", route_url, "HTTP/1.1")
    request.headers = request_headers
    request.raw_data = None
    request.data = {}

    if data_text:
        request.raw_data = data_text
        if request_headers.get("content-type", "").startswith("application/json"):
            try:
                request.data = json.loads(data_text)
            except Exception as exc:
                print(f"USB REQ: failed to parse JSON body: {exc}")

    handler = catchall_handler
    try:
        handler = _routes[request.path]
    except KeyError:
        print(f"USB REQ: route not found: {request.path}")

    if handler is None:
        return json.dumps({
            "status": 404,
            "headers": {"Content-Type": "text/plain"},
            "body": "Route not found",
        })

    response = handler(request)
    response = _normalize_response(response)

    if isinstance(response, Response):
        return _render_response(response)

    print(f"USB REQ: invalid response type: {type(response)}")
    return json.dumps({
        "status": 500,
        "headers": {"Content-Type": "text/plain"},
        "body": "Invalid response type",
    })


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
            response_text = handle_usb_api_request(route_url, headers, data)
            print(response_text)
        except Exception as e:
            print(f"USB REQ: error processing request: {e}")
            # Continue processing other requests even if one fails


def send_game_status():
    gs = GameStatus.game_report()
    # gs['zoom_initials'] = S.zoom_initials
    gs_json = json.dumps(gs)
    print(f"ZOOM: GAME: {gs_json}")
