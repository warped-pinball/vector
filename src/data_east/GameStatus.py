# Data East

# This file is part of the Warped Pinball DE-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Data East
Game Status
"""

import time
import DataMapper
import SharedState as S
from logger import logger_instance
log = logger_instance


# Initialize the game status in SharedState
#S.game_status = {"game_active": False, "number_of_players": 0, "time_game_start": None, "time_game_end": None, "poll_state": 0}
S.game_status["game_active"] = False
S.game_status["poll_state"] = 0


END_HOLD_MS = 15_000
end_hold_start = None
gameActive = False


def game_report():
    """Generate a report of the current game status, return dict"""
    global end_hold_start, gameActive

    try:
        # read ball once and use the value in the conditional
        data = DataMapper.get_in_play_data()
        if data["GameActive"] != True:
            # game is not active
            if end_hold_start is None:
                end_hold_start = time.ticks_ms()
            else:
                if time.ticks_diff(time.ticks_ms(), end_hold_start) >= END_HOLD_MS:
                    gameActive = False
        else:
            # game is active
            end_hold_start = None
            gameActive = True

        data["GameActive"] = gameActive
        
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
