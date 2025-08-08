# Network discovery utilities for Raspberry Pi Pico 2W boards
# Implements a discovery request on boot and periodic refreshes.

import socket
from time import time

from ujson import dumps, loads

# The UDP port we will send/receive on
DISCOVERY_PORT = 37020
DISCOVER_REFRESH = 600  # send a new discovery request every 10 minutes
MAXIMUM_KNOWN_DEVICES = 50  # limit number of tracked devices

# Known devices keyed by 4 byte IP representation
known_devices = {}
recv_sock = None
send_sock = None
last_discover_time = 0
local_ip_bytes = None
self_info = None


def ip_to_bytes(ip_str: str) -> bytes:
    """Convert dotted-quad string to 4 byte representation."""
    return bytes(int(part) for part in ip_str.split("."))


def bytes_to_ip(ip_bytes: bytes) -> str:
    """Convert 4 byte IP representation back to dotted-quad string."""
    return ".".join(str(b) for b in ip_bytes)


def setup() -> None:
    """Initialise discovery state for this board."""
    global known_devices, local_ip_bytes, self_info

    from phew import get_ip_address
    from SharedState import gdata
    from systemConfig import SystemVersion

    local_ip_bytes = ip_to_bytes(get_ip_address())
    self_info = {
        "name": gdata["GameInfo"]["GameName"],
        "version": SystemVersion,
        "self": True,
    }
    known_devices = {local_ip_bytes: self_info}
    refresh_known_devices()


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


def handle_message(msg: dict, ip_str: str) -> None:
    """Handle an incoming message from ``ip_str``."""
    global known_devices

    ip_bytes = ip_to_bytes(ip_str)

    if msg.get("discover"):
        send_intro(ip_bytes)
        refresh_known_devices()
        return

    if "name" in msg and "version" in msg:
        known_devices[ip_bytes] = {
            "version": msg["version"],
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
            return

        try:
            msg = loads(data.decode("utf-8"))
        except ValueError:
            continue

        handle_message(msg, addr[0])


def maybe_discover() -> None:
    """Broadcast a discovery request if our refresh interval has elapsed."""
    if (time() - last_discover_time) >= DISCOVER_REFRESH:
        refresh_known_devices()


def refresh_known_devices() -> None:
    """Clear known devices and broadcast a discovery request."""
    global known_devices

    known_devices = {local_ip_bytes: self_info}
    broadcast_discover()


def enforce_limit() -> None:
    """Ensure we do not track more than MAXIMUM_KNOWN_DEVICES."""
    global known_devices, local_ip_bytes

    if len(known_devices) <= MAXIMUM_KNOWN_DEVICES:
        return

    # Always keep the local device
    new_known = {local_ip_bytes: known_devices.get(local_ip_bytes)}
    for ip, info in known_devices.items():
        if ip == local_ip_bytes:
            continue
        new_known[ip] = info
        if len(new_known) >= MAXIMUM_KNOWN_DEVICES:
            break
    known_devices = new_known


def debug_known_devices() -> None:  # pragma: no cover - debugging helper
    printable = {bytes_to_ip(ip): info for ip, info in known_devices.items()}
    print("Known devices:", printable)
