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
# How many times a finished game is sent, and how far apart. These datagrams
# are not acknowledged, so sending again is the only defence against a dropped
# packet. Origin records which attempt arrived first, so how well these
# numbers are chosen is something that can be reviewed rather than guessed at.
# The attempt number also varies the payload, which matters: send_origin_message
# drops a message identical to the one before it.
_END_OF_GAME_ATTEMPTS = const(6)
_END_OF_GAME_RETRY_MS = const(5000)
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


def push_end_of_game(game):
    """Report a finished game to Origin, and keep reporting it for a while.

    *game* is ``[game_num, [initials, score], ... ]``, one entry per player.

    What is sent is a copy taken here, not the caller's list. The caller's is
    live: claiming a score on the board's own web page rewrites an entry in
    place, and the game counter moves on to the next game. Holding a reference
    would let a message change between attempts, so two listeners could end up
    with different ideas of the same game.

    How many attempts, and how far apart, is not the caller's business -- it
    has a finished game to report and no way to know what makes delivery
    reliable -- so it is decided here.
    """
    plays = [
        [play[0], play[1]]
        for play in game[1:]
        if len(play) == 2 and isinstance(play[1], int) and play[1] != 0
    ]
    if not plays:
        return

    _send_end_of_game(game[0], plays, 1)


def _send_end_of_game(game_num, plays, attempt):
    """Send one attempt, then book the next one if any are left.

    Each attempt schedules its successor rather than a loop counting down
    somewhere, so the only state is what the pending task closes over. Nothing
    survives a reboot, which is right: an unsent game is not worth keeping.
    """
    send_origin_message(
        "end_of_game", {"plays": plays, "try": attempt, "game_num": game_num}
    )

    if attempt >= _END_OF_GAME_ATTEMPTS:
        return

    from phew.server import schedule

    def resend_end_of_game():
        _send_end_of_game(game_num, plays, attempt + 1)

    # frequency_ms=None runs the task once and drops it from the schedule.
    schedule(resend_end_of_game, phase_ms=_END_OF_GAME_RETRY_MS, frequency_ms=None)


def push_reset():
    send_origin_message("reset")
