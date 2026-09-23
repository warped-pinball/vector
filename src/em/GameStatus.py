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
from origin import push_game_state

log = logger_instance

# Initialize the game status in SharedState
S.game_status = {"game_active": False, "number_of_players": 0, "time_game_start": None, "time_game_end": None, "poll_state": 0}


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


def _get_machine_score(player):
    """get score  from scoretrack module"""
    return ScoreTrack.getPlayerScore(player)


def game_report():
    """Generate a report of the current game status, return dict"""
    data = {}
    try:
        data["GameActive"] = S.game_status["game_active"]

        data["Scores"] = [
            _get_machine_score(0),
            _get_machine_score(1),
            _get_machine_score(2),
            _get_machine_score(3),
        ]

        configured_players = (
            S.gdata.get("players")
            if S.gdata.get("players") is not None
            else S.gdata.get("total_players", S.gdata.get("number_of_players", 1))
        )
        try:
            configured_players = int(configured_players)
        except Exception:
            configured_players = 1
        configured_players = max(1, min(4, configured_players))

        # Keep both field names for compatibility with existing frontends.
        data["NumberOfPlayers"] = configured_players
        data["number_of_players"] = configured_players

        active_format = getattr(S, "active_format", {})
        data["ActiveFormatName"] = active_format.get("Name", "Standard")
        data["ActiveFormatId"] = active_format.get("Id", 0)

    except Exception as e:
        log.log(f"GSTAT: Error in report generation: {e}")
    return data


def poll_fast():
    """Watch for game start/end and push the updated status to origin.

    EM has no machine ball-in-play register to poll - ScoreTrack.py already
    maintains the authoritative S.game_status["game_active"] flag from real
    sensor activity (see CheckForNewScores). This just edge-detects changes
    in that flag to timestamp start/end; poll_state tracks the *previously
    seen* active state (0=inactive, 1=active), not a machine ball number.
    """
    active = S.game_status["game_active"]
    was_active = S.game_status["poll_state"] == 1

    if active and not was_active:
        S.game_status["time_game_start"] = time.ticks_ms()
        print("GSTAT: start game @ time=", S.game_status["time_game_start"])
        S.game_status["poll_state"] = 1
    elif was_active and not active:
        S.game_status["time_game_end"] = time.ticks_ms()
        print("GSTAT: end game @ time=", S.game_status["time_game_end"])
        S.game_status["poll_state"] = 0

    global _last_report
    _last_report = game_report()
    push_game_state(_last_report)
