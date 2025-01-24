import socket
import time

import ujson

# The UDP port we will send/receive on
DISCOVERY_PORT = 37020
DEVICE_TIMEOUT = 60  # Will announce at 1/2 this interval
MAXIMUM_KNOWN_DEVICES = 10  # TODO establish what a reasonable limit is

known_devices = {}
recv_sock = None
send_sock = None


def setup():
    global recv_sock, send_sock, known_devices

    # Prepare a socket for receiving broadcast from others
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.bind(("0.0.0.0", DISCOVERY_PORT))
    recv_sock.settimeout(0)  # Non-blocking

    # Prepare a socket for sending broadcast
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # add self to known devices
    from SharedState import WarpedVersion, gdata, ipAddress

    if ipAddress:
        known_devices[ipAddress] = {"version": WarpedVersion, "name": gdata["GameInfo"]["GameName"], "self": True}


def announce():
    """Broadcast this device’s info to the local network."""
    from time import time

    from SharedState import WarpedVersion, gdata, ipAddress

    if not ipAddress:
        return

    # Broadcast to 255.255.255.255 on DISCOVERY_PORT
    global send_sock, known_devices
    send_sock.sendto(
        ujson.dumps({"version": WarpedVersion, "name": gdata["GameInfo"]["GameName"]}).encode("utf-8"),
        ("255.255.255.255", DISCOVERY_PORT),
    )

    # Prune devices that haven't been seen in a while
    # technically we could do this in the listen() function
    # but it makes more sense to do it here because the announce frequency is closer to the timeout
    now = time()
    known_devices = {ip_str: info for ip_str, info in known_devices.items() if info.get("self", False) or (now - info["last_seen"]) <= DEVICE_TIMEOUT}


def listen():
    """
    Check for any incoming broadcast announcements from other boards and update known devices.
    Non-blocking: if no data, returns immediately.
    """
    global recv_sock, known_devices
    while True:
        try:
            data, addr = recv_sock.recvfrom(1024)
        except OSError:
            # No data available
            return

        try:
            msg = ujson.loads(data.decode("utf-8"))
        except ValueError:
            # If it's not valid JSON, ignore it
            continue

        # TODO authenticate the message

        if "name" in msg and "version" in msg:
            ip_str = addr[0]
            version = msg["version"]
            name = msg["name"]

            # Update our known devices dictionary
            known_devices[ip_str] = {"version": version, "last_seen": time.time(), "name": name}

            # if there are more than MAXIMUM_KNOWN_DEVICES, remove the ip address that's most different from own
            if len(known_devices) > MAXIMUM_KNOWN_DEVICES:
                from SharedState import ipAddress

                # Find the IP address that's most different from our own
                # ideally this will make for a semi-stable set of known devices which will
                # make it more logical when switching between them
                own_ip_parts = [int(part) for part in ipAddress.split(".")]
                worst_ip = None
                worst_diff = 0
                for ip_str in known_devices:
                    # Don't remove self
                    if known_devices[ip_str].get("self", False):
                        continue

                    other_ip_parts = [int(part) for part in ip_str.split(".")]
                    diff = sum(abs(own - other) for own, other in zip(own_ip_parts, other_ip_parts))
                    if worst_ip is None or diff > worst_diff:
                        worst_ip = ip_str
                        worst_diff = diff
                del known_devices[worst_ip]
                print("Removed", worst_ip, "from known devices")

            print("Known devices:", known_devices)
