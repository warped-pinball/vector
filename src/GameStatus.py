import json
import time
import SharedState as S
from Shadow_Ram_Definitions import shadowRam

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
        print(f"GSTAT: error in get_machine_score: {e}")
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
        print(f"GSTAT: error in get_ball_in_play: {e}")
    return 0


def game_report():
    """Generate a report of the current game status, return JSON."""
    data = {}
    try:
        data["BallInPlay"] = _get_ball_in_play()
        data["Player1Score"] = _get_machine_score(0)
        data["Player2Score"] = _get_machine_score(1)
        data["Player3Score"] = _get_machine_score(2)
        data["Player4Score"] = _get_machine_score(3)

        if S.game_status["time_game_start"] is not None:
            if S.game_status["game_active"]:
                data["GameTime"] = (time.ticks_ms() - S.game_status["time_game_start"]) / 1000
            elif S.game_status["time_game_end"] is not None and S.game_status["time_game_end"] > S.game_status["time_game_start"]:
                data["GameTime"] = (S.game_status["time_game_end"] - S.game_status["time_game_start"]) / 1000
            else:
                data["GameTime"] = 0
        else:
            data["GameTime"] = 0

        data["GameActive"] = S.game_status["game_active"]
    except Exception as e:
        print(f"GSTAT: Error in report generation: {e}")   
    return json.dumps(data)


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


if __name__ == "__main__":
    import GameDefsLoad
    GameDefsLoad.go()
    print(game_report())
    poll_fast()
