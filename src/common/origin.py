"""Origin integration helpers."""

import socket

try:
    from ujson import dumps
except ImportError:
    from json import dumps

from GameStatus import game_report

send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)


def send_origin_message(message_type, data):
    try:
        from machine import unique_id
        from ubinascii import hexlify

        uid = hexlify(unique_id()).decode()

        packet = dumps({"machine_id": uid, "type": message_type, "data": data})
        send_sock.sendto(packet.encode(), ("255.255.255.255", 6809))
    except Exception as e:
        print("Error sending origin message:", e)


def push_game_state():
    """Send current game state payload to Origin."""
    data = game_report()
    send_origin_message("game_state", data)
    return data


def push_end_of_game(game):
    """Send end-of-game payload to Origin."""
    send_origin_message("game_over", game)
    return game
