import os
import sys
import time

from ujson import loads

# Ensure we can import the discovery module
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


def test_handle_message_stores_ip_in_first_four_chars():
    discovery.handle_message({"name": "Test"}, "192.168.0.20")
    devices = [d for d in discovery.known_devices if not d.startswith(discovery.local_ip_chars)]
    assert len(devices) == 1
    entry = devices[0]
    assert [ord(c) for c in entry[:4]] == [192, 168, 0, 20]
    assert entry[4:] == "Test"


def test_handle_message_discover_triggers_intro(monkeypatch):
    sent = {}
    refreshed = {}

    def fake_intro(ip):
        sent["ip"] = ip

    def fake_refresh():
        refreshed["called"] = True

    monkeypatch.setattr(discovery, "send_intro", fake_intro)
    monkeypatch.setattr(discovery, "refresh_known_devices", fake_refresh)
    discovery.handle_message({"discover": True}, "192.168.0.30")
    assert sent["ip"] == discovery.ip_to_bytes("192.168.0.30")
    assert refreshed.get("called")


def test_maybe_discover_resends_after_interval():
    class DummySock:
        def __init__(self):
            self.sent = []

        def setsockopt(self, *args, **kwargs):
            pass

        def sendto(self, data, addr):
            self.sent.append((data, addr))

    dummy = DummySock()
    discovery.send_sock = dummy
    discovery.last_discover_time = time.time() - (discovery.DISCOVER_REFRESH + 1)
    discovery.maybe_discover()
    assert dummy.sent  # Should have broadcasted

    dummy.sent.clear()
    discovery.last_discover_time = time.time()
    discovery.maybe_discover()
    assert not dummy.sent


def test_refresh_known_devices_resets_known_devices(monkeypatch):
    discovery.known_devices.append("".join(chr(b) for b in discovery.ip_to_bytes("192.168.0.20")) + "Test")
    called = {}

    def fake_broadcast():
        called["done"] = True

    monkeypatch.setattr(discovery, "broadcast_discover", fake_broadcast)
    discovery.refresh_known_devices()
    assert discovery.known_devices == [discovery.self_entry]
    assert called.get("done")


def test_handle_message_truncates_long_name():
    long_name = "X" * (discovery.MAX_NAME_LENGTH + 5)
    discovery.handle_message({"name": long_name}, "192.168.0.21")
    ip_chars = "".join(chr(b) for b in discovery.ip_to_bytes("192.168.0.21"))
    stored = [d for d in discovery.known_devices if d.startswith(ip_chars)][0]
    assert len(stored[4:]) == discovery.MAX_NAME_LENGTH


def test_announce_broadcasts_self_info():
    class DummySock:
        def __init__(self):
            self.sent = []

        def setsockopt(self, *args, **kwargs):
            pass

        def sendto(self, data, addr):
            self.sent.append((data, addr))

    dummy = DummySock()
    discovery.send_sock = dummy
    discovery.announce()
    assert dummy.sent
    data, addr = dummy.sent[0]
    assert addr == ("255.255.255.255", discovery.DISCOVERY_PORT)
    payload = loads(data.decode("utf-8"))
    assert payload["name"] == discovery.self_info["name"]
    assert payload["version"] == discovery.self_info["version"]
