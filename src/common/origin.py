from discovery import send_sock
from ujson import dumps
from urandom import getrandbits
from utime import ticks_diff, ticks_ms

challenges = []  # queue of server-provided challenges
previous_state = None  # last gamestate string sent to server


# Simulated gameplay state (can be disabled by commenting out a single line in push_game_state)
_sim_initialized = False
_sim_scores = [0, 0, 0, 0]
_sim_ball_in_play = 1
_sim_current_player = 0  # 0..3 for players 1..4
_sim_plays_remaining = 0
_sim_game_start_ms = None


def _randint(a, b):
    span = b - a + 1
    return a + (getrandbits(16) % span)


def _reset_new_game():
    global _sim_scores, _sim_ball_in_play, _sim_current_player, _sim_plays_remaining, _sim_game_start_ms

    _sim_scores = [0, 0, 0, 0]
    _sim_ball_in_play = 1
    _sim_current_player = 0
    _sim_plays_remaining = _randint(3, 12)
    _sim_game_start_ms = ticks_ms()


def _push_game_state_sim(game_time, scores, ball_in_play, game_active):
    global previous_state
    global _sim_initialized, _sim_scores, _sim_ball_in_play, _sim_current_player, _sim_plays_remaining, _sim_game_start_ms

    try:
        # One-time init
        if not _sim_initialized:
            _sim_initialized = True
            _reset_new_game()

        # If last ball ended (ball 0), start a new game
        if _sim_ball_in_play == 0:
            _reset_new_game()

        # If this player is done, advance player (and maybe ball)
        if _sim_plays_remaining <= 0:
            _sim_current_player = (_sim_current_player + 1) % 4
            _sim_plays_remaining = _randint(15, 40)
            if _sim_current_player == 0:
                _sim_ball_in_play += 1
                if _sim_ball_in_play > 5:
                    # Game over: reset ball to 0 and scores to 0 (visible "reset" frame)
                    _sim_ball_in_play = 0
                    _sim_scores = [0, 0, 0, 0]

        # If a ball is active, add some score to the active player
        if _sim_ball_in_play > 0:
            inc = _randint(1000, 50000)
            _sim_scores[_sim_current_player] += inc
            _sim_plays_remaining -= 1

        # Compute game time
        now = ticks_ms()
        game_time_ms = ticks_diff(now, _sim_game_start_ms) if _sim_game_start_ms is not None else 0

        # Deduplicate same state
        state_tail = "{},{},{},{},{}".format(_sim_scores[0], _sim_scores[1], _sim_scores[2], _sim_scores[3], _sim_ball_in_play)
        if previous_state == state_tail:
            return

    except Exception as e:
        print("Error pushing game state (sim):", e)

    _push_game_state_real(game_time_ms, _sim_scores, _sim_ball_in_play, game_active=_sim_ball_in_play > 0)


def send_origin_message(message_type, data):
    try:
        from machine import unique_id
        from ubinascii import hexlify

        uid = hexlify(unique_id()).decode()

        packet = dumps({"machine_id": uid, "type": message_type, "data": data})
        send_sock.sendto(packet.encode(), ("255.255.255.255", 6809))
    except Exception as e:
        print("Error sending origin message:", e)


def _push_game_state_real(game_time, scores, ball_in_play, game_active):
    global previous_state
    try:
        # Deduplicate same state
        state_tail = "{},{},{},{},{}".format(
            scores[0] if len(scores) > 0 else 0,
            scores[1] if len(scores) > 1 else 0,
            scores[2] if len(scores) > 2 else 0,
            scores[3] if len(scores) > 3 else 0,
            ball_in_play,
        )
        if previous_state == state_tail:
            return

        send_origin_message(
            "game_state",
            {
                "gameTimeMs": game_time if game_time is not None else 0,
                "scores": scores,
                "ball_in_play": ball_in_play,
                "game_active": game_active,
            },
        )

        previous_state = state_tail

    except Exception as e:
        print("Error pushing game state (real):", e)


def push_game_state(game_time, scores, ball_in_play, game_active):
    # Toggle simulation: comment the next line to disable simulated gameplay.
    return _push_game_state_sim(game_time, scores, ball_in_play, game_active)

    # Normal behavior: uncomment the next line to use real game state.
    # return _push_game_state_real(game_time, scores, ball_in_play, game_active)


def push_end_of_game(game):
    # ensure list of tuplies with initial, and score
    plays = [play for play in game["plays"] if len(play) == 2 and isinstance(play[0], str) and isinstance(play[1], int) and play[1] != 0]
    if not plays:
        return

    send_origin_message("end_of_game", {"plays": plays})
