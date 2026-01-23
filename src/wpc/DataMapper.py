# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
WPC DataMapper

Translation layer between WPC machine data formats (shadow RAM, JSON configs)
and the MicroPython application. Handles all data format conversions including
BCD scores, ASCII initials, and other WPC-specific encodings.

This module provides functions to read and write data from/to shadow RAM,
converting between machine formats and usable Python data structures.
"""

from logger import logger_instance

log = logger_instance

import SharedState as S
from Shadow_Ram_Definitions import shadowRam


def _bcd_to_int(score_bytes):
    """
    Convert BCD (Binary Coded Decimal) bytes from WPC machine format to integer.
    
    WPC uses standard BCD encoding where each byte contains two decimal digits
    (high nibble and low nibble). Handles up to 8 BCD bytes.
    
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
    Convert integer to BCD (Binary Coded Decimal) bytes for WPC machine format.
    
    Args:
        number: Integer value to convert
        num_bytes: Number of bytes to generate (if None, uses config)
        
    Returns:
        bytearray: BCD-encoded bytes, zero-padded to num_bytes length
    """
    if num_bytes is None:
        if S.gdata.get("HighScores", {}).get("Type") == 10:
            num_bytes = S.gdata["HighScores"]["BytesInScore"]
        else:
            num_bytes = 6  # Default: 6 BCD bytes for 12 digit score
    
    # Pad with zeros to ensure it has num_bytes*2 digits
    num_str = f"{number:0{num_bytes*2}d}"
    bcd_bytes = bytearray(num_bytes)
    
    # Fill byte array
    for i in range(num_bytes):
        bcd_bytes[i] = (int(num_str[2 * i]) << 4) + int(num_str[2 * i + 1])
    
    return bcd_bytes


def _initials_validate(initials):
    """
    Validate and clean initials for WPC machines.
    
    WPC uses standard ASCII encoding for initials (A-Z).
    Ensures initials are 3 uppercase letters, replacing invalid characters
    with spaces.
    
    Args:
        initials: String of initials (may be any length)
        
    Returns:
        tuple: (clean_str, result_bytes)
            - clean_str: 3-character string of validated initials
            - result_bytes: bytearray(3) with ASCII byte values
    """
    # Ensure initials is a string
    if not isinstance(initials, str):
        initials = str(initials) if initials else ""
    
    if not initials:
        return "   ", bytearray([32, 32, 32])
    
    # Condition the initials - only allow A-Z
    clean_str = ""
    for c in initials.upper():
        if "A" <= c <= "Z":
            clean_str += c
    
    # Special cases that indicate no player
    if clean_str in ["", "A"]:  # Single 'A' can mean timeout during initials entry
        clean_str = "   "
    
    # Pad or truncate to 3 characters
    clean_str = (clean_str + "   ")[:3]
    
    # Convert to bytes
    result_bytes = bytearray(3)
    for i in range(3):
        result_bytes[i] = ord(clean_str[i])
    
    return clean_str, result_bytes


def read_high_scores():
    """
    Read and decode the high scores from WPC shadow RAM.
    
    WPC Type 10 high scores:
    - 4 regular high scores plus optional Grand Champion
    - Standard BCD encoding
    - ASCII initials (3 characters per score)
    - Separate checksum for high scores and Grand Champion
    
    Returns:
        list: List of [initials, score] pairs
            Index 0: Grand Champion (if configured)
            Index 1-4: High scores 1-4
            [[initials, score], ...] where initials is string, score is int
    """
    high_scores = [["", 0], ["", 0], ["", 0], ["", 0], ["", 0]]
    
    # Validate HighScores configuration exists
    if "HighScores" not in S.gdata:
        log.log("HighScores configuration missing")
        return high_scores
    
    try:
        if S.gdata["HighScores"]["Type"] != 10:  # Type 10 is standard WPC
            log.log(f"DataMapper: Unsupported HighScores Type {S.gdata['HighScores']['Type']}")
            return high_scores
        
        # Read 4 regular high scores (index 1-4)
        for idx in range(1, 5):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + (idx - 1) * S.gdata["HighScores"]["ScoreSpacing"]
            score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
            high_scores[idx][1] = _bcd_to_int(score_bytes)
            
            # Filter out very low scores (likely placeholders)
            #if high_scores[idx][1] < 1000:
            #    high_scores[idx][1] = 0
        
        # Read Grand Champion score if configured (index 0)
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]
            score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
            high_scores[0][1] = _bcd_to_int(score_bytes)
            
            # Calculate the maximum fake score (all BCD bytes set to 0x99)
            max_fake_score = int("".join(["99"] * S.gdata["HighScores"]["BytesInScore"]))
            
            # Filter out placeholder scores
            #if high_scores[0][1] < 1000 or high_scores[0][1] >= max_fake_score:
            #    high_scores[0][1] = 0
        
        # Read initials for regular high scores
        if "InitialAdr" in S.gdata["HighScores"]:
            for idx in range(1, 5):
                initial_start = S.gdata["HighScores"]["InitialAdr"] + (idx - 1) * S.gdata["HighScores"]["InitialSpacing"]
                initials_bytes = shadowRam[initial_start : initial_start + 3]
                
                try:
                    # WPC uses standard ASCII encoding
                    high_scores[idx][0] = bytes(initials_bytes).decode("ascii")
                except Exception:
                    high_scores[idx][0] = ""
                
                # Clear placeholder/invalid initials
                if high_scores[idx][0] in ["???", "", None, "   "]:
                    high_scores[idx][0] = ""
        
        # Read Grand Champion initials if configured
        if "GrandChampInitAdr" in S.gdata["HighScores"]:
            initial_start = S.gdata["HighScores"]["GrandChampInitAdr"]
            initials_bytes = shadowRam[initial_start : initial_start + 3]
            
            try:
                high_scores[0][0] = bytes(initials_bytes).decode("ascii")
            except Exception:
                high_scores[0][0] = ""
            
            if high_scores[0][0] in ["???", "", None, "   "]:
                high_scores[0][0] = ""
    
    except (IndexError, KeyError, ValueError) as e:
        log.log(f"High score read error: {e}")
    
    return high_scores


def write_high_scores(high_scores):
    """
    Write high scores and initials to WPC shadow RAM.
    
    Args:
        high_scores: List of [initials, score] pairs
            Index 0: Grand Champion (if configured)
            Index 1-4: High scores 1-4
            Format: [[initials, score], ...] where initials is string, score is int
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Validate HighScores configuration exists
    if "HighScores" not in S.gdata:
        log.log("HighScores configuration missing")
        return False
    
    try:
        if S.gdata["HighScores"]["Type"] != 10:  # Type 10 is standard WPC
            log.log(f"DataMapper: Unsupported HighScores Type for write: {S.gdata['HighScores']['Type']}")
            return False
        
        # Ensure all initials are properly formatted (empty initials cause issues)
        for index in range(5):
            if index < len(high_scores):
                if len(high_scores[index][0]) != 3:
                    high_scores[index][0] = "   "
        
        # Determine if Grand Champion is configured
        gc = 0
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            gc = 1
            # Write Grand Champion score
            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]
            try:
                score_bcd = _int_to_bcd(high_scores[0][1])
            except Exception:
                log.log("DATAMAPPER: Grand Champion score convert problem")
                score_bcd = _int_to_bcd(100)
            
            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = score_bcd
            
            # Write Grand Champion initials
            if "GrandChampInitAdr" in S.gdata["HighScores"]:
                try:
                    initial_start = S.gdata["HighScores"]["GrandChampInitAdr"]
                    initials, initials_bytes = _initials_validate(high_scores[0][0])
                    shadowRam[initial_start : initial_start + 3] = initials_bytes
                except Exception:
                    log.log("DATAMAPPER: Grand Champion initials write problem")
                    # Write placeholder (AAA = '@@@' in ASCII 64)
                    shadowRam[initial_start : initial_start + 3] = bytearray([64, 64, 64])
        
        # Write 4 regular high scores
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["ScoreSpacing"]
            
            try:
                score_bcd = _int_to_bcd(high_scores[index + gc][1])
            except Exception:
                log.log(f"DATAMAPPER: Score {index} convert problem")
                score_bcd = _int_to_bcd(100)
            
            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = score_bcd
            
            # Write initials
            try:
                initial_start = S.gdata["HighScores"]["InitialAdr"] + index * S.gdata["HighScores"]["InitialSpacing"]
                initials, initials_bytes = _initials_validate(high_scores[index + gc][0])
                shadowRam[initial_start : initial_start + 3] = initials_bytes
            except Exception:
                log.log(f"DATAMAPPER: Score {index} initials write problem")
                shadowRam[initial_start : initial_start + 3] = bytearray([64, 64, 64])
        
        # Fix checksums after writing scores
        fix_high_score_checksum()
        
        log.log("Successfully wrote high scores to shadow RAM")
        return True
    
    except (IndexError, KeyError, ValueError) as e:
        log.log(f"High score write error: {e}")
        return False


def fix_high_score_checksum():
    """
    Calculate and write checksums for WPC high score data.
    
    WPC Type 10 uses two separate checksums:
    1. Main high scores checksum
    2. Grand Champion checksum (if configured)
    
    Checksum calculation: 0xFFFF - sum(bytes in range)
    Stored as MSB, LSB at ChecksumResultAdr
    """
    def _calc_checksum(start_adr, end_adr):
        """Calculate checksum for a range of addresses"""
        chk = 0
        for adr in range(start_adr, end_adr + 1):
            chk += shadowRam[adr]
        chk = 0xFFFF - chk
        msb = (chk >> 8) & 0xFF
        lsb = chk & 0xFF
        return msb, lsb
    
    if S.gdata.get("HighScores", {}).get("Type") == 10:  # Type 10 for standard WPC
        # Main high scores checksum
        msb, lsb = _calc_checksum(S.gdata["HighScores"]["ChecksumStartAdr"], S.gdata["HighScores"]["ChecksumEndAdr"])
        shadowRam[S.gdata["HighScores"]["ChecksumResultAdr"]] = msb
        shadowRam[S.gdata["HighScores"]["ChecksumResultAdr"] + 1] = lsb
        
        # Grand Champion checksum (if configured)
        if "GCChecksumStartAdr" in S.gdata["HighScores"]:
            msb, lsb = _calc_checksum(S.gdata["HighScores"]["GCChecksumStartAdr"], S.gdata["HighScores"]["GCChecksumEndAdr"])
            shadowRam[S.gdata["HighScores"]["GCChecksumResultAdr"]] = msb
            shadowRam[S.gdata["HighScores"]["GCChecksumResultAdr"] + 1] = lsb


def read_in_play_scores():
    """
    Read the current in-play scores for all 4 players.
    
    WPC Type 10 in-play scores:
    - 4 player scores stored sequentially
    - Standard BCD encoding
    - Fixed spacing between player scores
    
    Returns:
        list: List of [initials, score] pairs for 4 players
            [[initials, score], [initials, score], ...]
            Initials will be empty strings (not available in in-play data)
    """
    in_play_scores = [["", 0], ["", 0], ["", 0], ["", 0]]
    
    try:
        if S.gdata.get("InPlay", {}).get("Type") == 10:  # Type 10 for standard WPC
            for idx in range(4):
                score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * S.gdata["InPlay"]["ScoreSpacing"]
                in_play_score_bytes = shadowRam[score_start : score_start + S.gdata["InPlay"]["ScoreBytes"]]
                in_play_scores[idx][1] = _bcd_to_int(in_play_score_bytes)
    except Exception as e:
        log.log(f"In-play scores read error: {e}")
    
    return in_play_scores


def get_ball_in_play():
    """
    Get the current ball number in play.
    
    WPC Type 1 ball tracking:
    - Direct byte value at configured address
    - 1-5 for balls in play, 0 for game over/not started
    - Also checks GameActiveAdr to confirm game is actually active
    
    Returns:
        int: Ball number (1-5) or 0 if no game active
    """
    try:
        if S.gdata.get("BallInPlay", {}).get("Type") == 1:
            ball_adr = S.gdata["BallInPlay"]["Address"]
            ret_value = shadowRam[ball_adr]
            
            # Double-check with GameActive flag if configured
            if "InPlay" in S.gdata and "GameActiveAdr" in S.gdata["InPlay"]:
                if shadowRam[S.gdata["InPlay"]["GameActiveAdr"]] != S.gdata["InPlay"]["GameActiveValue"]:
                    ret_value = 0
            
            return ret_value
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_ball_in_play: {e}")
    
    return 0


def write_ball_in_play(ball_number):

    """
    Write the current ball number in play to shadow RAM.
    
    WPC Type 1 ball tracking:
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
    
    WPC stores player-up as 1-4 at configured address.
    
    Returns:
        int: Player number (1-4) or 0 if not available
    """
    try:
        if "InPlay" in S.gdata and "PlayerUp" in S.gdata["InPlay"]:
            adr = S.gdata["InPlay"]["PlayerUp"]
            return shadowRam[adr]
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_player_up: {e}")
    
    return 0


def get_players_in_game():
    """
    Get the number of players in the current game.
    
    WPC stores player count (1-4) at configured address.
    
    Returns:
        int: Number of players (1-4) or 0 if not available
    """
    try:
        if "InPlay" in S.gdata and "Players" in S.gdata["InPlay"]:
            adr = S.gdata["InPlay"]["Players"]
            return shadowRam[adr]
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_players_in_game: {e}")
    
    return 0


def get_game_active():
    """
    Check if a game is currently active.
    
    WPC uses a specific byte value at a configured address to indicate
    an active game.
    
    Returns:
        bool: True if game is active, False otherwise
    """
    try:
        if "InPlay" in S.gdata and "GameActiveAdr" in S.gdata["InPlay"]:
            game_active_value = shadowRam[S.gdata["InPlay"]["GameActiveAdr"]]
            return game_active_value == S.gdata["InPlay"]["GameActiveValue"]
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_game_active: {e}")
    
    return False


def get_live_scores():
    scores = [0, 0, 0, 0]
    try:
        for idx in range(4):
            score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * S.gdata["InPlay"]["ScoreSpacing"]
            score_bytes = shadowRam[score_start : score_start + S.gdata["InPlay"]["ScoreBytes"]]
            scores[idx] = _bcd_to_int(score_bytes)
    except Exception as e:
        log.log(f"DATAMAPPER: error getting in-play scores: {e}")

    return scores


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
            score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * S.gdata["InPlay"]["ScoreSpacing"]
            score_bcd = _int_to_bcd(scores[idx], S.gdata["InPlay"]["ScoreBytes"])
            shadowRam[score_start : score_start + S.gdata["InPlay"]["ScoreBytes"]] = score_bcd
            
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
    if "InPlay" not in S.gdata or S.gdata["InPlay"].get("Type") != 10:
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


def remove_machine_scores(grand_champ_mode="Max"):
    """
    Remove/reset machine high scores to prepare for forced initial entry.
    
    Sets scores to low placeholder values and initials to 'AAA'.
    Grand Champion can be set to max (so all scores go to positions 1-4)
    or to zero (for leaderboard reset).
    
    Args:
        grand_champ_mode: "Max" to set GC to maximum score, "Zero" to reset
    
    WPC Type 10 only.
    """
    if S.gdata.get("HighScores", {}).get("Type") != 10:
        return
    
    log.log("DATAMAPPER: Remove machine scores type 10")
    
    # Reset 4 regular high scores
    for index in range(4):
        score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["ScoreSpacing"]
        initial_start = S.gdata["HighScores"]["InitialAdr"] + index * S.gdata["HighScores"]["InitialSpacing"]
        
        # Clear score to 0
        for i in range(S.gdata["HighScores"]["BytesInScore"]):
            shadowRam[score_start + i] = 0
        
        # Set placeholder score (60, 50, 40, 30)
        shadowRam[score_start + S.gdata["HighScores"]["BytesInScore"] -1 ] = 0x10 * (4 - index)
        
        # Set initials to 'AAA' (0x41 = 'A' in ASCII)
        for i in range(3):
            shadowRam[initial_start + i] = 0x41+i
    
    # Handle Grand Champion score
    if "GrandChampScoreAdr" in S.gdata["HighScores"]:
        score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]
        
        if grand_champ_mode == "Max":
            # Set Grand Champion score to maximum (all 0x99)
            print("GRAND CHAMP to MAX")
            for i in range(S.gdata["HighScores"]["BytesInScore"]):
                shadowRam[score_start + i] = 0x99
        elif grand_champ_mode == "Zero":
            # Set Grand Champion to minimum
            for i in range(S.gdata["HighScores"]["BytesInScore"]):
                shadowRam[score_start + i] = 0x00
            # Set small placeholder score (9000)
            shadowRam[score_start + S.gdata["HighScores"]["BytesInScore"] - 2] = 0x90
    
    # Update checksums
    fix_high_score_checksum()


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
    
    value=20  #for WPC
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
    Uses the list from get_switches() and the 'Names' list from S.gdata['Switches'].
    If a name is empty, display 'NotUsed' instead.
    """
    switch_values = get_switches()
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
