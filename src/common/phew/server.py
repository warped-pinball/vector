import time

import machine
import ntptime
import uasyncio
from machine import RTC
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH

import faults
from ScoreTrack import CheckForNewScores, initialize_leaderboard, check_for_machine_high_scores
from SPI_Store import sflash_driver_init, write_16_fram
from SPI_UpdateStore import initialize as sflash_initialize
from SPI_UpdateStore import tick as sflash_tick

from . import logging

ntptime.host = "pool.ntp.org"  # Setting a specific NTP server
rtc = RTC()

led_board = machine.Pin(26, machine.Pin.OUT)
led_board.low()  # low is ON

_routes = {}
catchall_handler = None
loop = uasyncio.get_event_loop()
monitor_count = 0


class Request:
    def __init__(self, method, uri, protocol):
        self.method = method
        self.protocol = protocol
        self.data = {}
        self.raw_data = None  # Will hold the raw JSON body if present
        query_string_start = uri.find("?") if uri.find("?") != -1 else len(uri)
        self.path = uri[:query_string_start]

    def __str__(self):
        return "\n".join([f"request: {self.method} {self.path} {self.protocol}", f"headers: {self.headers}", f"data: {self.data}"])


class Response:
    def __init__(self, body, status=200, headers=None):
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


async def _parse_headers(reader):
    headers = {}
    while True:
        header_line = await reader.readline()
        if header_line == b"\r\n":  # crlf denotes body start
            break
        name, value = header_line.decode().strip().split(": ", 1)
        headers[name.lower()] = value
    return headers


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

        handler = catchall_handler
        try:
            handler = _routes[request.path]
        except KeyError:
            logging.info(f"Route not found: {request.path}")

        # TODO make parsing json and headers lazy
        request.headers = await _parse_headers(reader)
        if "content-length" in request.headers and "content-type" in request.headers:
            if request.headers["content-type"].startswith("application/json"):
                raw_body, parsed_data = await _parse_json_body(reader, request.headers)
                request.raw_data = raw_body
                request.data = parsed_data

        response = handler(request)

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
def add_route(path, handler):
    global _routes
    if path in _routes:
        raise ValueError(f"Route already exists: {path}")
    _routes[path] = handler


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
            attempt += 1
            time.sleep(0.2)
    print("   Failed to update date after several attempts.")


def initialize_timedate():
    update_time(1)
    year, month, day, _, _, _, _, _ = rtc.datetime()
    print("   Current UTC Date (Y/M/D): ", year, month, day)


MemIndex = 0
poll_counter = 0


def copy_to_fram():
    global MemIndex
    write_16_fram(SRAM_DATA_BASE + MemIndex, MemIndex)
    MemIndex += 16
    if MemIndex >= SRAM_DATA_LENGTH:
        MemIndex = 0
        print("FRAM: cycle complete")
        led_board.toggle()


_scheduled_tasks = []

# Use this to stop the schedule temporarily
_halt_schedule = False


def restart_schedule():
    for i, t in enumerate(_scheduled_tasks):  # Use index to update tuple
        # t[2] is next_run, t[3] is phase
        _scheduled_tasks[i] = (t[0], t[1], time.ticks_add(time.ticks_ms(), t[3]), t[3], t[4])


def schedule(func, phase_ms, frequency_ms=None, log=None):
    # Tuple order: (func, freq, next_run, phase, log)
    _scheduled_tasks.append((func, frequency_ms, time.ticks_add(time.ticks_ms(), phase_ms), phase_ms, log))


async def run_scheduled():
    global _halt_schedule
    while True:
        # default to 1 second in the future
        next_wake = time.ticks_add(time.ticks_ms(), 1000)
        for i, t in enumerate(_scheduled_tasks):  # Use index to update tuple
            if time.ticks_diff(time.ticks_ms(), t[2]) >= 0:  # t[2] is next_run
                if t[4] is not None:  # t[4] is log
                    print(t[4])  # TODO should we actually log this or is print enough?

                # run the task
                try:
                    t[0]()  # t[0] is func
                except Exception as e:
                    logging.error(f"Error running scheduled task: {e}")

                # reschedule or remove tasks
                if t[1] is None:  # t[1] is freq
                    _scheduled_tasks.remove(t)
                else:
                    # Replace tuple with updated next_run (t[2])
                    _scheduled_tasks[i] = (t[0], t[1], time.ticks_add(t[2], t[1]), t[3], t[4])

            # track next wake up time
            if time.ticks_diff(next_wake, t[2]) > 0:  # t[2] is next_run
                next_wake = t[2]

        delay = time.ticks_diff(next_wake, time.ticks_ms())
        if delay > 0:  # only sleep if we have time to sleep
            await uasyncio.sleep_ms(delay)

        while _halt_schedule:
            await uasyncio.sleep_ms(1000)


# TODO option to resume/start without boot up tasks
def create_schedule(ap_mode: bool = False):
    from resource import go as resource_go

    from backend import connect_to_wifi
    from discovery import DEVICE_TIMEOUT, announce, listen
    from displayMessage import refresh
    from GameStatus import poll_fast

    #
    # one time tasks
    #
    # set the display message
    schedule(refresh, 30000)

    # initialize the leader board right away
    schedule(initialize_leaderboard, 600, log="Server: Initialize Leader Board")

    # check for scores in the machine  (picks up deafults after reboot)
    schedule(check_for_machine_high_scores, 9500, log="Server: Power up machine score check")

    # print out memory usage
    schedule(resource_go, 5000, 10000)

    # initialize the fram
    schedule(sflash_driver_init, 200)

    # initialize the sflash
    schedule(sflash_initialize, 700)

    #
    # reoccuring tasks
    #

    # update the game status every 0.25 second
    schedule(poll_fast, 15000, 250)

    # start checking scores every 5 seconds 15 seconds after boot
    schedule(CheckForNewScores, 15000, 5000)

    # call serial flash tick every 1 second for ongoing erase operations
    schedule(sflash_tick, 1000, 1000)

    # only if there are no hardware faults
    if not faults.fault_is_raised(faults.ALL_HDWR):
        # copy ram values to fram every 0.1 seconds
        schedule(copy_to_fram, 0, 100)

    # non AP mode only tasks
    if not ap_mode:
        # every 1/2 of DEVICE_TIMEOUT announce our presence
        schedule(announce, 10000, DEVICE_TIMEOUT * 1000 // 2)

        # every 1/20 of DEVICE_TIMEOUT listen for others
        schedule(listen, 10000, DEVICE_TIMEOUT * 1000 // 20)

        # initialize the time and date 5 seconds after boot
        schedule(initialize_timedate, 5000, log="Server: Initialize time /date")

        # reconnect to wifi occasionally
        schedule(connect_to_wifi, 0, 120000, log="Server: Check Wifi")
    restart_schedule()


def run(ap_mode: bool, host="0.0.0.0", port=80):
    logging.info("> starting web server on port {}".format(port))
    loop.create_task(uasyncio.start_server(_handle_request, host, port, backlog=5))
    create_schedule(ap_mode)
    loop.create_task(run_scheduled())

    print("Server: Loop Forever")
    loop.run_forever()
    faults.raise_fault(faults.SFTW02)


def stop():
    loop.stop()


def close():
    loop.close()
