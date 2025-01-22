import socket
import time

import network
import ujson

# Replace with your Wi-Fi credentials
WIFI_SSID = "This LAN Is My LAN"
WIFI_PASSWORD = "allhailhypnotoad"

# The UDP port we will send/receive on
DISCOVERY_PORT = 37020

# How often (in seconds) we broadcast our info
BROADCAST_INTERVAL = 5

# How long (in seconds) before we consider a device "gone" if no updates
DEVICE_TIMEOUT = 30

# Basic info about this device
DEVICE_TYPE = "warped pinball"
SOFTWARE_VERSION = "v1.0.0"


def connect_wifi(ssid, password):
    """Connect to the specified Wi-Fi network."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            time.sleep(0.2)
    print("Connected. Network config:", wlan.ifconfig())
    return wlan


class DiscoveryService:
    """
    Sends periodic broadcast announcements and listens for announcements from others.
    Maintains a dictionary of discovered devices.
    """

    def __init__(self, device_type, version, broadcast_port=DISCOVERY_PORT):
        """
        :param device_type: e.g. "warped pinball"
        :param version: e.g. "v1.0.0"
        :param broadcast_port: UDP port to use for discovery
        """
        self.device_type = device_type
        self.version = version
        self.broadcast_port = broadcast_port

        # This dictionary will map:
        #     ip_string -> {"device_type": str, "version": str, "last_seen": float}
        self.known_devices = {}

        # Prepare a socket for receiving broadcast from others
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.recv_sock.bind(("0.0.0.0", broadcast_port))
        self.recv_sock.settimeout(0)  # Non-blocking

        # Prepare a socket for sending broadcast
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # We will fill this in after Wi-Fi connects
        self.own_ip = None

        # Last time we broadcasted
        self._last_broadcast = 0

    def set_own_ip(self, ip_str):
        """Set the IP address for this device (after connecting Wi-Fi)."""
        self.own_ip = ip_str

    def broadcast_announce(self):
        """Broadcast this device’s info to the local network."""
        if not self.own_ip:
            return
        message = {"type": self.device_type, "version": self.version, "ip": self.own_ip}
        data = ujson.dumps(message)
        # Broadcast to 255.255.255.255 on DISCOVERY_PORT
        self.send_sock.sendto(data.encode("utf-8"), ("255.255.255.255", self.broadcast_port))
        # Alternatively, you could broadcast to the network-specific broadcast address, e.g. "192.168.1.255"

    def handle_incoming(self):
        """
        Check for any incoming broadcast announcements from other boards and update known devices.
        Non-blocking: if no data, returns immediately.
        """
        while True:
            try:
                data, addr = self.recv_sock.recvfrom(1024)
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
                self.known_devices[ip_str] = {"device_type": device_type, "version": version, "last_seen": time.time()}

    def prune_old_devices(self):
        """Remove devices not heard from in a while."""
        now = time.time()
        to_remove = []
        for ip_str, info in self.known_devices.items():
            if (now - info["last_seen"]) > DEVICE_TIMEOUT:
                to_remove.append(ip_str)

        for ip_str in to_remove:
            del self.known_devices[ip_str]

    def update(self):
        """
        Call this periodically:
         - Broadcast our presence (if it’s time)
         - Listen for others
         - Prune old devices
        """
        now = time.time()
        # Send broadcast every BROADCAST_INTERVAL seconds
        if (now - self._last_broadcast) >= BROADCAST_INTERVAL:
            self.broadcast_announce()
            self._last_broadcast = now

        # Listen for others
        self.handle_incoming()

        # Prune devices
        self.prune_old_devices()

    def get_known_devices(self):
        """Return a dictionary (copy) of known devices."""
        return dict(self.known_devices)


def main():
    wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    my_ip = wlan.ifconfig()[0]

    ds = DiscoveryService(DEVICE_TYPE, SOFTWARE_VERSION, DISCOVERY_PORT)
    ds.set_own_ip(my_ip)

    # Example main loop
    while True:
        ds.update()
        # For debugging, print the discovered devices every so often
        # But in practice, you'd do something else with this info
        print("Known devices:", ds.get_known_devices())
        time.sleep(2)


if __name__ == "__main__":
    main()
