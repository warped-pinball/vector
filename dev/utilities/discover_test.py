import json
import socket
import sys
import time

DISCOVERY_PORT = 37020
BROADCAST_INTERVAL = 5  # Seconds between sending broadcasts
DEVICE_TIMEOUT = 30  # Seconds before we consider a device "gone"

DEVICE_TYPE = "desktop_tester"
SOFTWARE_VERSION = "v1.0.0"


def get_local_ip():
    """
    Attempt to determine the local IP address by creating a temporary
    UDP connection to a public IP (8.8.8.8) and checking which address
    we used. This should work on most Windows/macOS/Linux setups.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print("Failed to determine local IP:", e)
        return "127.0.0.1"


class DesktopDiscovery:
    def __init__(self, device_type, version):
        self.device_type = device_type
        self.version = version

        # Known devices: ip -> { "device_type": str, "version": str, "last_seen": float }
        self.known_devices = {}

        # Prepare our receive socket
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.recv_sock.bind(("0.0.0.0", DISCOVERY_PORT))
        self.recv_sock.setblocking(False)

        # Prepare our send socket (for broadcast)
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self.last_broadcast_time = 0
        self.local_ip = get_local_ip()

    def broadcast_announce(self):
        """Send a JSON broadcast with our IP, device type, and version."""
        message = {"version": self.version, "name": "DesktopTester"}
        data = json.dumps(message).encode("utf-8")
        # Broadcast to the "all 1s" address on the given port
        self.send_sock.sendto(data, ("255.255.255.255", DISCOVERY_PORT))

    def receive_announcements(self):
        """Receive any incoming broadcast packets, parse them, and update known devices."""
        while True:
            try:
                data, addr = self.recv_sock.recvfrom(1024)
            except BlockingIOError:
                # No more data to read
                break
            except Exception as e:
                print("Error receiving data:", e)
                break

            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                # Not valid JSON
                continue

            # Expecting: { "ip": str, "type": str, "version": str }
            if "name" in msg and "version" in msg:
                name = msg["name"]
                version = msg["version"]

                now = time.time()
                self.known_devices[addr[0]] = {"version": version, "last_seen": now, "name": name}

    def prune_old_devices(self):
        now = time.time()
        stale_ips = []
        for ip_str, info in self.known_devices.items():
            if (now - info["last_seen"]) > DEVICE_TIMEOUT:
                stale_ips.append(ip_str)
        for ip_str in stale_ips:
            del self.known_devices[ip_str]

    def update(self):
        """Perform one discovery iteration: broadcast (if needed), receive, prune."""
        now = time.time()
        # Broadcast every BROADCAST_INTERVAL seconds
        if (now - self.last_broadcast_time) >= BROADCAST_INTERVAL:
            self.broadcast_announce()
            self.last_broadcast_time = now

        # Listen for others
        self.receive_announcements()

        # Prune
        self.prune_old_devices()


def main():
    dd = DesktopDiscovery(DEVICE_TYPE, SOFTWARE_VERSION)
    print(f"Local IP: {dd.local_ip}")
    print("Starting discovery on port", DISCOVERY_PORT)

    try:
        while True:
            dd.update()
            # Print out known devices
            if dd.known_devices:
                print("Known devices:")
                for ip_str, info in dd.known_devices.items():
                    print(f"  {ip_str} => {info}")
            else:
                print("No devices discovered yet.")
            time.sleep(2)
    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)


if __name__ == "__main__":
    main()
