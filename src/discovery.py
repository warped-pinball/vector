import socket
import time

import ujson

# The UDP port we will send/receive on
DISCOVERY_PORT = 37020
DEVICE_TIMEOUT = 30

known_devices = {}
recv_sock = None
send_sock = None


def setup():
    global recv_sock, send_sock

    # Prepare a socket for receiving broadcast from others
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.bind(("0.0.0.0", DISCOVERY_PORT))
    recv_sock.settimeout(0)  # Non-blocking

    # Prepare a socket for sending broadcast
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)


def announce():
    """Broadcast this device’s info to the local network."""
    from SharedState import WarpedVersion, ipAddress

    global send_sock

    if not ipAddress:
        return

    message = {
        "version": WarpedVersion,
        "ip": ipAddress,
    }
    data = ujson.dumps(message)
    # Broadcast to 255.255.255.255 on DISCOVERY_PORT
    send_sock.sendto(data.encode("utf-8"), ("255.255.255.255", DISCOVERY_PORT))


def listen():
    """
    Check for any incoming broadcast announcements from other boards and update known devices.
    Non-blocking: if no data, returns immediately.
    """
    while True:
        try:
            data, addr = recv_sock.recvfrom(1024)
        except OSError:
            # No data available
            break

        try:
            msg = ujson.loads(data.decode("utf-8"))
        except ValueError:
            # If it's not valid JSON, ignore it
            continue

        if "ip" in msg and "type" in msg and "version" in msg:
            ip_str = msg["ip"]
            device_type = msg["type"]
            version = msg["version"]

            # Update our known devices dictionary
            known_devices[ip_str] = {"device_type": device_type, "version": version, "last_seen": time.time()}

    def prune_old_devices(self):
        """Remove devices not heard from in a while."""
        now = time.time()
        to_remove = []
        for ip_str, info in self.known_devices.items():
            if (now - info["last_seen"]) > DEVICE_TIMEOUT:
                to_remove.append(ip_str)

        for ip_str in to_remove:
            del self.known_devices[ip_str]
