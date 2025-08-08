import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from src.common import discovery  # noqa: E402


def setup_function():
    discovery.known_devices = []
    discovery.recv_sock = None
    discovery.send_sock = None
    discovery.last_discover_time = 0
    discovery.local_ip_bytes = discovery.ip_to_bytes("192.168.0.10")
    discovery.local_ip_chars = "".join(chr(b) for b in discovery.local_ip_bytes)
    discovery.self_info = {
        "name": "local",
        "version": "1",
        "self": True,
    }
    discovery.self_entry = discovery.local_ip_chars + discovery.self_info["name"]
    discovery.known_devices.append(discovery.self_entry)


def _ip_chars(ip: str) -> str:
    return "".join(chr(b) for b in discovery.ip_to_bytes(ip))


def test_is_registry_lowest_ip():
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
    msg = {"full": [{"ip": "192.168.0.20", "name": "Peer"}]}
    discovery.handle_message(msg, "192.168.0.20")
    assert called.get("hello")
    assert discovery.known_devices == [
        discovery.self_entry,
        _ip_chars("192.168.0.20") + "Peer",
    ]


def test_handle_offline_promotes_registry(monkeypatch):
    discovery.local_ip_bytes = discovery.ip_to_bytes("192.168.0.20")
    discovery.local_ip_chars = "".join(chr(b) for b in discovery.local_ip_bytes)
    discovery.self_entry = discovery.local_ip_chars + discovery.self_info["name"]
    ip10 = _ip_chars("192.168.0.10")
    discovery.known_devices = [ip10 + "A", discovery.self_entry, _ip_chars("192.168.0.30") + "B"]

    called = {}

    def fake_broadcast():
        called["full"] = True

    monkeypatch.setattr(discovery, "broadcast_full_list", fake_broadcast)
    discovery.handle_message({"offline": "192.168.0.10"}, "192.168.0.30")
    assert called.get("full")
    assert all(not d.startswith(ip10) for d in discovery.known_devices)
