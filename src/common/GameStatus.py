# SYS9 and SYS11

import time

import DataMapper
import SharedState as S
from logger import logger_instance
from origin import push_game_state

log = logger_instance

# Initialize fast poll status in SharedState
S.game_status["game_active"] = False
S.game_status["poll_state"] = 0

# Most recent report computed by poll_fast (4Hz). The HTTP route returns this
# cached copy instead of recomputing per request, decoupling poll frequency
# from web request rate and avoiding per-request allocations (GC pressure).
_last_report = None


def cached_report():
    """Return the most recent game report from poll_fast.

    Falls back to computing one on demand if the poller has not run yet
    (e.g. a request arrives during boot before the first poll tick).
    """
    if _last_report is None:
        return game_report()
    return _last_report


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
        active_format = getattr(S, "active_format", {})
        data["ActiveFormatName"] = active_format.get("Name", "Standard")
        data["ActiveFormatId"] = active_format.get("Id", 0)
        data["game_num"] = S.gameCounter


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

    global _last_report
    _last_report = game_report()
    push_game_state(_last_report)
