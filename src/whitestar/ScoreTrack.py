#  Whitestar

# This file is part of the Warped Pinball Vector (Whitestar) Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    This module is responsible for tracking scores and updating the leaderboard.
    Must account for highscores and in play score availability

Whitestar: a game is active while PlayerUp is non-zero (InPlay Type 40).
The live scores (5 byte BCD, players 1-4) are read during play and at game
end.

With HighScores Type 40 (all game configs) the machine table is kept in step
with the leaderboard:
  - power-up: scores in the machine that Vector does not have are imported,
    then the leaderboard's top scores are written into the machine table
  - "enter initials on game": the table is replaced by low placeholders at
    game start, so every player's score makes the table and the game asks
    for initials; after the game the initials are matched to the player
    scores and the leaderboard is written back into the machine
  - web changes (delete a score, reset, import) call place_machine_scores()
With HighScores Type 0 scores go to the leaderboard without initials and can
be claimed from the web page.
"""
import DataMapper
import SharedState as S
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


def _min_score():
    """Scores at or below this are placeholders / noise and never recorded."""
    return S.gdata["GameInfo"].get("MinScore", 10000)


def reset_scores():
    """reset leader board scores (and the machine's table when it is known)"""
    global top_scores
    print("RESET Leader scores")
    DataStore.blankStruct("leaders")
    # drop the cached copy too, or place_machine_scores() writes the old leaders back
    top_scores = []
    DataMapper.remove_machine_scores()


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


def claim_score(initials, player_index, score, from_machine=False):
    """claim a score from the recent scores list - do not require a player index, search all

    from_machine: the score came from the machine's own high score table, so it is placed even when
    it is not in the claim list"""
    global recent_scores

    if not isinstance(initials, str):
        raise ValueError("SCORE: invalid initials")
    if isinstance(score, bool) or not isinstance(score, int) or score <= 0:
        raise ValueError("SCORE: invalid score")

    # condition the initials - machines freak if non printables get in
    i_initials = ""
    for c in initials.upper():
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

    if from_machine:
        update_leaderboard({"initials": initials, "full_name": None, "score": score, "game": 0})
        return

    raise ValueError("SCORE: Score not found in claim list")


def _place_game_in_claim_list(game):
    """place game up to four players in claim list"""
    recent_scores.insert(0, game)
    recent_scores.pop()
    print("SCORE: add to claims list: ", recent_scores)


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
    playername, playernum = find_player_by_initials(new_entry)

    if not playername or playername in [" ", "@@@", "   ", ""]:
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
        if entry["initials"] == "" and entry["score"] == new_entry["score"]:
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
            rec = {"initials": "   ", "full_name": "", "score": 100 + (count - i) * 100, "date": "01/01/2025", "game_count": 0}
            log.log(f"SCORE: leaders[{i}] was None/corrupt, using default")
        top_scores.append(rec)


def check_for_machine_high_scores(report=True):
    """pick up high scores with initials the machine has that the leaderboard has not (HighScores Type 40 only)"""
    if not DataMapper.high_scores_supported():
        return
    known = [(entry.get("initials", ""), entry.get("score", 0)) for entry in top_scores]
    for initials, score in DataMapper.read_high_scores():
        if score <= _min_score() or not initials.strip():
            continue
        if (initials, score) in known:
            continue
        if report:
            print(f"SCORE: place game score into vector {initials} {score}")
        claim_score(initials, 0, score, from_machine=True)


def place_machine_scores():
    """Write the leaderboard's top scores back into the machine's high score table (HighScores Type 40 only)"""
    global top_scores
    if not DataMapper.high_scores_supported():
        return

    print("SCORE: Place Whitestar machine scores")
    count = S.gdata["HighScores"].get("NumberOfScores", 4)
    machine_scores = []
    for entry in top_scores[:count]:
        initials = entry.get("initials", "") or "   "
        if len(initials) != 3:
            initials = "   "
        machine_scores.append([initials, entry.get("score", 0)])
    while len(machine_scores) < count:
        machine_scores.append(["", 0])

    DataMapper.write_high_scores(machine_scores)


def update_tournament(new_entry):
    """place a single new score in the tournament board fram"""

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        log.log("SCORE: tournament add bad Initials")
        return False

    if new_entry["score"] < _min_score():
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


# State for CheckForNewScores
STATE_INIT = 0      # power up initialization
STATE_WAITING = 1   # waiting for a game to start
STATE_PLAYING = 2   # game in progress
STATE_INITIALS = 3  # game over, waiting for initials to be entered on the machine
STATE_FINISH = 4    # record the game

_game_state = STATE_INIT
GameEndCount = 0
initials_capture_this_game = False
live_scores = [["", 0], ["", 0], ["", 0], ["", 0]]
# most players seen during the current game; the game clears its Players byte at game over
players_this_game = 0
# initials entry on the machine is ~90 seconds per player, polls are 5 seconds apart
INITIALS_TIMEOUT_POLLS = 75


def _snapshot_live_scores():
    """Latest machine scores; keeps the previous snapshot when the machine has blanked them."""
    global live_scores
    scores = DataMapper.get_live_scores()
    if any(score != 0 for score in scores):
        live_scores = [["", scores[i]] for i in range(4)]
    return live_scores


def CheckForNewScores():
    """called by scheduler every 5 seconds"""
    global nGameIdleCounter, GameEndCount, _game_state, initials_capture_this_game, live_scores
    global push_game_count, last_pushed_game, players_this_game

    if push_game_count > 0:
        from origin import push_end_of_game

        push_game_count += 1
        push_end_of_game(last_pushed_game, push_game_count)
        if push_game_count > 5:
            push_game_count = 0

    # power up init state - only runs once
    if _game_state == STATE_INIT:
        _game_state = STATE_WAITING
        check_for_machine_high_scores()
        place_machine_scores()

    # only run this if ball in play / in play tracking is enabled
    if S.gdata["BallInPlay"]["Type"] != DataMapper.BALL_IN_PLAY_TYPE or S.gdata["InPlay"]["Type"] != DataMapper.IN_PLAY_TYPE:
        return

    # waiting for a game to start
    if _game_state == STATE_WAITING:
        # Check if active_format is non-zero; if so, return early
        # Allows game in progress to finish in normal mode when format is activated
        if S.active_format.get("Id", 0) != 0:
            return

        nGameIdleCounter += 1  # claim score list expiration timer
        if nGameIdleCounter > (3 * 60 // 5):  # 3 min, push empty onto list so old games expire
            game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
            _place_game_in_claim_list(game)
            nGameIdleCounter = 0
            print("SCORE: game list 3 minute expire")

        # players could be putting in initials from the last game, always check here
        check_for_machine_high_scores()

        print("SCORE: game start check ", nGameIdleCounter)
        if DataMapper.get_game_active():
            _game_state = STATE_PLAYING
            log.log("SCORE: Game Started")
            nGameIdleCounter = 0
            live_scores = [["", 0], ["", 0], ["", 0], ["", 0]]
            players_this_game = DataMapper.get_players_in_game()

            initials_capture_this_game = DataMapper.high_scores_supported() and DataStore.read_record("extras", 0)["enter_initials_on_game"] is True
            if initials_capture_this_game:
                DataMapper.remove_machine_scores()

    # waiting for game to end
    elif _game_state == STATE_PLAYING:
        print("SCORE: game end check")
        _snapshot_live_scores()
        # players can be added during ball 1; keep the highest count, it reads 0 after game over
        players_this_game = max(players_this_game, DataMapper.get_players_in_game())
        if not DataMapper.get_game_active():
            GameEndCount = 0
            _game_state = STATE_INITIALS if initials_capture_this_game else STATE_FINISH

    # game over, wait for initials to be entered
    elif _game_state == STATE_INITIALS:
        GameEndCount += 1
        if GameEndCount > INITIALS_TIMEOUT_POLLS:
            _game_state = STATE_FINISH

        # a new game started while waiting - wrap up now
        if DataMapper.get_game_active():
            _game_state = STATE_FINISH

        # an entry counts once all 3 initials are in (the game shows a cursor while a name is being typed)
        high_scores = DataMapper.read_high_scores()
        high_score_count = sum(1 for entry in high_scores if entry[1] > _min_score() and sum(1 for c in entry[0] if c.isalpha()) == 3)
        # the Players byte is 0 by now, so compare against the count kept during play (at least 1)
        expected_players = max(players_this_game, 1)
        print("SCORE: waiting for initials, count = ", high_score_count, " players = ", expected_players)
        if high_score_count >= expected_players:
            print("SCORE: done - got all players initials")
            _game_state = STATE_FINISH

    # game over clean up process - no elif, runs in the same poll
    if _game_state == STATE_FINISH:
        _game_state = STATE_WAITING

        scores = [[entry[0], entry[1]] for entry in live_scores]
        if initials_capture_this_game:
            log.log("SCORE: end, use high scores")
            scores = DataMapper.match_in_play_with_high_score_initials(scores, DataMapper.read_high_scores())
        else:
            log.log("SCORE: end, use in-play scores")

        # placeholder / tiny scores are not games
        scores = [[entry[0], entry[1]] if entry[1] > _min_score() else ["", 0] for entry in scores]

        if DataStore.read_record("extras", 0)["tournament_mode"]:
            for i in range(4):
                if scores[i][1] > _min_score():
                    update_tournament({"initials": scores[i][0], "score": scores[i][1]})
        else:
            for i in range(4):
                if scores[i][1] > _min_score():
                    update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

        # Update claim list
        game = [S.gameCounter] + [tuple(scores[i]) for i in range(4)]

        from origin import push_end_of_game

        push_game_count = 1
        last_pushed_game = game
        push_end_of_game(last_pushed_game, push_game_count)
        _place_game_in_claim_list(game)

        # put high scores back in machine memory
        if initials_capture_this_game:
            place_machine_scores()
        initials_capture_this_game = False

        S.gameCounter = (S.gameCounter + 1) % 100
