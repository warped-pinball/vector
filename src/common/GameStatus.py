# SYS9 and SYS11

import time

import SharedState as S
from logger import logger_instance
from origin import config as origin_config
from origin import push_game_state
from Shadow_Ram_Definitions import shadowRam

log = logger_instance

# Initialize the game status in SharedState
S.game_status = {"game_active": False, "number_of_players": 0, "time_game_start": None, "time_game_end": None, "poll_state": 0}


def _BCD_to_Int(number_BCD):
    """Convert BCD number from machine to regular int."""
    number_int = 0
    for byte in number_BCD:
        high_digit = byte >> 4
        low_digit = byte & 0x0F
        if low_digit > 9:
            low_digit = 0
        if high_digit > 9:
            high_digit = 0
        number_int = number_int * 100 + high_digit * 10 + low_digit
    return number_int


def _get_machine_score(player):
    """Read a single live score from machine memory (0=player1, 3=player4)."""
    try:
        if S.gdata.get("InPlay", {}).get("Type", 0) != 0:
            start = S.gdata["InPlay"]["ScoreAdr"] + player * 4
            score_bytes = shadowRam[start : start + 4]
            return _BCD_to_Int(score_bytes)
        else:
            print("GSTAT: InPlay not defined")
    except Exception as e:
        log.log(f"GSTAT: error in get_machine_score: {e}")
    return 0


def _get_ball_in_play():
    """Get the ball in play number. 0 if game over."""
    try:
        ball_in_play = S.gdata["BallInPlay"]
        if ball_in_play["Type"] == 1:
            token = shadowRam[ball_in_play["Address"]]
            mapping = {ball_in_play["Ball1"]: 1, ball_in_play["Ball2"]: 2, ball_in_play["Ball3"]: 3, ball_in_play["Ball4"]: 4, ball_in_play["Ball5"]: 5}
            return mapping.get(token, 0)
    except Exception as e:
        log.log(f"GSTAT: error in get_ball_in_play: {e}")
    return 0


END_HOLD_MS = 15_000
end_hold_start = None
gameActive = False


def game_report():
    """Generate a report of the current game status, return dict"""
    global end_hold_start, gameActive
    data = {}
    try:
        ball = _get_ball_in_play()
        if ball == 0:
            if end_hold_start is None:
                end_hold_start = time.ticks_ms()
            else:
                if time.ticks_diff(time.ticks_ms(), end_hold_start) >= END_HOLD_MS:
                    gameActive = False
        else:
            # ball non 0
            end_hold_start = None
            gameActive = True

        data["GameActive"] = gameActive
        data["BallInPlay"] = ball

        data["Scores"] = [
            _get_machine_score(0),
            _get_machine_score(1),
            _get_machine_score(2),
            _get_machine_score(3),
        ]

        """
        if S.game_status["time_game_start"] is not None:
            if S.game_status["game_active"]:
                data["GameTime"] = (time.ticks_ms() - S.game_status["time_game_start"]) / 1000
            elif S.game_status["time_game_end"] is not None and S.game_status["time_game_end"] > S.game_status["time_game_start"]:
                data["GameTime"] = (S.game_status["time_game_end"] - S.game_status["time_game_start"]) / 1000
            else:
                data["GameTime"] = 0
        else:
            data["GameTime"] = 0
        """

    except Exception as e:
        log.log(f"GSTAT: Error in report generation: {e}")
    return data


def poll_fast():
    """Poll for game start and end time."""
    ps = S.game_status["poll_state"]
    if ps == 0:
        S.game_status["game_active"] = False
        # watch for game start
        if _get_ball_in_play() != 0:
            S.game_status["time_game_start"] = time.ticks_ms()
            S.game_status["game_active"] = True
            print("GSTAT: start game @ time=", S.game_status["time_game_start"])
            S.game_status["poll_state"] = 1
    elif ps == 1:
        # watch for game end
        if _get_ball_in_play() == 0:
            S.game_status["time_game_end"] = time.ticks_ms()
            print("GSTAT: end game @ time=", S.game_status["time_game_end"])
            S.game_status["game_active"] = False
            S.game_status["poll_state"] = 2
    else:
        S.game_status["poll_state"] = 0

    if origin_config.is_enabled():  # temporarily disable pushing game state to server
        push_game_state(
            game_time=int((time.ticks_ms() - S.game_status["time_game_start"]) / 1000) if S.game_status["game_active"] and S.game_status["time_game_start"] is not None else 0,
            scores=[
                _get_machine_score(0),
                _get_machine_score(1),
                _get_machine_score(2),
                _get_machine_score(3),
            ],
            ball_in_play=_get_ball_in_play(),
            game_active=S.game_status["game_active"],
        )
