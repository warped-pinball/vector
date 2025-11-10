# WPC

# This file is part of the Warped Pinball WPC-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
'''
WPC
Game Status

'''



import time
from Shadow_Ram_Definitions import shadowRam
import SharedState as S
from logger import logger_instance
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
            start = S.gdata["InPlay"]["ScoreAdr"] + player * S.gdata["InPlay"]["ScoreSpacing"]
            score_bytes = shadowRam[start : start + S.gdata["InPlay"]["ScoreBytes"]]
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
            ret_value = shadowRam[ball_in_play["Address"]]           
            if shadowRam[S.gdata["InPlay"]["GameActiveAdr"]] != S.gdata["InPlay"]["GameActiveValue"]:
                ret_value = 0   
            #print(" ball value ",ret_value)    
            return ret_value
        
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

        data["Scores"] = [
            _get_machine_score(0),
            _get_machine_score(1),
            _get_machine_score(2),
            _get_machine_score(3),
        ]

        '''
        if S.game_status["time_game_start"] is not None:
            if S.game_status["game_active"]:
                data["GameTime"] = (time.ticks_ms() - S.game_status["time_game_start"]) / 1000
            elif S.game_status["time_game_end"] is not None and S.game_status["time_game_end"] > S.game_status["time_game_start"]:
                data["GameTime"] = (S.game_status["time_game_end"] - S.game_status["time_game_start"]) / 1000
            else:
                data["GameTime"] = 0
        else:
            data["GameTime"] = 0
        '''
        
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

