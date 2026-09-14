# Origin messages: live game events pushed from this board to one listener.
#
# Origin (or any other listener) registers itself over the authenticated
# /api/origin/target route, handing over a shared secret.  From then on this
# board unicasts game events to that one address and signs every datagram
# with the secret.  With nobody registered it sends nothing at all.
#
# Datagrams used to go to the broadcast address, which meant every board on
# the network shouted at every listener -- enough broadcast traffic to jam the
# WiFi chip, and anything on the LAN could forge a score.
#
# Frame layout (UDP, port 6809):
#
#     +--------------------------+------------------+
#     | 16 ASCII hex chars (MAC) | UTF-8 JSON body  |
#     +--------------------------+------------------+
#
# The MAC is the first 8 bytes of HMAC-SHA256(secret, body), hex-encoded.
# The body carries a counter "n" that increments with every datagram, so a
# listener can drop replays; it resets when a listener re-registers.

from binascii import crc32

import discovery
from machine import unique_id
from micropython import const
from SPI_DataStore import read_record as ds_read_record
from ubinascii import hexlify
from ujson import dumps

# UDP port a listener receives Origin messages on
_ORIGIN_PORT = const(6809)
# Hex characters of truncated HMAC-SHA256 prefixed to every datagram
_MAC_LEN = const(16)
# Secrets are short hex strings; cap the length so a caller can't park a large
# allocation on the board
MAX_SECRET_LENGTH = const(64)

_cached_machine_id = None
_previous_checksum = None

# Where Origin messages go, as 4 raw IP bytes, plus the secret they are signed
# with.  RAM only: a reboot clears both and the listener re-registers, which is
# also how a restarted or relocated listener recovers.
_target_ip = None
_target_secret = None
_counter = 0


def get_machine_id():
    global _cached_machine_id
    if _cached_machine_id is not None:
        return _cached_machine_id
    message = hexlify(unique_id()).decode() + ds_read_record("configuration", 0).get("gamename", "")
    _cached_machine_id = (crc32(message.encode()) & 0xFFFFFFFF).to_bytes(4, "big").hex()
    return _cached_machine_id


def set_target(ip_str, secret):
    """Send Origin messages to ``ip_str``, signed with ``secret``."""
    global _target_ip, _target_secret, _counter, _previous_checksum
    _target_ip = discovery.ip_to_bytes(ip_str)
    _target_secret = secret.encode("utf-8")
    # A new registration is a fresh conversation: restart the counter, and
    # forget the last message so the listener hears the current state at once.
    _counter = 0
    _previous_checksum = None


def clear_target():
    """Stop sending Origin messages anywhere."""
    global _target_ip, _target_secret, _counter
    _target_ip = None
    _target_secret = None
    _counter = 0


def get_target():
    """The registered listener's IP as a dotted quad, or None."""
    if _target_ip is None:
        return None
    return discovery.bytes_to_ip(_target_ip)


def send_origin_message(message_type, data=None):
    global _previous_checksum, _counter

    if _target_ip is None:
        return

    try:
        # Compute a cheap checksum of the inputs before JSON serialization to avoid unnecessary allocations
        checksum = crc32((message_type + str(data)).encode()) & 0xFFFFFFFF
        if checksum == _previous_checksum:
            return

        _counter += 1
        message = {"machine_id": get_machine_id(), "type": message_type, "n": _counter}
        if data is not None:
            message["data"] = data
        body = dumps(message).encode()

        from backend import hmac_sha256

        packet = hexlify(hmac_sha256(_target_secret, body))[:_MAC_LEN] + body
        print(f"Sending origin message: {message_type} with data: {data}")
        discovery.send_sock.sendto(packet, (discovery.bytes_to_ip(_target_ip), _ORIGIN_PORT))
        _previous_checksum = checksum
    except Exception as e:
        print("Error sending origin message:", e)


def push_game_state(game_report):
    send_origin_message("game_state", game_report)


def push_end_of_game(game, try_count):
    # game = [0, ['', 0], ['', 0], ['', 0], ['', 0]]
    # try_count is 1 for first attempt and then increments for retransmits

    # ensure list of tuples with initial, and score
    plays = []
    for play in game[1:]:
        if len(play) == 2 and isinstance(play[1], int) and play[1] != 0:
            if isinstance(play, tuple):
                plays.append(list(play))
            else:
                plays.append(play)

    if not plays:
        return

    send_origin_message("end_of_game", {"plays": plays, "try": try_count, "game_num": game[0]})


def push_reset():
    send_origin_message("reset")
