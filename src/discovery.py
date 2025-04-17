# The UDP port we will send/receive on
DISCOVERY_PORT = 37020
GAME_STATUS_PORT = 37021
GAME_FINAL_SCORE_PORT = 37022
DEVICE_TIMEOUT = 60  # Will announce at 1/2 this interval
MAXIMUM_KNOWN_DEVICES = 10  # TODO establish what a reasonable limit is

known_devices = {}
recv_sock = None
send_sock = None


def setup():
    global known_devices

    from phew import get_ip_address
    from SharedState import WarpedVersion, gdata

    known_devices[get_ip_address()] = {"name": gdata["GameInfo"]["GameName"], "version": WarpedVersion, "self": True}


def broadcast(msg, port):
    """
    Broadcast a string to a UDP port.
    """
    import socket

    # if the msg is a dict, convert it to a string
    if isinstance(msg, dict):
        from json import dumps

        msg = dumps(msg)
    elif not isinstance(msg, str):
        raise ValueError("msg must be a string or dict")

    try:
        print("Broadcasting:", msg, "to port", port)
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        send_sock.sendto(msg.encode("utf-8"), ("255.255.255.255", port))
    except Exception as e:
        print("Failed to broadcast:", e)
    finally:
        send_sock.close()


def broadcast_game_status():
    """
    Broadcast the game status to the local network.
    """
    from GameStatus import game_report
    from phew import get_ip_address

    msg = {"game_ip": get_ip_address(), "game_status": game_report()}

    broadcast(msg, GAME_STATUS_PORT)


def announce():
    """Broadcast this device's info to the local network."""
    from time import time

    from phew import get_ip_address
    from SharedState import WarpedVersion, gdata

    msg = {"version": WarpedVersion, "name": gdata["GameInfo"]["GameName"], "ip": get_ip_address()}

    broadcast(msg, DISCOVERY_PORT)

    # Prune devices that haven't been seen in a while
    global known_devices
    now = time()
    known_devices = {ip_str: info for ip_str, info in known_devices.items() if info.get("self", False) or (now - info["last_seen"]) <= DEVICE_TIMEOUT}


def listen():
    """
    Check for any incoming broadcast announcements from other boards and update known devices.
    Non-blocking: if no data, returns immediately.
    """
    global recv_sock, known_devices

    from time import time

    from ujson import loads

    if not recv_sock:
        import socket

        # Prepare a socket for receiving broadcast from others
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        recv_sock.bind(("0.0.0.0", DISCOVERY_PORT))
        recv_sock.settimeout(0)  # Non-blocking

    while True:
        try:
            data, addr = recv_sock.recvfrom(1024)
        except OSError:
            # No data available
            return

        try:
            msg = loads(data.decode("utf-8"))
        except ValueError:
            # If it's not valid JSON, ignore it
            continue

        # TODO authenticate the message

        if "name" in msg and "version" in msg:
            ip_str = addr[0]
            version = msg["version"]
            name = msg["name"]

            # Update our known devices dictionary
            known_devices[ip_str] = {"version": version, "last_seen": time(), "name": name}

            def bisect_left(arr, x):
                left, right = 0, len(arr)
                while left < right:
                    mid = (left + right) // 2
                    if arr[mid] < x:
                        left = mid + 1
                    else:
                        right = mid
                return left

            if len(known_devices) > MAXIMUM_KNOWN_DEVICES:
                devices = [(info["name"], ip_str, info.get("self", False)) for ip_str, info in known_devices.items()]
                local_device = next((d for d in devices if d[2]), None)
                if not local_device:
                    return
                local_name, local_ip, _ = local_device
                others = sorted([d for d in devices if not d[2]], key=lambda x: x[0])
                index = bisect_left([d[0] for d in others], local_name)
                selected = [local_device]
                up = index
                down = index - 1

                while len(selected) < MAXIMUM_KNOWN_DEVICES and (up < len(others) or down >= 0):
                    if up < len(others):
                        selected.append(others[up])
                        up += 1
                        if len(selected) == MAXIMUM_KNOWN_DEVICES:
                            break
                    if down >= 0 and len(selected) < MAXIMUM_KNOWN_DEVICES:
                        selected.append(others[down])
                        down -= 1

                new_known = {}
                for name, ip_str, is_self in selected:
                    new_known[ip_str] = known_devices[ip_str]
                known_devices = new_known

            print("Known devices:", known_devices)
