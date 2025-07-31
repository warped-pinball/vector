import usocket
import ubinascii
import urandom
import struct

class WebSocket:
    """Minimal synchronous WebSocket client."""

    def __init__(self, sock):
        self.sock = sock

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        length = len(data)
        # text frame opcode 1, FIN=1
        header = bytearray([0x81])
        if length < 126:
            header.append(0x80 | length)
        elif length < (1 << 16):
            header.append(0x80 | 126)
            header.extend(struct.pack('>H', length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack('>Q', length))
        mask = bytes(urandom.getrandbits(8) for _ in range(4))
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.send(header + masked)

    def recv(self):
        hdr = self._recv_exact(2)
        opcode = hdr[0] & 0x0F
        if opcode == 0x8:
            return b''
        length = hdr[1] & 0x7F
        if length == 126:
            length = struct.unpack('>H', self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack('>Q', self._recv_exact(8))[0]
        mask = None
        if hdr[1] & 0x80:
            mask = self._recv_exact(4)
        data = self._recv_exact(length)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return data

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

    def _recv_exact(self, size):
        buf = b''
        while len(buf) < size:
            buf += self.sock.recv(size - len(buf))
        return buf

def connect(url):
    if not url.startswith("ws://"):
        raise ValueError("WebSocket URL must start with ws://")
    url_no_scheme = url[5:]
    if '/' in url_no_scheme:
        host_part, path = url_no_scheme.split('/', 1)
        path = '/' + path
    else:
        host_part = url_no_scheme
        path = '/'
    if ':' in host_part:
        host, port = host_part.split(':', 1)
        port = int(port)
    else:
        host = host_part
        port = 80
    addr = usocket.getaddrinfo(host, port)[0][-1]
    sock = usocket.socket()
    sock.connect(addr)
    key_bytes = bytes(urandom.getrandbits(8) for _ in range(16))
    key = ubinascii.b2a_base64(key_bytes).strip()
    headers = (
        'GET {path} HTTP/1.1\r\n'
        'Host: {host}\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        'Sec-WebSocket-Key: {key}\r\n'
        'Sec-WebSocket-Version: 13\r\n\r\n'
    ).format(path=path, host=host, key=key.decode())
    sock.send(headers.encode())
    # Read HTTP response
    response = b''
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(64)
        if not chunk:
            raise OSError('WebSocket handshake failed')
        response += chunk
    return WebSocket(sock)
