# This file is part of the Warped Pinball SYSEM-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
EM
Game Status

"""
import time

import ScoreTrack

# from Shadow_Ram_Definitions import shadowRam
import SharedState as S
from logger import logger_instance
from origin import config as origin_config
from origin import push_game_state

log = logger_instance

# Initialize the game status in SharedState
S.game_status = {"game_active": False, "number_of_players": 0, "time_game_start": None, "time_game_end": None, "poll_state": 0}


def _get_machine_score(player):
    """get score  from scoretrack module"""
    return ScoreTrack.getPlayerScore(player)


def _get_ball_in_play():
    """Get the ball in play number. 0 if game over."""
    return 1


def game_report():
    """Generate a report of the current game status, return dict"""
    data = {}
    try:
        # data["BallInPlay"] = _get_ball_in_play()

        data["GameActive"] = S.game_status["game_active"]

        data["Scores"] = [
            _get_machine_score(0),
            _get_machine_score(1),
            _get_machine_score(2),
            _get_machine_score(3),
        ]

    except Exception as e:
        log.log(f"GSTAT: Error in report generation: {e}")
    return data


def poll_fast():
    """Poll for game start and end time."""
    ps = S.game_status["poll_state"]
    if ps == 0:
        S.game_status["game_active"] = False
        if _get_ball_in_play() != 0:
            S.game_status["time_game_start"] = time.ticks_ms()
            S.game_status["game_active"] = True
            print("GSTAT: start game @ time=", S.game_status["time_game_start"])
            S.game_status["poll_state"] = 1
    elif ps == 1:
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
