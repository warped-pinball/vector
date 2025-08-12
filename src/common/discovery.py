# Network discovery utilities for Raspberry Pi Pico 2W boards
#
# Devices on the same network coordinate to maintain a shared registry of
# participants.  The board with the lowest IP address becomes the "registry"
# device and is responsible for broadcasting the full list of known peers when
# new devices arrive or when peers are marked offline.

import socket
from random import choice

try:  # MicroPython may lack the ``typing`` module
    from typing import Generator, Iterable, Optional, Tuple
except ImportError:  # pragma: no cover - fallback for MicroPython
    Generator = Iterable = Optional = Tuple = None  # type: ignore


class MessageType:
    """Types of discovery messages represented as integer constants."""

    HELLO = 1
    FULL = 2
    PING = 3
    PONG = 4
    OFFLINE = 5


# UDP port used for discovery traffic
DISCOVERY_PORT = 37020

# Refresh known devices every 10 minutes
DISCOVER_REFRESH = 600

# Limit list sizes and names to avoid memory abuse
MAXIMUM_KNOWN_DEVICES = 50
MAX_NAME_LENGTH = 32

# Storage for known devices.  Each entry is a bytes object where the first four
# bytes are the IP address bytes and the remainder is the game name.
known_devices = []

# Sockets are created lazily
recv_sock = None
send_sock = None

# Track a single peer we're awaiting a pong from
pending_ping = None


class DiscoveryMessage:
    """Structured discovery message with compact binary encoding."""

    __slots__ = ("type", "name", "peers", "ip")

    def __init__(self, mtype: int, name: Optional[bytes] = None, peers: Optional[Iterable[Tuple[str, str]]] = None, ip: Optional[bytes] = None) -> None:
        self.type = mtype
        self.name = name
        self.peers = peers
        self.ip = ip

    @classmethod
    def hello(cls, name: bytes) -> "DiscoveryMessage":
        return cls(MessageType.HELLO, name=name)

    @classmethod
    def full(cls, peers: Iterable[bytes]) -> "DiscoveryMessage":
        return cls(MessageType.FULL, peers=peers)

    @classmethod
    def ping(cls) -> "DiscoveryMessage":
        return cls(MessageType.PING)

    @classmethod
    def pong(cls) -> "DiscoveryMessage":
        return cls(MessageType.PONG)

    @classmethod
    def offline(cls, ip: bytes) -> "DiscoveryMessage":
        return cls(MessageType.OFFLINE, ip=ip)

    # ------------------------------------------------------------------ display
    def __repr__(self) -> str:  # pragma: no cover - trivial
        tname = {
            MessageType.HELLO: "HELLO",
            MessageType.FULL: "FULL",
            MessageType.PING: "PING",
            MessageType.PONG: "PONG",
            MessageType.OFFLINE: "OFFLINE",
        }.get(self.type, str(self.type))

        if self.type == MessageType.HELLO and self.name is not None:
            return f"<DiscoveryMessage {tname} name={self.name.decode('utf-8', 'ignore')}>"
        if self.type == MessageType.FULL:
            return f"<DiscoveryMessage {tname}>"
        if self.type == MessageType.OFFLINE and self.ip is not None:
            return f"<DiscoveryMessage {tname} ip={bytes_to_ip(self.ip)}>"
        return f"<DiscoveryMessage {tname}>"

    # ------------------------------------------------------------------ encoding
    def encode(self) -> bytes:
        if self.type == MessageType.HELLO and self.name is not None:
            name_bytes = self.name[:MAX_NAME_LENGTH]
            return bytes([MessageType.HELLO, len(name_bytes)]) + name_bytes

        if self.type == MessageType.FULL and self.peers is not None:
            peers_list = list(self.peers)
            parts = [bytes([MessageType.FULL, len(peers_list)])]
            for ip_bytes, name in peers_list:
                name_bytes = name[:MAX_NAME_LENGTH]
                parts.append(ip_bytes + bytes([len(name_bytes)]) + name_bytes)
            return b"".join(parts)

        if self.type == MessageType.PING:
            return bytes([MessageType.PING])

        if self.type == MessageType.PONG:
            return bytes([MessageType.PONG])

        if self.type == MessageType.OFFLINE and self.ip is not None:
            return bytes([MessageType.OFFLINE]) + self.ip

        raise ValueError("Incomplete message for encoding")

    # ------------------------------------------------------------------ decoding
    @staticmethod
    def decode(data: bytes):
        if not data:
            return None
        mtype = data[0]

        if mtype == MessageType.HELLO:
            if len(data) < 2:
                return None
            name_len = data[1]
            name = data[2 : 2 + name_len]
            return DiscoveryMessage(MessageType.HELLO, name=name)

        if mtype == MessageType.FULL:
            print(f"Decoding FULL message with length {len(data)}")
            print(f"Data: {data}")
            if len(data) < 2:
                return None
            count = data[1]

            def peer_gen():
                offset = 2
                for _ in range(count):
                    if len(data) < offset + 5:
                        return
                    ip_part = data[offset : offset + 4]
                    offset += 4
                    name_len = data[offset]
                    offset += 1
                    name = data[offset : offset + name_len]
                    offset += name_len
                    yield ip_part, name

            return DiscoveryMessage(MessageType.FULL, peers=peer_gen())

        if mtype == MessageType.PING:
            return DiscoveryMessage(MessageType.PING)

        if mtype == MessageType.PONG:
            return DiscoveryMessage(MessageType.PONG)

        if mtype == MessageType.OFFLINE:
            if len(data) < 5:
                return None
            return DiscoveryMessage(MessageType.OFFLINE, ip=data[1:5])

        raise ValueError(f"Unknown message type {mtype} in data: {data}")


def ip_to_bytes(ip_str: str) -> bytes:
    return bytes(int(part) for part in ip_str.split("."))


def bytes_to_ip(ip_bytes: bytes) -> str:
    return ".".join(str(b) for b in ip_bytes)


def _get_local_ip_bytes() -> bytes:
    from phew import get_ip_address

    return ip_to_bytes(get_ip_address())


def _get_local_name_bytes() -> bytes:
    """Retrieve this board's game name, truncated to the max length."""
    from SharedState import gdata

    str_name = gdata["GameInfo"]["GameName"][:MAX_NAME_LENGTH]

    return str_name.encode("utf-8")


def _send(msg: DiscoveryMessage, addr: tuple = ("255.255.255.255", DISCOVERY_PORT)) -> None:
    print(f"DISCOVERY:Sending message to {addr}: {msg}")

    global send_sock
    if not send_sock:
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    send_sock.sendto(msg.encode(), addr)


def broadcast_hello() -> None:
    """Broadcast that this device has joined the network."""
    _send(DiscoveryMessage.hello(_get_local_name_bytes()))


def broadcast_full_list() -> None:
    """Broadcast the full list of known devices."""
    global known_devices
    local_ip_bytes = _get_local_ip_bytes()
    peers = [(local_ip_bytes, _get_local_name_bytes())] + [(d[:4], d[4:]) for d in known_devices]
    _send(DiscoveryMessage.full(peers))


def registry_ip_bytes() -> bytes:
    # find the minimum known device IP
    global known_devices
    if not known_devices:
        return _get_local_ip_bytes()

    # get the lowest IP address from known devices
    return min(d[:4] for d in known_devices + [_get_local_ip_bytes()])


def is_registry() -> bool:
    """Return True if this device is the registry (lowest IP) in ``known_devices``."""
    return registry_ip_bytes() == _get_local_ip_bytes()


def _add_or_update(ip_bytes: bytes, name: str) -> None:
    """Insert or update a peer keeping ``known_devices`` sorted."""
    global known_devices
    print(f"DISCOVERY: Adding/updating device {bytes_to_ip(ip_bytes)} with name {name.decode('utf-8', 'ignore')}")

    if ip_bytes == _get_local_ip_bytes():
        return

    entry = ip_bytes + name
    for i, dev in enumerate(known_devices):
        peer_ip = dev[:4]
        if peer_ip == ip_bytes:
            known_devices[i] = entry
            return
        if peer_ip > ip_bytes:
            if len(known_devices) < MAXIMUM_KNOWN_DEVICES:
                known_devices.insert(i, entry)
            return
    if len(known_devices) < MAXIMUM_KNOWN_DEVICES:
        known_devices.append(entry)


def registry_should_broadcast():
    # global pending_ping
    if is_registry():
        broadcast_full_list()
    else:
        print("DISCOVERY: The registry should broadcast, but I am not the registry.")
    # elif len(known_devices) > 0:
    #     pending_ping = registry_ip_bytes()


def handle_message(msg: DiscoveryMessage, ip_str: str) -> None:
    """Handle an incoming message from ``ip_str``."""
    print(f"DISCOVERY: Received message from {ip_str}: {msg}")
    global pending_ping, known_devices

    ip_bytes = ip_to_bytes(ip_str)

    if pending_ping == ip_bytes:
        pending_ping = None

    if msg.type == MessageType.HELLO and msg.name is not None:
        name = msg.name[:MAX_NAME_LENGTH]
        _add_or_update(ip_bytes, name)
        registry_should_broadcast()
    elif msg.type == MessageType.OFFLINE and msg.ip is not None:
        # if someone is saying I'm offline, reintroduce myself
        off_ip = msg.ip
        if off_ip == _get_local_ip_bytes():
            broadcast_hello()
        else:
            # remove the offline device from the known devices list
            # known_devices = [d for d in known_devices if not d.startswith(off_ip)]

            # ping the supposedly offline device
            _send(DiscoveryMessage.ping(), (bytes_to_ip(off_ip), DISCOVERY_PORT))
            pending_ping = off_ip

        # expect the registry to re-broadcast the full list
        registry_should_broadcast()
        return
    elif msg.type == MessageType.FULL and msg.peers is not None:
        found_self = False
        for ip_bytes_peer, name in msg.peers:
            name = name[:MAX_NAME_LENGTH]
            if ip_bytes_peer == _get_local_ip_bytes():
                found_self = True
            _add_or_update(ip_bytes_peer, name)
        if not found_self and len(known_devices) < MAXIMUM_KNOWN_DEVICES:
            broadcast_hello()
        return
    elif ip_bytes not in [d[:4] for d in known_devices]:
        # if we don't know this sender, send a hello
        if is_registry():
            broadcast_full_list()
        else:
            broadcast_hello()

    if msg.type == MessageType.PING:
        _send(DiscoveryMessage.pong(), (ip_str, DISCOVERY_PORT))
        return

    # if msg.type == MessageType.PONG:
    #     if pending_ping == ip_bytes:
    #         pending_ping = None
    #     return


def listen() -> None:
    """Check for any incoming discovery packets. Non-blocking."""

    global recv_sock
    if not recv_sock:
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        recv_sock.bind(("0.0.0.0", DISCOVERY_PORT))
        recv_sock.settimeout(0)

    while True:
        try:
            data, addr = recv_sock.recvfrom(1024)
        except OSError:
            return

        try:
            msg = DiscoveryMessage.decode(data)
            if msg:
                handle_message(msg, addr[0])
        except Exception as main_e:
            # fall back to parsing json
            try:
                from json import loads

                msg = loads(data)
                if "name" in msg:
                    _add_or_update(ip_to_bytes(addr[0]), msg["name"].encode("utf-8", "ignore"))
                    global pending_ping
                    if pending_ping == ip_to_bytes(addr[0]):
                        pending_ping = None
            except Exception as fallback_e:
                print(f"DISCOVERY: Error decoding message {main_e} tried fallback: {fallback_e}")


def get_peer_map() -> dict:
    """Return mapping of known devices keyed by IP string."""
    global known_devices

    peers = {bytes_to_ip(_get_local_ip_bytes()): {"name": _get_local_name_bytes(), "self": True}}
    for dev in known_devices:
        ip_bytes, name = dev[:4], dev[4:]
        ip = bytes_to_ip(ip_bytes)
        peers[ip] = {"name": name.decode("utf-8", "ignore"), "self": False}
    return peers


def ping_random_peer() -> None:
    """Ping a random peer and mark previous one offline if it didn't respond."""

    global pending_ping, known_devices

    # If a previous ping is still pending, mark that peer offline
    if pending_ping and pending_ping != _get_local_ip_bytes():
        _send(DiscoveryMessage.offline(pending_ping))
        known_devices = [d for d in known_devices if not d.startswith(pending_ping)]
        if is_registry():
            broadcast_full_list()
        pending_ping = None

    # if we have no peers introduce myself to the void
    if len(known_devices) == 0:
        print("No known devices to ping.")
        pending_ping = None
        broadcast_hello()
        return

    ip_bytes = choice(known_devices)[:4]
    _send(DiscoveryMessage.ping(), (bytes_to_ip(ip_bytes), DISCOVERY_PORT))
    pending_ping = ip_bytes
