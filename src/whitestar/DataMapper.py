# This file is part of the Warped Pinball Vector (Whitestar) Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Whitestar DataMapper

Translation layer between Whitestar (Sega / Stern 1995-2006) machine data
formats (shadow RAM, JSON configs) and the MicroPython application.

Config types handled here (see ConfigTools/Doc/config_type.md):
    BallInPlay     40  plain ball byte, 0 when no game; BallsPerGameAdr (BCD adjustment)
    InPlay         40  5 byte packed BCD scores, 5 apart; PlayerUp 0 = no game; Players 1-MaxPlayers
    HighScores     40  NumberOfScores x 5 byte BCD scores in a row, ASCII names (3 initials or
                       10 character names), ScoreAdrNV backup copy inside the adjustment checksum.
                       All 31 game configs (traced from the ROMs 2026-11-14, untested on a machine).
    Adjustments    40  main block at $1E00 with an 8 bit sum, BCD checked extra block(s)
    DisplayMessage 40  36 character custom message (3 x 12), 41 = 48 characters (2 x 24)
    Switches       40  the game's own switch health tables plus a games counter (read mostly)

Everything the common modules (GameStatus, Formats, Switches, backend) call
on a DataMapper is provided here, plus the Whitestar specific helpers used
by Adjustments, displayMessage, ScoreTrack and the Whitestar Switches module.
"""

from logger import logger_instance
log = logger_instance

import SharedState as S
from Shadow_Ram_Definitions import shadowRam

BALL_IN_PLAY_TYPE = 40
IN_PLAY_TYPE = 40
HIGH_SCORES_TYPE = 40
ADJUSTMENTS_TYPE = 40
DISPLAY_MESSAGE_TYPES = (40, 41)
SWITCHES_TYPE = 40

# Whitestar RAM is 8K; anything outside is a config error, never a RAM access
RAM_LENGTH = 0x2000


# ---------------------------------------------------------------------------
# BCD / text helpers
# ---------------------------------------------------------------------------
def _bcd_to_int(bcd_bytes):
    """Packed BCD bytes (most significant first) to int. Invalid nibbles read as 0."""
    result = 0
    for byte in bcd_bytes:
        high_digit = (byte >> 4) & 0x0F
        low_digit = byte & 0x0F
        if high_digit > 9:
            high_digit = 0
        if low_digit > 9:
            low_digit = 0
        result = result * 100 + high_digit * 10 + low_digit
    return result


def _int_to_bcd(value, num_bytes):
    """int to packed BCD, most significant byte first, zero padded / truncated to num_bytes."""
    if value < 0:
        value = 0
    result = bytearray(num_bytes)
    for i in range(num_bytes - 1, -1, -1):
        low_digit = value % 10
        value //= 10
        high_digit = value % 10
        value //= 10
        result[i] = (high_digit << 4) | low_digit
    return result


def bcd_byte_to_int(byte):
    """One BCD byte to int (0-99). Returns -1 when either nibble is not 0-9."""
    high_digit = (byte >> 4) & 0x0F
    low_digit = byte & 0x0F
    if high_digit > 9 or low_digit > 9:
        return -1
    return high_digit * 10 + low_digit


def is_bcd(data):
    """True when every nibble of data is 0-9 (what the Whitestar power-on check demands)."""
    for byte in data:
        if (byte & 0x0F) > 9 or (byte >> 4) > 9:
            return False
    return True


def _initials_validate(initials):
    """
    Condition initials for the machine: A-Z and space only, 3 characters.
    '@' and digits become spaces, lower case is raised. A single 'A' means
    the player timed out during entry, it is treated as no initials.

    Returns (clean_str, bytearray(3)) of plain ASCII.
    """
    if not isinstance(initials, str):
        initials = str(initials) if initials else ""

    clean_str = ""
    for c in initials.upper():
        code = ord(c)
        if 0x41 <= code <= 0x5A:
            clean_str += c
        elif c in " @" or 0x30 <= code <= 0x39:
            clean_str += " "

    if clean_str.strip() == "A":
        clean_str = "   "

    clean_str = (clean_str + "   ")[:3]
    result_bytes = bytearray(3)
    for i in range(3):
        result_bytes[i] = ord(clean_str[i])
    return clean_str, result_bytes


def _section(name, wanted_type):
    """The config section when its Type is one of wanted_type, else None."""
    cfg = S.gdata.get(name)
    if not isinstance(cfg, dict):
        return None
    t = cfg.get("Type", 0)
    if isinstance(wanted_type, tuple):
        return cfg if t in wanted_type else None
    return cfg if t == wanted_type else None


def _read_value(data, data_format):
    """Decode a Modes / ModeChamps value: u8, BCD, u16 (little endian) or u16be."""
    if data_format == "BCD":
        return _bcd_to_int(data)
    if data_format == "u16":
        if len(data) >= 2:
            return data[0] | (data[1] << 8)
    elif data_format == "u16be":
        if len(data) >= 2:
            return (data[0] << 8) | data[1]
    elif data_format != "u8":
        log.log(f"DATAMAPPER: Unknown format '{data_format}'")
    return data[0] if len(data) > 0 else 0


# ---------------------------------------------------------------------------
# In play: players, player up, ball, game active
# ---------------------------------------------------------------------------
def _player_up_raw():
    """The PlayerUp byte as the game keeps it: 1 to Players during a game, 0 otherwise."""
    cfg = _section("InPlay", IN_PLAY_TYPE)
    if cfg is None:
        return 0
    try:
        value = shadowRam[cfg["PlayerUp"]]
        # anything above the most players the game allows is noise (unformatted RAM)
        if value > cfg.get("MaxPlayers", 6):
            return 0
        return value
    except Exception as e:
        log.log(f"DATAMAPPER: error reading player up: {e}")
    return 0


def get_game_active():
    """
    A Whitestar game is active while PlayerUp is non-zero. Game over and
    power-up clear PlayerUp, BallInPlay and Players together.
    """
    return _player_up_raw() != 0


def get_player_up():
    """
    Current player 1-4, 0 when no game is running.
    Sega titles allow 6 players; Vector tracks 4 scores, so player 5 and 6
    are reported as 0 (same convention as the Classics mapper).
    """
    value = _player_up_raw()
    return value if value <= 4 else 0


def get_players_in_game():
    """Number of players 1-4 (capped at 4 on 6 player games), 0 when no game or not configured."""
    cfg = _section("InPlay", IN_PLAY_TYPE)
    if cfg is None:
        return 0
    try:
        value = shadowRam[cfg["Players"]]
        if value > cfg.get("MaxPlayers", 6):
            return 0
        return min(value, 4)
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_players_in_game: {e}")
    return 0


def get_ball_in_play():
    """
    Ball in play 1 to balls per game, 0 when no game is running.
    BallInPlay Type 40: plain byte at Address. It is only trusted while
    PlayerUp says a game is on.
    """
    cfg = _section("BallInPlay", BALL_IN_PLAY_TYPE)
    if cfg is None:
        return 0
    try:
        if not get_game_active():
            return 0
        value = shadowRam[cfg["Address"]]
        return value if 0 < value <= 9 else 0
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_ball_in_play: {e}")
    return 0


def get_balls_per_game():
    """The balls per game adjustment (BCD, in the main adjustment block). 0 when unknown."""
    cfg = _section("BallInPlay", BALL_IN_PLAY_TYPE)
    if cfg is None or not cfg.get("BallsPerGameAdr"):
        return 0
    value = bcd_byte_to_int(shadowRam[cfg["BallsPerGameAdr"]])
    return value if 0 < value <= 9 else 0


def write_ball_in_play(ball_number):
    """
    Write the ball in play byte.

    5 means "last ball" to the Formats module. The Whitestar OS ends the
    game after the ball that equals the balls per game adjustment, so the
    adjustment value is written in that case (as on Data East).
    """
    cfg = _section("BallInPlay", BALL_IN_PLAY_TYPE)
    if cfg is None:
        return False
    try:
        if ball_number == 5:
            balls_per_game = get_balls_per_game()
            if balls_per_game:
                ball_number = balls_per_game
        shadowRam[cfg["Address"]] = ball_number & 0xFF
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: error in write_ball_in_play: {e}")
    return False


# ---------------------------------------------------------------------------
# In play scores
# ---------------------------------------------------------------------------
def _score_layout():
    """(ScoreAdr, bytes per score, spacing) for InPlay Type 40, or None."""
    cfg = _section("InPlay", IN_PLAY_TYPE)
    if cfg is None:
        return None
    return cfg["ScoreAdr"], cfg.get("BytesInScore", 5), cfg.get("ScoreSpacing", 5)


def read_in_play_scores():
    """
    The four player scores straight from shadow RAM (never the Formats scores).

    Returns:
        list: [[initials, score], ...] for players 1-4, initials always ""
    """
    in_play_scores = [["", 0], ["", 0], ["", 0], ["", 0]]
    layout = _score_layout()
    if layout is None:
        return in_play_scores
    adr, nbytes, spacing = layout
    try:
        for idx in range(4):
            start = adr + idx * spacing
            in_play_scores[idx][1] = _bcd_to_int(shadowRam[start : start + nbytes])
    except Exception as e:
        log.log(f"DATAMAPPER: in-play scores read error: {e}")
    return in_play_scores


def get_live_scores(use_format=True):
    """
    Live scores for players 1-4 as a list of 4 ints.

    With a Format active (and use_format True) the Formats module's own
    player scores are returned, otherwise the machine's scores.
    """
    try:
        if use_format is True and S.active_format.get("Id", 0) != 0:
            import Formats
            return list(Formats.player_scores)
    except Exception as e:
        log.log(f"DATAMAPPER: error getting format scores: {e}")

    return [entry[1] for entry in read_in_play_scores()]


def write_live_scores(scores):
    """Write 4 player scores (list of ints) into the machine's score blocks."""
    layout = _score_layout()
    if layout is None:
        return False
    if not isinstance(scores, (list, tuple)) or len(scores) != 4:
        log.log("DATAMAPPER: invalid scores format, expected list of 4 integers")
        return False
    adr, nbytes, spacing = layout
    try:
        for idx in range(4):
            start = adr + idx * spacing
            shadowRam[start : start + nbytes] = _int_to_bcd(int(scores[idx]), nbytes)
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: error writing in-play scores: {e}")
    return False


def get_in_play_data():
    """
    Game state for the status report and the web UI:
        GameActive, BallInPlay, PlayerUp, PlayersInGame, Scores (4 ints)
    """
    data = {
        "GameActive": False,
        "BallInPlay": 0,
        "PlayerUp": 0,
        "PlayersInGame": 0,
        "Scores": [0, 0, 0, 0],
    }
    if _section("InPlay", IN_PLAY_TYPE) is None:
        return data

    data["GameActive"] = get_game_active()
    data["BallInPlay"] = get_ball_in_play()
    data["PlayerUp"] = get_player_up()
    data["PlayersInGame"] = get_players_in_game()
    data["Scores"] = get_live_scores()
    return data


def get_flipper_state():
    """
    Flipper switch state (left, right). No Whitestar config has a Flippers
    section yet; the WPC bit layouts (Type 10 / 11) are accepted if one is added.
    """
    try:
        cfg = _section("Flippers", (10, 11))
        if cfg is not None:
            v = shadowRam[cfg["Address"]]
            if cfg["Type"] == 10:
                return (v & 0x80) != 0, (v & 0x20) != 0
            return (v & 0x02) != 0, (v & 0x01) != 0
    except Exception as e:
        log.log(f"DATAMAPPER: error in get_flipper_state: {e}")
    return False, False


# ---------------------------------------------------------------------------
# High scores (Type 40). Type 0 = not available.
#
#   ScoreAdr        NumberOfScores x 5 byte packed BCD, MSB first, 5 apart
#   InitialAdr      one name per entry, InitialSpacing apart, ASCII padded with
#                   spaces. Early Sega games keep 3 initials (spacing 3), Starship
#                   Troopers 3 letters + 1 non-ASCII byte (spacing 4, the 4th byte
#                   is left alone), the later games 10 character names (spacing 10).
#   ScoreAdrNV      the "backup high score" adjustments: NumberOfScores x 5 bytes
#                   inside the summed main adjustment block. Every high score reset
#                   (factory, operator, every-N-games) copies them into the table,
#                   so they are kept equal to what Vector writes.
#
# The game's power-on check needs every nibble of the score table to be 0-9 or it
# clears all of NVRAM; scores are only ever written as packed BCD here. On the late
# Stern games #1 is the Grand Champion (kept through the periodic reset).
# ---------------------------------------------------------------------------
NAME_PAD_MIN_SPACING = 5    # spacing 3 and 4 hold initials only; 10 is a padded name
PLACEHOLDER_STEP = 100      # placeholder scores 100, 200, ... are below every score cut-off


def high_scores_supported():
    return _section("HighScores", HIGH_SCORES_TYPE) is not None


def _number_of_scores(cfg):
    return cfg.get("NumberOfScores", 4)


def _max_score(nbytes):
    """Largest score the table can hold (10 digits for 5 bytes)."""
    return 10 ** (nbytes * 2) - 1


def _name_bytes(initials, spacing):
    """
    The bytes to write for one name: 3 initials, then spaces up to the name
    length on games that keep longer names. Spacing 3 and 4 write 3 bytes only.
    """
    _, initials_bytes = _initials_validate(initials)
    if spacing >= NAME_PAD_MIN_SPACING:
        return initials_bytes + bytearray(b" " * (spacing - 3))
    return initials_bytes


def read_high_scores():
    """
    Read the machine high score table.

    Returns:
        list: [[initials, score], ...], NumberOfScores entries (at least 4),
              highest first as the game keeps them. Blank initials are "".
              All zero when HighScores is Type 0.
    """
    cfg = _section("HighScores", HIGH_SCORES_TYPE)
    count = 4 if cfg is None else max(4, _number_of_scores(cfg))
    high_scores = [["", 0] for _ in range(count)]
    if cfg is None:
        return high_scores

    try:
        nbytes = cfg.get("BytesInScore", 5)
        multiplier = cfg.get("Multiplier", 1)
        for idx in range(_number_of_scores(cfg)):
            start = cfg["ScoreAdr"] + idx * cfg.get("ScoreSpacing", nbytes)
            high_scores[idx][1] = _bcd_to_int(shadowRam[start : start + nbytes]) * multiplier

        if cfg.get("InitialAdr", 0):
            for idx in range(_number_of_scores(cfg)):
                start = cfg["InitialAdr"] + idx * cfg.get("InitialSpacing", 3)
                raw = "".join(chr(b) for b in shadowRam[start : start + 3])
                clean, _ = _initials_validate(raw)
                high_scores[idx][0] = "" if clean.strip() == "" or clean == "???" else clean
    except Exception as e:
        log.log(f"DATAMAPPER: high score read error: {e}")
    return high_scores


def write_high_scores(high_scores):
    """
    Write a high score table ([[initials, score], ...]) to the machine.

    The whole table is written: entries are sorted highest first, and any
    slots left over get low placeholder scores with blank names, so the game
    never sees an unsorted table or stale entries below the new ones. Scores
    are clamped to what 5 BCD bytes hold. The backup copy at ScoreAdrNV is
    kept equal and the adjustment checksum is re-summed afterwards.
    """
    cfg = _section("HighScores", HIGH_SCORES_TYPE)
    if cfg is None:
        return False

    count = _number_of_scores(cfg)
    nbytes = cfg.get("BytesInScore", 5)
    multiplier = cfg.get("Multiplier", 1)

    entries = []
    for entry in high_scores:
        try:
            initials = entry[0] if entry and entry[0] else ""
            score = int(entry[1]) if entry and len(entry) > 1 and entry[1] else 0
        except (TypeError, ValueError):
            continue
        if score < 0:
            score = 0
        if initials.strip() or score > 0:
            entries.append((initials, score))
    entries.sort(key=lambda e: e[1], reverse=True)
    entries = entries[:count]

    # fill the rest of the table with descending placeholders below the lowest real entry
    previous = entries[-1][1] if entries else None
    for slot in range(len(entries), count):
        placeholder = (count - slot) * PLACEHOLDER_STEP
        if previous is not None and placeholder >= previous:
            placeholder = max(0, previous - 1)
        entries.append(("", placeholder))
        previous = placeholder

    try:
        spacing = cfg.get("ScoreSpacing", nbytes)
        name_spacing = cfg.get("InitialSpacing", 3)
        backup = cfg.get("ScoreAdrNV", 0)
        max_score = _max_score(nbytes)
        for idx, (initials, score) in enumerate(entries):
            if multiplier > 1:
                score = score // multiplier
            score_bcd = _int_to_bcd(min(score, max_score), nbytes)
            start = cfg["ScoreAdr"] + idx * spacing
            shadowRam[start : start + nbytes] = score_bcd
            if backup:
                start = backup + idx * spacing
                shadowRam[start : start + nbytes] = score_bcd

            if cfg.get("InitialAdr", 0):
                start = cfg["InitialAdr"] + idx * name_spacing
                name = _name_bytes(initials, name_spacing)
                shadowRam[start : start + len(name)] = name

        _set_adjustment_checksum()
        log.log(f"DATAMAPPER: wrote {count} high scores to shadow RAM")
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: high score write error: {e}")
    return False


def write_high_score(index, initials, score):
    """
    Change one entry of the machine table (0 = top) without touching the
    others: writes the score (and its backup copy) and the name, then fixes
    the adjustment checksum. The caller keeps the table sorted.
    """
    cfg = _section("HighScores", HIGH_SCORES_TYPE)
    if cfg is None or not 0 <= index < _number_of_scores(cfg):
        return False
    try:
        nbytes = cfg.get("BytesInScore", 5)
        spacing = cfg.get("ScoreSpacing", nbytes)
        multiplier = cfg.get("Multiplier", 1)
        score = max(0, int(score))
        if multiplier > 1:
            score = score // multiplier
        score_bcd = _int_to_bcd(min(score, _max_score(nbytes)), nbytes)
        start = cfg["ScoreAdr"] + index * spacing
        shadowRam[start : start + nbytes] = score_bcd
        if cfg.get("ScoreAdrNV", 0):
            start = cfg["ScoreAdrNV"] + index * spacing
            shadowRam[start : start + nbytes] = score_bcd
        if cfg.get("InitialAdr", 0):
            name_spacing = cfg.get("InitialSpacing", 3)
            start = cfg["InitialAdr"] + index * name_spacing
            name = _name_bytes(initials, name_spacing)
            shadowRam[start : start + len(name)] = name
        _set_adjustment_checksum()
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: high score write error: {e}")
    return False


def remove_machine_scores():
    """
    Replace the machine high scores with low placeholders (blank initials)
    so that any real score beats them and the game asks for initials.
    """
    cfg = _section("HighScores", HIGH_SCORES_TYPE)
    if cfg is None:
        return
    log.log("DATAMAPPER: Remove machine scores type 40")
    count = _number_of_scores(cfg)
    write_high_scores([["", (count - idx) * 100] for idx in range(count)])


def match_in_play_with_high_score_initials(in_play_scores, high_scores):
    """
    Copy initials from the high score table onto the in-play scores with
    the same value. Each high score entry is used at most once.
    """
    used = []
    for in_play_score in in_play_scores:
        for idx, high_score in enumerate(high_scores):
            if idx not in used and in_play_score[1] == high_score[1] and in_play_score[1] != 0:
                in_play_score[0] = high_score[0]
                used.append(idx)
                break
    return in_play_scores


# ---------------------------------------------------------------------------
# Adjustments: checksum and custom message switch
# ---------------------------------------------------------------------------
def adjustment_ranges():
    """
    (main_start, main_end, checksum_adr, extra_start, extra_end, extra2_start, extra2_end)
    for Adjustments Type 40 (ends inclusive), or None. Absent blocks are (0, 0).
    """
    cfg = _section("Adjustments", ADJUSTMENTS_TYPE)
    if cfg is None:
        return None
    r = (
        cfg.get("ChecksumStartAdr", 0),
        cfg.get("ChecksumEndAdr", 0),
        cfg.get("ChecksumResultAdr", 0),
        cfg.get("ExtraStartAdr", 0),
        cfg.get("ExtraEndAdr", 0),
        cfg.get("Extra2StartAdr", 0),
        cfg.get("Extra2EndAdr", 0),
    )
    if r[0] == 0 or r[1] < r[0] or r[2] == 0:
        return None
    for adr in r:
        if adr >= RAM_LENGTH:
            log.log("DATAMAPPER: adjustment address outside RAM")
            return None
    return r


def _set_adjustment_checksum():
    """
    Re-sum the main adjustment block: 8 bit sum, no complement, into ChecksumResultAdr.
    Returns True when the stored byte already matched (nothing changed).
    """
    r = adjustment_ranges()
    if r is None:
        return True
    start, end, result_adr = r[0], r[1], r[2]
    checksum = sum(shadowRam[start : end + 1]) & 0xFF
    matched = shadowRam[result_adr] == checksum
    shadowRam[result_adr] = checksum
    return matched


def fix_adjustment_checksum():
    """Public name for the boot time checksum repair (see Memory_Main)."""
    return _set_adjustment_checksum()


def adjustments_valid():
    """True when the main and extra blocks are all BCD and the sum matches, i.e. the game will accept them."""
    r = adjustment_ranges()
    if r is None:
        return True
    start, end, result_adr, extra_start, extra_end = r[0], r[1], r[2], r[3], r[4]
    if not is_bcd(shadowRam[start : end + 1]):
        return False
    if extra_start and extra_end >= extra_start and not is_bcd(shadowRam[extra_start : extra_end + 1]):
        return False
    return shadowRam[result_adr] == (sum(shadowRam[start : end + 1]) & 0xFF)


def enable_message(enable):
    """
    Turn the custom message on (1) or off (0). CustomMessageOn sits in the
    summed main block, so the checksum is fixed afterwards. Nothing is
    written when the byte already has the requested value.
    """
    cfg = _section("Adjustments", ADJUSTMENTS_TYPE)
    if cfg is None:
        return
    adr = cfg.get("CustomMessageOn")
    if not adr:
        return
    value = 1 if enable else 0
    if shadowRam[adr] == value:
        return
    shadowRam[adr] = value
    _set_adjustment_checksum()


# ---------------------------------------------------------------------------
# Display message (Types 40 and 41)
# ---------------------------------------------------------------------------
def _message_layout():
    """(line length, number of lines) for the configured DisplayMessage type, or None."""
    cfg = _section("DisplayMessage", DISPLAY_MESSAGE_TYPES)
    if cfg is None or not cfg.get("Address"):
        return None
    if cfg["Type"] == 40:
        return 12, 3   # 36 characters, same layout as Data East Type 20
    return 24, 2       # 48 characters


def _message_char(c):
    """Only space, A-Z, digits and '.' are safe on the display; everything else becomes a space."""
    c = c.upper()
    if ("A" <= c <= "Z") or ("0" <= c <= "9") or c == ".":
        return c
    return " "


def set_message(message):
    """
    Put a text message on the game's custom message (attract mode) and turn it on.
    The text is fitted to the display's lines; see format_text_lines.
    """
    layout = _message_layout()
    if layout is None:
        return False
    line_length, num_lines = layout
    cfg = S.gdata["DisplayMessage"]
    try:
        lines = format_text_lines(message, line_length, num_lines)
        adr = cfg["Address"]
        offset = 0
        for line in lines:
            for ch in line:
                shadowRam[adr + offset] = ord(_message_char(ch))
                offset += 1
        enable_message(True)
        return True
    except Exception as e:
        log.log(f"DATAMAPPER: set_message error: {e}")
    return False


def blank_message():
    """Clear the message text (spaces) and turn the custom message off."""
    layout = _message_layout()
    if layout is None:
        return
    line_length, num_lines = layout
    adr = S.gdata["DisplayMessage"]["Address"]
    for i in range(line_length * num_lines):
        shadowRam[adr + i] = 0x20
    enable_message(False)


def format_text_lines(text, line_length, num_lines):
    """
    Break a text string into num_lines centred lines of line_length.
    Breaks on spaces first, then on a period near the centre (for IP
    addresses). If the text is too long, whole words are dropped from the
    end, keeping every token that holds a digit or a period.
    """
    max_chars = line_length * num_lines
    text = text.strip()
    tokens = text.split()

    def has_number_or_period(token):
        return any(c.isdigit() or c == "." for c in token)

    if len(text) > max_chars:
        keepers = []
        droppable = []
        for i, token in enumerate(tokens):
            if has_number_or_period(token):
                keepers.append((i, token))
            else:
                droppable.append((i, token))

        result_tokens = dict(keepers)
        for idx, token in droppable:
            test_tokens = dict(result_tokens)
            test_tokens[idx] = token
            test_text = " ".join(test_tokens[i] for i in sorted(test_tokens.keys()))
            if len(test_text) <= max_chars:
                result_tokens[idx] = token
            else:
                break
        text = " ".join(result_tokens[i] for i in sorted(result_tokens.keys()))

    def centred(line):
        padding = line_length - len(line)
        left = padding // 2
        return " " * left + line + " " * (padding - left)

    lines = []
    remaining = text
    for i in range(num_lines):
        if not remaining:
            lines.append(" " * line_length)
            continue

        if len(remaining) <= line_length:
            lines.append(centred(remaining))
            remaining = ""
            continue

        break_pos = -1
        # break on a space, as late as possible, unless the rest would not fit the lines left
        for j in range(line_length - 1, -1, -1):
            if j < len(remaining) and remaining[j] == " ":
                lines_left = num_lines - i - 1
                if lines_left > 0 and len(remaining[j:].strip()) > lines_left * line_length:
                    continue
                break_pos = j
                break

        if break_pos == -1:
            # no usable space: split a number on a period near the centre
            centre = line_length // 2
            search_range = min(line_length + 5, len(remaining))
            for offset in range(search_range):
                pos_right = centre + offset
                pos_left = centre - offset
                if pos_right < search_range and remaining[pos_right] == ".":
                    break_pos = pos_right + 1
                    break
                if 0 <= pos_left < len(remaining) and remaining[pos_left] == ".":
                    break_pos = pos_left + 1
                    break

        if break_pos == -1 or break_pos > line_length:
            break_pos = line_length

        lines.append(centred(remaining[:break_pos].strip()))
        remaining = remaining[break_pos:].strip()

    return lines


# ---------------------------------------------------------------------------
# Switch health tables (Type 40)
# ---------------------------------------------------------------------------
def switches_supported():
    return _section("Switches", SWITCHES_TYPE) is not None


def get_switch_tables():
    """
    The game's switch health tables.

    Returns:
        tuple: (cur_nc, cur_st, rep_nc, rep_st, games) - four 8 byte copies
               (bit = 1: switch flagged; byte = column, bit = row) and the
               games played in the current 50 game period (int, -1 when the
               counter is not valid BCD). None when Switches is not Type 40.
    """
    cfg = _section("Switches", SWITCHES_TYPE)
    if cfg is None:
        return None
    try:
        adr = cfg["Address"]
        counter_adr = cfg.get("CounterAdr", adr + 96)
        cur_nc = bytes(shadowRam[adr : adr + 8])
        cur_st = bytes(shadowRam[adr + 8 : adr + 16])
        rep_nc = bytes(shadowRam[adr + 16 : adr + 24])
        rep_st = bytes(shadowRam[adr + 24 : adr + 32])
        games = bcd_byte_to_int(shadowRam[counter_adr])
        return cur_nc, cur_st, rep_nc, rep_st, games
    except Exception as e:
        log.log(f"DATAMAPPER: error reading switch tables: {e}")
    return None


def switch_mask_monitored():
    """8 byte mask of the switches that have a name in the config (the ones the game monitors)."""
    mask = bytearray(8)
    cfg = _section("Switches", SWITCHES_TYPE)
    if cfg is None:
        return mask
    names = cfg.get("Names", [])
    for idx in range(min(64, len(names))):
        if names[idx]:
            mask[idx // 8] |= 1 << (idx % 8)
    return mask


def get_switch_counts():
    """
    Per switch count in the shape the Data East Type 20 diagnostics use:
    50 if flagged in the previous period's report, the games played so far
    if flagged in the current period, else 0. Kept for tools that expect it;
    the Whitestar Switches module uses get_switch_tables() directly.
    """
    tables = get_switch_tables()
    if tables is None:
        return []
    cur_nc, cur_st, rep_nc, rep_st, games = tables
    if games < 0:
        games = 0
    length = S.gdata["Switches"].get("Length", 64)
    counts = [0] * length
    for idx in range(min(length, 64)):
        col, bit = divmod(idx, 8)
        mask = 1 << bit
        if (rep_nc[col] | rep_st[col]) & mask:
            counts[idx] = 50
        elif (cur_nc[col] | cur_st[col]) & mask:
            counts[idx] = games
    return counts


def get_switches_tripped():
    """Whitestar keeps no per-switch activity bytes, so there is no 'tripped since last poll' list."""
    return []


def write_switches_nominal():
    """No activity bytes to reset on Whitestar."""
    return False


# ---------------------------------------------------------------------------
# Modes / mode champions (config driven, no Whitestar config has them yet)
# ---------------------------------------------------------------------------
def get_modes():
    """
    Named values from S.gdata["Modes"]: Address (int or "0x.."), Length,
    Format (u8 / BCD / u16 / u16be), optional OffValue and Multiplier.
    Returns {} when none are configured.
    """
    modes_data = {}
    modes = S.gdata.get("Modes")
    if not isinstance(modes, dict):
        return modes_data
    try:
        for mode_name, mode_config in modes.items():
            address = mode_config.get("Address", 0)
            if isinstance(address, str):
                address = int(address, 16) if address.startswith("0x") else int(address)
            length = mode_config.get("Length", 1)
            value = _read_value(shadowRam[address : address + length], mode_config.get("Format", "u8"))
            off_value = mode_config.get("OffValue", None)
            if off_value is None or value > off_value:
                modes_data[mode_name] = value * mode_config.get("Multiplier", 1)
    except Exception as e:
        log.log(f"DATAMAPPER: Error reading modes: {e}")
    return modes_data


def get_mode_champs():
    """
    Mode champions from S.gdata["ModeChamps"]: InitialAdr (3 ASCII) and a
    Scores list of {Address, Length, Format}. Returns {} when none are configured.
    """
    champs_data = {}
    champs = S.gdata.get("ModeChamps")
    if not isinstance(champs, dict):
        return champs_data
    try:
        for mode_name, mode_config in champs.items():
            initials = ""
            initial_adr = mode_config.get("InitialAdr", 0)
            if initial_adr > 0:
                try:
                    initials = bytes(shadowRam[initial_adr : initial_adr + 3]).decode("ascii").strip()
                    if initials in ["???", "", "\x00\x00\x00"]:
                        initials = ""
                except Exception:
                    initials = ""

            score_values = []
            for component in mode_config.get("Scores", []):
                address = component.get("Address", 0)
                length = component.get("Length", 1)
                score_values.append(_read_value(shadowRam[address : address + length], component.get("Format", "u8")))

            champs_data[mode_name] = {"initials": initials, "scores": score_values}
    except Exception as e:
        log.log(f"DATAMAPPER: Error reading mode champs: {e}")
    return champs_data
