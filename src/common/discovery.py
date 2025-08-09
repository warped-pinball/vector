# Network discovery utilities for Raspberry Pi Pico 2W boards
#
# Devices on the same network coordinate to maintain a shared registry of
# participants.  The board with the lowest IP address becomes the "registry"
# device and is responsible for broadcasting the full list of known peers when
# new devices arrive or when peers are marked offline.

import socket
from random import choice
from time import sleep, time

from ujson import dumps, loads

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

last_discover_time = 0
local_ip_bytes = None
local_ip_chars = ""

# Track a single peer we're awaiting a pong from
pending_ping = None


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
    refresh_known_devices()


def _ensure_send_sock() -> None:
    global send_sock
    if not send_sock:
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)


def broadcast_hello() -> None:
    """Broadcast that this device has joined the network."""
    _ensure_send_sock()
    msg = {"hello": True, "name": _get_local_name()}
    try:
        send_sock.sendto(dumps(msg).encode("utf-8"), ("255.255.255.255", DISCOVERY_PORT))
    except Exception as e:  # pragma: no cover - network errors are non-deterministic
        print("Failed to send hello:", e)


def broadcast_full_list() -> None:
    """Broadcast the full list of known devices."""

    _ensure_send_sock()
    payload = "|".join([local_ip_chars + _get_local_name()] + known_devices)
    msg = {"full": payload}
    try:
        send_sock.sendto(dumps(msg).encode("utf-8"), ("255.255.255.255", DISCOVERY_PORT))
    except Exception as e:  # pragma: no cover - network errors are non-deterministic
        print("Failed to broadcast full list:", e)


def send_ping(target_ip: bytes) -> None:
    """Send a direct ping to ``target_ip``."""

    _ensure_send_sock()
    try:
        send_sock.sendto(dumps({"ping": True}).encode("utf-8"), (bytes_to_ip(target_ip), DISCOVERY_PORT))
    except Exception as e:  # pragma: no cover - network errors are non-deterministic
        print("Failed to send ping:", e)


def is_registry() -> bool:
    """Return True if this device has the lowest IP in ``known_devices``."""

    for dev in known_devices:
        peer_bytes = bytes(ord(c) for c in dev[:4])
        if peer_bytes < local_ip_bytes:
            return False
    return True


def _add_or_update(ip_chars: str, name: str) -> None:
    """Insert or update a peer keeping ``known_devices`` sorted."""

    entry = ip_chars + name
    lo, hi = 0, len(known_devices)
    while lo < hi:
        mid = (lo + hi) // 2
        peer_ip = known_devices[mid][:4]
        if peer_ip < ip_chars:
            lo = mid + 1
        elif peer_ip > ip_chars:
            hi = mid
        else:
            known_devices[mid] = entry
            return
    if len(known_devices) >= MAXIMUM_KNOWN_DEVICES:
        return
    known_devices.insert(lo, entry)


def handle_message(msg: dict, ip_str: str) -> None:
    """Handle an incoming message from ``ip_str``."""

    global known_devices, last_discover_time, pending_ping

    last_discover_time = time()
    ip_bytes = ip_to_bytes(ip_str)
    ip_chars = "".join(chr(b) for b in ip_bytes)

    if msg.get("ping"):
        _ensure_send_sock()
        try:
            send_sock.sendto(dumps({"pong": True}).encode("utf-8"), (ip_str, DISCOVERY_PORT))
        except Exception:  # pragma: no cover - network errors are non-deterministic
            pass
        return

    if msg.get("pong"):
        if pending_ping == ip_bytes:
            pending_ping = None
        return

    if msg.get("offline"):
        off_ip = msg["offline"]
        off_chars = "".join(chr(b) for b in ip_to_bytes(off_ip))
        known_devices = [d for d in known_devices if not d.startswith(off_chars)]
        if is_registry():
            broadcast_full_list()
        return

    if msg.get("hello"):
        name = str(msg.get("name", ""))[:MAX_NAME_LENGTH]
        _add_or_update(ip_chars, name)
        if is_registry() and ip_chars != local_ip_chars:
            broadcast_full_list()
        return

    if msg.get("full"):
        peers_str = msg["full"]
        if not isinstance(peers_str, str):
            return
        peers = [p for p in peers_str.split("|") if p]
        new_list = []
        found_self = False
        for peer in peers:
            if len(peer) < 4:
                continue
            ip_chars_peer = peer[:4]
            name = peer[4:][:MAX_NAME_LENGTH]
            if ip_chars_peer == local_ip_chars:
                found_self = True
            else:
                new_list.append(ip_chars_peer + name)
        new_list.sort()
        known_devices = new_list[:MAXIMUM_KNOWN_DEVICES]
        if not found_self and len(known_devices) < MAXIMUM_KNOWN_DEVICES:
            broadcast_hello()
        return

    if "name" in msg:  # Backwards compatibility for simple announcements
        name = str(msg["name"])[:MAX_NAME_LENGTH]
        _add_or_update(ip_chars, name)


def listen() -> None:
    """Check for any incoming discovery packets.  Non-blocking."""

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
            msg = loads(data.decode("utf-8"))
        except ValueError:
            continue
        handle_message(msg, addr[0])


def refresh_known_devices() -> None:
    """Rebuild the known devices list by syncing with the network."""

    global known_devices, last_discover_time, pending_ping
    known_devices = []
    pending_ping = None
    broadcast_hello()
    last_discover_time = time()
    end = time() + 1.0
    while time() < end:
        listen()
        sleep(0.05)
    if is_registry():
        broadcast_full_list()


def maybe_discover() -> None:
    """Refresh the device list if the refresh interval has elapsed."""

    if (time() - last_discover_time) >= DISCOVER_REFRESH:
        refresh_known_devices()


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

    global pending_ping, known_devices

    peers = [d for d in known_devices if not d.startswith(local_ip_chars)]

    # If a previous ping is still pending, mark that peer offline
    if pending_ping:
        off_chars = "".join(chr(b) for b in pending_ping)
        known_devices = [d for d in known_devices if not d.startswith(off_chars)]
        ip_str = bytes_to_ip(pending_ping)
        _ensure_send_sock()
        try:
            send_sock.sendto(dumps({"offline": ip_str}).encode("utf-8"), ("255.255.255.255", DISCOVERY_PORT))
        except Exception:  # pragma: no cover - network errors are non-deterministic
            pass
        if is_registry():
            broadcast_full_list()
        pending_ping = None
        peers = [d for d in known_devices if not d.startswith(local_ip_chars)]
    if not peers:
        return
    target = choice(peers)
    ip_bytes = bytes(ord(c) for c in target[:4])
    send_ping(ip_bytes)
    pending_ping = ip_bytes
