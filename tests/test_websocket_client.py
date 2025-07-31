import sys
import types
import base64
import os

# Ensure module can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'common'))
# Provide stub modules so websocket_client can be imported on CPython
sys.modules.setdefault('usocket', types.SimpleNamespace())
sys.modules.setdefault('ubinascii', types.SimpleNamespace(b2a_base64=lambda b: base64.b64encode(b)))
sys.modules.setdefault('urandom', types.SimpleNamespace(getrandbits=lambda n: 0))
import websocket_client


def _fake_usocket():
    class DummySocket:
        def __init__(self):
            self.sent = []
            self._done = False
        def connect(self, addr):
            self.addr = addr
        def send(self, data):
            self.sent.append(data)
        def recv(self, n):
            if not self._done:
                self._done = True
                return b"HTTP/1.1 101 Switching Protocols\r\n\r\n"
            return b""
        def close(self):
            pass
    return types.SimpleNamespace(
        getaddrinfo=lambda host, port: [(None, None, None, None, ('0.0.0.0', port))],
        socket=lambda: DummySocket(),
    )


def test_connect_does_not_request_large_bit_counts(monkeypatch):
    calls = []
    def fake_getrandbits(n):
        calls.append(n)
        if n > 32:
            raise ValueError("bits must be 32 or less")
        return 0
    monkeypatch.setattr(websocket_client, 'urandom', types.SimpleNamespace(getrandbits=fake_getrandbits))
    monkeypatch.setattr(websocket_client, 'usocket', _fake_usocket())
    monkeypatch.setattr(websocket_client, 'ubinascii', types.SimpleNamespace(b2a_base64=lambda b: base64.b64encode(b)))

    ws = websocket_client.connect("ws://example")
    assert isinstance(ws, websocket_client.WebSocket)
    assert max(calls) <= 32


def test_send_uses_small_random_mask(monkeypatch):
    calls = []
    def fake_getrandbits(n):
        calls.append(n)
        if n > 32:
            raise ValueError("bits must be 32 or less")
        return 0
    monkeypatch.setattr(websocket_client, 'urandom', types.SimpleNamespace(getrandbits=fake_getrandbits))
    class DummySock:
        def __init__(self):
            self.sent = b''
        def send(self, data):
            self.sent = data
    sock = DummySock()
    ws = websocket_client.WebSocket(sock)
    ws.send("hi")
    assert max(calls) <= 32
