import time

import machine
import ntptime
import uasyncio
from machine import RTC

import faults
from ScoreTrack import CheckForNewScores, initialize_leaderboard
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH
from SPI_Store import sflash_driver_init, write_16_fram
from SPI_UpdateStore import initialize as sflash_initialize
from SPI_UpdateStore import tick as sflash_tick

from . import logging

ntptime.host = "pool.ntp.org"  # Setting a specific NTP server
rtc = RTC()

led_board = machine.Pin(26, machine.Pin.OUT)
led_board.low()  # low is ON

_routes = []
catchall_handler = None
loop = uasyncio.get_event_loop()
monitor_count = 0


class Request:
    def __init__(self, method, uri, protocol):
        self.method = method
        self.uri = uri
        self.protocol = protocol
        self.form = {}
        self.data = {}
        self.raw_data = None  # Will hold the raw JSON body if present
        self.query = {}
        query_string_start = uri.find("?") if uri.find("?") != -1 else len(uri)
        self.path = uri[:query_string_start]

    def __str__(self):
        return "\n".join([f"request: {self.method} {self.path} {self.protocol}", f"headers: {self.headers}", f"form: {self.form}", f"data: {self.data}"])


class Response:
    def __init__(self, body, status=200, headers=None):
        # we can't use {} as default value for headers as it is mutable and would be shared between instances
        if headers is None:
            headers = {}
        self.status = status
        self.headers = headers
        self.body = body

    def add_header(self, name, value):
        self.headers[name] = value

    def __str__(self):
        return f"""\
status: {self.status}
headers: {self.headers}
body: {self.body}"""


class Route:
    def __init__(self, path, handler, method="GET"):
        self.path = path
        self.method = method
        self.handler = handler

    # returns True if the supplied request matches this route
    def matches(self, request):
        if request.method != self.method:
            return False
        return request.path == self.path

    # call the route handler passing any named parameters in the path
    def call_handler(self, request):
        return self.handler(request)

    def __repr__(self):
        return f"<Route object {self.path} ({', '.join(self.methods)})>"


# parses the headers for a http request (or the headers attached to
# each field in a multipart/form-data)
async def _parse_headers(reader):
    headers = {}
    while True:
        header_line = await reader.readline()
        if header_line == b"\r\n":  # crlf denotes body start
            break
        name, value = header_line.decode().strip().split(": ", 1)
        headers[name.lower()] = value
    return headers


# returns the route matching the supplied path or None
def _match_route(request):
    for idx, route in enumerate(_routes):
        if route.matches(request):
            print(f"Matched route at index {idx}")
            return route
    return None


# if the content type is application/json then parse the body
async def _parse_json_body(reader, headers):
    import json

    content_length_bytes = int(headers["content-length"])
    body = await reader.readexactly(content_length_bytes)
    body_str = body.decode()
    return body_str, json.loads(body_str)


# handle an incoming request to the web server
async def _handle_request(reader, writer):
    try:
        response = None

        request_start_time = time.ticks_ms()

        request_line = await reader.readline()
        try:
            method, uri, protocol = request_line.decode().split()
        except Exception as e:
            logging.error(e)
            return

        request = Request(method, uri, protocol)
        request.headers = await _parse_headers(reader)
        if "content-length" in request.headers and "content-type" in request.headers:
            if request.headers["content-type"].startswith("application/json"):
                raw_body, parsed_data = await _parse_json_body(reader, request.headers)
                request.raw_data = raw_body
                request.data = parsed_data

        route = _match_route(request)
        if route:
            response = route.call_handler(request)
        elif catchall_handler:
            response = catchall_handler(request)

        # if shorthand body generator only notation used then convert to tuple
        if type(response).__name__ == "generator":
            response = (response,)

        # if shorthand body text only notation used then convert to tuple
        if isinstance(response, str):
            response = (response,)

        # if shorthand tuple notation used then build full response object
        if isinstance(response, tuple):
            body = response[0]
            status = response[1] if len(response) >= 2 else 200
            headers = response[2] if len(response) >= 3 else {"Content-Type": "text/html"}

            # Handle legacy single content type as a string
            if isinstance(headers, str):
                headers = {"Content-Type": headers}

            response = Response(body, status=status)

            # Add all headers
            for key, value in headers.items():
                response.add_header(key, value)

            if hasattr(body, "__len__"):
                response.add_header("Content-Length", len(body))

        # write status line
        writer.write(f"HTTP/1.1 {response.status} {response.status}\r\n".encode("ascii"))

        # write headers
        for key, value in response.headers.items():
            writer.write(f"{key}: {value}\r\n".encode("ascii"))

        # blank line to denote end of headers
        writer.write("\r\n".encode("ascii"))

        if type(response.body).__name__ == "generator":
            # generator
            for chunk in response.body:
                writer.write(chunk)
                await writer.drain()
        else:
            # string/bytes
            writer.write(response.body)
            await writer.drain()

        writer.close()
        await writer.wait_closed()

        processing_time = time.ticks_ms() - request_start_time
        logging.info(f"> {request.method} {request.path} ({response.status}) [{processing_time}ms]")
    except Exception as e:
        # last line of defense to keep server from crashing
        logging.error(f"Error handling request: {e}")


# adds a new route to the routing table
def add_route(path, handler, method="GET"):
    global _routes
    _routes.append(Route(path, handler, method))
    # descending complexity order so most complex routes matched first
    # TODO maybe we should dynamically sort this list by call frequency
    _routes = sorted(_routes, key=lambda route: len(route.path), reverse=True)


def set_callback(handler):
    global catchall_handler
    catchall_handler = handler


def redirect(url, status=301):
    return Response("", status, {"Location": url})


# Function to update time from NTP server with retry mechanism
def update_time(retry=1):
    attempt = 0
    print("Server: Date Update")
    while attempt <= retry:
        try:
            ntptime.settime()  # This updates the RTC based on NTP server time
            print("   Date update ok")
            return
        except Exception as e:
            print("   Failed to update date:", e)
            attempt = attempt + 1
            time.sleep(0.2)
    print("   Failed to update date after several attempts.")


def initialize_timedate():
    update_time(1)
    year, month, day, _, _, _, _, _ = rtc.datetime()
    print("   Current UTC Date (Y/M/D): ", year, month, day)


MemIndex = 0
poll_counter = 0


# TODO this should live in SPI_Store
def copy_to_fram():
    global MemIndex

    write_16_fram(SRAM_DATA_BASE + MemIndex, MemIndex)
    MemIndex = MemIndex + 16

    if MemIndex >= SRAM_DATA_LENGTH:
        MemIndex = 0
        print("FRAM: cycle complete")
        led_board.toggle()


_scheduled_tasks = []


def restart_schedule():
    for t in _scheduled_tasks:
        t["next_run"] = time.ticks_add(time.ticks_ms(), t["phase"])


def schedule(func, phase_ms, frequency_ms=None, log=None):
    # Note: async function will not print to console
    _scheduled_tasks.append(
        {
            "func": func,
            "freq": frequency_ms,
            # we need to use time.ticks_add to handle rollover
            "next_run": time.ticks_add(time.ticks_ms(), phase_ms),
            # we need to store the phase so we can restart the schedule
            "phase": phase_ms,
            "log": log,
        }
    )


async def run_scheduled():
    while True:
        # default to 1 second in the future
        next_wake = time.ticks_add(time.ticks_ms(), 1000)
        for t in _scheduled_tasks:
            if time.ticks_diff(time.ticks_ms(), t["next_run"]) >= 0:
                if t["log"] is not None:
                    print(t["log"])  # TODO should we actually log this or is print enough?

                # run the task
                t["func"]()

                # reschedule or remove tasks
                if t["freq"] is None:
                    _scheduled_tasks.remove(t)
                else:
                    t["next_run"] = time.ticks_add(t["next_run"], t["freq"])

            # track next wake up time
            if time.ticks_diff(next_wake, t["next_run"]) > 0:
                next_wake = t["next_run"]

        delay = time.ticks_diff(next_wake, time.ticks_ms())
        if delay > 0:  # only sleep if we have time to sleep
            await uasyncio.sleep_ms(delay)


def create_schedule(ap_mode: bool = False):
    from resource import go as resource_go

    from discovery import DEVICE_TIMEOUT, announce, listen
    from displayMessage import refresh
    from GameStatus import poll_fast

    #
    # one time tasks
    #
    # TODO confirm all print statments instead return a string since prints will not show up
    # set the display message 30 seconds after boot
    schedule(refresh, 30000)

    # initialize the leader board 10 seconds after boot
    schedule(initialize_leaderboard, 10000, log="Server: Initialize Leader Board")

    # print out memory usage 45 seconds after boot
    schedule(resource_go, 5000, 10000)

    # initialize the fram
    schedule(sflash_driver_init, 200)

    # initialize the sflash
    schedule(sflash_initialize, 700)

    #
    # reoccuring tasks
    #

    # update the game status every 0.25 second
    schedule(poll_fast, 0, 250)

    # start checking scores every 5 seconds 15 seconds after boot
    schedule(CheckForNewScores, 15000, 5000)

    # only if there are no hardware faults
    if not faults.fault_is_raised(faults.ALL_HDWR):
        # copy ram values to fram every 0.1 seconds
        schedule(copy_to_fram, 0, 100)

    # call serial flash tick every 1 second for ongoing erase operations
    schedule(sflash_tick, 1000, 1000)

    # non AP mode only tasks
    if not ap_mode:
        # every 1/2 of DEVICE_TIMEOUT announce our presence
        schedule(announce, 10000, DEVICE_TIMEOUT * 1000 // 2)

        # every 1/20 of DEVICE_TIMEOUT listen for others
        schedule(listen, 10000, DEVICE_TIMEOUT * 1000 // 20)

        # initialize the time and date 5 seconds after boot
        schedule(initialize_timedate, 5000, log="Server: Initialize time /date")

    restart_schedule()


def run(ap_mode: bool, host="0.0.0.0", port=80):
    logging.info("> starting web server on port {}".format(port))
    loop.create_task(
        # TODO backlog is number of connections that can be queued. experiment with larger numbers
        uasyncio.start_server(_handle_request, host, port, backlog=5)
    )

    create_schedule(ap_mode)
    loop.create_task(run_scheduled())

    print("Server: Loop Forever")
    loop.run_forever()
    faults.raise_fault(faults.SFTW02)


def stop():
    loop.stop()


def close():
    loop.close()
