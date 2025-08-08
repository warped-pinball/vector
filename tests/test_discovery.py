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


def test_refresh_known_devices_prunes_and_sorts(monkeypatch):
    ip20 = "".join(chr(b) for b in discovery.ip_to_bytes("192.168.0.20"))
    ip30 = "".join(chr(b) for b in discovery.ip_to_bytes("192.168.0.30"))
    discovery.known_devices.extend([ip20 + "Test", ip30 + "Other"])

    def fake_listen(duration, delay):
        discovery.announce()
        # Unmark self
        for i, dev in enumerate(discovery.known_devices):
            if dev.startswith(discovery.local_ip_chars):
                discovery.known_devices[i] = dev[:4] + chr(ord(dev[4]) & 0x7F) + dev[5:]
                break
        # Only device at ip20 responds
        discovery.handle_message({"name": "Test"}, "192.168.0.20")

    monkeypatch.setattr(discovery, "listen_for", fake_listen)
    monkeypatch.setattr(discovery, "broadcast_discover", lambda: None)
    discovery.refresh_known_devices()
    assert discovery.known_devices == [discovery.self_entry, ip20 + "Test"]


def test_refresh_known_devices_passes_delay(monkeypatch):
    discovery.local_ip_bytes = discovery.ip_to_bytes("192.168.0.20")
    discovery.local_ip_chars = "".join(chr(b) for b in discovery.local_ip_bytes)
    discovery.self_entry = discovery.local_ip_chars + discovery.self_info["name"]
    discovery.known_devices = [
        "".join(chr(b) for b in discovery.ip_to_bytes("192.168.0.10")) + "A",
        discovery.self_entry,
    ]

    captured = {}

    def fake_listen(duration, delay):
        captured["delay"] = delay
        discovery.announce()
        for i, dev in enumerate(discovery.known_devices):
            if dev.startswith(discovery.local_ip_chars):
                discovery.known_devices[i] = dev[:4] + chr(ord(dev[4]) & 0x7F) + dev[5:]
                break

    monkeypatch.setattr(discovery, "listen_for", fake_listen)
    monkeypatch.setattr(discovery, "broadcast_discover", lambda: None)
    discovery.refresh_known_devices()
    assert captured["delay"] == 0.5
