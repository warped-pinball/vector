import os
import sys

# Ensure src directory is on sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from common.discovery import (
    encode_message,
    decode_message,
)


def _ip_chars(*bytes_):
    return ''.join(chr(b) for b in bytes_)


def test_encode_decode_hello():
    msg = {"hello": True, "name": "Test"}
    data = encode_message(msg)
    assert decode_message(data) == msg


def test_encode_decode_full():
    p1 = _ip_chars(192, 168, 0, 1) + "dev1"
    p2 = _ip_chars(192, 168, 0, 2) + "dev2"
    payload = "|".join([p1, p2])
    msg = {"full": payload}
    data = encode_message(msg)
    assert decode_message(data) == msg


def test_encode_decode_ping_pong():
    assert decode_message(encode_message({"ping": True})) == {"ping": True}
    assert decode_message(encode_message({"pong": True})) == {"pong": True}


def test_encode_decode_offline():
    msg = {"offline": "192.168.0.5"}
    data = encode_message(msg)
    assert decode_message(data) == msg
