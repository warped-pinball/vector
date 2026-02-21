# SYS9 and SYS11

import time
import DataMapper
import SharedState as S
from logger import logger_instance
from origin import push_game_state
from Shadow_Ram_Definitions import shadowRam

log = logger_instance

# Initialize fast poll status in SharedState
S.game_status["game_active"] = False
S.game_status["poll_state"] = 0


def game_report():
    """Generate a report of the current game status, return dict"""

    try:
        data = DataMapper.get_in_play_data()
        gameActive = data["GameActive"]
        
        # Get mode data and add to report if available
        modes = DataMapper.get_modes()
        if modes and gameActive:
            data["Modes"] = modes
        
        # Add active format name
        data["ActiveFormatName"] = S.active_format.get("Name", "Standard")

    except Exception as e:
        log.log(f"GSTAT: Error in report generation: {e}")

    return data


# this is called at 4 calls per second
def poll_fast():
    """
    Poll for game start and end time.
    """
    ps = S.game_status["poll_state"]
    if ps == 0:
        S.game_status["game_active"] = False
        if DataMapper.get_ball_in_play() != 0:
            S.game_status["time_game_start"] = time.ticks_ms()
            S.game_status["game_active"] = True
            print("GSTAT: start game @ time=", S.game_status["time_game_start"])
            S.game_status["poll_state"] = 1
    elif ps == 1:
        if DataMapper.get_ball_in_play() == 0:
            S.game_status["time_game_end"] = time.ticks_ms()
            print("GSTAT: end game @ time=", S.game_status["time_game_end"])
            S.game_status["game_active"] = False
            S.game_status["poll_state"] = 2
    else:
        S.game_status["poll_state"] = 0

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
