from binascii import crc32

import discovery
from machine import unique_id
from SPI_DataStore import read_record as ds_read_record
from ubinascii import hexlify
from ujson import dumps

_cached_machine_id = None
_previous_checksum = None


def get_machine_id():
    global _cached_machine_id
    if _cached_machine_id is not None:
        return _cached_machine_id
    message = hexlify(unique_id()).decode() + ds_read_record("configuration", 0).get("gamename", "")
    _cached_machine_id = (crc32(message.encode()) & 0xFFFFFFFF).to_bytes(4, "big").hex()
    return _cached_machine_id


def send_origin_message(message_type, data=None):
    global _previous_checksum
    try:
        # Compute a cheap checksum of the inputs before JSON serialization to avoid unnecessary allocations
        checksum = crc32((message_type + str(data)).encode()) & 0xFFFFFFFF
        if checksum == _previous_checksum:
            return

        if data is not None:
            packet = dumps({"machine_id": get_machine_id(), "type": message_type, "data": data})
        else:
            packet = dumps({"machine_id": get_machine_id(), "type": message_type})

        print(f"Sending origin message: {message_type} with data: {data}")
        discovery.send_sock.sendto(packet.encode(), ("255.255.255.255", 6809))
        _previous_checksum = checksum
    except Exception as e:
        print("Error sending origin message:", e)


def push_game_state(game_report):
    send_origin_message("game_state", game_report)


def push_end_of_game(game,try_count):
    # game = [0, ['', 0], ['', 0], ['', 0], ['', 0]]
    # try_count is 1 for first attempt and then increments for retransmits

    print("Pushing end_of_game:", game, " try:",try_count)

    # ensure list of tuples with initial, and score
    plays = []
    for play in game[1:]:
        if len(play) == 2 and isinstance(play[0], str) and isinstance(play[1], int) and play[1] != 0:
            if isinstance(play, tuple):
                plays.append(list(play))
            else:
                plays.append(play)

    if not plays:
        return

    send_origin_message("end_of_game", {"plays": plays, "try": try_count, "game_num": game[0] })


def push_reset():
    send_origin_message("reset")
