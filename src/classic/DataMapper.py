# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Classics DataMapper

Translation layer between SYS11 machine data formats (shadow RAM, JSON configs)
and the MicroPython application. Handles all data format conversions including
BCD scores, ASCII/Type3 initials, and other SYS11-specific encodings.

This module provides functions to read and write data from/to shadow RAM,
converting between machine formats and usable Python data structures.
"""

import time

from logger import logger_instance
log = logger_instance
import SharedState as S
from Shadow_Ram_Definitions import shadowRam


def _bcd_to_int(score_bytes):
    """
    Convert BCD (Binary Coded Decimal) bytes from SYS11 machine format to integer.
    
    SYS11 uses standard BCD encoding where each byte contains two decimal digits
    (high nibble and low nibble). Invalid digits (>9) are treated as 0.
    Typically handles 4 BCD bytes for 8-digit scores.
    
    Args:
        score_bytes: bytearray or list of BCD-encoded bytes
        
    Returns:
        int: Decoded integer value
    """
    score = 0
    for byte in score_bytes:
        high_digit = byte >> 4
        low_digit = byte & 0x0F
        
        # Sanitize invalid BCD digits
        if low_digit > 9:
            low_digit = 0
        if high_digit > 9:
            high_digit = 0
            
        score = score * 100 + high_digit * 10 + low_digit
    return score



def _reversed_digit_score(base_adr, num_digits):
    """
    Decode a score stored as one decimal digit per byte (upper nibble),
    least-significant digit first (byte at base_adr is the ones digit,
    base_adr+1 is the tens digit, etc). Invalid digits, including the
    0xF blanking code used to suppress a leading zero, are treated as 0
    (which is a no-op on the leading digit).

    Args:
        base_adr: Address of the least-significant digit byte
        num_digits: Number of digit bytes to read

    Returns:
        int: Decoded integer value
    """
    score = 0
    for i in range(num_digits - 1, -1, -1):
        digit = shadowRam[base_adr + i] >> 4
        if digit > 9:
            digit = 0
        score = score * 10 + digit
    return score


def read_high_scores():
    """
    Read and decode the high score from shadow RAM.

    SYS11 Type 30 high score:
    - Only 1 high score available, no initials
    - 5 decimal digits, each BCD coded in the upper nibble of one byte
    - Most significant digit at ScoreAdr, each next digit at ScoreAdr-1, -2, ...
    - Result is multiplied by 10

    Returns:
        list: List of [initials, score] pairs
            Index 0-3: High scores 1-4 (only index 0 is populated)
            [[initials, score], ...] where initials is string, score is int
    """
    high_scores = [["", 0], ["", 0], ["", 0], ["", 0]]

    # Validate HighScores configuration exists
    if "HighScores" not in S.gdata:
        log.log("HighScores configuration missing")
        return high_scores

    try:
        if S.gdata["HighScores"]["Type"] != 30:
            log.log(f"DataMapper: Unsupported HighScores Type {S.gdata['HighScores']['Type']}")
            return high_scores

        # Score is 5 decimal digits, each BCD coded in the upper nibble of
        # one byte, most significant digit at ScoreAdr and each following
        # digit at the next lower address.
        score_adr = S.gdata["HighScores"]["ScoreAdr"]
        score = 0
        for i in range(5):
            digit = (shadowRam[score_adr - i] >> 4) & 0x0F
            if digit > 9:
                digit = 0
            score = score * 10 + digit
        high_scores[0][1] = score * 10

    except (IndexError, KeyError) as e:
        log.log(f"High score read error: {e}")

    return high_scores


def write_high_scores(high_scores):
    """
    No-op: SYS11 classics do not support writing high scores back to shadow RAM.

    Args:
        high_scores: List of [initials, score] pairs (unused)

    Returns:
        bool: True, as if the write succeeded
    """
    return True


def read_in_play_scores():
    """
    Read the current in-play scores for all 4 players (SYS11 classics).

    InPlay.Type 30: one decimal digit per byte, upper nibble,
    least-significant digit first, ScoreSpacing bytes between each
    player's block.

    Returns:
        list: List of [initials, score] pairs for 4 players
            [[initials, score], [initials, score], ...  ]
            Initials are always empty strings (not available in in-play data)
    """
    scores = get_live_scores(False)
    return [["", scores[0]], ["", scores[1]], ["", scores[2]], ["", scores[3]]]



_last_live_scores = [0, 0, 0, 0]


def get_live_scores(use_format=True):
    """
    Get live scores for all 4 players.

    If a game is active (get_game_active()), reads the current scores - from
    Formats.player_scores if a Format is active, otherwise from SYS11 shadow
    RAM (InPlay.Type 30: one decimal digit per byte, upper nibble,
    least-significant digit first, ScoreSpacing bytes between each player's
    block) - and caches the result. If no game is active, shadow RAM is no
    longer reliable, so the last cached reading is returned instead - unless
    a read from InPlay.LastScoreAdr (the display digits, which still hold
    the final score after the game ends) agrees with the cache on at least
    3 of 4 players, in which case that reading is accepted as the new cache.

    Returns:
        list: List of 4 integer scores [score1, score2, score3, score4]
    """
    global _last_live_scores

    if not get_game_active():
        try:
            in_play = S.gdata["InPlay"]
            if in_play["Type"] == 30 and "LastScoreAdr" in in_play:
                last_scores = [0, 0, 0, 0]
                for idx in range(4):
                    base_adr = in_play["LastScoreAdr"] + idx * in_play["ScoreSpacing"]
                    last_scores[idx] = _reversed_digit_score(base_adr, in_play["ScoreBytes"])

                matches = sum(1 for i in range(4) if last_scores[i] == _last_live_scores[i])
                if matches >= 3:
                    _last_live_scores = last_scores
        except Exception as e:
            log.log(f"DATAMAPPER: error getting LastScoreAdr scores: {e}")

        return list(_last_live_scores)

    scores = [0, 0, 0, 0]

    # Check if a Format is active
    try:
        if use_format is True and S.active_format.get("Id", 0) != 0:
            # Format is active - use player_scores from Formats module
            import Formats
            scores = list(Formats.player_scores)
            _last_live_scores = scores
            return scores
    except Exception as e:
        log.log(f"DATAMAPPER: error getting format scores: {e}")

    # No active format - read from shadow RAM
    try:
        in_play = S.gdata["InPlay"]
        if in_play["Type"] != 30:
            return scores

        for idx in range(4):
            base_adr = in_play["ScoreAdr"] + idx * in_play["ScoreSpacing"]
            scores[idx] = _reversed_digit_score(base_adr, in_play["ScoreBytes"])
    except Exception as e:
        log.log(f"DATAMAPPER: error getting in-play scores: {e}")

    _last_live_scores = scores
    return scores



def get_ball_in_play():
    """
    Get the current ball number in play (SYS11 classics).

    Reads the raw ball number from shadow RAM at BallInPlay.Address.

    Returns:
        int: Ball number in play, or 0 if unavailable
    """
    try:
        if S.gdata["BallInPlay"]["Type"] != 30:
            return 0
        return shadowRam[S.gdata["BallInPlay"]["Address"]]
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_ball_in_play: {e}")
        return 0


def write_ball_in_play(ball_number):

    """
    Write the current ball number in play to shadow RAM.
    
    Args:
        ball_number: int - Ball number to write (0-5)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        ball_config = S.gdata.get("BallInPlay", {})
        if ball_config.get("Type") != 30:
            return False

        shadowRam[ball_config["Address"]] = ball_number
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: error in write_ball_in_play: {e}")

    return False


def get_player_up():
    """
    Get the current player number (whose turn it is).

    SYS11 classics store player-up as the 1-4 player number directly at the
    configured address (not 0-based).

    Returns:
        int: Player number (1-4) or 0 if not available
    """
    try:
        if "InPlay" in S.gdata and S.gdata["InPlay"].get("Type") == 30 and "PlayerUp" in S.gdata["InPlay"]:
            adr = S.gdata["InPlay"]["PlayerUp"]
            return shadowRam[adr]
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_player_up: {e}")

    return 0


def get_players_in_game():
    """
    Get the number of players in the current game.
    
    SYS11 stores player count (0-3) at configured address.
    
    Returns:
        int: Number of players (1-4) or 0 if not available
    """
    try:
        if "InPlay" in S.gdata and S.gdata["InPlay"].get("Type") == 30 and "Players" in S.gdata["InPlay"]:
            adr = S.gdata["InPlay"]["Players"]
            return shadowRam[adr]
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_players_in_game: {e}")

    return 0


def get_game_active():
    """
    Check if a game is currently active 

    Reads InPlay.GameActiveAdr from shadow RAM. 0 = inactive, non-zero = active.

    Returns:
        bool: True if game is active, False otherwise
    """
    try:
        in_play = S.gdata["InPlay"]
        if in_play["Type"] != 30:
            return False

        return shadowRam[in_play["GameActiveAdr"]] != 0

    except Exception as e:
        log.log(f"DATAMAPPER: error get_game_active {e}")

    return False





def write_live_scores(scores):
    """
    No-op: SYS11 classics do not support writing live scores back to shadow RAM.

    Args:
        scores: List of 4 integer scores (unused)

    Returns:
        bool: True, as if the write succeeded
    """
    return True


# The web UI polls /api/game/status every 1500ms (scores.js) and only
# latches a "final" score snapshot from a poll where GameActive is still
# True. The hardware active flag can drop in the same instant the final
# score digit lands, so report GameActive True for a bit longer than one
# client poll interval after it actually goes false - this guarantees at
# least one poll sees the final score while still "active", regardless of
# how the two poll cycles happen to line up in time.
_GAME_ACTIVE_HOLD_MS = 3000
_game_inactive_since = None


def get_in_play_data():
    """
    Get comprehensive in-play game data.

    Returns a dictionary with:
        - GameActive: bool - Is a game currently running
        - BallInPlay: int - Current ball number (1-5, or 0)
        - PlayerUp: int - Current player (1-4, or 0)
        - PlayersInGame: int - Total players (1-4, or 0)
        - Scores: list - Current scores for all 4 players [int, int, int, int]

    If game is not active, most values will be 0/False.

    Returns:
        dict: Game state data
    """
    global _game_inactive_since

    data = {
        "GameActive": False,
        "BallInPlay": 0,
        "PlayerUp": 0,
        "PlayersInGame": 0,
        "Scores": [0, 0, 0, 0],
    }

    raw_active = get_game_active()
    if raw_active:
        _game_inactive_since = None
        reported_active = True
    else:
        if _game_inactive_since is None:
            _game_inactive_since = time.ticks_ms()
        reported_active = time.ticks_diff(time.ticks_ms(), _game_inactive_since) < _GAME_ACTIVE_HOLD_MS

    data["GameActive"] = reported_active

    # Get ball in play
    data["BallInPlay"] = get_ball_in_play()

    # Get player up
    data["PlayerUp"] = get_player_up()

    # Get players in game
    data["PlayersInGame"] = get_players_in_game()

    # Get live scores for all 4 players
    data["Scores"] = get_live_scores()

    #print("DATAMAPPER: get_in_play_data:", data)
    return data


def remove_machine_scores():
    """
    No-op: SYS11 classics do not support resetting machine high scores.
    """
    return



def match_in_play_with_high_score_initials(in_play_scores, high_scores):
    """
    Match in-play scores with high score initials.
    
    When a player achieves a high score, their in-play score will match
    one of the high scores. This function copies the initials from the
    high score list to the in-play score list for matching scores.
    
    Each high score initial is used only once to prevent duplicate assignments
    when players have identical scores.
    
    Args:
        in_play_scores: List of [initials, score] pairs from in-play data
        high_scores: List of [initials, score] pairs from high score data
    
    Returns:
        list: Updated in_play_scores with initials filled in where matches found
    """
    
    return in_play_scores



def get_flipper_state():
    """
    Read the flipper state from SYS11 shadow RAM.
    
    Returns the flipper state (left, right) at the configured flipper address.
    Type 1: Normal (left=bit1, right=bit0)
    Type 2: Reversed (left=bit0, right=bit1)
    
    Returns:
        tuple: (left, right) boolean values, or (0, 0) if not configured
    """
   
    
    return 0, 0






def get_modes():
    """
    Read game mode data from shadow RAM.
    
    Reads mode-specific data (like mission progress, fish caught, etc.)
    based on configuration in S.gdata["Modes"]. Each mode can have:
    - Address: Memory address (hex string "0x515" or integer)
    - Length: Number of bytes to read
    - Format: Data format ("u8", "BCD", etc.)
    - OffValue: Value threshold - mode excluded if value <= OffValue (optional)
    - Multiplier: Multiply result by this value (optional)
    
    Returns:
        dict: Dictionary with mode names as keys and their values
              Only includes modes where value > OffValue
              Returns empty dict if no modes configured
              Example: {"Fish Caught": 5, "Monster Fish": 1234}
    """
    modes_data = {}
    
    # Check if Modes configuration exists
    if "Modes" not in S.gdata:
        return modes_data
    
    try:
        for mode_name, mode_config in S.gdata["Modes"].items():
            # Parse address (could be hex string like "0x515" or integer)
            address = mode_config.get("Address", 0)
            if isinstance(address, str):
                # Convert hex string to integer
                address = int(address, 16) if address.startswith("0x") else int(address)
            
            # Get configuration parameters
            length = mode_config.get("Length", 1)
            data_format = mode_config.get("Format", "u8")
            multiplier = mode_config.get("Multiplier", 1)
            off_value = mode_config.get("OffValue", None)
            
            # Read bytes from shadow RAM
            mode_bytes = shadowRam[address : address + length]
            
            # Convert based on format
            if data_format == "u8":
                # Unsigned 8-bit integer
                value = mode_bytes[0] if len(mode_bytes) > 0 else 0
            elif data_format == "BCD":
                # BCD encoded
                value = _bcd_to_int(mode_bytes)
            elif data_format == "u16":
                # Unsigned 16-bit integer (little-endian)
                if len(mode_bytes) >= 2:
                    value = mode_bytes[0] | (mode_bytes[1] << 8)
                elif len(mode_bytes) == 1:
                    value = mode_bytes[0]
                else:
                    value = 0
            elif data_format == "u16be":
                # Unsigned 16-bit integer (big-endian)
                if len(mode_bytes) >= 2:
                    value = (mode_bytes[0] << 8) | mode_bytes[1]
                elif len(mode_bytes) == 1:
                    value = mode_bytes[0]
                else:
                    value = 0
            else:
                # Unknown format, treat as raw byte value
                log.log(f"DATAMAPPER: Unknown format '{data_format}' for mode '{mode_name}'")
                value = mode_bytes[0] if len(mode_bytes) > 0 else 0
            
            # Only include mode if value > OffValue (if OffValue is specified)
            if off_value is not None:
                if value > off_value:
                    modes_data[mode_name] = value * multiplier
            else:
                # No OffValue specified, always include
                modes_data[mode_name] = value * multiplier
    
    except Exception as e:
        log.log(f"DATAMAPPER: Error reading modes: {e}")
    
    return modes_data





def get_switches_tripped():
    """
    Read switch values from shadow RAM and return whether each switch is tripped.

    Returns:
        list: List of boolean values (True if switch value > 20, False otherwise), 
              or empty list if not configured or unsupported type.
    """
   

    return []




def write_switches_nominal():
    """
    Write a fixed value to all switch memory locations in shadow RAM.
    Uses the same address and length from the Switches section as get_switches().
    
    Args:
        value: The value to write to all switch locations (default: 20)
        
    Returns:
        bool: True if successful, False if not configured or unsupported type
    """
  
    return True
 

def print_switches():
    """
    Print the switch names and their values in two columns.
    Uses the list from get_switches_tripped() and the 'Names' list from S.gdata['Switches'].
    If a name is empty, display 'NotUsed' instead.
    """
    return


    