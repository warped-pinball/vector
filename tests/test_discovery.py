import os
import sys

from ujson import loads

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from src.common import discovery  # noqa: E402


def setup_function():
    discovery.known_devices = []
    discovery.recv_sock = None
    discovery.send_sock = None
    discovery.last_discover_time = 0
    discovery.pending_ping = None
    discovery.local_ip_bytes = discovery.ip_to_bytes("192.168.0.10")
    discovery.local_ip_chars = "".join(chr(b) for b in discovery.local_ip_bytes)
    discovery._get_local_name = lambda: "local"


def _ip_chars(ip: str) -> str:
    return "".join(chr(b) for b in discovery.ip_to_bytes(ip))


def test_is_registry_lowest_ip():
    assert discovery.is_registry()
    discovery.known_devices.append(_ip_chars("192.168.0.20") + "Peer")
    assert discovery.is_registry()
    discovery.known_devices.append(_ip_chars("192.168.0.5") + "A")
    assert not discovery.is_registry()


def test_handle_hello_registry_broadcasts_full_list(monkeypatch):
    called = {}

    def fake_broadcast():
        called["full"] = True

    monkeypatch.setattr(discovery, "broadcast_full_list", fake_broadcast)
    discovery.handle_message({"hello": True, "name": "Peer"}, "192.168.0.20")
    assert called.get("full")
    assert any(d.startswith(_ip_chars("192.168.0.20")) for d in discovery.known_devices)


def test_handle_full_list_rebuilds_and_resends_hello_if_missing_self(monkeypatch):
    called = {}

    def fake_hello():
        called["hello"] = True

    monkeypatch.setattr(discovery, "broadcast_hello", fake_hello)
    msg = {"full": _ip_chars("192.168.0.20") + "Peer"}
    discovery.handle_message(msg, "192.168.0.20")
    assert called.get("hello")
    assert discovery.known_devices == [_ip_chars("192.168.0.20") + "Peer"]


def test_handle_offline_promotes_registry(monkeypatch):
    discovery.local_ip_bytes = discovery.ip_to_bytes("192.168.0.20")
    discovery.local_ip_chars = "".join(chr(b) for b in discovery.local_ip_bytes)
    ip10 = _ip_chars("192.168.0.10")
    discovery.known_devices = [ip10 + "A", _ip_chars("192.168.0.30") + "B"]

    called = {}

    def fake_broadcast():
        called["full"] = True

    monkeypatch.setattr(discovery, "broadcast_full_list", fake_broadcast)
    discovery.handle_message({"offline": "192.168.0.10"}, "192.168.0.30")
    assert called.get("full")
    assert all(not d.startswith(ip10) for d in discovery.known_devices)


def test_handle_pong_clears_pending_ping():
    ip_bytes = discovery.ip_to_bytes("192.168.0.20")
    discovery.pending_ping = ip_bytes
    discovery.handle_message({"pong": True}, "192.168.0.20")
    assert discovery.pending_ping is None


def test_offline_for_self_triggers_hello(monkeypatch):
    called = {}

    def fake_hello():
        called["hello"] = True

    monkeypatch.setattr(discovery, "broadcast_hello", fake_hello)
    discovery.handle_message({"offline": "192.168.0.10"}, "192.168.0.20")
    assert called.get("hello")


def test_ping_marks_offline_on_next_call(monkeypatch):
    peer_ip = "192.168.0.20"
    ip_chars = _ip_chars(peer_ip)
    discovery.known_devices.append(ip_chars + "Peer")

    called = {}

    def fake_broadcast():
        called["full"] = True

    monkeypatch.setattr(discovery, "broadcast_full_list", fake_broadcast)
    monkeypatch.setattr(discovery, "choice", lambda peers: peers[0])

    class DummySock:
        def __init__(self):
            self.packets = []

        def sendto(self, data, addr):
            self.packets.append((data, addr))

    discovery.send_sock = DummySock()

    discovery.ping_random_peer()
    assert discovery.pending_ping == discovery.ip_to_bytes(peer_ip)
    discovery.ping_random_peer()

    assert discovery.pending_ping is None
    assert ip_chars not in [d[:4] for d in discovery.known_devices]
    data, addr = discovery.send_sock.packets[1]
    assert addr == ("255.255.255.255", discovery.DISCOVERY_PORT)
    assert loads(data.decode("utf-8")) == {"offline": peer_ip}
    assert called.get("full")


def test_handle_hello_ignores_when_full():
    # Fill the list to the maximum
    for i in range(discovery.MAXIMUM_KNOWN_DEVICES):
        ip = f"192.168.0.{i+1}"
        discovery.known_devices.append(_ip_chars(ip) + "P")
    before = list(discovery.known_devices)
    discovery.handle_message({"hello": True, "name": "Extra"}, "192.168.0.99")
    assert discovery.known_devices == before


def test_broadcast_full_list_packs_payload():
    discovery.known_devices = [_ip_chars("192.168.0.20") + "Peer"]

    packets = []

    class DummySock:
        def sendto(self, data, addr):
            packets.append((data, addr))

    discovery.send_sock = DummySock()
    discovery.broadcast_full_list()
    data, addr = packets[0]
    msg = loads(data.decode("utf-8"))
    parts = msg["full"].split("|")
    assert parts[0] == _ip_chars("192.168.0.10") + "local"
    assert parts[1] == _ip_chars("192.168.0.20") + "Peer"
    assert addr == ("255.255.255.255", discovery.DISCOVERY_PORT)


def test_add_or_update_keeps_sorted():
    discovery._add_or_update(_ip_chars("192.168.0.20"), "A")
    discovery._add_or_update(_ip_chars("192.168.0.5"), "B")
    discovery._add_or_update(_ip_chars("192.168.0.30"), "C")
    ips = [d[:4] for d in discovery.known_devices]
    assert ips == [_ip_chars("192.168.0.5"), _ip_chars("192.168.0.20"), _ip_chars("192.168.0.30")]
