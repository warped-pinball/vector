#    DataEast

# This file is part of the Warped Pinball DataEast (Vector) - Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    This module is responsible for tracking scores and updating the leaderboard.
    Must account for highscores and in play score availability
"""
import SharedState as S
import SPI_DataStore as DataStore
from logger import logger_instance
log = logger_instance
from machine import RTC
import DataMapper

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
    [5, ("", 0), ("", 0), ("", 0), ("", 0)],
]


def reset_scores():
    """
        reset high scores
    """
    from SPI_DataStore import blankStruct
    print("RESET Leader scores")
    blankStruct("leaders")
    machine_scores = [["", 1000], ["", 900], ["", 800], ["", 700], ["", 600], ["", 500]]
    DataMapper.write_high_scores(machine_scores)

def get_claim_score_list():
    """
        fetch the list of claimable scores
    """
    result = []
    if DataStore.read_record("extras", 0)["claim_scores"] is True:
        for game in recent_scores[:4]:
            # if there are any unclaimed non zero scores, add them to the list
            if any(score[0] == "" and score[1] != 0 for score in game[1:]):
                # add the game to the list, with all zero scores removed
                result.append([score for score in game[1:] if score[1] != 0])
    return result


def claim_score(initials, player_index, score):
    """
        claim a score from the recent scores list - do not require a player index, search all
    """
    global recent_scores

    # condition the initials - more important than one would think.  machines freak if non printables get in
    initials = initials.upper()
    i_initials = ""
    for c in initials:
        if "A" <= c <= "Z":
            i_initials += c
    initials = (i_initials + "   ")[:3]

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
    """update a players individual score board"""
    initials = new_entry["initials"]
    playername, playernum = find_player_by_initials(new_entry)

    if not playername or playername in [" ", "@@@", "   ", ""]:
        # print("SCORE: No indiv player ", initials)
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
    new_entry["initials"] = ("".join(c.upper() for c in initials if c.isalpha()) )[:3]

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

    # load up top scores from fram with safe defaults
    count = DataStore.memory_map["leaders"]["count"]
    top_scores = []
    for i in range(count):
        rec = DataStore.read_record("leaders", i)
        if rec is None or not isinstance(rec, dict):
            # Create a blank/safe entry if the record is None or corrupt
            rec = {
                "initials": "   ",
                "full_name": "",
                "score": 100 + (count - i) * 100,  # Descending placeholder scores
                "date": "01/01/2025",
                "game_count": 0
            }
            log.log(f"SCORE: leaders[{i}] was None/corrupt, using default")
        top_scores.append(rec)


def check_for_machine_high_scores(report=True):
    # check for high scores in machine that we dont have yet
    pass
    #print(" Check for machine high scores - - - - - - - - -- not - placeholder")


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

# State constants for CheckForNewScores
STATE_INIT = 0           # Power up initialization
STATE_WAITING = 1        # Waiting for game to start
STATE_PLAYING = 2        # Game in progress
_game_state = STATE_INIT


def CheckForNewScores():
    """Called by scheduler every 5 seconds. Tracks game state and updates scores."""
    global nGameIdleCounter, GameEndCount, _game_state

    print(f"SCORE: CheckForNewScores - State={_game_state}, GameEndCount={GameEndCount}, IdleCounter={nGameIdleCounter}")

    # power up init state - only runs once
    if _game_state == STATE_INIT:
        _game_state = STATE_WAITING
        print("SCORE: State 0 - Power up initialization")        
        scores=DataMapper.read_high_scores()        
        print("Power up read machine scores - ",scores)
        for entry in scores:
            # Convert from [initials, score] list format to dict format for update leaderboard
            if isinstance(entry, list) and len(entry) >= 2:
                update_leaderboard({"initials": entry[0], "score": entry[1]})
            elif isinstance(entry, dict):
                update_leaderboard(entry)


        # Pull top 6 scores from leaderboard and write to machine
        machine_scores = []
        for i in range(min(6, len(top_scores))):
            initials = top_scores[i].get("initials", "")
            score = top_scores[i].get("score", 0)
            machine_scores.append([initials, score])    
        
        DataMapper.write_high_scores(machine_scores)


    # only run this if ball in play is enabled
    if S.gdata["BallInPlay"]["Type"] == 20:       
        print(f"SCORE: BallInPlay enabled, current state={_game_state}")

        # waiting for a game to start
        if _game_state == STATE_WAITING:        
            print(f"SCORE: State WAITING - Waiting for game start, IdleCounter={nGameIdleCounter}")
            
            nGameIdleCounter += 1  # claim score list expiration timer
            if nGameIdleCounter > (3 * 60 / 5):  # 3 min, push empty onto list so old games expire
                game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
                _place_game_in_claim_list(game)
                nGameIdleCounter = 0
                print("SCORE: game list 10 minute expire")

            ballInPlay = DataMapper.get_ball_in_play()
            print(f"SCORE: Ball in play = {ballInPlay}")

            if ballInPlay != 0:            
                _game_state = STATE_PLAYING  # Game Started!
                
                log.log("SCORE: Game Started")
                nGameIdleCounter = 0
                if DataStore.read_record("extras", 0)["enter_initials_on_game"] is True:
                    print("SCORE: Removing machine scores (enter_initials_on_game=True)")
                    highScores = [["aaa", 900], ["aaa", 800], ["aaa", 700], ["aaa", 600]]
                    DataMapper.write_high_scores(highScores)
                    
                S.gameCounter = (S.gameCounter + 1) % 100
                print(f"SCORE: New game counter = {S.gameCounter}")

        # waiting for game to end
        elif _game_state == STATE_PLAYING:
            print("SCORE: State PLAYING - Game in progress, waiting for end")         

            ballInPlay = DataMapper.get_ball_in_play()
            print(f"SCORE: Ball in play = {ballInPlay}")
            if ballInPlay == 0:       
                _game_state = STATE_WAITING       
                if S.gdata["HighScores"]["Type"] in range(20, 29):
                    if DataStore.read_record("extras", 0)["enter_initials_on_game"] == True:                    
                        high_scores = DataMapper.read_high_scores()
                        in_play_data = DataMapper.get_in_play_data()
                        in_play_scores = in_play_data["Scores"]
                        print("in play scores - - - - ", in_play_scores)
                        scores = []

                        # Build scores as a list of [initials, score] pairs
                        for in_play_score in in_play_scores:
                            initials = ""
                            for high_score in high_scores:
                                if in_play_score == high_score[1]:
                                    initials = high_score[0]
                                    break
                            scores.append([initials, in_play_score])

                        high_score_count = sum(1 for score in scores if score[1] > 10000)                   
                        print(f"SCORE: High scores entered at game end: {high_score_count}",scores)
                       
                    else:
                        # read in play scores after game over to populate claim list ?  ?
                        log.log("SCORE: end, use in-play scores")
                        in_play_data = DataMapper.get_in_play_data()
                        
                        # Extract scores list from the returned dictionary
                        if isinstance(in_play_data, dict) and "Scores" in in_play_data:
                            # Convert from [score1, score2, score3, score4] to [["", score1], ["", score2], ...]
                            scores = [["", score] for score in in_play_data["Scores"]]
                        else:
                            log.log(f"SCORE: get_in_play_data returned invalid type: {type(in_play_data)}")
                            scores = [["", 0], ["", 0], ["", 0], ["", 0]]
                        print(f"SCORE: In-play scores: {scores}")
           

                    tournament_mode = DataStore.read_record("extras", 0)["tournament_mode"]
                    print(f"SCORE: tournament_mode = {tournament_mode}")
            
                    if tournament_mode:
                        print("SCORE: Updating tournament scores")
                        for i in range(0, 4):
                            if scores[i][1] > 10000:
                                print(f"SCORE: Tournament update - Player {i}: {scores[i]}")
                                update_tournament({"initials": scores[i][0], "score": scores[i][1]})
                    else:
                        print("SCORE: Updating leaderboard scores")
                        for i in range(0, 4):
                            if scores[i][1] > 10000:
                                print(f"SCORE: Leaderboard update - Player {i}: {scores[i]}")
                                update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

                    # Update claim list
                    game = [S.gameCounter] + [tuple(scores[i]) for i in range(4)]
                    print(f"SCORE: Raw game scores: {game}")

                    # Set any placeholder scores less than 10000 to zero and no initials
                    game = [game[0]] + [("", 0) if score[1] < 10000 else score for score in game[1:]]

                    print(f"SCORE: Cleaned game scores: {game}")
                    _place_game_in_claim_list(game)

                    # put high scores back in machine memory
                    if  DataStore.read_record("extras", 0)["enter_initials_on_game"] is True:        
                        print("SCORE: Placing high scores back in machine")

                        # Pull top 6 scores from leaderboard
                        machine_scores = []
                        for i in range(min(6, len(top_scores))):
                            initials = top_scores[i].get("initials", "")
                            score = top_scores[i].get("score", 0)
                            machine_scores.append([initials, score])
                        
                        # Pad to 6 entries if needed
                        while len(machine_scores) < 6:
                            machine_scores.append(["", 0])
                        
                        # Write to machine
                        DataMapper.write_high_scores(machine_scores)
                    
                    print("SCORE: Cleanup complete - returning to state 1")

    else:
        print(f"SCORE: BallInPlay Type={S.gdata['BallInPlay']['Type']} - not monitoring game state")
