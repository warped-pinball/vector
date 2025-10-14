# This file is part of the Warped Pinball SYSEM-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
'''
EM
Game Status

'''
import time
import sensorRead
from origin import config as origin_config
from origin import push_game_state
#from Shadow_Ram_Definitions import shadowRam
import SharedState as S
from logger import logger_instance
log = logger_instance

# Initialize the game status in SharedState
S.game_status = {"game_active": False, "number_of_players": 0, "time_game_start": None, "time_game_end": None, "poll_state": 0}

import ScoreTrack


def _ticks_ms():
    """Return milliseconds using MicroPython's ticks_ms when available."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def _get_machine_score(player):
    """get score  from scoretrack module"""    
    return ScoreTrack.getPlayerScore(player)

def _get_ball_in_play():
    """Get the ball in play number. 0 if game over."""
    try:
        return 1 if sensorRead.gameActive() else 0
    except Exception as e:
        log.log(f"GSTAT: error reading game active: {e}")
    return 1 if S.game_status.get("game_active") else 0


def _current_scores():
    """Return list of scores for up to four players."""
    return [
        _get_machine_score(0),
        _get_machine_score(1),
        _get_machine_score(2),
        _get_machine_score(3),
    ]
  

def game_report():
    """Generate a report of the current game status, return dict"""
    data = {}
    try:
        current_ball = _get_ball_in_play()
        data["BallInPlay"] = current_ball

        data["GameActive"] = S.game_status["game_active"]

        data["Scores"] = _current_scores()
        
    except Exception as e:
        log.log(f"GSTAT: Error in report generation: {e}")
    return data


def poll_fast():
    """Poll for game start and end time."""
    current_ball = _get_ball_in_play()
    game_is_active = current_ball != 0
    ps = S.game_status["poll_state"]
    if ps == 0:
        if game_is_active:
            S.game_status["time_game_start"] = _ticks_ms()
            S.game_status["time_game_end"] = None
            print("GSTAT: start game @ time=", S.game_status["time_game_start"])
            S.game_status["poll_state"] = 1
    elif ps == 1:
        if not game_is_active:
            S.game_status["time_game_end"] = _ticks_ms()
            print("GSTAT: end game @ time=", S.game_status["time_game_end"])
            S.game_status["poll_state"] = 2
    else:
        S.game_status["poll_state"] = 0

    S.game_status["game_active"] = game_is_active

    if not origin_config.is_enabled():
        return

    try:
        start_time = S.game_status.get("time_game_start")
        end_time = S.game_status.get("time_game_end")
        if game_is_active and start_time is not None:
            game_time = int((_ticks_ms() - start_time) / 1000)
        elif start_time is not None and end_time is not None and end_time >= start_time:
            game_time = int((end_time - start_time) / 1000)
        else:
            game_time = 0

        push_game_state(
            game_time=game_time,
            scores=_current_scores(),
            ball_in_play=current_ball,
        )
    except Exception as e:
        log.log(f"GSTAT: failed to push origin game state: {e}")

