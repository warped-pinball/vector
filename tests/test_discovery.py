import os
import sys
import time

# Ensure we can import the discovery module
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from src.common import discovery


def setup_function():
    discovery.known_devices = {}
    discovery.recv_sock = None
    discovery.send_sock = None
    discovery.last_discover_time = 0
    discovery.local_ip_bytes = discovery.ip_to_bytes("192.168.0.10")
    discovery.known_devices[discovery.local_ip_bytes] = {
        "name": "local",
        "version": "1",
        "self": True,
    }


def test_handle_message_stores_ip_as_bytes():
    discovery.handle_message({"name": "Test", "version": "1"}, "192.168.0.20")
    keys = [k for k in discovery.known_devices.keys() if k != discovery.local_ip_bytes]
    assert len(keys) == 1
    assert isinstance(keys[0], bytes) and len(keys[0]) == 4


def test_handle_message_discover_triggers_intro(monkeypatch):
    sent = {}

    def fake_intro(ip):
        sent["ip"] = ip

    monkeypatch.setattr(discovery, "send_intro", fake_intro)
    discovery.handle_message({"discover": True}, "192.168.0.30")
    assert sent["ip"] == discovery.ip_to_bytes("192.168.0.30")


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

