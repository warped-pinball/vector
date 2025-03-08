# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    This module is responsible for tracking scores and updating the leaderboard.
    Must account for highscores and in play score avilability
"""
from machine import RTC
from Shadow_Ram_Definitions import shadowRam

import displayMessage
import SharedState as S
import SPI_DataStore as DataStore
from logger import logger_instance

log = logger_instance

rtc = RTC()
top_scores = []
nGameIdleCounter = 0

# hold the last four (plus two older records) games worth of scores.
# first number is game counter (game ID), then 4 scores plus intiials
recent_scores = [
    [0, ("", 0), ("", 0), ("", 0), ("", 0)],
    [1, ("", 0), ("", 0), ("", 0), ("", 0)],
    [2, ("", 0), ("", 0), ("", 0), ("", 0)],
    [3, ("", 0), ("", 0), ("", 0), ("", 0)],
    [4, ("", 0), ("", 0), ("", 0), ("", 0)],
    [5, ("", 0), ("", 6), ("", 0), ("", 0)],
]


def get_claim_score_list():
    result = []
    if DataStore.read_record("extras", 0)["claim_scores"] is True:
        for game in recent_scores[:4]:
            # if there are any unclaimed non zero scores, add them to the list
            if any(score[0] == "" and score[1] != 0 for score in game[1:]):
                # add the game to the list, with all zero scores removed
                result.append([score for score in game[1:] if score[1] != 0])
    return result


def claim_score(initials, player_index, score):
    # claim a score from the recent scores list
    global recent_scores

    initials = initials.upper()
    for game_index, game in enumerate(recent_scores):
        if game[player_index + 1][1] == score and game[player_index + 1][0] == "":
            print("SCORE: claim new score:", initials, score, game_index, player_index)
            recent_scores[game_index][player_index + 1] = (initials, score)
            new_score = { "initials": initials, "full_name": None, "score": score, "game": game[0] }
            if DataStore.read_record("extras", 0)["tournament_mode"]:
                update_tournament(new_score)
            else:
                update_leaderboard(new_score)
            return
    raise ValueError("SCORE: Score not found in claim list")


def _place_game_in_claim_list(game):
    """place game up to four players in claim list"""
    recent_scores.insert(0, game)
    recent_scores.pop()
    print("SCORE: add to claims list: ", recent_scores)


def _read_machine_score(HighScores):
    """read machine scores
    and if HighScores is True try to get intials from highscore area
    """
    high_scores = [["", 0], ["", 0], ["", 0], ["", 0]]
    in_play_scores = [["", 0], ["", 0], ["", 0], ["", 0]]

    # Build a set of all four in-play scores, index=0,1,2,3 (player number)
    try:
        if S.gdata["InPlay"]["Type"] == 1:
            for idx in range(4):
                score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * 4
                in_play_score_bytes = shadowRam[score_start : score_start + 4]
                in_play_scores[idx][1] = _bcd_to_int(in_play_score_bytes)
    except Exception:
        pass

    # grab four high scores (in order of high->low score, not player number!)
    if HighScores:
        if S.gdata["HighScores"]["Type"] in [1, 2, 3, 9]:
            for idx in range(4):
                score_start = S.gdata["HighScores"]["ScoreAdr"] + idx * 4
                score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
                high_scores[idx][1] = _bcd_to_int(score_bytes)
                if high_scores[idx][1] < 1000:
                    high_scores[idx][1] = 0

        # initials
        if "InitialAdr" in S.gdata["HighScores"]:
            for idx in range(4):
                initial_start = S.gdata["HighScores"]["InitialAdr"] + idx * 3
                initials_bytes = shadowRam[initial_start : initial_start + 3]

                if S.gdata["HighScores"]["Type"] in [1, 2]:  # 0x40=space, A-Z normal ASCII
                    initials_bytes = [0x20 if b == 0x40 else (b & 0x7F) for b in initials_bytes]
                    high_scores[idx][0] = bytes(initials_bytes).decode("ascii")
                elif S.gdata["HighScores"]["Type"] == 3:  # 0=space,1='0',10='9', 11='A'
                    try:
                        processed_initials = bytearray([0x20 if byte == 0 else byte + 0x36 for byte in initials_bytes])
                        high_scores[idx][0] = processed_initials.decode("ascii")
                    except Exception:
                        high_scores[idx][0] = None

                if high_scores[idx][0] in ["???", "", None, "   "]:  # no player, allow claim
                    high_scores[idx][0] = ""

        # if we have high scores, intials AND in-play socres, put initials to the in play scores
        for in_play_score in in_play_scores:
            for high_score in high_scores:
                if in_play_score[1] == high_score[1]:
                    in_play_score[0] = high_score[0]  # copy initals over

    if all(score[1] == 0 for score in in_play_scores):
        return high_scores
    else:
        return in_play_scores


def _bcd_to_int(score_bytes):
    """game system (BCD to integer conversion)
    0xF is = to zero
    """
    score = 0
    for byte in score_bytes:
        high_digit = byte >> 4
        low_digit = byte & 0x0F
        if low_digit > 9:
            low_digit = 0
        if high_digit > 9:
            high_digit = 0
        score = score * 100 + high_digit * 10 + low_digit
    return score


def _int_to_bcd(number):
    """int back to BCD coded for the game"""
    if not (0 <= number <= 99999999):
        raise ValueError("SCORE: Number out of range")

    # pad with zeros to ensure it has 8 digits
    num_str = f"{number:08d}"
    bcd_bytes = bytearray(4)
    # Fill byte array
    for i in range(4):
        bcd_bytes[i] = (int(num_str[2 * i]) << 4) + int(num_str[2 * i + 1])
    return bcd_bytes


def _ascii_to_type3(c):
    """convert ascii character to machine type 3 display character"""
    return 0 if c == 0x20 or c < 0x0B or c > 0x90 else c - 0x36


def place_machine_scores():
    """write four highest scores & initials from storage to machine memory"""
    global top_scores

    if S.gdata["HighScores"]["Type"] == 1 or S.gdata["HighScores"]["Type"] == 3:
        print("SCORE: Place system 11 machine scores")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            try:
                scoreBCD = _int_to_bcd(top_scores[index]["score"])
            except Exception:
                print("SCORE: score convert problem")
                scoreBCD = _int_to_bcd(100)

            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = scoreBCD
            print("  top scores: ", top_scores[index])

            try:
                initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3
                initials = top_scores[index]["initials"]
                for i in range(3):
                    if S.gdata["HighScores"]["Type"] == 1:
                        shadowRam[initial_start + i] = ord(initials[i])
                    elif S.gdata["HighScores"]["Type"] == 3:
                        shadowRam[initial_start + i] = _ascii_to_type3(ord(initials[i]))

            except Exception:
                print("SCORE: place machine scores exception")
                shadowRam[initial_start] = 64
                shadowRam[initial_start + 1] = 64
                shadowRam[initial_start + 2] = 64

    elif S.gdata["HighScores"]["Type"] == 9:
        # system 9, copy in scores, no intiials
        print("SCORE: Place system 9 machine high scores")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["BytesInScore"]
            shadowRam[score_start : score_start + 4] = _int_to_bcd(top_scores[index]["score"])


def _remove_machine_scores():
    """remove machine scores"""
    if S.gdata["HighScores"]["Type"] == 1 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:  # system 11 type 1
        log.log("SCORE: Remove machine scores type 1")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3
            for i in range(4):
                shadowRam[score_start + i] = 0  # score
            for i in range(3):
                shadowRam[initial_start + i] = 0x3F  # intials
            shadowRam[score_start + 2] = 5 - index

    elif S.gdata["HighScores"]["Type"] == 3 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:  # system 11, type 3
        log.log("SCORE: Remove machine scores type 3")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3

            for i in range(4):
                shadowRam[score_start + i] = 0
            shadowRam[score_start + 2] = 5 - index
            for i in range(3):
                shadowRam[initial_start + i] = 0x00

    elif S.gdata["HighScores"]["Type"] == 9:
        log.log("SCORE: Remove machine scores system 9")
        place_machine_scores()


def find_player_by_initials(new_entry):
    """find players name from list of intials with names from storage"""
    findInitials = new_entry["initials"]
    if findInitials == "" or findInitials is None:
        return ("", -1)
    count = DataStore.memory_map["names"]["count"]
    for index in range(count):
        rec = DataStore.read_record("names", index)
        if rec is not None:
            if rec["initials"] == findInitials:
                player_name = rec["full_name"].strip("\x00")
                return (player_name, index)
    return ("", -1)


def update_individual_score(new_entry):
    """upadate a players individual score board"""
    initials = new_entry["initials"]
    playername, playernum = find_player_by_initials(new_entry)

    if not playername or playername in [" ", "@@@", "   "]:
        print("SCORE: No indiv player ", initials)
        return False

    if not (0 <= playernum < DataStore.memory_map["individual"]["count"]):
        print("SCORE: Player out of range")
        return False

    new_entry["full_name"] = playername

    # Load existing scores
    scores = []
    num_scores = DataStore.memory_map["individual"]["count"]
    print("SCORE: num sores = ", num_scores, playernum)
    for i in range(num_scores):
        scores.append(DataStore.read_record("individual", i, playernum))

    scores.append(new_entry)
    scores.sort(key=lambda x: x["score"], reverse=True)
    scores = scores[:20]

    # Save the updated scores
    for i in range(num_scores):
        DataStore.write_record("individual", scores[i], i, playernum)

    print(f"Updated scores for {initials}")
    return True


def update_leaderboard(new_entry):
    """called by check for new scores,    one call for each valid new score entry"""
    global top_scores

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        print("SCORE: Bad Initials")
        return False

    year, month, day, _, _, _, _, _ = rtc.datetime()
    new_entry["date"] = f"{month:02d}/{day:02d}/{year}"

    print("SCORE: Update Leader Board: ", new_entry)
    update_individual_score(new_entry)

    # add player name to new_entry if there is an initals match
    new_entry["full_name"], ind = find_player_by_initials(new_entry)
    if new_entry["full_name"] is None:
        new_entry["full_name"] = ""

    # Load scores
    top_scores = [DataStore.read_record("leaders", i) for i in range(DataStore.memory_map["leaders"]["count"])]

    # if matches a record without initials in top_scores (score claim) - just add initials
    for entry in top_scores:
        if entry["initials"] == "" and entry["score"] == new_entry["score"]:
            entry["initials"] = new_entry["initials"]
            entry["full_name"] = new_entry["full_name"]
            DataStore.write_record("leaders", entry, top_scores.index(entry))
            return True

    # Check if the score already exists in the top_scores list
    if any(entry["initials"] == new_entry["initials"] and entry["score"] == new_entry["score"] for entry in top_scores):
        return False  # Entry already exists, do not add it

    # Check if the new score is higher than the lowest in the list or if the list is not full
    top_scores.append(new_entry)
    top_scores.sort(key=lambda x: x["score"], reverse=True)

    count = DataStore.memory_map["leaders"]["count"]
    top_scores = top_scores[:count]
    for i in range(count):
        DataStore.write_record("leaders", top_scores[i], i)

    return True


def initialize_leaderboard():
    """power up init for leader board"""
    global top_scores
    print("SCORE: Init leader board")

    # init gameCounter, find highest # in tournament board
    n = 0
    for i in range(DataStore.memory_map["tournament"]["count"]):
        try:
            game_value = DataStore.read_record("tournament", i)["game"]
            n = max(game_value, n)
        except (KeyError, TypeError):
            log.log(f"SCORE: Error reading game value at index {i}")
            continue
    S.gameCounter = n

    # load up top scores from fram
    count = DataStore.memory_map["leaders"]["count"]
    top_scores = [DataStore.read_record("leaders", i) for i in range(count)]

    # make sure we have 4 entries
    while len(top_scores) < 4:
        fake_entry = {"initials": "ZZZ", "full_name": " ", "score": 100, "date": "04/17/2024"}
        top_scores.append(fake_entry)


def check_for_machine_high_scores():
    # check for high scores in machine that we dont have yet
    scores = _read_machine_score(True)
    year, month, day, _, _, _, _, _ = rtc.datetime()
    for idx in range(4):
        if scores[idx][1] > 1000:  # could be left over ip address digits in system 9
            new_score = {"initials": scores[idx][0], "full_name": "", "score": scores[idx][1], "date": f"{month:02d}/{day:02d}/{year}", "game_count": S.gameCounter}
            update_leaderboard(new_score)


def update_tournament(new_entry):
    """place a single new score in the tournament board fram"""

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        print("SCORE: tournament add bad Initials")
        return False

    if new_entry["score"] < 1000 :
        print("SCORE: tournament add bad score")
        return False

    count = DataStore.memory_map["tournament"]["count"]
    rec = DataStore.read_record("tournament", 0)
    nextIndex = rec["index"]


    #check for a match in the tournament board, for Claim Score function
    #   look back 6 games x 4 scores = 24 places for a match
    if "game" in new_entry:  #claim will have a game count
        print("SCORE: tournament claim score checking")
        for i in range(24):
            ind = nextIndex - 1 - i
            if ind < 0:
                ind += count
            rec = DataStore.read_record("tournament", ind)
            if rec["game"] == new_entry["game"] and rec["score"] == new_entry["score"]:
                rec["initials"] = new_entry["initials"]                
                DataStore.write_record("tournament", rec, ind)
        return


    new_entry["game"] = S.gameCounter
    new_entry["full_name"] = ""
    new_entry["index"] = nextIndex
    DataStore.write_record("tournament", new_entry, nextIndex)
    log.log(f"SCORE: tournament new score {new_entry}")

    nextIndex += 1
    if nextIndex >= count:
        nextIndex = 0
    rec = DataStore.read_record("tournament", 0)
    rec["index"] = nextIndex
    DataStore.write_record("tournament", rec, 0)
    return


def CheckForNewScores(nState=[0]):
    """called by scheduler every 5 seconds"""
    global nGameIdleCounter

    if nState[0] == 0:  # power up init
        displayMessage.refresh_9()
        if DataStore.read_record("extras", 0)["show_ip_address"] is False or S.gdata["HighScores"]["Type"] in [1, 2, 3]:
            place_machine_scores()
        nState[0] = 1

        # if enter initials on game set high score rewards to zero
        if S.gdata["HSRewards"]["Type"] == 1 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:
            shadowRam[S.gdata["HSRewards"]["HS1"]] = S.gdata["HSRewards"]["DisableByte"]
            shadowRam[S.gdata["HSRewards"]["HS2"]] = S.gdata["HSRewards"]["DisableByte"]
            shadowRam[S.gdata["HSRewards"]["HS3"]] = S.gdata["HSRewards"]["DisableByte"]
            shadowRam[S.gdata["HSRewards"]["HS4"]] = S.gdata["HSRewards"]["DisableByte"]

    if S.gdata["BallInPlay"]["Type"] == 1:  # 0 disables score tracking
        BallInPlayAdr = S.gdata["BallInPlay"]["Address"]
        Ball1Value = S.gdata["BallInPlay"]["Ball1"]
        Ball2Value = S.gdata["BallInPlay"]["Ball2"]
        Ball3Value = S.gdata["BallInPlay"]["Ball3"]
        Ball4Value = S.gdata["BallInPlay"]["Ball4"]
        Ball5Value = S.gdata["BallInPlay"]["Ball5"]

        if nState[0] == 1:  # waiting for a game to start
            nGameIdleCounter += 1  # claim score list expiration timer
            if nGameIdleCounter > (3 * 60 / 5):  # 3 min, push empty onto list so old games expire
                game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
                _place_game_in_claim_list(game)
                nGameIdleCounter = 0
                print("SCORE: game list 10 minute expire")

            print("SCORE: game start check ", nGameIdleCounter)
            if shadowRam[BallInPlayAdr] in (Ball1Value, Ball2Value, Ball3Value, Ball4Value, Ball5Value):
                nState[0] = 2
                # Game Started!
                log.log("SCORE: Game Started")
                nGameIdleCounter = 0
                _remove_machine_scores()
                S.gameCounter = (S.gameCounter + 1) % 100

        elif nState[0] == 2:  # waiting for game to end
            print("SCORE: game end check")
            if shadowRam[BallInPlayAdr] not in (Ball1Value, Ball2Value, Ball3Value, Ball4Value, Ball5Value, 0xFF):
                # game over, get new scores
                nState[0] = 1
                if (S.gdata["HighScores"]["Type"] == 9) or (DataStore.read_record("extras", 0)["enter_initials_on_game"] is False):
                    # in play scores
                    log.log("SCORE: end, use in-play scores")
                    scores = _read_machine_score(False)                    
                else:
                    # high scores
                    log.log("SCORE: end, use high scores")
                    scores = _read_machine_score(True)
             
                if DataStore.read_record("extras", 0)["tournament_mode"]:
                    for i in range(0, 4):
                        update_tournament({"initials": scores[i][0], "score": scores[i][1]})
                else:
                    for i in range(0, 4):                    
                        update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

                game = [S.gameCounter, scores[0], scores[1], scores[2], scores[3]]
                _place_game_in_claim_list(game)

                # put high scores back in machine memory
                place_machine_scores()

                # put ip address back up on system 9 displays
                displayMessage.refresh_9()
