# Discover boards on the network

The discovery helpers in `src/common/discovery.py` broadcast a small UDP heartbeat on port `37020`. Boards elect the lowest IP as the registry device, which replies with the full peer list.

On a laptop or desktop you will need to implement the wire protocol yourself (you cannot import the MicroPython helpers directly). The script below mirrors the on-device behavior using standard Python sockets.

## Quick start

1. Broadcast a HELLO frame (`[1, name_length, name bytes]`) on UDP port `37020`.
2. Listen for FULL responses (`[2, count, ip bytes..., name length, name bytes]`) from the elected registry node.
3. Parse the peer map from the FULL payload and refresh it periodically.

Ready-to-run desktop script:

```
#!/usr/bin/env python3
import socket
import time

DISCOVERY_PORT = 37020
NAME = "DesktopClient"


def send_hello(sock: socket.socket):
    name_bytes = NAME.encode("utf-8")[:32]
    payload = bytes([1, len(name_bytes)]) + name_bytes
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))


def decode_full(data: bytes):
    peers = {}
    if len(data) < 2 or data[0] != 2:
        return peers
    count = data[1]
    offset = 2
    for _ in range(count):
        if len(data) < offset + 5:
            break
        ip_bytes = data[offset : offset + 4]
        offset += 4
        name_len = data[offset]
        offset += 1
        name = data[offset : offset + name_len].decode("utf-8", "ignore")
        offset += name_len
        ip_str = socket.inet_ntoa(ip_bytes)
        peers[ip_str] = name
    return peers


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", DISCOVERY_PORT))
    send_hello(sock)
    print("Broadcasted discovery HELLO... listening for peers")

    while True:
        sock.settimeout(5)
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            send_hello(sock)
            continue

        peers = decode_full(data)
        if peers:
            print(f"Registry {addr[0]} reports peers: {peers}")


if __name__ == "__main__":
    main()
```

Run the script on the same network as the boards. It will rebroadcast a HELLO every few seconds if no responses arrive.
