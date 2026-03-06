from binascii import crc32

from discovery import send_sock
from machine import unique_id
from SPI_DataStore import read_record as ds_read_record
from ubinascii import hexlify
from ujson import dumps

previous_packet = None


def get_machine_id():
    message = hexlify(unique_id()).decode() + ds_read_record("configuration", 0).get("gamename", "")
    return (crc32(message.encode()) & 0xFFFFFFFF).to_bytes(4, "big").hex()


def send_origin_message(message_type, data=None):
    global previous_packet
    try:
        if data is not None:
            packet = dumps({"machine_id": get_machine_id(), "type": message_type, "data": data})
        else:
            packet = dumps({"machine_id": get_machine_id(), "type": message_type})

        if packet == previous_packet:
            return  # Skip sending duplicate packet

        print(f"Sending origin message: {message_type} with data: {data}")
        send_sock.sendto(packet.encode(), ("255.255.255.255", 6809))
        previous_packet = packet
    except Exception as e:
        print("Error sending origin message:", e)


def push_game_state(game_report):
    send_origin_message("game_state", game_report)


def push_end_of_game(game):
    # [0, ['', 0], ['', 0], ['', 0], ['', 0]]

    print("Pushing end_of_game:", game)

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

    send_origin_message("end_of_game", {"plays": plays})


def push_reset():
    send_origin_message("reset")
