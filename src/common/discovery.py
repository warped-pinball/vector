# Network discovery utilities for Raspberry Pi Pico 2W boards
# Implements a discovery request on boot and periodic refreshes.

from time import time
import socket
from ujson import dumps, loads

# The UDP port we will send/receive on
DISCOVERY_PORT = 37020
DEVICE_TIMEOUT = 60  # seconds before a device is considered gone
DISCOVER_REFRESH = 600  # send a new discovery request every 10 minutes
MAXIMUM_KNOWN_DEVICES = 10  # limit number of tracked devices

# Known devices keyed by 4 byte IP representation
known_devices = {}
recv_sock = None
send_sock = None
last_discover_time = 0
local_ip_bytes = None


def ip_to_bytes(ip_str: str) -> bytes:
    """Convert dotted-quad string to 4 byte representation."""
    return socket.inet_aton(ip_str)


def bytes_to_ip(ip_bytes: bytes) -> str:
    """Convert 4 byte IP representation back to dotted-quad string."""
    return socket.inet_ntoa(ip_bytes)


def setup() -> None:
    """Initialise discovery state for this board."""
    global known_devices, local_ip_bytes

    from phew import get_ip_address
    from SharedState import gdata
    from systemConfig import SystemVersion

    local_ip_bytes = ip_to_bytes(get_ip_address())
    known_devices[local_ip_bytes] = {
        "name": gdata["GameInfo"]["GameName"],
        "version": SystemVersion,
        "self": True,
    }
    broadcast_discover()


def send_intro(target_ip: bytes) -> None:
    """Send our device information directly to ``target_ip``."""
    global send_sock

    from SharedState import gdata
    from systemConfig import SystemVersion

    if not send_sock:
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    msg = {"version": SystemVersion, "name": gdata["GameInfo"]["GameName"]}
    try:
        send_sock.sendto(dumps(msg).encode("utf-8"), (bytes_to_ip(target_ip), DISCOVERY_PORT))
    except Exception as e:  # pragma: no cover - network errors are non-deterministic
        print("Failed to send intro:", e)


def broadcast_discover() -> None:
    """Broadcast a discovery request to the local network."""
    global send_sock, last_discover_time

    if not send_sock:
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        send_sock.sendto(dumps({"discover": True}).encode("utf-8"), ("255.255.255.255", DISCOVERY_PORT))
    except Exception as e:  # pragma: no cover - network errors are non-deterministic
        print("Failed to send discovery request:", e)
    last_discover_time = time()
    prune_known_devices()


def handle_message(msg: dict, ip_str: str) -> None:
    """Handle an incoming message from ``ip_str``."""
    global known_devices

    ip_bytes = ip_to_bytes(ip_str)

    if msg.get("discover"):
        send_intro(ip_bytes)
        return

    if "name" in msg and "version" in msg:
        known_devices[ip_bytes] = {
            "version": msg["version"],
            "last_seen": time(),
            "name": msg["name"],
        }
        enforce_limit()
        debug_known_devices()


def listen() -> None:
    """Check for any incoming discovery or intro packets. Non-blocking."""
    global recv_sock

    if not recv_sock:
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        recv_sock.bind(("0.0.0.0", DISCOVERY_PORT))
        recv_sock.settimeout(0)  # Non-blocking

    while True:
        try:
            data, addr = recv_sock.recvfrom(1024)
        except OSError:
            prune_known_devices()
            return

        try:
            msg = loads(data.decode("utf-8"))
        except ValueError:
            continue

        handle_message(msg, addr[0])


def maybe_discover() -> None:
    """Broadcast a discovery request if our refresh interval has elapsed."""
    if (time() - last_discover_time) >= DISCOVER_REFRESH:
        broadcast_discover()


def prune_known_devices() -> None:
    """Remove devices that have not been seen recently."""
    global known_devices

    now = time()
    known_devices = {
        ip: info
        for ip, info in known_devices.items()
        if info.get("self", False) or ("last_seen" in info and (now - info["last_seen"]) <= DEVICE_TIMEOUT)
    }


def enforce_limit() -> None:
    """Ensure we do not track more than MAXIMUM_KNOWN_DEVICES."""
    global known_devices, local_ip_bytes

    if len(known_devices) <= MAXIMUM_KNOWN_DEVICES:
        return

    # Always keep the local device
    local_info = known_devices.get(local_ip_bytes)
    others = [
        (ip, info)
        for ip, info in known_devices.items()
        if ip != local_ip_bytes
    ]
    # Keep the most recently seen others
    others.sort(key=lambda item: item[1]["last_seen"], reverse=True)

    new_known = {local_ip_bytes: local_info}
    for ip, info in others[: MAXIMUM_KNOWN_DEVICES - 1]:
        new_known[ip] = info
    known_devices = new_known


def debug_known_devices() -> None:  # pragma: no cover - debugging helper
    printable = {bytes_to_ip(ip): info for ip, info in known_devices.items()}
    print("Known devices:", printable)

