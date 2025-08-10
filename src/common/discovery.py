# Network discovery utilities for Raspberry Pi Pico 2W boards
#
# Devices on the same network coordinate to maintain a shared registry of
# participants.  The board with the lowest IP address becomes the "registry"
# device and is responsible for broadcasting the full list of known peers when
# new devices arrive or when peers are marked offline.

import socket
from enum import IntEnum
from dataclasses import dataclass
from typing import Generator, Iterable, Optional, Tuple
from random import choice


class MessageType(IntEnum):
    """Types of discovery messages."""

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

# Storage for known devices.  Each entry is a string where the first four
# characters are the IP address bytes and the remainder is the game name.
known_devices = []

# Sockets are created lazily
recv_sock = None
send_sock = None

local_ip_bytes = None
local_ip_chars = ""

# Track a single peer we're awaiting a pong from
pending_ping = None

@dataclass
class DiscoveryMessage:
    """Structured discovery message with compact binary encoding."""

    type: MessageType
    name: Optional[str] = None
    peers: Optional[Iterable[Tuple[str, str]]] = None
    ip: Optional[str] = None

    @classmethod
    def hello(cls, name: str) -> "DiscoveryMessage":
        return cls(MessageType.HELLO, name=name)

    @classmethod
    def full(cls, peers: Iterable[Tuple[str, str]]) -> "DiscoveryMessage":
        return cls(MessageType.FULL, peers=peers)

    @classmethod
    def ping(cls) -> "DiscoveryMessage":
        return cls(MessageType.PING)

    @classmethod
    def pong(cls) -> "DiscoveryMessage":
        return cls(MessageType.PONG)

    @classmethod
    def offline(cls, ip: str) -> "DiscoveryMessage":
        return cls(MessageType.OFFLINE, ip=ip)

    # ------------------------------------------------------------------ encoding
    def encode(self) -> bytes:
        if self.type is MessageType.HELLO and self.name is not None:
            name_bytes = self.name[:MAX_NAME_LENGTH].encode("utf-8")
            return bytes([MessageType.HELLO, len(name_bytes)]) + name_bytes

        if self.type is MessageType.FULL and self.peers is not None:
            peers_list = list(self.peers)
            parts = [bytes([MessageType.FULL, len(peers_list)])]
            for ip_chars, name in peers_list:
                ip_part = bytes(ord(c) for c in ip_chars[:4])
                name_bytes = name[:MAX_NAME_LENGTH].encode("utf-8")
                parts.append(ip_part + bytes([len(name_bytes)]) + name_bytes)
            return b"".join(parts)

        if self.type is MessageType.PING:
            return bytes([MessageType.PING])

        if self.type is MessageType.PONG:
            return bytes([MessageType.PONG])

        if self.type is MessageType.OFFLINE and self.ip is not None:
            return bytes([MessageType.OFFLINE]) + ip_to_bytes(self.ip)

        raise ValueError("Incomplete message for encoding")

    # ------------------------------------------------------------------ decoding
    @staticmethod
    def decode(data: bytes) -> Optional["DiscoveryMessage"]:
        if not data:
            return None
        mtype = MessageType(data[0])

        if mtype is MessageType.HELLO:
            if len(data) < 2:
                return None
            name_len = data[1]
            name = data[2 : 2 + name_len].decode("utf-8", "ignore")
            return DiscoveryMessage(MessageType.HELLO, name=name)

        if mtype is MessageType.FULL:
            if len(data) < 2:
                return None
            count = data[1]

            def peer_gen() -> Generator[Tuple[str, str], None, None]:
                offset = 2
                for _ in range(count):
                    if len(data) < offset + 5:
                        return
                    ip_part = data[offset : offset + 4]
                    offset += 4
                    name_len = data[offset]
                    offset += 1
                    name = data[offset : offset + name_len].decode("utf-8", "ignore")
                    offset += name_len
                    ip_chars = "".join(chr(b) for b in ip_part)
                    yield ip_chars, name

            return DiscoveryMessage(MessageType.FULL, peers=peer_gen())

        if mtype is MessageType.PING:
            return DiscoveryMessage(MessageType.PING)

        if mtype is MessageType.PONG:
            return DiscoveryMessage(MessageType.PONG)

        if mtype is MessageType.OFFLINE:
            if len(data) < 5:
                return None
            ip_str = bytes_to_ip(data[1:5])
            return DiscoveryMessage(MessageType.OFFLINE, ip=ip_str)

        return None

def ip_to_bytes(ip_str: str) -> bytes:
    """Convert dotted-quad string to a 4-byte representation."""

    return bytes(int(part) for part in ip_str.split("."))


def bytes_to_ip(ip_bytes: bytes) -> str:
    """Convert 4-byte representation to dotted-quad string."""

    return ".".join(str(b) for b in ip_bytes)


def _get_local_name() -> str:
    """Retrieve this board's game name, truncated to the max length."""

    from SharedState import gdata

    return gdata["GameInfo"]["GameName"][:MAX_NAME_LENGTH]


def setup() -> None:
    """Initialise discovery state for this board."""

    global known_devices, local_ip_bytes, local_ip_chars

    from phew import get_ip_address

    local_ip_bytes = ip_to_bytes(get_ip_address())
    local_ip_chars = "".join(chr(b) for b in local_ip_bytes)
    known_devices = []
    broadcast_hello()


def _send(msg: DiscoveryMessage, addr: tuple = ("255.255.255.255", DISCOVERY_PORT)) -> None:
    print(f"DISCOVERY:Sending message to {addr}: {msg}")

    global send_sock
    if not send_sock:
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:  # pragma: no cover - network errors are non-deterministic
        send_sock.sendto(msg.encode(), addr)
    except Exception:
        pass


def broadcast_hello() -> None:
    """Broadcast that this device has joined the network."""
    _send(DiscoveryMessage.hello(_get_local_name()))


def broadcast_full_list() -> None:
    """Broadcast the full list of known devices."""

    peers = [(local_ip_chars, _get_local_name())] + [(d[:4], d[4:]) for d in known_devices]
    _send(DiscoveryMessage.full(peers))


def registry_ip_bytes() -> bytes:
    # find the minimum known device IP
    global known_devices, local_ip_bytes
    if not known_devices:
        return local_ip_bytes
    return min(bytes(dev[:4]) for dev in known_devices)


def is_registry() -> bool:
    """Return True if this device is the registry (lowest IP) in ``known_devices``."""
    return registry_ip_bytes() == local_ip_bytes


def _add_or_update(ip_chars: str, name: str) -> None:
    """Insert or update a peer keeping ``known_devices`` sorted."""

    if ip_chars == local_ip_chars:
        return

    entry = ip_chars + name
    for i, dev in enumerate(known_devices):
        peer_ip = dev[:4]
        if peer_ip == ip_chars:
            known_devices[i] = entry
            return
        if peer_ip > ip_chars:
            if len(known_devices) < MAXIMUM_KNOWN_DEVICES:
                known_devices.insert(i, entry)
            return
    if len(known_devices) < MAXIMUM_KNOWN_DEVICES:
        known_devices.append(entry)


def registry_should_broadcast():
    global pending_ping
    if len(known_devices) > 0:
        if is_registry():
            broadcast_full_list()
        else:
            pending_ping = registry_ip_bytes()


def handle_message(msg: DiscoveryMessage, ip_str: str) -> None:
    """Handle an incoming message from ``ip_str``."""
    print(f"DISCOVERY: Received message from {ip_str}: {msg}")
    global pending_ping, known_devices, local_ip_bytes, local_ip_chars

    ip_bytes = ip_to_bytes(ip_str)
    ip_chars = "".join(chr(b) for b in ip_bytes)

    if msg.type is MessageType.PING:
        _send(DiscoveryMessage.pong(), (ip_str, DISCOVERY_PORT))
        if ip_chars not in [d[:4] for d in known_devices]:
            broadcast_hello()
        return

    if msg.type is MessageType.PONG:
        if pending_ping == ip_bytes:
            pending_ping = None
        return

    if msg.type is MessageType.OFFLINE and msg.ip is not None:
        off_ip = msg.ip
        if off_ip == bytes_to_ip(local_ip_bytes):
            broadcast_hello()
            return
        off_chars = "".join(chr(b) for b in ip_to_bytes(off_ip))
        known_devices = [d for d in known_devices if not d.startswith(off_chars)]
        registry_should_broadcast()
        return

    if msg.type is MessageType.HELLO and msg.name is not None:
        name = msg.name[:MAX_NAME_LENGTH]
        _add_or_update(ip_chars, name)
        registry_should_broadcast()

    if msg.type is MessageType.FULL and msg.peers is not None:
        found_self = False
        for ip_chars_peer, name in msg.peers:
            name = name[:MAX_NAME_LENGTH]
            if ip_chars_peer == local_ip_chars:
                found_self = True
            _add_or_update(ip_chars_peer, name)
        if not found_self and len(known_devices) < MAXIMUM_KNOWN_DEVICES:
            broadcast_hello()
        return


def _recv():
    """Receive a discovery packet if available."""

    global recv_sock
    if not recv_sock:
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        recv_sock.bind(("0.0.0.0", DISCOVERY_PORT))
        recv_sock.settimeout(0)

    try:
        data, addr = recv_sock.recvfrom(1024)
    except OSError:
        return None, None
    msg = DiscoveryMessage.decode(data)
    return (msg, addr) if msg else (None, None)


def listen() -> None:
    """Check for any incoming discovery packets.  Non-blocking."""

    while True:
        msg, addr = _recv()
        if not msg:
            return
        handle_message(msg, addr[0])


def get_peer_map() -> dict:
    """Return mapping of known devices keyed by IP string."""

    peers = {bytes_to_ip(local_ip_bytes): {"name": _get_local_name(), "self": True}}
    for dev in known_devices:
        ip_chars, name = dev[:4], dev[4:]
        ip = bytes_to_ip(bytes(ord(c) for c in ip_chars))
        peers[ip] = {"name": name, "self": False}
    return peers


def ping_random_peer() -> None:
    """Ping a random peer and mark previous one offline if it didn't respond."""

    global pending_ping, known_devices, local_ip_bytes

    peers = [d for d in known_devices if not d.startswith(local_ip_chars)]

    # If a previous ping is still pending, mark that peer offline
    if pending_ping and pending_ping != local_ip_bytes:
        off_chars = "".join(chr(b) for b in pending_ping)
        known_devices = [d for d in known_devices if not d.startswith(off_chars)]
        ip_str = bytes_to_ip(pending_ping)
        _send(DiscoveryMessage.offline(ip_str))
        if is_registry():
            broadcast_full_list()
        pending_ping = None
        peers = [d for d in known_devices if not d.startswith(local_ip_chars)]
    if not peers:
        broadcast_hello()
    target = choice(peers)
    ip_bytes = bytes(ord(c) for c in target[:4])
    _send(DiscoveryMessage.ping(), (bytes_to_ip(ip_bytes), DISCOVERY_PORT))
    pending_ping = ip_bytes
