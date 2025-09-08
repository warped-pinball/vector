import asyncio

try:
    from mqtt_as import MQTTClient
    from mqtt_as import config as MQTT_CONFIG
except ImportError:  # pragma: no cover - runtime on microcontroller
    MQTTClient = None
    MQTT_CONFIG = {}


class MQTTConnection:
    """Synchronous wrapper around micropython-mqtt's MQTTClient."""

    def __init__(self, loop, topic):
        self._loop = loop
        self._topic = topic if isinstance(topic, bytes) else topic.encode()
        self._client = None
        self._last = None

    # Callback invoked by MQTTClient when a subscribed message arrives
    def _cb(self, topic, msg, *_):
        if bytes(topic) == self._topic:
            self._last = msg

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def set_client(self, client):
        self._client = client

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        self._run(self._client.publish(self._topic, data))

    def recv(self):
        self._last = None

        async def _wait():
            while self._last is None:
                await self._client.wait_msg()
            msg = self._last
            self._last = None
            return msg

        return self._run(_wait())

    def close(self):
        try:
            self._run(self._client.disconnect())
        except Exception:
            pass


def connect(url):
    """Connect to an MQTT broker using a URL of the form mqtt://host:port/topic"""
    if not url.startswith("mqtt://"):
        raise ValueError("MQTT URL must start with mqtt://")

    url_no_scheme = url[7:]
    if "/" in url_no_scheme:
        host_part, topic = url_no_scheme.split("/", 1)
    else:
        host_part, topic = url_no_scheme, "origin"

    if ":" in host_part:
        host, port = host_part.split(":", 1)
        port = int(port)
    else:
        host, port = host_part, 1883

    if MQTTClient is None:
        raise RuntimeError("mqtt_as module is required for MQTT connections")

    loop = asyncio.get_event_loop()
    conn = MQTTConnection(loop, topic)
    cfg = MQTT_CONFIG.copy()
    cfg.update({"server": host, "port": port, "subs_cb": conn._cb})

    client = MQTTClient(cfg)
    conn.set_client(client)
    conn._run(client.connect())
    conn._run(client.subscribe(topic, 0))
    return conn
