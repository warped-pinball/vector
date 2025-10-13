import errno as _errno
import socket as _socket
import struct as _struct
import time as _time

import uerrno as _errno
import urandom as _urandom
import usocket as _socket
import ustruct as _struct
import utime as _time

# UPH/1 MicroPython client (UDP side)
# Specification (all integer fields are big-endian/network order):
#  0..3   Magic            = ASCII b"UPH1"
#  4      Flags            = bit0 (0x01) indicates response expected
#  5      Method           = HTTP verb enum (0=GET, 1=POST, 2=PUT, 3=DELETE, 4=PATCH, 5=HEAD, 6=OPTIONS, ...)
#  6..9   RequestID        = uint32
#  10     HostLen          = uint8
#  11..   Host             = ASCII host name / IP
#  X..X+1 UpstreamPort     = uint16 (target HTTP server port)
#  Y      PathLen          = uint8 (no leading "/")
#  Z..    Path             = ASCII path component (no leading slash)
#  A      HeaderCount      = uint8
#           Repeated HeaderCount times:
#             kLen (uint8), key (ASCII)
#             vLen (uint8), value (UTF-8)
#  ...    BodyLen          = uint16
#  ...    Body             = opaque bytes
#
# Notes:
# - This client builds request frames to a UPH gateway over UDP. The message embeds
#   the upstream HTTP target (Host/UpstreamPort) and HTTP request details (method, path, headers, body).
# - Responses are received as raw frames and parsed with the same structure. The "Method" byte in a
#   response may be repurposed by the gateway (e.g., to carry status code) depending on server design.
# - All length-constrained fields must fit within uint8 (<=255) for names/values, and uint16 for body (<=65535).


# HTTP method -> enum mapping
METHODS = {
    "GET": 0,
    "POST": 1,
    "PUT": 2,
    "DELETE": 3,
    "PATCH": 4,
    "HEAD": 5,
    "OPTIONS": 6,
}
METHODS_INV = {v: k for k, v in METHODS.items()}

_MAGIC = b"UPH1"
_FLAG_EXPECT_RESP = 0x01


def _as_method_code(method):
    if isinstance(method, int):
        if 0 <= method <= 255:
            return method
        raise ValueError("method int out of range (0..255)")
    if not method:
        raise ValueError("method required")
    m = str(method).upper()
    if m in METHODS:
        return METHODS[m]
    raise ValueError("unsupported method: %r" % method)


def _ensure_ascii(s, field):
    if isinstance(s, bytes):
        try:
            s.decode("ascii")
            return s
        except Exception:
            raise ValueError("%s must be ASCII" % field)
    s = str(s)
    try:
        b = s.encode("ascii")
    except Exception:
        raise ValueError("%s must be ASCII" % field)
    return b


def _ensure_utf8(s):
    if isinstance(s, bytes):
        # Assume already UTF-8; do a light validation if desired
        return s
    return str(s).encode("utf-8")


def _u8(n, name="len"):
    if not (0 <= n <= 255):
        raise ValueError("%s must fit in uint8 (0..255)" % name)
    return n


def _u16(n, name="len"):
    if not (0 <= n <= 65535):
        raise ValueError("%s must fit in uint16 (0..65535)" % name)
    return n


def _gen_req_id():
    if _urandom:
        b = _urandom.getrandbits(32) if hasattr(_urandom, "getrandbits") else int.from_bytes(_urandom.random(4), "big")
        return b & 0xFFFFFFFF
    # Fallback: ticks_ms with a simple mix
    t = int(getattr(_time, "ticks_ms", lambda: int(_time.time() * 1000))())
    return ((t & 0xFFFF) << 16) ^ (t * 2654435761 & 0xFFFFFFFF)


def build_uph_frame(host, upstream_port, path, method="GET", headers=None, body=b"", request_id=None, expect_response=True):
    """
    Build a UPH/1 frame (bytes).
    host: upstream HTTP host (str/bytes ASCII)
    upstream_port: int (0..65535)
    path: ASCII path without leading "/" (will be normalized)
    method: HTTP verb (str or int code)
    headers: dict or iterable of (k,v), names ASCII, values UTF-8
    body: bytes or str (UTF-8 encoded)
    request_id: uint32 or None
    expect_response: bool -> sets Flags bit0
    """
    flags = _FLAG_EXPECT_RESP if expect_response else 0
    method_code = _as_method_code(method)
    req_id = request_id if request_id is not None else _gen_req_id()

    host_b = _ensure_ascii(host, "host")
    _u8(len(host_b), "HostLen")
    up_port = _u16(int(upstream_port), "UpstreamPort")

    # Normalize path (no leading "/")
    if isinstance(path, bytes):
        try:
            path.decode("ascii")
        except Exception:
            raise ValueError("path must be ASCII")
        path_b = path.lstrip(b"/")
    else:
        path_b = _ensure_ascii(str(path).lstrip("/"), "path")
    _u8(len(path_b), "PathLen")

    # Headers
    hdr_items = []
    if headers:
        if isinstance(headers, dict):
            it = headers.items()
        else:
            it = headers
        for k, v in it:
            kb = _ensure_ascii(k, "header name")
            vb = _ensure_utf8(v)
            _u8(len(kb), "header name len")
            _u8(len(vb), "header value len")
            hdr_items.append((kb, vb))
    _u8(len(hdr_items), "HeaderCount")

    # Body
    if not isinstance(body, (bytes, bytearray, memoryview)):
        body_b = _ensure_utf8(body)
    else:
        body_b = bytes(body)
    _u16(len(body_b), "BodyLen")

    parts = []
    parts.append(_MAGIC)
    parts.append(bytes((flags,)))
    parts.append(bytes((method_code,)))
    parts.append(_struct.pack("!I", req_id))
    parts.append(bytes((len(host_b),)))
    parts.append(host_b)
    parts.append(_struct.pack("!H", up_port))
    parts.append(bytes((len(path_b),)))
    parts.append(path_b)
    parts.append(bytes((len(hdr_items),)))
    for kb, vb in hdr_items:
        parts.append(bytes((len(kb),)))
        parts.append(kb)
        parts.append(bytes((len(vb),)))
        parts.append(vb)
    parts.append(_struct.pack("!H", len(body_b)))
    parts.append(body_b)

    return req_id, b"".join(parts)


def parse_uph_frame(buf):
    """
    Parse a UPH/1 frame into a dict. Raises ValueError on malformed input.
    Returns: {
      magic, flags, method, request_id,
      host, upstream_port, path,
      headers_list: [(k,v), ...],
      headers: {k: v, ...},   # first occurrence wins
      body (bytes)
    }
    """
    if not isinstance(buf, (bytes, bytearray, memoryview)):
        raise ValueError("buf must be bytes-like")
    mv = memoryview(buf)
    o = 0

    if len(mv) < 4:
        raise ValueError("buffer too short")
    magic = bytes(mv[o : o + 4])
    o += 4
    if magic != _MAGIC:
        raise ValueError("bad magic")

    if len(mv) < o + 1 + 1 + 4:
        raise ValueError("buffer too short (header)")
    flags = mv[o]
    o += 1
    method = mv[o]
    o += 1
    request_id = _struct.unpack("!I", mv[o : o + 4])[0]
    o += 4

    if len(mv) < o + 1:
        raise ValueError("buffer too short (HostLen)")
    hlen = mv[o]
    o += 1
    if len(mv) < o + hlen:
        raise ValueError("buffer too short (Host)")
    host = bytes(mv[o : o + hlen]).decode("ascii")
    o += hlen

    if len(mv) < o + 2:
        raise ValueError("buffer too short (UpstreamPort)")
    upstream_port = _struct.unpack("!H", mv[o : o + 2])[0]
    o += 2

    if len(mv) < o + 1:
        raise ValueError("buffer too short (PathLen)")
    plen = mv[o]
    o += 1
    if len(mv) < o + plen:
        raise ValueError("buffer too short (Path)")
    path = bytes(mv[o : o + plen]).decode("ascii")
    o += plen

    if len(mv) < o + 1:
        raise ValueError("buffer too short (HeaderCount)")
    hcount = mv[o]
    o += 1

    headers_list = []
    for _i in range(hcount):
        if len(mv) < o + 1:
            raise ValueError("buffer too short (kLen)")
        klen = mv[o]
        o += 1
        if len(mv) < o + klen:
            raise ValueError("buffer too short (key)")
        key = bytes(mv[o : o + klen]).decode("ascii")
        o += klen

        if len(mv) < o + 1:
            raise ValueError("buffer too short (vLen)")
        vlen = mv[o]
        o += 1
        if len(mv) < o + vlen:
            raise ValueError("buffer too short (value)")
        value = bytes(mv[o : o + vlen]).decode("utf-8")
        o += vlen

        headers_list.append((key, value))

    if len(mv) < o + 2:
        raise ValueError("buffer too short (BodyLen)")
    body_len = _struct.unpack("!H", mv[o : o + 2])[0]
    o += 2
    if len(mv) < o + body_len:
        raise ValueError("buffer too short (Body)")
    body = bytes(mv[o : o + body_len])
    o += body_len

    # Build headers dict (first occurrence wins)
    headers = {}
    for k, v in headers_list:
        if k not in headers:
            headers[k] = v

    return {
        "magic": magic,
        "flags": flags,
        "method": method,
        "request_id": request_id,
        "host": host,
        "upstream_port": upstream_port,
        "path": path,
        "headers_list": headers_list,
        "headers": headers,
        "body": body,
        "bytes_used": o,
    }


def _borrow_udp_socket(default_timeout=2.0):
    """
    Try to reuse a UDP socket from discovery.py; fall back to a new one.
    """
    sock = None
    try:
        import discovery  # type: ignore

        for name in ("udp_sock", "udp_socket", "sock", "socket"):
            s = getattr(discovery, name, None)
            if s and hasattr(s, "sendto") and hasattr(s, "recvfrom"):
                sock = s
                break
        if sock is None:
            get_sock = getattr(discovery, "get_socket", None)
            if callable(get_sock):
                s = get_sock()
                if s and hasattr(s, "sendto"):
                    sock = s
    except Exception:
        sock = None

    if sock is None:
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        try:
            sock.settimeout(default_timeout)
        except Exception:
            pass
        created = True
    else:
        try:
            sock.settimeout(default_timeout)
        except Exception:
            pass
        created = False
    return sock, created


class UPHClient:
    """
    Lightweight UPH/1 UDP client.
    gateway_addr: (host, port) tuple of the UPH gateway to send frames to.
    sock: optional UDP socket (will try to borrow from discovery.py if None).
    timeout: socket timeout in seconds.
    retries: number of resend attempts on timeout in request() (0 = no retry).
    """

    def __init__(self, gateway_addr, sock=None, timeout=2.0, retries=0):
        if not isinstance(gateway_addr, (tuple, list)) or len(gateway_addr) != 2:
            raise ValueError("gateway_addr must be (host, port)")
        self.gateway = (gateway_addr[0], int(gateway_addr[1]))
        self.retries = int(retries)
        self._own_socket = False
        if sock is None:
            sock, created = _borrow_udp_socket(timeout)
            self._own_socket = created
        self.sock = sock
        try:
            self.sock.settimeout(timeout)
        except Exception:
            pass

    def close(self):
        if self._own_socket and self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send(self, host, upstream_port, path, method="GET", headers=None, body=b"", request_id=None, expect_response=True):
        """
        Build and send a UPH frame. Returns request_id.
        """
        req_id, frame = build_uph_frame(
            host=host,
            upstream_port=upstream_port,
            path=path,
            method=method,
            headers=headers,
            body=body,
            request_id=request_id,
            expect_response=expect_response,
        )
        self.sock.sendto(frame, self.gateway)
        return req_id

    def recv(self, timeout=None, expect_request_id=None, max_bytes=4096):
        """
        Receive one UPH frame. Optionally filter by request_id.
        Returns (addr, parsed_dict).
        """
        if timeout is not None:
            try:
                self.sock.settimeout(timeout)
            except Exception:
                pass

        while True:
            data, addr = self.sock.recvfrom(max_bytes)
            try:
                parsed = parse_uph_frame(data)
            except Exception:
                # Ignore malformed frames
                continue
            if expect_request_id is not None and parsed["request_id"] != expect_request_id:
                # Not the one we are waiting for; ignore and keep waiting
                continue
            return addr, parsed

    def request(self, host, upstream_port, path, method="GET", headers=None, body=b"", request_id=None, timeout=None):
        """
        Send a request and wait for the matching response. Retries on timeout.
        Returns (addr, response_dict).
        """
        req_id = self.send(
            host=host,
            upstream_port=upstream_port,
            path=path,
            method=method,
            headers=headers,
            body=body,
            request_id=request_id,
            expect_response=True,
        )
        attempts = 0
        last_err = None
        while attempts <= self.retries:
            try:
                addr, resp = self.recv(timeout=timeout, expect_request_id=req_id)
                return addr, resp
            except OSError as e:
                last_err = e
                # ETIMEDOUT or EAGAIN -> retry
                if getattr(e, "errno", None) in (getattr(_errno, "ETIMEDOUT", -1), getattr(_errno, "EAGAIN", -1)):
                    attempts += 1
                    if attempts <= self.retries:
                        # resend the same frame if we can (rebuild identical frame)
                        # We rebuild to avoid storing the frame; request_id remains the same.
                        self.send(
                            host=host,
                            upstream_port=upstream_port,
                            path=path,
                            method=method,
                            headers=headers,
                            body=body,
                            request_id=req_id,
                            expect_response=True,
                        )
                        continue
                raise
            except Exception as e:
                last_err = e
                raise
        if last_err:
            raise last_err


# Convenience top-level helpers


def uph_sendto(gateway_addr, host, upstream_port, path, method="GET", headers=None, body=b"", request_id=None, expect_response=False, timeout=2.0, sock=None):
    """
    One-shot send of a UPH frame. Returns request_id.
    """
    client = UPHClient(gateway_addr=gateway_addr, sock=sock, timeout=timeout, retries=0)
    try:
        return client.send(host, upstream_port, path, method, headers, body, request_id, expect_response)
    finally:
        client.close()


def uph_request(gateway_addr, host, upstream_port, path, method="GET", headers=None, body=b"", request_id=None, timeout=2.0, retries=0, sock=None):
    """
    One-shot request/response. Returns (addr, response_dict).
    """
    client = UPHClient(gateway_addr=gateway_addr, sock=sock, timeout=timeout, retries=retries)
    try:
        return client.request(host, upstream_port, path, method, headers, body, request_id, timeout=timeout)
    finally:
        client.close()


# If this module is executed directly (simple smoke test build/parse)
if __name__ == "__main__":
    # Build and parse a local frame to validate structure
    rid, frame = build_uph_frame(
        host="example.com",
        upstream_port=80,
        path="api/v1/test",
        method="GET",
        headers={"Accept": "application/json", "X-Req": "1"},
        body=b"",
        request_id=1234,
        expect_response=True,
    )
    parsed = parse_uph_frame(frame)
    print("Built req_id:", rid, "Parsed req_id:", parsed["request_id"], "Path:", parsed["path"], "Host:", parsed["host"])
