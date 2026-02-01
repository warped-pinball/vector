# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
SYS11 DataMapper

Translation layer between SYS11 machine data formats (shadow RAM, JSON configs)
and the MicroPython application. Handles all data format conversions including
BCD scores, ASCII/Type3 initials, and other SYS11-specific encodings.

This module provides functions to read and write data from/to shadow RAM,
converting between machine formats and usable Python data structures.
"""

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


def _int_to_bcd(number, num_bytes=None):
    """
    Convert integer to BCD (Binary Coded Decimal) bytes for SYS11 machine format.
    
    Args:
        number: Integer value to convert
        num_bytes: Number of bytes to generate (if None, uses default of 4)
        
    Returns:
        bytearray: BCD-encoded bytes, zero-padded to num_bytes length
    """
    if num_bytes is None:
        num_bytes = 4  # Default: 4 BCD bytes for 8 digit score (SYS11 standard)
    
    # Pad with zeros to ensure it has num_bytes*2 digits
    num_str = f"{number:0{num_bytes*2}d}"
    bcd_bytes = bytearray(num_bytes)
    
    # Fill byte array
    for i in range(num_bytes):
        bcd_bytes[i] = (int(num_str[2 * i]) << 4) + int(num_str[2 * i + 1])
    
    return bcd_bytes


def _ascii_to_type3(c):
    """Convert ASCII character to machine type 3 display character."""
    return 0 if c == 0x20 or c < 0x0B or c > 0x90 else c - 0x36


def read_high_scores():
    """
    Read and decode the high scores from SYS11 shadow RAM.
    
    SYS11 Type 1,2,3,9 high scores:
    - 4 high scores (no Grand Champion)
    - Standard BCD encoding (4 bytes per score)
    - ASCII or custom encoding for initials (3 characters per score)
    - Type 1: 0x40=space, A-Z normal ASCII
    - Type 2: Similar to Type 1
    - Type 3: 0=space, 1='0', 10='9', 11='A'
    - Type 9: No initials, scores only
    
    Returns:
        list: List of [initials, score] pairs
            Index 0-3: High scores 1-4
            [[initials, score], ...] where initials is string, score is int
    """
    high_scores = [["", 0], ["", 0], ["", 0], ["", 0]]
    
    # Validate HighScores configuration exists
    if "HighScores" not in S.gdata:
        log.log("HighScores configuration missing")
        return high_scores
    
    try:
        if S.gdata["HighScores"]["Type"] not in [1, 2, 3, 9]:
            log.log(f"DataMapper: Unsupported HighScores Type {S.gdata['HighScores']['Type']}")
            return high_scores
        
        # Read 4 high scores (index 0-3)
        for idx in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + idx * 4
            score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
            high_scores[idx][1] = _bcd_to_int(score_bytes)
            
            # Filter out very low scores (likely placeholders)
            if high_scores[idx][1] < 1000:
                high_scores[idx][1] = 0
        
        # Read initials for high scores (Type 1, 2, 3 only - Type 9 has no initials)
        if "InitialAdr" in S.gdata["HighScores"]:
            for idx in range(4):
                initial_start = S.gdata["HighScores"]["InitialAdr"] + idx * 3
                initials_bytes = shadowRam[initial_start : initial_start + 3]
                
                if S.gdata["HighScores"]["Type"] in [1, 2]:  # 0x40=space, A-Z normal ASCII
                    initials_bytes = [0x20 if b == 0x40 else (b & 0x7F) for b in initials_bytes]
                    try:
                        high_scores[idx][0] = bytes(initials_bytes).decode("ascii")
                    except Exception:
                        high_scores[idx][0] = ""
                elif S.gdata["HighScores"]["Type"] == 3:  # 0=space, 1='0', 10='9', 11='A'
                    try:
                        processed_initials = bytearray([0x20 if byte == 0 else byte + 0x36 for byte in initials_bytes])
                        high_scores[idx][0] = processed_initials.decode("ascii")
                    except Exception:
                        high_scores[idx][0] = ""
                
                # Clear placeholder/invalid initials
                if high_scores[idx][0] in ["???", "", None, "   "]:
                    high_scores[idx][0] = ""
    
    except (IndexError, KeyError) as e:
        log.log(f"High score read error: {e}")
    
    return high_scores


def write_high_scores(high_scores):
    """
    Write high scores and initials to SYS11 shadow RAM.
    
    Args:
        high_scores: List of [initials, score] pairs
            Index 0-3: High scores 1-4
            Format: [[initials, score], ...] where initials is string, score is int
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Validate HighScores configuration exists
    if "HighScores" not in S.gdata:
        log.log("HighScores configuration missing")
        return False
    
    try:
        if S.gdata["HighScores"]["Type"] not in [1, 2, 3, 9]:
            log.log(f"DataMapper: Unsupported HighScores Type for write: {S.gdata['HighScores']['Type']}")
            return False
        
        # Ensure all initials are properly formatted (empty initials cause issues)
        for index in range(4):
            if index < len(high_scores):
                if len(high_scores[index][0]) != 3:
                    high_scores[index][0] = "   "
        
        # Write 4 high scores
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            
            try:
                score_bcd = _int_to_bcd(high_scores[index][1])
            except Exception:
                log.log(f"DATAMAPPER: Score {index} convert problem")
                score_bcd = _int_to_bcd(100)
            
            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = score_bcd
            
            # Write initials (Type 1, 2, 3 only - Type 9 has no initials)
            if "InitialAdr" in S.gdata["HighScores"]:
                try:
                    initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3
                    initials = high_scores[index][0]
                    
                    if S.gdata["HighScores"]["Type"] == 1:
                        for i in range(3):
                            shadowRam[initial_start + i] = ord(initials[i])
                    elif S.gdata["HighScores"]["Type"] == 3:
                        for i in range(3):
                            shadowRam[initial_start + i] = _ascii_to_type3(ord(initials[i]))
                    elif S.gdata["HighScores"]["Type"] == 2:
                        for i in range(3):
                            shadowRam[initial_start + i] = ord(initials[i])
                except Exception:
                    log.log(f"DATAMAPPER: Score {index} initials write problem")
                    shadowRam[initial_start : initial_start + 3] = bytearray([64, 64, 64])
        
        log.log("Successfully wrote high scores to shadow RAM")
        return True
       
    except (IndexError, KeyError, ValueError) as e:
        log.log(f"High score write error: {e}")
        return False


def read_in_play_scores():
    """
    Read the current in-play scores for all 4 players.
    
    SYS11 Type 1 in-play scores:
    - 4 player scores stored sequentially
    - Standard BCD encoding (4 bytes per score)
    - Fixed spacing between player scores
    
    Returns:
        list: List of [initials, score] pairs for 4 players
            [[initials, score], [initials, score], ...  ]
            Initials will be empty strings (not available in in-play data)
    """
    in_play_scores = [["", 0], ["", 0], ["", 0], ["", 0]]
    
    try:
        if S.gdata.get("InPlay", {}).get("Type") == 1:  # Type 1 for SYS11
            for idx in range(4):
                score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * 4
                in_play_score_bytes = shadowRam[score_start : score_start + 4]
                in_play_scores[idx][1] = _bcd_to_int(in_play_score_bytes)
    except Exception as e:
        log.log(f"In-play scores read error: {e}")
    
    return in_play_scores



def get_live_scores(use_format=True):
    """
    Get live scores for all 4 players.
    
    If a Format is active (active_format != 0), pulls scores from Formats.player_scores.
    Otherwise reads from SYS11 shadow RAM.
    
    Returns:
        list: List of 4 integer scores [score1, score2, score3, score4]
    """
    scores = [0, 0, 0, 0]
    
    # Check if a Format is active
    try:
        if use_format is True and hasattr(S, 'active_format') and S.active_format != 0:
            # Format is active - use player_scores from Formats module
            import Formats
            scores = list(Formats.player_scores)
            return scores
    except Exception as e:
        log.log(f"DATAMAPPER: error getting format scores: {e}")
    
    # No active format - read from shadow RAM
    try:
        for idx in range(4):
            score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * 4
            score_bytes = shadowRam[score_start : score_start + 4]
            scores[idx] = _bcd_to_int(score_bytes)
    except Exception as e:
        log.log(f"DATAMAPPER: error getting in-play scores: {e}")

    return scores



def get_ball_in_play():
    """
    Get the current ball number in play
    SYS11 Type 1 ball tracking
    Returns:
        int: Ball number (1-5) or 0 if no game active
    """
    try:
        ball_in_play = S.gdata["BallInPlay"]
        if ball_in_play["Type"] == 1:
            token = shadowRam[ball_in_play["Address"]]
            mapping = {ball_in_play["Ball1"]: 1, ball_in_play["Ball2"]: 2, ball_in_play["Ball3"]: 3, ball_in_play["Ball4"]: 4, ball_in_play["Ball5"]: 5}
            return mapping.get(token, 0)
    except Exception as e:
        log.log(f"GSTAT: error in get_ball_in_play: {e}")
    return 0


def write_ball_in_play(ball_number):

    """
    Write the current ball number in play to shadow RAM.
    
    SYS11 Type 1 ball tracking:
    - Direct byte value at configured address
    - 1-5 for balls in play, 0 for game over/not started
    
    Args:
        ball_number: int - Ball number to write (0-5)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if S.gdata.get("BallInPlay", {}).get("Type") == 1:
            ball_adr = S.gdata["BallInPlay"]["Address"]
            shadowRam[ball_adr] = ball_number
            return True
    except Exception as e:
        log.log(f"DATAMAPPER: error in write_ball_in_play: {e}")
    
    return False


def get_player_up():
    """
    Get the current player number (whose turn it is).
    
    SYS11 stores player-up as 0-3 at configured address.
    
    Returns:
        int: Player number (1-4) or 0 if not available
    """
    try:
        if "InPlay" in S.gdata and "PlayerUp" in S.gdata["InPlay"]:
            adr = S.gdata["InPlay"]["PlayerUp"]
            return shadowRam[adr]+1
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
        if "InPlay" in S.gdata and "Players" in S.gdata["InPlay"]:
            adr = S.gdata["InPlay"]["Players"]
            return shadowRam[adr]+1
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_players_in_game: {e}")
    
    return 0


def get_game_active():
    """
    Check if a game is currently active.
    
    Returns:
        bool: True if game is active, False otherwise
    """
    return 0 != get_ball_in_play()





def write_live_scores(scores):
    """
    Write live scores to shadow RAM.
    
    Args:
        scores: List of 4 integer scores [p1_score, p2_score, p3_score, p4_score]
        
    Returns:
        bool: True if write was successful, False otherwise
    """
    try:
        if not isinstance(scores, (list, tuple)) or len(scores) != 4:
            log.log(f"DATAMAPPER: invalid scores format, expected list of 4 integers")
            return False
            
        for idx in range(4):
            score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * 4
            score_bcd = _int_to_bcd(scores[idx])
            shadowRam[score_start : score_start + 4] = score_bcd
            
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: error writing in-play scores: {e}")
        return False


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
    data = {
        "GameActive": False,
        "BallInPlay": 0,
        "PlayerUp": 0,
        "PlayersInGame": 0,
        "Scores": [0, 0, 0, 0],
    }
    
    # Check if InPlay configuration exists and is valid
    if "InPlay" not in S.gdata or S.gdata["InPlay"].get("Type") != 1:
        return data
    
    # Get game active status
    data["GameActive"] = get_game_active()
    
    # Get ball in play
    data["BallInPlay"] = get_ball_in_play()
    
    # Get player up
    data["PlayerUp"] = get_player_up()
    
    # Get players in game
    data["PlayersInGame"] = get_players_in_game()
    
    # Get live scores for all 4 players    
    data["Scores"] = get_live_scores()
   
    return data


def remove_machine_scores():
    """
    Remove/reset machine high scores to prepare for forced initial entry.
    
    Sets scores to low placeholder values and initials to '???' or spaces.
    For Type 1/2: initials set to 0x3F ('?')
    For Type 3: initials set to 0x00 (space)
    For Type 9: no initials, just reset scores
    
    SYS11 Types 1, 2, 3, 9.
    """
    if S.gdata.get("HighScores", {}).get("Type") not in [1, 2, 3, 9]:
        return
    
    log.log(f"DATAMAPPER: Remove machine scores type {S.gdata['HighScores']['Type']}")
    
    # Reset 4 high scores
    for index in range(4):
        score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
        
        # Clear score to 0
        for i in range(4):
            shadowRam[score_start + i] = 0
        
        # Set placeholder score (50, 40, 30, 20)
        shadowRam[score_start + 2] = 5 - index
        
        # Set initials based on type
        if "InitialAdr" in S.gdata["HighScores"]:
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3
            
            if S.gdata["HighScores"]["Type"] in [1, 2]:
                # Type 1/2: Set to 0x3F ('?')
                for i in range(3):
                    shadowRam[initial_start + i] = 0x3F
            elif S.gdata["HighScores"]["Type"] == 3:
                # Type 3: Set to 0x00 (space)
                for i in range(3):
                    shadowRam[initial_start + i] = 0x00


def match_in_play_with_high_score_initials(in_play_scores, high_scores):
    """
    Match in-play scores with high score initials.
    
    When a player achieves a high score, their in-play score will match
    one of the high scores. This function copies the initials from the
    high score list to the in-play score list for matching scores.
    
    Args:
        in_play_scores: List of [initials, score] pairs from in-play data
        high_scores: List of [initials, score] pairs from high score data
    
    Returns:
        list: Updated in_play_scores with initials filled in where matches found
    """
    for in_play_score in in_play_scores:
        for high_score in high_scores:
            if in_play_score[1] == high_score[1] and in_play_score[1] != 0:
                in_play_score[0] = high_score[0]  # Copy initials over
                break
    
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
    try:
        if "Flippers" in S.gdata and S.gdata["Flippers"].get("Type") in [1, 2]:
            flipper_address = S.gdata["Flippers"]["Address"]
            v=shadowRam[flipper_address]
            left = (v & 0x02) != 0
            right = (v & 0x01) != 0
            
            # Type 2: Reverse left and right
            if S.gdata["Flippers"]["Type"] == 2:
                return right, left
            
            return left, right

    except Exception as e:
        log.log(f"DATAMAPPER: error in get_flipper_state: {e}")
    
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
    switches_cfg = S.gdata.get("Switches")
    if not switches_cfg or switches_cfg.get("Type") != 10:
        return []

    address = switches_cfg.get("Address", 0)
    length = switches_cfg.get("Length", 0)
    try:
        return [shadowRam[address + i] > 20 for i in range(length)]
    except Exception as e:
        log.log(f"DATAMAPPER: Error reading switches: {e}")
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
    switches_cfg = S.gdata.get("Switches")
    if not switches_cfg or switches_cfg.get("Type") != 10:
        return False
    
    value=20  # for SYS11 switches
    address = switches_cfg.get("Address", 0)
    length = switches_cfg.get("Length", 0)
    if address == 0 or length == 0:
        return False
    
    try:
        for i in range(length):
            shadowRam[address + i] = value
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: Error writing switches: {e}")
        return False


def print_switches():
    """
    Print the switch names and their values in two columns.
    Uses the list from get_switches_tripped() and the 'Names' list from S.gdata['Switches'].
    If a name is empty, display 'NotUsed' instead.
    """
    switch_values = get_switches_tripped()
    names = []
    if "Switches" in S.gdata and "Names" in S.gdata["Switches"]:
        names = S.gdata["Switches"]["Names"]
    else:
        names = ["NotUsed"] * len(switch_values)

    for idx, value in enumerate(switch_values):
        # Support list of lists: [name, number]
        if idx < len(names) and isinstance(names[idx], list) and len(names[idx]) > 0:
            name = names[idx][0] if names[idx][0] else "NotUsed"
        else:
            name = "NotUsed"
        print(f"{name:<24} {value}")
