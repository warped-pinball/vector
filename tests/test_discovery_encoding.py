import os
import sys

# Ensure src directory is on sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from common.discovery import DiscoveryMessage, MessageType


def _ip_chars(*bytes_):
    return ''.join(chr(b) for b in bytes_)


def test_encode_decode_hello():
    msg = DiscoveryMessage.hello("Test")
    data = msg.encode()
    decoded = DiscoveryMessage.decode(data)
    assert decoded and decoded.type == MessageType.HELLO and decoded.name == "Test"


def test_encode_decode_full():
    peers = [(_ip_chars(192, 168, 0, 1), "dev1"), (_ip_chars(192, 168, 0, 2), "dev2")]
    msg = DiscoveryMessage.full(peers)
    data = msg.encode()
    decoded = DiscoveryMessage.decode(data)
    assert decoded and decoded.type == MessageType.FULL
    assert list(decoded.peers) == peers


def test_encode_decode_ping_pong():
    assert DiscoveryMessage.decode(DiscoveryMessage.ping().encode()).type == MessageType.PING
    assert DiscoveryMessage.decode(DiscoveryMessage.pong().encode()).type == MessageType.PONG


def test_encode_decode_offline():
    ip = bytes([192, 168, 0, 5])
    msg = DiscoveryMessage.offline(ip)
    data = msg.encode()
    decoded = DiscoveryMessage.decode(data)
    assert decoded and decoded.type == MessageType.OFFLINE and decoded.ip == ip
