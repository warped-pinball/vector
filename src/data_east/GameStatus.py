# WPC

# This file is part of the Warped Pinball WPC-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
WPC
Game Status

"""


import time

import SharedState as S
from logger import logger_instance
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


def _get_machine_score():
    """Read all four live scores from machine memory."""
    try:
        # Import ScoreTrack to use its _read_machine_score function
        from ScoreTrack import _read_machine_score
        
        # Get all in-play scores (UseHighScores=False for live scores)
        in_play_scores = _read_machine_score(UseHighScores=False)
        
        # Return list of four scores [score0, score1, score2, score3]
        return [in_play_scores[i][1] for i in range(4)]
        
    except Exception as e:
        log.log(f"GSTAT: error in get_machine_score: {e}")
    return [0, 0, 0, 0]


def _get_ball_in_play():
    """Get the ball in play number. 0 if game over."""
    try:
        ball_in_play = S.gdata["BallInPlay"]
        if ball_in_play["Type"] == 1:
            ret_value = shadowRam[ball_in_play["Address"]]
            return ret_value

    except Exception as e:
        log.log(f"GSTAT: error in get_ball_in_play: {e}")
    return 0


def _get_player_up():
    """Get the player up  (1-4)"""
    try:
        if S.gdata.get("InPlay", {}).get("PlayerUp", 0) != 0:
            adr = S.gdata["InPlay"]["PlayerUp"]
            return shadowRam[adr]
    except Exception:
        pass
    return 0


END_HOLD_MS = 15_000
end_hold_start = None
gameActive = False


def game_report():
    """Generate a report of the current game status, return dict"""
    global end_hold_start, gameActive
    data = {}

    try:
        # read ball once and use the value in the conditional
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

        # Get all four scores in one call
        data["Scores"] = _get_machine_score()

        data["PlayerUp"] = _get_player_up()

    except Exception as e:
        log.log(f"GSTAT: Error in report generation: {e}")
    return data


# this is called at 4 calls per second
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
