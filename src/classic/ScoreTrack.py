# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track - Classic

    This module is responsible for tracking scores and updating the leaderboard.
    Classics only support BallInPlay/InPlay/HighScores Type 30: a single
    machine high score with no initials, and per-player in-play scores read
    from shadow RAM via DataMapper.
"""
import displayMessage
import SharedState as S
import DataMapper
import SPI_DataStore as DataStore
from logger import logger_instance
from machine import RTC

log = logger_instance

rtc = RTC()
top_scores = []
nGameIdleCounter = 0
push_game_count = 0
last_pushed_game = [["", 0], ["", 0], ["", 0], ["", 0]]

# hold the last four (plus two older records) games worth of scores.
# first number is game counter (game ID), then 4 scores plus initials
recent_scores = [
    [0, ("", 0), ("", 0), ("", 0), ("", 0)],
    [1, ("", 0), ("", 0), ("", 0), ("", 0)],
    [2, ("", 0), ("", 0), ("", 0), ("", 0)],
    [3, ("", 0), ("", 0), ("", 0), ("", 0)],
    [4, ("", 0), ("", 0), ("", 0), ("", 0)],
    [5, ("", 0), ("", 0), ("", 0), ("", 0)],
]


def reset_scores():
    # reset leader board scores
    from SPI_DataStore import blankStruct
    blankStruct("leaders")


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

    # Sanitize initials: 3 uppercase letters only
    initials = ("".join(c for c in initials.upper() if c.isalpha()) + "   ")[:3]

    for game_index, game in enumerate(recent_scores):
        if game[player_index + 1][1] == score and game[player_index + 1][0] == "":
            log.log(f"SCORE: claim new score: {initials}, {score}, {game_index}, {player_index}")
            recent_scores[game_index][player_index + 1] = (initials, score)
            new_score = {"initials": initials, "full_name": None, "score": score, "game": game[0]}
            if DataStore.read_record("extras", 0)["tournament_mode"]:
                update_tournament(new_score)
            else:
                update_leaderboard(new_score)
            return
    raise ValueError("SCORE: Score not found in claim list")


def _place_game_in_claim_list(game):
    """place game up to four players in claim list"""
    global push_game_count, last_pushed_game
    recent_scores.insert(0, game)
    recent_scores.pop()
    print("SCORE: add to claims list: ", recent_scores)


def place_machine_scores():
    """No-op: classics do not support writing scores back to the machine."""
    return


def find_player_by_initials(new_entry):
    """find players name from list of initials with names from storage"""
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
    """update a players individual score board"""
    initials = new_entry["initials"]
    playername, playernum = find_player_by_initials(new_entry)

    if not playername or playername in [" ", "@@@", "   "]:
        print("SCORE: No indiv player ", initials)
        return False

    if not (0 <= playernum < DataStore.memory_map["individual"]["count"]):
        log.log("SCORE: Player out of range")
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
    scores = scores[:num_scores]

    # Save the updated scores
    for i in range(num_scores):
        DataStore.write_record("individual", scores[i], i, playernum)

    print(f"Updated scores for {initials}")
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

    log.log(f"SCORE: Update Leader Board: {new_entry}")
    update_individual_score(new_entry)

    # add player name to new_entry if there is an initials match
    if not new_entry.get("full_name"):  # could come in with name from score load on admin page
        new_entry["full_name"], _ = find_player_by_initials(new_entry)
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


def check_for_machine_high_scores():
    """check for a high score in the machine that vector doesn't have yet"""
    if S.gdata.get("HighScores", {}).get("Type") != 30:
        return

    score = DataMapper.read_high_scores()[0][1]
    if score > 1000:  # could be leftover placeholder digits
        year, month, day, _, _, _, _, _ = rtc.datetime()
        new_score = {"initials": "", "full_name": "", "score": score, "date": f"{month:02d}/{day:02d}/{year}", "game_count": S.gameCounter}
        log.log("SCORE: place machine high score into vector")
        update_leaderboard(new_score)


def update_tournament(new_entry):
    """place a single new score in the tournament board fram"""

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        log.log("SCORE: tournament add bad Initials")
        return False

    if new_entry["score"] < 1000:
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


def CheckForNewScores(nState=[0]):
    """called by scheduler every 5 seconds"""
    global nGameIdleCounter, push_game_count, last_pushed_game

    if push_game_count > 0:
        from origin import push_end_of_game
        push_game_count += 1
        push_end_of_game(last_pushed_game, push_game_count)
        if push_game_count > 5:
            push_game_count = 0

    if nState[0] == 0:  # power up init        
        nState[0] = 1

    if S.gdata["BallInPlay"]["Type"] == 30:

        if nState[0] == 1:  # waiting for a game to start

            # Check if active_format is non-zero; if so, return early
            # Allows game in progress to finish in normal mode when format is activated
            if S.active_format.get("Id", 0) != 0:
                return

            nGameIdleCounter += 1  # claim score list expiration timer
            if nGameIdleCounter > (3 * 60 // 5):  # 3 min, push empty onto list so old games expire
                game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
                _place_game_in_claim_list(game)
                nGameIdleCounter = 0
                print("SCORE: game list 10 minute expire")

            print("SCORE: game start check ", nGameIdleCounter)
            if DataMapper.get_game_active():
                nState[0] = 2
                # Game Started!
                log.log("SCORE: Game Started")
                nGameIdleCounter = 0

        elif nState[0] == 2:  # waiting for game to end
            print("SCORE: game end check")
            if not DataMapper.get_game_active():
                # Game just went inactive. The score digits can still be
                # settling right at this instant, so don't trust it - wait
                # for the next poll tick and read the final scores then.
                nState[0] = 3

        elif nState[0] == 3:  # confirm game end, read final settled scores
            print("SCORE: game end confirm - final score read")
            scores = DataMapper.read_in_play_scores()

            if DataStore.read_record("extras", 0)["tournament_mode"]:
                for i in range(0, 4):
                    update_tournament({"initials": scores[i][0], "score": scores[i][1]})
            else:
                for i in range(0, 4):
                    update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

            game = [S.gameCounter, scores[0], scores[1], scores[2], scores[3]]
            _place_game_in_claim_list(game)

            from origin import push_end_of_game
            push_game_count = 1
            last_pushed_game = game
            push_end_of_game(last_pushed_game, push_game_count)

            S.gameCounter = (S.gameCounter + 1) % 100
            nState[0] = 1
