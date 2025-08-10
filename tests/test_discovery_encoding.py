import os
import sys

# Ensure src directory is on sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from common.discovery import DiscoveryMessage, MessageType
from common import discovery


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


def test_repr_readable():
    ip = bytes([192, 168, 0, 5])
    assert "HELLO" in repr(DiscoveryMessage.hello("X"))
    assert "OFFLINE" in repr(DiscoveryMessage.offline(ip))
    assert "192.168.0.5" in repr(DiscoveryMessage.offline(ip))


def test_repr_full_does_not_consume():
    peers = [(_ip_chars(1, 2, 3, 4), "a"), (_ip_chars(5, 6, 7, 8), "b")]
    msg = DiscoveryMessage.full(iter(peers))
    _ = repr(msg)
    data = msg.encode()
    decoded = DiscoveryMessage.decode(data)
    assert list(decoded.peers) == peers


def test_registry_ip_bytes_returns_minimum_peer_ip():
    """Ensure registry_ip_bytes handles string entries without TypeError."""
    # Save old globals to restore after test
    old_devices = discovery.known_devices
    old_local_ip = discovery.local_ip_bytes
    try:
        discovery.known_devices = [
            _ip_chars(192, 168, 0, 5) + "Game5",
            _ip_chars(192, 168, 0, 3) + "Game3",
        ]
        discovery.local_ip_bytes = bytes([192, 168, 0, 10])
        assert discovery.registry_ip_bytes() == bytes([192, 168, 0, 3])
    finally:
        discovery.known_devices = old_devices
        discovery.local_ip_bytes = old_local_ip
