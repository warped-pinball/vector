import uasyncio, os, time
from . import logging
from machine import Timer
import machine
import SPI_Store as fram
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE
from ScoreTrack import CheckForNewScores, initialize_leaderboard
from machine import RTC
import ntptime,time
import displayMessage
import resource
import SharedState
import reset_control 
import gc
import SPI_DataStore as DataStore
import GameStatus
import faults

ntptime.host = 'pool.ntp.org'  # Setting a specific NTP server
rtc = RTC()

led_board = machine.Pin(26, machine.Pin.OUT)
led_board.low()  #low is ON

_routes = []
catchall_handler = None
loop = uasyncio.get_event_loop()
monitor_count=0

def file_exists(filename):
  try:
    return (os.stat(filename)[0] & 0x4000) == 0
  except OSError:
    return False


def urldecode(text):
  text = text.replace("+", " ")
  result = ""
  token_caret = 0
  # decode any % encoded characters
  while True:
    start = text.find("%", token_caret)
    if start == -1:
      result += text[token_caret:]
      break
    result += text[token_caret:start]
    code = int(text[start + 1:start + 3], 16)
    result += chr(code)
    token_caret = start + 3
  return result

def _parse_query_string(query_string):
  result = {}
  for parameter in query_string.split("&"):
    key, value = parameter.split("=", 1)
    key = urldecode(key)
    value = urldecode(value)
    result[key] = value
  return result


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
    self.query_string = uri[query_string_start + 1:]
    if self.query_string:
      self.query = _parse_query_string(self.query_string)

  def __str__(self):
    return f"""\
request: {self.method} {self.path} {self.protocol}
headers: {self.headers}
form: {self.form}
data: {self.data}"""


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


content_type_map = {
  "html": "text/html",
  "jpg": "image/jpeg",
  "jpeg": "image/jpeg",
  "svg": "image/svg+xml",
  "json": "application/json",
  "png": "image/png",
  "css": "text/css",
  "js": "text/javascript",
  "csv": "text/csv",
}


class FileResponse(Response):
  def __init__(self, file, status=200, headers={}):
    self.status = 404
    self.headers = headers
    self.file = file

    try:
      if (os.stat(self.file)[0] & 0x4000) == 0:
        self.status = 200

        # auto set content type
        extension = self.file.split(".")[-1].lower()
        if extension in content_type_map:
          headers["Content-Type"] = content_type_map[extension]

        headers["Content-Length"] = os.stat(self.file)[6]
    except OSError:
      return False


class Route:
  def __init__(self, path, handler, methods=["GET"]):
    self.path = path
    self.methods = methods
    self.handler = handler
    self.path_parts = path.split("/")

  # returns True if the supplied request matches this route
  def matches(self, request):
    if request.method not in self.methods:
      return False
    compare_parts = request.path.split("/")
    if len(compare_parts) != len(self.path_parts):
      return False
    for part, compare in zip(self.path_parts, compare_parts):
      if not part.startswith("<") and part != compare:
        return False
    return True

  # call the route handler passing any named parameters in the path
  def call_handler(self, request):
    parameters = {}
    for part, compare in zip(self.path_parts, request.path.split("/")):
      if part.startswith("<"):
        name = part[1:-1]
        parameters[name] = compare

    return self.handler(request, **parameters)
        
  def __str__(self):
    return f"""\
path: {self.path}
methods: {self.methods}
"""

  def __repr__(self):
    return f"<Route object {self.path} ({', '.join(self.methods)})>"


# parses the headers for a http request (or the headers attached to
# each field in a multipart/form-data)
async def _parse_headers(reader):
  headers = {}
  while True:
    header_line = await reader.readline()
    if header_line == b"\r\n": # crlf denotes body start
      break
    name, value = header_line.decode().strip().split(": ", 1)
    headers[name.lower()] = value
  return headers


# returns the route matching the supplied path or None
def _match_route(request):
  for route in _routes:
    if route.matches(request):
      return route
  return None


# if the content type is multipart/form-data then parse the fields
async def _parse_form_data(reader, headers):
  gc.collect()

  boundary = headers["content-type"].split("boundary=")[1]
  # discard first boundary line
  dummy = await reader.readline()

  form = {}
  while True:
    # get the field name
    field_headers = await _parse_headers(reader)
    if len(field_headers) == 0:
      break
    name = field_headers["content-disposition"].split("name=\"")[1][:-1]
    # get the field value
    value = ""
    while True:
      line = await reader.readline()
      line = line.decode().strip()
      # if we hit a boundary then save the value and move to next field
      if line == "--" + boundary:
        form[name] = value
        break
      # if we hit end of form data boundary then save value and return
      if line == "--" + boundary + "--":
        form[name] = value
        return form
      value += line
  return None


# if the content type is application/json then parse the body
async def _parse_json_body(reader, headers):
  import json
  content_length_bytes = int(headers["content-length"])
  body = await reader.readexactly(content_length_bytes)
  body_str = body.decode()
  return body_str, json.loads(body_str)


status_message_map = {
  200: "OK", 201: "Created", 202: "Accepted", 
  203: "Non-Authoritative Information", 204: "No Content",
  205: "Reset Content", 206: "Partial Content", 300: "Multiple Choices",
  301: "Moved Permanently", 302: "Found", 303: "See Other",
  304: "Not Modified", 305: "Use Proxy", 306: "Switch Proxy",
  307: "Temporary Redirect", 308: "Permanent Redirect",
  400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
  404: "Not Found", 405: "Method Not Allowed", 406: "Not Acceptable",
  408: "Request Timeout", 409: "Conflict", 410: "Gone",
  414: "URI Too Long", 415: "Unsupported Media Type", 
  416: "Range Not Satisfiable", 418: "I'm a teapot",
  500: "Internal Server Error", 501: "Not Implemented"
}


# handle an incoming request to the web server
async def _handle_request(reader, writer):
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
    if request.headers["content-type"].startswith("multipart/form-data"):
      request.form = await _parse_form_data(reader, request.headers)
    if request.headers["content-type"].startswith("application/json"):
      raw_body, parsed_data = await _parse_json_body(reader, request.headers)
      request.raw_data = raw_body
      request.data = parsed_data
    if request.headers["content-type"].startswith("application/x-www-form-urlencoded"):
      form_data = await reader.read(int(request.headers["content-length"]))
      request.form = _parse_query_string(form_data.decode()) 

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

    if hasattr(body, '__len__'):
      response.add_header("Content-Length", len(body))

  # write status line
  status_message = status_message_map.get(response.status, "Unknown")
  writer.write(f"HTTP/1.1 {response.status} {status_message}\r\n".encode("ascii"))

  # write headers
  for key, value in response.headers.items():
    writer.write(f"{key}: {value}\r\n".encode("ascii"))

  # blank line to denote end of headers
  writer.write("\r\n".encode("ascii"))
 
  if isinstance(response, FileResponse):
    # file
    with open(response.file, "rb") as f:
      while True:
        chunk = f.read(1024)
        if not chunk:
          break
        writer.write(chunk)
        await writer.drain()
  elif type(response.body).__name__ == "generator":
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
  logging.info(f"> {request.method} {request.path} ({response.status} {status_message}) [{processing_time}ms]")


# adds a new route to the routing table
def add_route(path, handler, methods=["GET"]):
  global _routes
  _routes.append(Route(path, handler, methods))
  # descending complexity order so most complex routes matched first
  _routes = sorted(_routes, key=lambda route: len(route.path_parts), reverse=True)


def set_callback(handler):
  global catchall_handler
  catchall_handler = handler


# decorator shorthand for adding a route
def route(path, methods=["GET"]):
  def _route(f):
    add_route(path, f, methods=methods)
    return f
  return _route


# decorator for adding catchall route
def catchall():
  def _catchall(f):
    set_callback(f)
    return f
  return _catchall
  

def redirect(url, status = 301):
  return Response("", status, {"Location": url})

def serve_file(file):
  return FileResponse(file)

# Function to update time from NTP server with retry mechanism
def update_time(retry=1):
    attempt = 0
    print("Server: Date Update")
    while attempt <= retry:
        try:
            ntptime.settime()  # This updates the RTC based on NTP server time
            print('   Date update ok')
            return
        except Exception as e:
            print('   Failed to update date:', e)
            attempt = attempt +1
            time.sleep(0.2)  
    print("   Failed to update date after several attempts.")


def initialize_timedate():
    update_time(1) 
    year, month, day, _, _, _, _, _ = rtc.datetime()
    print('   Current UTC Date (Y/M/D): ', year, month, day)


MemIndex=0
poll_counter=0
async def FRAMTimer():
    global MemIndex,poll_counter   
    while True:
        fram.write_16_fram(SRAM_DATA_BASE+MemIndex, MemIndex)
        MemIndex = MemIndex + 16
        #fram.write_16_fram(SRAM_DATA_BASE+MemIndex, MemIndex)
        #MemIndex = MemIndex + 16       
        #print("MEM in SEVER: ",MemIndex)

        poll_counter+=1
        if poll_counter>1:
          GameStatus.poll_fast()
          poll_counter=0

        await uasyncio.sleep(0.1)
        if MemIndex >= SRAM_DATA_LENGTH:
             MemIndex=0
             print("MEM in SERVER: FRAM cycle complete")
             led_board.toggle()

             
scCount=[0]
enableScoreChecks=[0]
def reset_bootup_counters():
  scCount[0] = 0  
  enableScoreChecks[0] = 0

async def ScoreCheck():  #scCount=[0],enableScoreChecks=[0]):
  global scCount,enableScoreChecks
  while True:       

    if enableScoreChecks[0] == 1:      
      CheckForNewScores()
        
    #power up init - each count is 5 seconds
    #runs 0->10 and ends
    if  scCount[0]<10:
        scCount[0]=scCount[0]+1
  
    if scCount[0] == 1:
        print("Server: Initialize time /date")
        initialize_timedate()
  
    if scCount[0] == 2:
        print("Server: Initialize Leader Board")
        initialize_leaderboard()
        
    if scCount[0] == 3:
        print("Server: init ball in play state machine")
        enableScoreChecks[0]=1
    
    if scCount[0] == 6:
        print("Server: Refresh display message")
        displayMessage.refresh()

    if scCount[0] == 9:
        print("\n")
        resource.go()
        print("\n")

    await uasyncio.sleep(5)
  
    
         
def run(host = "0.0.0.0", port = 80): 
  logging.info("> starting web server on port {}".format(port))
  loop.create_task(uasyncio.start_server(_handle_request, host, port))
  
  #perodic tasks specific to Warped Pinball SYS11
  if not faults.fault_is_raised(faults.ALL_HDWR):
    loop.create_task(FRAMTimer())    #store ram values in non-volatile Fram
    
  loop.create_task(ScoreCheck())   #Check For new scores

  print("Server: Loop Forever")
  loop.run_forever()
  print("Server: run forever return fault")
  

def stop():
  loop.stop()

def close():
  loop.close()
  
  