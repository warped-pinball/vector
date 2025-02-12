# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    V0.2 9/7/2024  period after initials handling
    V0.3 11/25/2024 game over fix for high speed
    V0.4 2/5/2024  add support for system 9
"""
from machine import RTC

import displayMessage
import SharedState
import SharedState as S
import SPI_DataStore as DataStore
from logger import logger_instance
from Shadow_Ram_Definitions import shadowRam
log = logger_instance

rtc = RTC()
top_scores = []
nGameIdleCounter = 0

# hold the last four (plus two older records) games worth of scores.
# first number is game counter (game ID), then 4 scores plus intiials
recent_scores = [
    # TODO put back to all zeros after testing
    [0, ("", 11287984), ("", 0), ("", 0), ("", 0)],
    [1, ("MSM", 546341), ("", 267822), ("", 0), ("", 0)],
    [2, ("", 1234), ("PSM", 245562), ("", 3), ("", 0)],
    [3, ("", 252351), ("", 2333352), ("", 12345678900), ("", 445733)],
    [4, ("", 5), ("", 0), ("", 0), ("", 0)],
    [5, ("", 0), ("", 6), ("", 0), ("", 0)],
]


def get_claim_score_list():
    result = []
    for game in recent_scores[:4]:
        # if there are any unclaimed non zero scores, add them to the list
        if any(score[0] == "" and score[1] != 0 for score in game[1:]):
            # add the game to the list, with all zero scores removed
            result.append([score for score in game[1:] if score[1] != 0])
    return result


def claim_score(initials, player_index, score):
    # claim a score
    global recent_scores

    initials = initials.upper()

    for game_index, game in enumerate(recent_scores):
        if game[player_index + 1][1] == score and game[player_index + 1][0] == "":
            print("SCORE: new score:", initials, score, game_index, player_index)
            recent_scores[game_index][player_index + 1] = (initials, score)          
            new_score = {"initials": initials, "full_name": None, "score": score} 
            update_leaderboard(new_score)
            return

    raise ValueError("SCORE: Score not found in claim list")


# read machine score
def read_machine_score(index):
    # system 11 (high scores)
    if "11" in S.gdata["GameInfo"]["System"]:
        score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
        initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3
        score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]

        # Read initials
        initials_bytes = shadowRam[initial_start : initial_start + 3]
        if S.gdata["HighScores"]["Type"] in [1, 2]:  # 0x40=space, A-Z normal ASCII
            initials_bytes = [0x20 if b == 0x40 else (b & 0x7F) for b in initials_bytes]
            initials = bytes(initials_bytes).decode("ascii")
        elif S.gdata["HighScores"]["Type"] == 3:  # 0=space,1='0',10='9', 11='A'
            processed_initials = bytearray([0x20 if byte == 0 else byte + 0x36 for byte in initials_bytes])
            try:
                initials = processed_initials.decode("ascii")
            except Exception:
                initials = ""
        else:
            initials = ""

    # System9 (in play scores)
    if "9" in S.gdata["GameInfo"]["System"]:
        initials = ""
        try:
            score_start = S.gdata["InPlayScores"]["ScoreAdr"] + index * 4
        except KeyError:
            return initials, 0
        score_bytes = shadowRam[score_start : score_start + S.gdata["InPlayScores"]["BytesInScore"]]

    # game system (BCD to integer conversion) - 0xF is = to zero
    score = 0
    for byte in score_bytes:
        high_digit = byte >> 4
        low_digit = byte & 0x0F
        if low_digit > 9:
            low_digit = 0
        if high_digit > 9:
            high_digit = 0
        score = score * 100 + high_digit * 10 + low_digit
    return initials, score


# convert integer to 8 digit BCD number like stored in game for high scores
def int_to_bcd(number):
    # Ensure the number is within the acceptable range
    if not (0 <= number <= 99999999):
        raise ValueError("SCORE: Number out of range")

    # pad with zeros to ensure it has 7 digits
    num_str = f"{number:08d}"
    bcd_bytes = bytearray(4)

    # Fill byte array
    bcd_bytes[0] = (int(num_str[0]) << 4) + int(num_str[1])  # Millions
    bcd_bytes[1] = (int(num_str[2]) << 4) + int(num_str[3])  # Hundred-th & ten-th
    bcd_bytes[2] = (int(num_str[4]) << 4) + int(num_str[5])  # Thousands & hundreds
    bcd_bytes[3] = (int(num_str[6]) << 4) + int(num_str[7])  # Tens & ones
    return bcd_bytes


def ascii_to_type3(c):
    """ convert ascii character to machine type 3 display character """
    if c == 0x20 or c < 0x0B or c > 0x90:
        return 0
    return c - 0x36  # char


# write four highest scores from storage to machine memory
def place_machine_scores():
    global top_scores
    
    if "11" in S.gdata["GameInfo"]["System"]:
        print("SCORE: Place system 11 machine scores")
        # system 11  
        if S.gdata["HighScores"]["Type"] == 1 or S.gdata["HighScores"]["Type"] == 3:
            for index in range(4):
                score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
                initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3
                try:
                    scoreBCD = int_to_bcd(top_scores[index]["score"])
                except Exception:
                    print("SCORE: score convert problem")
                    scoreBCD = int_to_bcd(100)

                for i in range(S.gdata["HighScores"]["BytesInScore"]):
                    shadowRam[score_start + i] = scoreBCD[i]
                try:
                    print("  top scores: ", top_scores[index])
                    initials = top_scores[index]["initials"]
                    for i in range(3):
                        if S.gdata["HighScores"]["Type"] == 1:
                            shadowRam[initial_start + i] = ord(initials[i])
                        elif S.gdata["HighScores"]["Type"] == 3:
                            shadowRam[initial_start + i] = ascii_to_type3(ord(initials[i]))

                except Exception:
                    print("SCORE: place machine scores exception")
                    shadowRam[initial_start] = 64
                    shadowRam[initial_start + 1] = 64
                    shadowRam[initial_start + 2] = 64

    elif "9" in S.gdata["GameInfo"]["System"]:   
        #system 9, needed when show ip address gets turned off
        print("SCORE: Replace system 9 high scores")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["BytesInScore"]
            shadowRam[score_start : score_start + 4] = int_to_bcd(top_scores[index]["score"])

        



def remove_machine_scores():
    """remove machine scores"""
    if S.gdata["HighScores"]["Type"] == 1 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:   # system 11 type 1
        log.log("SCORE: Remove machine scores 1")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3
            for i in range(4):
                shadowRam[score_start + i] = 0  # score
            for i in range(3):
                shadowRam[initial_start + i] = 0x3F  # intials
            shadowRam[score_start + 2] = 5 - index

    elif S.gdata["HighScores"]["Type"] == 3 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:  # system 11, type 3
        log.log("SCORE: Remove machine scores 3")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3

            for i in range(4):
                shadowRam[score_start + i] = 0
            shadowRam[score_start + 2] = 5 - index
            for i in range(3):
                shadowRam[initial_start + i] = 0x00

    elif S.gdata["HighScores"]["Type"] == 9:        
        place_machine_scores() 
      


def find_player_by_initials(new_entry):
    """
    find players name from list of intials with names from storage
    """
    findInitials = new_entry["initials"]
    count = DataStore.memory_map["names"]["count"]
    for index in range(count):
        rec = DataStore.read_record("names", index)
        if rec is not None:
            if rec["initials"] == findInitials:
                player_name = rec["full_name"].strip("\x00")
                return (player_name, index)
    return (" ", -1)


def update_individual_score(new_entry):
    """
    upadate a players individual score board

    """
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
    """  called by check for new scores,    one call for each valid new score entry   """
    global top_scores

    if new_entry["initials"] == "@@@" or new_entry["initials"] == "   ":   #check for corruption
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
    """    power up init for leader board     """
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

    #load up top scores from fram
    count = DataStore.memory_map["leaders"]["count"]
    top_scores = [DataStore.read_record("leaders", i) for i in range(count)]

    # make sure we have 4 entries
    while len(top_scores) < 4:
        fake_entry = {"initials": "ZZZ", "full_name": " ", "score": 100, "date": "04/17/2024"}
        top_scores.append(fake_entry)

    # for system 11 only, check for high scores in machine that we dont have yet-
    if "11" in S.gdata["GameInfo"]["System"]:
        for i in range(4):
            initials, score = read_machine_score(i)
            if any(0x40 < ord(initial) <= 0x5A for initial in initials[:3]):  #confirm initals - not blanked out
                year, month, day, _, _, _, _, _ = rtc.datetime()
                new_score = {"initials": initials, "full_name": "    ", "score": score, "date": f"{month:02d}/{day:02d}/{year}", "game_count": SharedState.gameCounter}
                update_leaderboard(new_score)


def update_tournamentboard(new_entry):
    """    place a new score in the tournament board fram    """
    count = DataStore.memory_map["tournament"]["count"]
    rec = DataStore.read_record("tournament", 0)
    nextIndex = rec["index"]

    new_entry["game"] = SharedState.gameCounter
    new_entry["index"] = nextIndex
    DataStore.write_record("tournament", new_entry, nextIndex)
    print("SCORE: tournament new score ", new_entry)

    nextIndex += 1
    if nextIndex >= count:
        nextIndex = 0
    rec = DataStore.read_record("tournament", 0)
    rec["index"] = nextIndex
    DataStore.write_record("tournament", rec, 0)
    return


def place_game_in_tournament(game):
    """
    place game (all four scores) in tournament board
        game: gamecounter, score 0, 1, 2, 3
    """
    year, month, day, _, _, _, _, _ = rtc.datetime()
    new_score = {"initials": " ", "full_name": " ", "score": 0, "date": f"{month:02d}/{day:02d}/{year}", "game": game[0]}

    for i in range(4):
        if int(game[i + 1][1]) > 0:
            new_score["score"] = int(game[i + 1][1])
            update_tournamentboard(new_score)


def place_game_in_claim_list(game):
    recent_scores.insert(0, game)
    recent_scores.pop()
    print("SCORE: add to claims list: ", recent_scores)



def CheckForNewScores(nState=[0]):
    """
    called by scheduler every 5 seconds
        
    """
    global nGameIdleCounter

    if S.gdata["BallInPlay"]["Type"] == 1:
        BallInPlayAdr = S.gdata["BallInPlay"]["Address"]
        Ball1Value = S.gdata["BallInPlay"]["Ball1"]
        Ball2Value = S.gdata["BallInPlay"]["Ball2"]
        Ball3Value = S.gdata["BallInPlay"]["Ball3"]
        Ball4Value = S.gdata["BallInPlay"]["Ball4"]
        Ball5Value = S.gdata["BallInPlay"]["Ball5"]

        if nState[0] == 0:  # waiting for a game to start
            nGameIdleCounter += 1  # claim score list expiration timer
            if nGameIdleCounter > (3 * 60 / 5):  # 3 min, push empty onto list so old games expire
                game = [SharedState.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
                place_game_in_claim_list(game)
                nGameIdleCounter = 0
                print("SCORE: game list 10 minute expire")

            print("SCORE: game start check ", nGameIdleCounter)
            if shadowRam[BallInPlayAdr] in (Ball1Value, Ball2Value, Ball3Value, Ball4Value, Ball5Value):
                #Game Staarted!
                nGameIdleCounter = 0                           
                remove_machine_scores()               
                SharedState.gameCounter = (SharedState.gameCounter + 1) % 100
                nState[0] = 1

        elif nState[0] == 1:  # waiting for game to end
            print("SCORE: game end check")
            if shadowRam[BallInPlayAdr] not in (Ball1Value, Ball2Value, Ball3Value, Ball4Value, Ball5Value, 0xFF):
                # game over, get new scores
                nState[0] = 0
                game = [SharedState.gameCounter, read_machine_score(0), read_machine_score(1), read_machine_score(2), read_machine_score(3)]
                
                if DataStore.read_record("extras", 0)["tournament_mode"]:
                    place_game_in_tournament(game)
                else:                    
                    for i in range(1, 5):                     
                        update_leaderboard({"initials": game[i][0], "score": game[i][1]})                   
                    place_game_in_claim_list(game)

                # put high scores back in machine memory
                place_machine_scores()

                #put ip address back up on system 9 displays
                if True == DataStore.read_record("extras", 0)["show_ip_address"]:
                    displayMessage.refresh_9()
