# This file is part of the Warped Pinball Vector (DataEast) Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Data East DataMapper

Translation layer between machine data formats (shadow RAM, JSON configs)
and the MicroPython application. Handles all data format conversions including
BCD scores, packed initials, and other machine-specific encodings.
"""

from logger import logger_instance
log = logger_instance

import SharedState as S
from Shadow_Ram_Definitions import shadowRam
import faults
    



def _bcd_to_int(bcd_bytes):
    """
    Convert BCD (Binary Coded Decimal) bytes from machine format to integer.
    """
    result = 0
    for byte in bcd_bytes:
        high_digit = (byte >> 4) & 0x0F
        low_digit = byte & 0x0F
        
        # Sanitize invalid BCD digits
        if high_digit > 9:
            high_digit = 0
        if low_digit > 9:
            low_digit = 0
            
        result = result * 100 + high_digit * 10 + low_digit
    return result


def _int_to_bcd(value, num_bytes):
    """
    Convert integer to BCD (Binary Coded Decimal) bytes for machine format.
        zero padded output 
    """
    result = bytearray(num_bytes)
    for i in range(num_bytes - 1, -1, -1):
        low_digit = value % 10
        value //= 10
        high_digit = value % 10
        value //= 10
        result[i] = (high_digit << 4) | low_digit
    return result

def _initials_to_bytes(initials):   
    """
       Simple ASCII encoding, padded to 3 bytes
    """
    result = bytearray(3)
    for i in range(min(3, len(initials))):
        c = initials[i]
        result[i] = ord(c) if ((c >= 'A' and c <= 'Z') or (c >= 'a' and c <= 'z') or (c >= '0' and c <= '9')) else ord(' ')
    return result

def _bytes_to_initials(initial_bytes):   
    """
       Simple ASCII decoding
    """
    result = ""
    for byte in initial_bytes[:3]:  # Typically 3 characters
        if 32 <= byte <= 126:  # Printable ASCII range
            result += chr(byte)
        else:
            result += " "
    return result.strip()





def read_high_scores():
    """
    Read and decode the high scores
        Returns with 6 or 4 numeric high scores
        and intitals intials
    """
    highScores = [["", 0], ["", 0], ["", 0], ["", 0], ["", 0], ["", 0] ]
    print("HIGH SCORES: DataMapper ")  #,highScores)

    # Validate HighScores configuration exists
    if "HighScores" not in S.gdata:
        log.log("HighScores configuration missing")
        return highScores

    try:
        if S.gdata["HighScores"]["Type"] < 20:  
            log.log("Data Mapper: HS return less than 20")
            return highScores

        NumberOfScores=S.gdata["HighScores"]["NumberOfScores"]
    except KeyError as e:
        log.log(f"HighScores config missing field: {e}")
        return highScores
    
    try:
        if S.gdata["HighScores"]["Type"] == 20:  
            for idx in range(NumberOfScores):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]           
                scoreBytes = ( shadowRam[scoreAddress : scoreAddress + 4] ) 
                highScores[idx][1] = _bcd_to_int(scoreBytes)
                highScores[idx][1] = highScores[idx][1] * S.gdata["HighScores"].get("Multiplier", 1)

        elif S.gdata["HighScores"]["Type"] == 24:          
            for idx in range(NumberOfScores):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]            
                scoreAddressMSB = S.gdata["HighScores"]["ScoreAdr"] + 24 + idx   # one MSByte         
        
                scoreBytes = [shadowRam[scoreAddressMSB]]   #One MSbyte
                scoreBytes.extend( shadowRam[scoreAddress : scoreAddress + 4] ) 

                #print("raw bytes",idx,scoreBytes)

                highScores[idx][1] = _bcd_to_int(scoreBytes)
                if highScores[idx][1] < 1000:
                    highScores[idx][1] = 0      

        elif S.gdata["HighScores"]["Type"] == 25:  
            for idx in range(NumberOfScores):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]
                scoreBytes = ( shadowRam[scoreAddress : scoreAddress + 5] ) 
                highScores[idx][1] = _bcd_to_int(scoreBytes)
                
        elif S.gdata["HighScores"]["Type"] == 27:  
            for idx in range(NumberOfScores):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]
                # Each byte contains only one digit (0-9) in lower nibble
                rawBytes = shadowRam[scoreAddress : scoreAddress + 7]            
                # Pack pairs of digits into BCD bytes
                packedBytes = bytearray()
                for i in range(0, len(rawBytes), 2):
                    high_digit = rawBytes[i] & 0x0F
                    low_digit = rawBytes[i + 1] & 0x0F if (i + 1) < len(rawBytes) else 0
                    packedBytes.append((high_digit << 4) | low_digit)
                
                highScores[idx][1] = _bcd_to_int(packedBytes)
        else:
            log.log(f"Unknown HighScores Type: {S.gdata['HighScores']['Type']}")
        
        #scores done now add intiials
        if "InitialAdr" in S.gdata["HighScores"] and S.gdata["HighScores"]["InitialAdr"] != 0:
            for idx in range(NumberOfScores):
                initial_start = S.gdata["HighScores"]["InitialAdr"] + idx * S.gdata["HighScores"]["InitialSpacing"]
                initials_bytes = shadowRam[initial_start : initial_start + 3]               
                try:
                    highScores[idx][0] = bytes(initials_bytes).decode("ascii")   #todo: normal ascii - need to use func some games have non standard symbols
                except (UnicodeDecodeError, ValueError) as e:
                    log.log(f"Invalid initials data at index {idx}: {e}")
                    highScores[idx][0] = ""
                    
                if highScores[idx][0] in ["???", "", None, "   "]:  # no player, allow claim
                    highScores[idx][0] = ""
            
        print("HIGH SCORES: $$$$$$$$$$$  ",highScores)

    except (IndexError, KeyError, ValueError) as e:        
        log.log(f"High score read error: {e}")

    return highScores




def write_high_scores(highScores):
    """
        Write high scores and initials to shadow RAM.
        
        Args:
            highScores: List of [initials, score] pairs, e.g. [["AAA", 10000], ["BBB", 5000], ...]
                    Can contain 4 or 6 entries (only writes as many as config allows)
        
        Returns:
            bool: True if successful, False otherwise
    """


    print("WRTIE HIGH SCORES %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")

    # Validate HighScores configuration exists
    if "HighScores" not in S.gdata:    
        log.log("HighScores configuration missing")
        return False

    try:
        if S.gdata["HighScores"]["Type"] < 20:  
            log.log("Data Mapper: HS Type < 20, write not supported")
            return False

        NumberOfScores = S.gdata["HighScores"]["NumberOfScores"]
    except KeyError as e:
        log.log(f"HighScores config missing field: {e}")
        return False
    
    # Filter out entries with zero score and empty initials
    filtered_scores = []
    for entry in highScores:
        initials = entry[0] if entry[0] else ""
        score = entry[1] if len(entry) > 1 else 0
        # Keep entry if it has either non-empty initials or non-zero score
        if initials.strip() or score > 0:
            filtered_scores.append(entry)
    
    # Limit to the number of scores the config supports
    entries_to_write = min(len(filtered_scores), NumberOfScores)
    
    # Use filtered list for writing
    highScores = filtered_scores
    
    try:
        if S.gdata["HighScores"]["Type"] == 20:
            # Type 20: 4-byte BCD scores with multiplier
            for idx in range(entries_to_write):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]
                
                # Apply reverse multiplier if present
                score = highScores[idx][1]
                multiplier = S.gdata["HighScores"].get("Multiplier", 1)
                if multiplier > 1:
                    score = score // multiplier
                
                # Convert to 4-byte BCD
                scoreBytes = _int_to_bcd(score, 4)
                shadowRam[scoreAddress : scoreAddress + 4] = scoreBytes

        elif S.gdata["HighScores"]["Type"] == 24:
            # Type 24: 5-byte BCD (1 MSB + 4 bytes)
            for idx in range(entries_to_write):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]
                scoreAddressMSB = S.gdata["HighScores"]["ScoreAdr"] + 24 + idx
                
                score = highScores[idx][1]
                scoreBytes = _int_to_bcd(score, 5)
                
                # Write MSB separately
                shadowRam[scoreAddressMSB] = scoreBytes[0]
                shadowRam[scoreAddress : scoreAddress + 4] = scoreBytes[1:5]

                #second storage location in NV ram area?
                if S.gdata["HighScores"].get("ScoreAdrNV",0) != 0:
                    scoreAddress = S.gdata["HighScores"]["ScoreAdrNV"] + idx * S.gdata["HighScores"]["ScoreSpacing"]
                    scoreAddressMSB = S.gdata["HighScores"]["ScoreAdrNV"] + 24 + idx
                    shadowRam[scoreAddressMSB] = scoreBytes[0]
                    shadowRam[scoreAddress : scoreAddress + 4] = scoreBytes[1:5]


        elif S.gdata["HighScores"]["Type"] == 25:
            # Type 25: 5-byte BCD scores
            for idx in range(entries_to_write):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]
                
                score = highScores[idx][1]
                
                # Convert to 5-byte BCD
                scoreBytes = _int_to_bcd(score, 5)
                shadowRam[scoreAddress : scoreAddress + 5] = scoreBytes
                
        elif S.gdata["HighScores"]["Type"] == 27:
            # Type 27: 7 bytes, one digit per byte in lower nibble
            for idx in range(entries_to_write):
                scoreAddress = S.gdata["HighScores"]["ScoreAdr"] + idx * S.gdata["HighScores"]["ScoreSpacing"]
                
                score = highScores[idx][1]
                
                # Convert to BCD first (4 bytes = 8 digits, but we need 7)
                scoreBytes = _int_to_bcd(score, 4)
                
                # Unpack BCD bytes into individual digit bytes
                digitBytes = bytearray(7)
                digit_idx = 6  # Start from rightmost position
                for bcd_byte in reversed(scoreBytes):
                    low_digit = bcd_byte & 0x0F
                    high_digit = (bcd_byte >> 4) & 0x0F
                    
                    if digit_idx >= 0:
                        digitBytes[digit_idx] = low_digit
                        digit_idx -= 1
                    if digit_idx >= 0:
                        digitBytes[digit_idx] = high_digit
                        digit_idx -= 1
                
                shadowRam[scoreAddress : scoreAddress + 7] = digitBytes
        else:
            faults.raise_fault(faults.CONF01, f"Unknown HighScores Type: {S.gdata['HighScores']['Type']}")
            log.log(f"Unknown HighScores Type: {S.gdata['HighScores']['Type']}")
            return False
        
        # Write initials if configured
        if "InitialAdr" in S.gdata["HighScores"] and S.gdata["HighScores"]["InitialAdr"] != 0:
            for idx in range(entries_to_write):
                initial_start = S.gdata["HighScores"]["InitialAdr"] + idx * S.gdata["HighScores"]["InitialSpacing"]
                
                # Get initials (ensure it's a string, default to spaces if empty)
                initials = highScores[idx][0]
                if not isinstance(initials, str) or not initials:
                    initials = "   "
                
                # Validate and pad initials to 3 characters
                initials = validate_initials(initials)
                
                # Convert to bytes (simple ASCII encoding)
                initials_bytes = _initials_to_bytes(initials)
                print("wirte intiial s-  - - - ",idx,initials,initial_start)
                shadowRam[initial_start : initial_start + 3] = initials_bytes
        
        log.log(f"Successfully wrote {NumberOfScores} high scores to shadow RAM")
        _set_adjustment_checksum()
        return True

    except (IndexError, KeyError, ValueError) as e:
        faults.raise_fault(faults.SFWR00, f"Error writing high scores: {e}")
        log.log(f"High score write error: {e}")
        return False




def get_ball_in_play():
    """
        Get the ball in play number (1-5). 0 if game over or no config
        only accept Data East TYPE 20
    """
    try:
        ball_in_play = S.gdata["BallInPlay"]
        if ball_in_play["Type"] == 20:
            ret_value = shadowRam[ball_in_play["Address"]]
            return ret_value

    except Exception as e:
        log.log(f"DATAMAP: error in get_ball_in_play: {e}")
    return 0



def get_in_play_data():
    """
    Return dict with whatever we can gather up:
        players in game
        player up
        live scores
        game active (boolean)
    If game not active - fill with mostly zeroes    
    """
    data = {
        "GameActive": False,
        "BallInPlay": 0,
        "PlayerUp": 0,
        "PlayersInGame": 0,
        "Scores": [0, 0, 0, 0]
    }
    
    # Check if InPlay configuration exists and is valid
    if "InPlay" not in S.gdata or S.gdata["InPlay"].get("Type", 0) not in range(20, 30):
        return data


    print("INPLAYYYYYYYYYYYYYYYYYYYyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy")

    data["BallInPlay"] = get_ball_in_play()    
    
    if data["BallInPlay"] == 0:
        return data
    
    # Game is active
    data["GameActive"] = True
    
    # Get player up
    try:
        if S.gdata.get("InPlay", {}).get("PlayerUp", 0) != 0:
            adr = S.gdata["InPlay"]["PlayerUp"]
            data["PlayerUp"] = shadowRam[adr]
    except Exception:
        pass
    
    # Get players in game count
    try:
        if S.gdata.get("InPlay", {}).get("PlayersInGame", 0) != 0:
            adr = S.gdata["InPlay"]["PlayersInGame"]
            data["PlayersInGame"] = shadowRam[adr]
    except Exception as e:
        log.log(f"DATAMAP: error getting players in game: {e}")
    
    # Get live scores for all 4 players
    try:       
        scores = [0, 0, 0, 0]
    
        if S.gdata["InPlay"]["Type"] == 20:
            # Type 20: Data East all in a row with multiplier
            for idx in range(4):
                score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * S.gdata["InPlay"]["ScoreSpacing"]
                score_bytes = shadowRam[score_start : score_start + S.gdata["InPlay"]["ScoreBytes"]]
                scores[idx] = _bcd_to_int(score_bytes) * S.gdata["InPlay"].get(["ScoreMultiplier"],1)
        
        elif S.gdata["InPlay"]["Type"] == 24:
            # Type 21: Data East break after fourth byte, assume 5 bytes total
            for idx in range(4):
                score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * 4
                score_fifth_byte_adr = S.gdata["InPlay"]["ScoreAdr"] + 16 + idx
                
                score_bytes = [shadowRam[score_fifth_byte_adr]]
                score_bytes.extend(shadowRam[score_start : score_start + 4])
                scores[idx] = _bcd_to_int(score_bytes)

        elif S.gdata["InPlay"]["Type"] == 25:
            # Type 25: 5-byte BCD scores
            for idx in range(4):
                scoreAddress = S.gdata["InPlay"]["ScoreAdr"] + idx * S.gdata["InPlay"]["ScoreSpacing"]                
                scoreBytes = ( shadowRam[scoreAddress : scoreAddress + 5] ) 
                scores[idx] = _bcd_to_int(scoreBytes)

        elif S.gdata["InPlay"]["Type"] == 27:
            for idx in range(4):
                scoreAddress = S.gdata["InPlay"]["ScoreAdr"] + idx * S.gdata["InPlay"]["ScoreSpacing"]
                # Each byte contains only one digit (0-9) in lower nibble
                rawBytes = shadowRam[scoreAddress : scoreAddress + 7]            
                # Pack pairs of digits into BCD bytes
                packedBytes = bytearray()
                for i in range(0, len(rawBytes), 2):
                    high_digit = rawBytes[i] & 0x0F
                    low_digit = rawBytes[i + 1] & 0x0F if (i + 1) < len(rawBytes) else 0
                    packedBytes.append((high_digit << 4) | low_digit)
                
                scores[idx] = _bcd_to_int(packedBytes)

        data["Scores"] = scores
            
    except Exception as e:
        log.log(f"DATAMAP: error getting in-play scores: {e}")
    
    return data



def _set_adjustment_checksum():
    """
        calculate and write checksum into shadowram
    """
    if S.gdata["Adjustments"].get("Type", 0) == 20:
        startAdr = S.gdata["Adjustments"]["ChecksumStartAdr"]
        endAdr = S.gdata["Adjustments"]["ChecksumEndAdr"]
        resultAdr = S.gdata["Adjustments"]["ChecksumResultAdr"]
        checksum=0
        for i in range(startAdr,endAdr):
            checksum = checksum + shadowRam[i]
        shadowRam[resultAdr]=checksum


def turn_off_high_score_rewards():
    if S.gdata["Adjsutments"]["Type"] == 20:
        #DataStore.read_record("extras", 0)["enter_initials_on_game"]:
        print("SCORE: Disabling HS rewards")
        for key, value in S.gdata["HSRewards"].items():
            if key.startswith("HS"):  # Check if the key starts with 'HS'
                shadowRam[value] = S.gdata["HSRewards"]["DisableByte"]


def set_message(message):
    """
        sets the custom message on the game display (fit to space avialable)
        turns on custom message
        and fixes checksum
    """  
    if S.gdata["DisplayMessage"].get("Type", 0) != 0:
        if S.gdata["DisplayMessage"]["Type"]==20:
            # 12 x 3 lines
            s=format_text_lines(message,12,3)

        elif S.gdata["DisplayMessage"]["Type"]==21:
            # 38 x 1 line
            s=format_text_lines(message,38,1)

        elif S.gdata["DisplayMessage"]["Type"]==22:
            # 14 x 3 lines
            s=format_text_lines(message,14,3)

        elif S.gdata["DisplayMessage"]["Type"]==23:
            # 16 x 3 lines
            s=format_text_lines(message,16,3)

        elif S.gdata["DisplayMessage"]["Type"]==24:
            # 21(24) x 2 lines.  21 visible, 24 in line
            s=format_text_lines(message,21,2)

        #copy string to shadow ram
        adr = S.gdata["DisplayMessage"]["Address"]
        
        # Write all lines contiguously to shadowRam
        offset = 0
        for line in s:
            for char in line:
                shadowRam[adr + offset] = ord(char)
                offset += 1
            if S.gdata["DisplayMessage"]["Type"]==24:
                offset += 3

        shadowRam[S.gdata["Adjustments"]["CustomMessageOn"]]=1

        _set_adjustment_checksum()



def message_off():
    """
        turn off display of the custom message
        fix checksum
    """ 
    shadowRam[S.gdata["Adjustments"]["CustomMessageOn"]]=0
    _set_adjustment_checksum()



def format_text_lines(text, line_length, num_lines):
    """
        Break a text string into multiple lines of fixed length.
        Tries to break on spaces first, then periods near center if needed.
        If text is too long, drops whole words from the end (keeping all numbers/periods).
    """
    
    #First check if text will fit in available space
    max_chars = line_length * num_lines
    text = text.strip()
    
    # Split into tokens (words and number groups)
    tokens = text.split()
    
    # Identify which tokens contain numbers or are just periods
    def has_number_or_period(token):
        return any(c.isdigit() or c == '.' for c in token)
    
    # Check if total text is too long - if so, drop words (but keep numbers)
    needs_word_dropping = len(text) > max_chars
    # Don't drop words just because a number is longer than one line - we can split numbers at periods
    
    # If we need to drop words, remove them (but keep numbers and periods)
    if needs_word_dropping:
        # Separate tokens into keepers (with numbers/periods) and droppable (pure words)
        keepers = []
        droppable = []
        for i, token in enumerate(tokens):
            if has_number_or_period(token):
                keepers.append((i, token))
            else:
                droppable.append((i, token))
        
        # Start with all keeper tokens
        result_tokens = dict(keepers)
        
        # Add droppable tokens from the beginning until we would exceed max_chars
        for idx, token in droppable:
            test_tokens = dict(result_tokens)
            test_tokens[idx] = token
            # Reconstruct in order
            test_text = ' '.join(test_tokens[i] for i in sorted(test_tokens.keys()))
            if len(test_text) <= max_chars:
                result_tokens[idx] = token
            else:
                break
        
        # Reconstruct text in original order
        text = ' '.join(result_tokens[i] for i in sorted(result_tokens.keys()))
    
    lines = []
    remaining = text
    
    for i in range(num_lines):
        if not remaining:
            # No more text, duplicate the previous line if available
            if lines:
                lines.append(lines[-1])
            else:
                lines.append(' ' * line_length)
            continue
        
        if len(remaining) <= line_length:
            # Remaining text fits in this line, center it with spaces on both sides
            padding = line_length - len(remaining)
            left_pad = padding // 2
            right_pad = padding - left_pad
            lines.append(' ' * left_pad + remaining + ' ' * right_pad)
            remaining = ""
            continue
        
        # Need to break the line
        break_pos = -1
        
        # First try to break on space within line_length
        for j in range(line_length - 1, -1, -1):
            if j < len(remaining) and remaining[j] == ' ':
                # Check if this break would leave content that won't fit
                lines_left = num_lines - i - 1
                if lines_left > 0:
                    remaining_after_break = remaining[j:].strip()
                    if len(remaining_after_break) > lines_left * line_length:
                        # This break would leave too much content, skip it
                        continue
                break_pos = j
                break
        
        if break_pos == -1:
            # No space found, try to break on period near center
            # Check if this looks like a number string (contains digits)
            has_digits = any(c.isdigit() for c in remaining[:min(line_length+5, len(remaining))])
            
            if has_digits:
                # For number strings, look for period near center to split at
                center = line_length // 2
                
                # Look for period near center (expanding search from center)
                # Search a bit beyond line_length for number strings
                search_range = min(line_length + 5, len(remaining))
                for offset in range(search_range):
                    # Check positions around center
                    pos_right = center + offset
                    pos_left = center - offset
                    
                    if pos_right < search_range and pos_right < len(remaining) and remaining[pos_right] == '.':
                        break_pos = pos_right + 1  # Include the period
                        break
                    if pos_left >= 0 and pos_left < len(remaining) and remaining[pos_left] == '.':
                        break_pos = pos_right + 1  # Include the period
                        break
            else:
                # For non-number strings, only search within line_length
                center = line_length // 2
                for offset in range(center):
                    pos_right = center + offset
                    pos_left = center - offset
                    
                    if pos_right < line_length and pos_right < len(remaining) and remaining[pos_right] == '.':
                        break_pos = pos_right + 1
                        break
                    if pos_left >= 0 and pos_left < len(remaining) and remaining[pos_left] == '.':
                        break_pos = pos_left + 1
                        break
        
        if break_pos == -1 or break_pos > line_length:
            # No good break point, just cut at line_length
            break_pos = line_length
        
        # Extract this line and pad with spaces on both sides
        line = remaining[:break_pos].strip()
        padding = line_length - len(line)
        left_pad = padding // 2
        right_pad = padding - left_pad
        lines.append(' ' * left_pad + line + ' ' * right_pad)
        
        # Move to next part
        remaining = remaining[break_pos:].strip()
    
    return lines




def validate_initials(initials):
    """
    Validate and sanitize player initials.
    
    Args:
        initials: str, proposed initials
        
    Returns:
        str: Validated initials (uppercase, alphanumeric, 3 chars)
    """
    # Ensure initials is a string
    if not isinstance(initials, str):
        initials = str(initials) if initials else ""
    
    if not initials:
        return "   "
    
    # Convert to uppercase and filter to alphanumeric
    clean = "".join(c for c in initials.upper() if (c >= 'A' and c <= 'Z') or (c >= '0' and c <= '9'))
    
    # Pad or truncate to 3 characters
    if len(clean) < 3:
        clean = clean + ' ' * (3 - len(clean))
    else:
        clean = clean[:3]
    
    return clean


