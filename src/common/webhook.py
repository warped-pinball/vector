# Webhook messages: a few rare board events POSTed over HTTPS to one URL.
#
# This is the off-LAN sibling of origin.py.  Origin listens on the same
# network and hears every game event over UDP; a webhook lives somewhere on
# the internet and only hears the events worth a round trip: the end of a
# game, a fault raised or cleared, and the board starting up.  The live game
# state stream never goes over a webhook.
#
# It is strictly opt-in.  The owner registers a URL and shared secret over
# the authenticated /api/webhook/target route; with nothing registered this
# module sends nothing and opens no connections.
#
# Each request is:
#
#     POST <url>
#     Content-Type: application/json
#     X-Vector-Signature: <64 hex chars of HMAC-SHA256(secret, body)>
#
#     {"machine_id": "...", "type": "end_of_game", "n": 7, "data": {...}}
#
# The body has the same shape as an Origin message, and "n" counts up from 1
# after every boot ("reset" is usually the first), so a receiver
# can spot a gap or a replay.
#
# Unlike Origin's target, the registration is saved in FRAM (the "webhook"
# record of SPI_DataStore): a listener on the internet cannot notice a reboot
# and re-register the way Origin does.  FRAM survives updates; a factory reset
# blanks the record.
#
# Delivery is best effort.  Events wait in a short RAM queue and are sent by
# a background task, never from the code that raised them, so a slow or
# unreachable server cannot stall score tracking.  A failed send is retried
# once; after that the event is dropped.

from micropython import const

# The FRAM record is a marker byte, the URL and the secret, both null padded
_RECORD_FORMAT = "<B160s64s"
# Marker byte of a saved registration.  Anything else, including FRAM that has
# never held this record, reads as "no webhook".
_REGISTERED = const(0x57)
# Longest URL and secret the record holds, in bytes
MAX_URL_LENGTH = const(160)
MAX_SECRET_LENGTH = const(64)
# Events waiting to be sent; the oldest is dropped when a new one arrives on a full queue.
# A boot sends three (fault, fault_cleared, reset) and a game sends one.
_MAX_QUEUE = const(4)
# Attempts per event before it is dropped
_MAX_ATTEMPTS = const(2)
# Wait before retrying a failed send
_RETRY_DELAY_MS = const(30000)
# Give up on a single request after this long
_REQUEST_TIMEOUT_S = const(15)

_url = None
_secret = None
_loaded = False
_counter = 0
_queue = []
_last_status = None
_last_error = None


def _write_record(url, secret):
    """Save the registration to FRAM, or blank the record when ``url`` is None."""
    from struct import pack

    import SPI_Store as fram
    from SPI_DataStore import memory_map

    if url is None:
        data = pack(_RECORD_FORMAT, 0, b"", b"")
    else:
        data = pack(_RECORD_FORMAT, _REGISTERED, url.encode("utf-8"), secret.encode("utf-8"))
    fram.write(memory_map["webhook"]["start"], data)


def _load():
    """Read the saved registration once, on first use."""
    global _url, _secret, _loaded
    if _loaded:
        return
    _loaded = True
    _url = None
    _secret = None
    try:
        from struct import unpack

        import SPI_Store as fram
        from SPI_DataStore import memory_map

        record = memory_map["webhook"]
        marker, url, secret = unpack(_RECORD_FORMAT, fram.read(record["start"], record["size"]))
        if marker != _REGISTERED:
            return
        url = url.rstrip(b"\0").decode("utf-8")
        parse_url(url)
        _url = url
        _secret = secret.rstrip(b"\0")
    except Exception:
        _url = None
        _secret = None


def parse_url(url):
    """Split an https URL into (host, port, path), or raise ValueError."""
    if not url.startswith("https://"):
        raise ValueError("url must start with https://")
    rest = url[8:]
    slash = rest.find("/")
    if slash == -1:
        host_port, path = rest, "/"
    else:
        host_port, path = rest[:slash], rest[slash:]
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host, port = host_port, 443
    if not host:
        raise ValueError("url has no host")
    return host, port, path


def set_target(url, secret):
    """Send webhook messages to ``url``, signed with ``secret``, and save the registration."""
    global _url, _secret, _loaded, _counter, _last_status, _last_error

    parse_url(url)
    if len(url.encode("utf-8")) > MAX_URL_LENGTH or len(secret.encode("utf-8")) > MAX_SECRET_LENGTH:
        raise ValueError("url or secret is too long")
    _write_record(url, secret)
    _url = url
    _secret = secret.encode("utf-8")
    _loaded = True
    _counter = 0
    _queue.clear()
    _last_status = None
    _last_error = None


def clear_target():
    """Stop sending webhook messages and forget the saved registration."""
    global _url, _secret, _loaded, _counter

    _write_record(None, None)
    _url = None
    _secret = None
    _loaded = True
    _counter = 0
    _queue.clear()


def release_memory():
    """Drop the waiting events.  LowMemoryMode calls this before an update, which ends in a reboot."""
    _queue.clear()


def get_status():
    """The registered URL and how delivery is going.  Never includes the secret."""
    _load()
    return {
        "url": _url,
        "queued": len(_queue),
        "last_status": _last_status,
        "last_error": _last_error,
    }


def send(message_type, data=None):
    """Queue an event for delivery.  Does nothing when no webhook is registered."""
    global _counter

    _load()
    if _url is None:
        return

    try:
        from origin import get_machine_id
        from ujson import dumps

        _counter += 1
        message = {"machine_id": get_machine_id(), "type": message_type, "n": _counter}
        if data is not None:
            message["data"] = data

        if len(_queue) >= _MAX_QUEUE:
            _queue.pop(0)
        # [body, attempts so far, earliest next attempt in ticks_ms]
        _queue.append([dumps(message).encode(), 0, 0])
    except Exception as e:
        print("Error queueing webhook message:", e)


async def _post(body):
    """POST ``body`` to the registered URL and return the HTTP status code."""
    from gc import collect

    import uasyncio
    from backend import hmac_sha256
    from ubinascii import hexlify

    host, port, path = parse_url(_url)
    host_header = host if port == 443 else "%s:%d" % (host, port)
    signature = hexlify(hmac_sha256(_secret, body)).decode()

    try:
        import ssl
    except ImportError:
        import ussl as ssl

    # Matches mrequests: encrypt the connection, but don't fail on a
    # certificate the board has no root store to check.  The signature, not
    # TLS, is what lets the receiver trust the message.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if hasattr(ssl, "CERT_OPTIONAL"):
        context.verify_mode = ssl.CERT_OPTIONAL

    # The TLS handshake needs a large block of free memory
    collect()

    reader, writer = await uasyncio.wait_for(uasyncio.open_connection(host, port, ssl=context), _REQUEST_TIMEOUT_S)
    try:
        writer.write(
            b"POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\nX-Vector-Signature: %s\r\nUser-Agent: Vector\r\nConnection: close\r\n\r\n"
            % (path.encode(), host_header.encode(), len(body), signature.encode())
        )
        writer.write(body)
        await uasyncio.wait_for(writer.drain(), _REQUEST_TIMEOUT_S)
        status_line = await uasyncio.wait_for(reader.readline(), _REQUEST_TIMEOUT_S)
        # b"HTTP/1.1 200 OK\r\n"
        return int(status_line.split(b" ", 2)[1])
    finally:
        writer.close()
        await writer.wait_closed()
        collect()


async def run():
    """Background task: deliver queued events one at a time."""
    global _last_status, _last_error
    from time import ticks_add, ticks_diff, ticks_ms

    import phew.server
    import uasyncio
    from phew import is_connected_to_wifi

    while True:
        await uasyncio.sleep_ms(1000)

        # An update halts the schedule to free memory; a TLS handshake would undo that
        if not _queue or _url is None or phew.server._halt_schedule:
            continue
        entry = _queue[0]
        if ticks_diff(ticks_ms(), entry[2]) < 0 or not is_connected_to_wifi():
            continue

        entry[1] += 1
        try:
            status = await _post(entry[0])
            _last_status = status
            _last_error = None
            delivered = 200 <= status < 300
        except Exception as e:
            _last_status = None
            _last_error = str(e) or type(e).__name__
            delivered = False

        # The queue may have been cleared or trimmed while the request was out
        if not _queue or _queue[0] is not entry:
            continue
        if delivered or entry[1] >= _MAX_ATTEMPTS:
            _queue.pop(0)
        else:
            entry[2] = ticks_add(ticks_ms(), _RETRY_DELAY_MS)
