import sys
import types
from pathlib import Path

sys.modules.setdefault("ubinascii", types.SimpleNamespace(a2b_base64=lambda s: b"", b2a_base64=lambda b: b""))
sys.modules.setdefault("ujson", types.SimpleNamespace(loads=lambda s: [], dumps=lambda obj: ""))
sys.modules.setdefault("backend", types.SimpleNamespace(hmac_sha256=lambda secret, msg: b""))
sys.modules.setdefault("curve25519", types.SimpleNamespace(generate_x25519_keypair=lambda: (types.SimpleNamespace(exchange=lambda x: b""), b"")))
rsa_key = types.ModuleType("key")
rsa_key.PublicKey = lambda n, e: None
rsa_pkcs1 = types.ModuleType("pkcs1")
rsa_pkcs1.verify = lambda body, sig, key: "SHA-256"
sys.modules.setdefault("rsa.key", rsa_key)
sys.modules.setdefault("rsa.pkcs1", rsa_pkcs1)
sys.modules.setdefault("SPI_DataStore", types.SimpleNamespace(read_record=lambda *a, **k: {}))
sys.modules.setdefault("mqtt_client", types.SimpleNamespace(connect=lambda url: None))

sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))
import common.origin as origin  # noqa: E402


class DummyMQTT:
    def __init__(self, recv_side_effect):
        self.recv_side_effect = recv_side_effect
        self.closed = False

    def recv(self):
        if isinstance(self.recv_side_effect, Exception):
            raise self.recv_side_effect
        return self.recv_side_effect

    def close(self):
        self.closed = True

    def send(self, msg):
        pass


def test_recv_reconnects_on_empty(monkeypatch):
    mqtt_instances = []

    def fake_connect(url):
        mqtt = DummyMQTT(None)
        mqtt_instances.append(mqtt)
        return mqtt

    monkeypatch.setattr(origin, "connect", fake_connect)

    origin.mqtt = None
    origin.recv()

    assert len(mqtt_instances) == 2
    assert not mqtt_instances[0].closed
    assert origin.mqtt is mqtt_instances[1]


def test_recv_reconnects_on_oserror(monkeypatch):
    mqtt_instances = []

    def fake_connect(url):
        mqtt = DummyMQTT(OSError())
        mqtt_instances.append(mqtt)
        return mqtt

    monkeypatch.setattr(origin, "connect", fake_connect)

    origin.mqtt = None
    origin.recv()

    assert len(mqtt_instances) == 2
    assert not mqtt_instances[0].closed
    assert origin.mqtt is mqtt_instances[1]
