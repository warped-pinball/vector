# WPC

# This file is part of the Warped Pinball WOC - Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    This module is responsible for tracking scores and updating the leaderboard.
    Must account for highscores and in play score avilability
"""
import SharedState as S
import SPI_DataStore as DataStore
from logger import logger_instance
from machine import RTC
from Shadow_Ram_Definitions import shadowRam

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


def reset_scores():
    """reset high scores"""
    from SPI_DataStore import blankStruct

    print(" RESET Leader scores")
    blankStruct("leaders")
    _remove_machine_scores(GrandChamp="Zero")


def fix_high_score_checksum():
    """fix high score checksum if needed, also do grand champion checksum"""

    def _calc_checksum(start_adr, end_adr):
        """calculate checksum for a range of addresses"""
        chk = 0
        for adr in range(start_adr, end_adr + 1):
            chk += shadowRam[adr]
        chk = 0xFFFF - chk
        msb = (chk >> 8) & 0xFF
        lsb = chk & 0xFF
        return msb, lsb

    if S.gdata["HighScores"]["Type"] == 10:  # 10 for std WPC
        msb, lsb = _calc_checksum(S.gdata["HighScores"]["ChecksumStartAdr"], S.gdata["HighScores"]["ChecksumEndAdr"])
        # print("SCORE: Checksum: ---------------- ", hex(msb), hex(lsb))
        shadowRam[S.gdata["HighScores"]["ChecksumResultAdr"]] = msb
        shadowRam[S.gdata["HighScores"]["ChecksumResultAdr"] + 1] = lsb

        msb, lsb = _calc_checksum(S.gdata["HighScores"]["GCChecksumStartAdr"], S.gdata["HighScores"]["GCChecksumEndAdr"])
        # print("SCORE: Checksum Grand Champ : ---------------- ", hex(msb), hex(lsb))
        shadowRam[S.gdata["HighScores"]["GCChecksumResultAdr"]] = msb
        shadowRam[S.gdata["HighScores"]["GCChecksumResultAdr"] + 1] = lsb


def get_claim_score_list():
    """fetch the list of claimable scores"""
    result = []
    if DataStore.read_record("extras", 0)["claim_scores"] is True:
        for game in recent_scores[:4]:
            # if there are any unclaimed non zero scores, add them to the list
            if any(score[0] == "" and score[1] != 0 for score in game[1:]):
                # add the game to the list, with all zero scores removed
                result.append([score for score in game[1:] if score[1] != 0])
    return result


def claim_score(initials, player_index, score):
    """claim a score from the recent scores list - do not require a player index, search all"""
    global recent_scores

    # condition the initials - more important than one would think.  machines freak if non printables get in
    initials = initials.upper()
    i_intials = ""
    for c in initials:
        if "A" <= c <= "Z":
            i_intials += c
    initials = (i_intials + "   ")[:3]

    if initials in ["@@@", "   ", "???", ""]:
        return

    for game_index, game in enumerate(recent_scores):
        for player_index in range(4):
            if game[player_index + 1][1] == score and game[player_index + 1][0] == "":
                log.log(f"SCORE: claim new score: {initials}, {score}, {game_index}, {player_index}")
                recent_scores[game_index][player_index + 1] = (initials, score)
                new_score = {"initials": initials, "full_name": None, "score": score, "game": game[0]}
                if DataStore.read_record("extras", 0)["tournament_mode"]:
                    update_tournament(new_score)
                else:
                    update_leaderboard(new_score)
                return

    # required for case where user resets high scores on the machine
    update_leaderboard({"initials": initials, "full_name": None, "score": score, "game": 0})


def _place_game_in_claim_list(game):
    """place game up to four players in claim list"""
    recent_scores.insert(0, game)
    recent_scores.pop()
    print("SCORE: add to claims list: ", recent_scores)
    from origin import push_end_of_game

    push_end_of_game(game)


def _read_machine_score(UseHighScores=True):
    """read machine scores - in play and highscores
    and if HighScores is True try to get intials from highscore area
    """
    high_scores = [["", 0], ["", 0], ["", 0], ["", 0], ["", 0]]
    in_play_scores = [["", 0], ["", 0], ["", 0], ["", 0]]

    # Build a set of all four in-play scores, index=0,1,2,3 (by player number)
    try:
        if S.gdata["InPlay"]["Type"] == 10:  # 10 for std WPC
            for idx in range(4):
                score_start = S.gdata["InPlay"]["ScoreAdr"] + idx * S.gdata["InPlay"]["ScoreSpacing"]
                in_play_score_bytes = shadowRam[score_start : score_start + S.gdata["InPlay"]["ScoreBytes"]]
                in_play_scores[idx][1] = _bcd_to_int(in_play_score_bytes)
    except Exception:
        pass

    # grab four high scores (in order of high->low score, not player number!)
    # there can be grand chanpion also - - put in 0th place
    if S.gdata["HighScores"]["Type"] == 10:  # 10 for std WPC
        for idx in range(1, 5):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + (idx - 1) * S.gdata["HighScores"]["ScoreSpacing"]
            score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
            high_scores[idx][1] = _bcd_to_int(score_bytes)
            if high_scores[idx][1] < 1000:
                high_scores[idx][1] = 0
        # is there a grand champion score also?    put in order, games have GC in 5th place
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]
            score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
            high_scores[0][1] = _bcd_to_int(score_bytes)

            # Calculate the maximum fake score (all BCD bytes set to 0x99)
            max_fake_score = int("".join(["99"] * S.gdata["HighScores"]["BytesInScore"]))
            if high_scores[0][1] < 1000 or high_scores[0][1] >= max_fake_score:  # if left over max score from reboot - do not keep it
                high_scores[0][1] = 0

        # initials
        if "InitialAdr" in S.gdata["HighScores"]:
            for idx in range(1, 5):
                initial_start = S.gdata["HighScores"]["InitialAdr"] + (idx - 1) * S.gdata["HighScores"]["InitialSpacing"]
                initials_bytes = shadowRam[initial_start : initial_start + 3]

                # normal ascii
                high_scores[idx][0] = bytes(initials_bytes).decode("ascii")

                if high_scores[idx][0] in ["???", "", None, "   "]:  # no player, allow claim
                    high_scores[idx][0] = ""

            # initials for grand champion
            if "GrandChampInitAdr" in S.gdata["HighScores"]:
                initial_start = S.gdata["HighScores"]["GrandChampInitAdr"]
                initials_bytes = shadowRam[initial_start : initial_start + 3]
                high_scores[0][0] = bytes(initials_bytes).decode("ascii")
                # print("grand champ initials ", high_scores[0][0])
                if high_scores[0][0] in ["???", "", None, "   "]:
                    high_scores[0][0] = ""

        # if we have high scores, intials AND in-play socres, put initials to the in play scores
        for in_play_score in in_play_scores:
            for high_score in high_scores:
                if in_play_score[1] == high_score[1]:
                    in_play_score[0] = high_score[0]  # copy initals over

    if UseHighScores:
        print("SCORE: High Scores used")
        return high_scores
    else:
        print("SCORE: In play scores used")
        return in_play_scores


def _bcd_to_int(score_bytes):
    """game system (BCD to integer conversion)
    up to 8 bcd bytes
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
    """change int back to BCD coded for the game
    tested to support large numbers - to 8 bcd digits"""
    if S.gdata["HighScores"]["Type"] == 10:
        ScoreBytes = S.gdata["HighScores"]["BytesInScore"]
    else:
        ScoreBytes = 6  # 6 bcd digits for 12 digit score

    # pad with zeros to ensure it has ScoreBytes*2 digits
    num_str = f"{number:0{ScoreBytes * 2}d}"
    bcd_bytes = bytearray(ScoreBytes)
    # Fill byte array
    for i in range(ScoreBytes):
        bcd_bytes[i] = (int(num_str[2 * i]) << 4) + int(num_str[2 * i + 1])
    return bcd_bytes


def place_machine_scores():
    """write four (plus grand champ?) highest scores & initials from storage to machine memory"""
    global top_scores

    # possible high score intials are empty if there was a reset / reboot etc
    # games do not like empties!
    for index in range(5):  # incase of grand champ - 5 scores
        if len(top_scores[index]["initials"]) != 3:
            top_scores[index]["initials"] = "   "
            # top_scores[index]["score"] = 100  only change intials, not score (blank initials happen with good scores sometimes)

    if S.gdata["HighScores"]["Type"] == 10:
        print("SCORE: Place WPC machine scores")

        gc = 0
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            gc = 1
            # place grand champion score
            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]
            try:
                scoreBCD = _int_to_bcd(top_scores[0]["score"])
            except Exception:
                log.log("SCORE: score convert problem")
                scoreBCD = _int_to_bcd(100)

            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = scoreBCD
            # print("  top scores: ", top_scores[0])

            # grand champ initials
            try:
                initial_start = S.gdata["HighScores"]["GrandChampInitAdr"]
                initials = top_scores[0]["initials"]
                for i in range(3):
                    shadowRam[initial_start + i] = ord(initials[i])  # std ASCII
            except Exception:
                log.log("SCORE: place machine scores exception")
                shadowRam[initial_start] = 64
                shadowRam[initial_start + 1] = 64
                shadowRam[initial_start + 2] = 64

        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["ScoreSpacing"]
            try:
                scoreBCD = _int_to_bcd(top_scores[index + gc]["score"])  # +1 (gc) if grand champ was loaded
            except Exception:
                log.log("SCORE: score convert problem")
                scoreBCD = _int_to_bcd(100)

            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = scoreBCD
            # print("  top scores: ", top_scores[index+gc])

            try:
                initial_start = S.gdata["HighScores"]["InitialAdr"] + index * S.gdata["HighScores"]["InitialSpacing"]
                initials = top_scores[index + gc]["initials"]
                for i in range(3):
                    shadowRam[initial_start + i] = ord(initials[i])  # std ASCII

            except Exception:
                log.log("SCORE: place machine scores exception")
                shadowRam[initial_start] = 64
                shadowRam[initial_start + 1] = 64
                shadowRam[initial_start + 2] = 64

        fix_high_score_checksum()


def _remove_machine_scores(GrandChamp="Max"):
    """remove machine scores to prep for forced intial entry  - WPC"""
    if S.gdata["HighScores"]["Type"] == 10:
        log.log("SCORE: Remove machine scores type 10")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["ScoreSpacing"]
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * S.gdata["HighScores"]["InitialSpacing"]

            for i in range(S.gdata["HighScores"]["BytesInScore"]):
                shadowRam[score_start + i] = 0  # score

            shadowRam[score_start + S.gdata["HighScores"]["BytesInScore"] - 2] = 0x10 * (6 - index)

            for i in range(3):
                shadowRam[initial_start + i] = 0x41  # intials all 'A'

        # set grand champion score to max, so all players will be int he normal 1-4 places
        # Or near zero for reset leaderboard function
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]
            if GrandChamp == "Max":
                # set grand champion score to max
                for i in range(S.gdata["HighScores"]["BytesInScore"]):
                    shadowRam[score_start + i] = 0x99
            elif GrandChamp == "Zero":
                # set grand champ to min
                for i in range(S.gdata["HighScores"]["BytesInScore"]):
                    shadowRam[score_start + i] = 0x00
                shadowRam[score_start + S.gdata["HighScores"]["BytesInScore"] - 2] = 0x90

        fix_high_score_checksum()


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
    # initials = new_entry["initials"]
    playername, playernum = find_player_by_initials(new_entry)

    if not playername or playername in [" ", "@@@", "   ", ""]:
        # print("SCORE: No indiv player ", initials)
        pass
        return False

    if not (0 <= playernum < DataStore.memory_map["individual"]["count"]):
        log.log("SCORE: Player out of range")
        return False

    new_entry["full_name"] = playername

    # Load existing scores
    scores = []
    num_scores = DataStore.memory_map["individual"]["count"]
    for i in range(num_scores):
        existing_score = DataStore.read_record("individual", i, playernum)
        if existing_score and existing_score.get("score") == new_entry["score"]:
            return False
        scores.append(existing_score)

    scores.append(new_entry)
    scores.sort(key=lambda x: x["score"], reverse=True)
    scores = scores[:num_scores]

    # Save the updated scores
    for i in range(num_scores):
        DataStore.write_record("individual", scores[i], i, playernum)

    # print(f"Updated scores for {initials}")
    return True


def update_leaderboard(new_entry):
    """called by check for new scores, one call for each valid new score entry"""
    global top_scores

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        log.log("SCORE: Bad Initials")
        return False

    # Sanitize initials: 3 uppercase letters only
    initials = new_entry.get("initials", "")
    new_entry["initials"] = ("".join(c.upper() for c in initials if c.isalpha()))[:3]

    if "date" not in new_entry:
        year, month, day, _, _, _, _, _ = rtc.datetime()
        new_entry["date"] = f"{month:02d}/{day:02d}/{year}"

    # add player name to new_entry if there is an initials match
    if not new_entry.get("full_name"):
        new_entry["full_name"] = find_player_by_initials(new_entry)[0]
        if new_entry["full_name"] is None:
            new_entry["full_name"] = ""

    # Load scores
    top_scores = [DataStore.read_record("leaders", i) for i in range(DataStore.memory_map["leaders"]["count"])]

    # if matches a record without initials in top_scores (score claim) - just add initials
    for entry in top_scores:
        # print(f"SCORE: Check for initials match: {entry['initials']} == {new_entry['initials']}, score: {entry['score']} == {new_entry['score']}")
        if entry["initials"] == "" and entry["score"] == new_entry["score"]:
            print(" using claim - - - - - ")
            entry["initials"] = new_entry["initials"]
            entry["full_name"] = new_entry["full_name"]
            DataStore.write_record("leaders", entry, top_scores.index(entry))

            update_individual_score(new_entry)
            return True

    # Check if the score already exists in the top_scores list
    if any(entry["score"] == new_entry["score"] for entry in top_scores):
        return False  # Entry already exists, do not add it

    update_individual_score(new_entry)
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


def check_for_machine_high_scores(report=True):
    # check for high scores in machine that we dont have yet
    scores = _read_machine_score(UseHighScores=True)
    year, month, day, _, _, _, _, _ = rtc.datetime()
    for idx in range(5):  # with WPC could be 5 scores - -
        if scores[idx][1] > 10000:  # ignore placed fake scores
            new_score = {"initials": scores[idx][0], "full_name": "", "score": scores[idx][1], "date": f"{month:02d}/{day:02d}/{year}", "game_count": S.gameCounter}

            if idx >= len(top_scores) or scores[idx][1] != top_scores[idx]["score"] or scores[idx][0] != top_scores[idx]["initials"]:
                if report:
                    print(f"SCORE: place game score into vector {new_score}")
                claim_score(new_score["initials"], 0, new_score["score"])


def update_tournament(new_entry):
    """place a single new score in the tournament board fram"""

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        log.log("SCORE: tournament add bad Initials")
        return False

    if new_entry["score"] < 10000:
        log.log("SCORE: tournament add bad score")
        return False

    count = DataStore.memory_map["tournament"]["count"]
    rec = DataStore.read_record("tournament", 0)
    nextIndex = rec["index"]

    # check for a match in the tournament board, for Claim Score function
    #   look back 6 games x 4 scores = 24 places for a match
    if "game" in new_entry:  # claim will have a game count
        log.log("SCORE: tournament claim score checking")
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


GameEndCount = 0


def CheckForNewScores(nState=[0]):
    """called by scheduler every 5 seconds"""
    global nGameIdleCounter, GameEndCount

    # power up init state - only runs once
    if nState[0] == 0:
        import machine

        # machine.mem32[0x20081FF8] = 0x01010B3B
        machine.mem32[0x20081FF8] = 0x02030101

        place_machine_scores()
        nState[0] = 1
        # if enter initials on game set high score rewards to zero
        if S.gdata["HSRewards"]["Type"] == 10 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:
            for key, value in S.gdata["HSRewards"].items():
                if key.startswith("HS"):  # Check if the key starts with 'HS'
                    shadowRam[value] = S.gdata["HSRewards"]["DisableByte"]
        from Adjustments import _fixChecksum

        _fixChecksum()

    # only run this if ball in play is enabled
    if S.gdata["BallInPlay"]["Type"] == 1:  # 0 disables score tracking
        # waiting for a game to start
        if nState[0] == 1:
            # Check if active_format exists and is not 0; if so, return early
            # allows gam eis progress to finish in normal mode when format is activeated
            if hasattr(S, "active_format") and getattr(S, "active_format", 0) != 0:
                return

            GameEndCount = 0
            nGameIdleCounter += 1  # claim score list expiration timer
            if nGameIdleCounter > (3 * 60 / 5):  # 3 min, push empty onto list so old games expire
                game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
                _place_game_in_claim_list(game)
                nGameIdleCounter = 0
                print("SCORE: game list 10 minute expire")

            # players could be putting in initials from last game in the event of top 5 score, always check here
            check_for_machine_high_scores(True)
            # if (DataStore.read_record("extras", 0)["enter_initials_on_game"] == False):
            # only call if new score or initials????
            place_machine_scores()

            print("SCORE: game start check ", nGameIdleCounter)
            if shadowRam[S.gdata["InPlay"]["GameActiveAdr"]] == S.gdata["InPlay"]["GameActiveValue"]:
                nState[0] = 2
                # Game Started!
                log.log("SCORE: Game Started")
                nGameIdleCounter = 0
                if DataStore.read_record("extras", 0)["enter_initials_on_game"]:
                    _remove_machine_scores()
                S.gameCounter = (S.gameCounter + 1) % 100

        # waiting for game to end
        elif nState[0] == 2:
            print("SCORE: game end check ")
            print(_read_machine_score(UseHighScores=True))
            if shadowRam[S.gdata["InPlay"]["GameActiveAdr"]] != S.gdata["InPlay"]["GameActiveValue"]:
                nState[0] = 3

        # game over, wait for intiials to be entered
        elif nState[0] == 3:
            # time out
            GameEndCount += 1
            if GameEndCount > 75:
                nState[0] = 4  # called @ 5second intervals, inital enter time limit is 90 seconds per player.
                GameEndCount = 0

            # game start check, if a game starts get out of here
            if shadowRam[S.gdata["InPlay"]["GameActiveAdr"]] == S.gdata["InPlay"]["GameActiveValue"]:
                nState[0] = 4

            # game has ended but players can be putting in initials now, wait for scores to show up
            if S.gdata["HighScores"]["Type"] == 10 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:
                # how many players? wait for all initials to go in and fake scores to be replaced

                # grand champ score is maxed out so no player gets it
                scores = _read_machine_score(UseHighScores=True)
                high_score_count = 0
                high_score_count = sum(1 for x in range(1, 5) if scores[x][1] > 10000)

                if high_score_count >= shadowRam[S.gdata["InPlay"]["Players"]]:
                    print("SCORE: initials are all entered now")
                    nState[0] = 4
                print("SCORE: waiting for initials, count = ", high_score_count, " players = ", shadowRam[S.gdata["InPlay"]["Players"]])
            else:
                # go ahead and end game, on game initials are not enabled
                print("SCORE: game over, not waiting for initials")
                nState[0] = 4

        # game over clean up process
        elif nState[0] == 4:
            # game over - back to top state
            nState[0] = 1
            if not DataStore.read_record("extras", 0)["enter_initials_on_game"]:
                # in play scores
                log.log("SCORE: end, use in-play scores")
                scores = _read_machine_score(UseHighScores=False)

            else:
                # high scores
                log.log("SCORE: end, use high scores")
                scores = _read_machine_score(UseHighScores=True)[1:]  # remove grand champ

            if DataStore.read_record("extras", 0)["tournament_mode"]:
                for i in range(0, 4):
                    if scores[i][1] > 10000:
                        update_tournament({"initials": scores[i][0], "score": scores[i][1]})
            else:
                for i in range(0, 4):
                    if scores[i][1] > 10000:
                        update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

            # Update claim list
            game = [S.gameCounter] + [tuple(scores[i]) for i in range(4)]

            # Set any placeholder scores less than 10000 to zero and no initials
            game = [game[0]] + [("", 0) if score[1] < 10000 else score for score in game[1:]]
            _place_game_in_claim_list(game)

            # put high scores back in machine memory
            if DataStore.read_record("extras", 0)["enter_initials_on_game"]:
                place_machine_scores()
