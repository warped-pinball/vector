# WPC

# This file is part of the Warped Pinball WOC - Wifi Project.
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



def reset_scores():
    from SPI_DataStore import blankStruct    
    blankStruct("leaders")
    _remove_machine_scores(GrandChampMax=False)



def fix_high_score_checksum():
    """fix high score checksum if needed"""
    # check for high score checksum
    if S.gdata["HighScores"]["Type"] == 10:  # 10 for std WPC
        chk = 0
        for adr in range(S.gdata["HighScores"]["ChecksumStartAdr"], S.gdata["HighScores"]["ChecksumEndAdr"] + 1):
            chk = chk + shadowRam[adr]
        chk =0xFFFF - chk
        # Store MSByte and LSByte
        msb = (chk >> 8) & 0xFF
        lsb = chk & 0xFF
        #print("SCORE: Checksum: ---------------- ", hex(chk), hex(msb), hex(lsb))
        shadowRam[S.gdata["HighScores"]["ChecksumResultAdr"]] = msb
        shadowRam[S.gdata["HighScores"]["ChecksumResultAdr"] + 1] = lsb



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

    #condition the initials - more important than one would think.  machines freak if non printables get in
    initials = initials.upper()
    i_intials = ""
    for c in initials:
        if 'A' <= c <= 'Z':
            i_intials += c
    initials = (i_intials + "   ")[:3]

    for game_index, game in enumerate(recent_scores):
        if game[player_index + 1][1] == score and game[player_index + 1][0] == "":
            log.log(f"SCORE: claim new score: {initials}, {score}, {game_index}, {player_index}")
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


def _read_machine_score(UseHighScores = True):
    """read machine scores
    and if HighScores is True try to get intials from highscore area
    """
    high_scores = [["", 0], ["", 0], ["", 0], ["", 0], ["", 0]]
    in_play_scores = [["", 0], ["", 0], ["", 0], ["", 0]]

    # Build a set of all four in-play scores, index=0,1,2,3 (by player number)
    try:
        if S.gdata["InPlay"]["Type"] == 10:  #10 for std WPC
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
            score_start = S.gdata["HighScores"]["ScoreAdr"] + (idx-1) * S.gdata["HighScores"]["ScoreSpacing"]
            score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
            high_scores[idx][1] = _bcd_to_int(score_bytes)
            if high_scores[idx][1] < 1000:
                high_scores[idx][1] = 0
        #is there a grand champion score also?    put in order, games have GC in 5th place
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]  
            score_bytes = shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]]
            high_scores[0][1] = _bcd_to_int(score_bytes)
            if high_scores[0][1] < 1000:
                high_scores[0][1] = 0


        # initials
        if "InitialAdr" in S.gdata["HighScores"]:
            for idx in range(1, 5):
                initial_start = S.gdata["HighScores"]["InitialAdr"] + (idx-1) * S.gdata["HighScores"]["InitialSpacing"]
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
                if high_scores[0][0] in ["???", "", None, "   "]:
                    high_scores[0][0] = ""


        # if we have high scores, intials AND in-play socres, put initials to the in play scores
        for in_play_score in in_play_scores:
            for high_score in high_scores:
                if in_play_score[1] == high_score[1]:
                    in_play_score[0] = high_score[0]  # copy initals over

    if UseHighScores:
        log.log("SCORE: High Scores used")
        return high_scores
    else:
        log.log("SCORE: In play scores used")
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
    num_str = f"{number:0{ScoreBytes*2}d}"
    bcd_bytes = bytearray(ScoreBytes)
    # Fill byte array
    for i in range(ScoreBytes):
        bcd_bytes[i] = (int(num_str[2 * i]) << 4) + int(num_str[2 * i + 1])
    return bcd_bytes



def place_machine_scores():
    """write four (plus grand champ?) highest scores & initials from storage to machine memory"""
    global top_scores

    #possible high score intials are empty if there was a reset / reboot etc
    #games do not like empties!
    for index in range(5):  # incase of grand champ - 5 scores
        if len(top_scores[index]["initials"]) != 3:
            top_scores[index]["initials"] = "   "
            #top_scores[index]["score"] = 100  only change intials, not score (blank initials happen with good scores sometimes)

    if S.gdata["HighScores"]["Type"] == 10:
        log.log("SCORE: Place WPC machine scores")

        gc=0
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            gc=1
            #place grand champion score
            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]
            try:
                scoreBCD = _int_to_bcd(top_scores[0]["score"])
            except Exception:
                log.log("SCORE: score convert problem")
                scoreBCD = _int_to_bcd(100)

            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = scoreBCD
            #print("  top scores: ", top_scores[0])

            #grand champ initials
            try:
                initial_start = S.gdata["HighScores"]["GrandChampInitAdr"]
                initials = top_scores[0]["initials"]
                for i in range(3):
                    shadowRam[initial_start + i] = ord(initials[i])   #std ASCII
            except Exception:
                log.log("SCORE: place machine scores exception")
                shadowRam[initial_start] = 64
                shadowRam[initial_start + 1] = 64
                shadowRam[initial_start + 2] = 64


        for index in range(4): 
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index *  S.gdata["HighScores"]["ScoreSpacing"]
            try:
                scoreBCD = _int_to_bcd(top_scores[index+gc]["score"])  # +1 (gc) if grand champ was loaded
            except Exception:
                log.log("SCORE: score convert problem")
                scoreBCD = _int_to_bcd(100)

            shadowRam[score_start : score_start + S.gdata["HighScores"]["BytesInScore"]] = scoreBCD
            #print("  top scores: ", top_scores[index+gc])

            try:
                initial_start = S.gdata["HighScores"]["InitialAdr"] + index * S.gdata["HighScores"]["InitialSpacing"]
                initials = top_scores[index+gc]["initials"]
                for i in range(3):
                    shadowRam[initial_start + i] = ord(initials[i])   #std ASCII
                    
            except Exception:
                log.log("SCORE: place machine scores exception")
                shadowRam[initial_start] = 64
                shadowRam[initial_start + 1] = 64
                shadowRam[initial_start + 2] = 64

        fix_high_score_checksum()
   




def _remove_machine_scores(GrandChampMax=True):
    """remove machine scores - WPC"""
    if S.gdata["HighScores"]["Type"] == 10 and DataStore.read_record("extras", 0)["enter_initials_on_game"] is True:     #WPC
        log.log("SCORE: Remove machine scores type 10")
        for index in range(4):
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["ScoreSpacing"]
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * S.gdata["HighScores"]["InitialSpacing"]

            for i in range(S.gdata["HighScores"]["BytesInScore"]):
                shadowRam[score_start + i] = 0       # score

            shadowRam[score_start + S.gdata["HighScores"]["BytesInScore"]-2] = 0x10 * (6 - index )

            for i in range(3):
                shadowRam[initial_start + i] = 0x41  # intials all 'A'


        # set grand champion score to max, so all players will be int he normal 1-4 places
        if "GrandChampScoreAdr" in S.gdata["HighScores"]:
            #initial_start = S.gdata["HighScores"]["GrandChampInitAdr"]
            #shadowRam[initial_start + i] = 0x41 
            #shadowRam[initial_start + i] = 0x41 
            #shadowRam[initial_start + i] = 0x41 

            score_start = S.gdata["HighScores"]["GrandChampScoreAdr"]            
            if GrandChampMax:
                # set grand champion score to max
                for i in range(S.gdata["HighScores"]["BytesInScore"]):
                    shadowRam[score_start + i] = 0x99
            #else: 
            #    for i in range(S.gdata["HighScores"]["BytesInScore"]):
            #        shadowRam[score_start + i] = 0x00
            #        shadowRam[score_start + S.gdata["HighScores"]["BytesInScore"]-4] = 0x90

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
    initials = new_entry["initials"]
    playername, playernum = find_player_by_initials(new_entry)

    if not playername or playername in [" ", "@@@", "   "]:
        #print("SCORE: No indiv player ", initials)
        pass
        return False

    if not (0 <= playernum < DataStore.memory_map["individual"]["count"]):
        log.log("SCORE: Player out of range")
        return False

    new_entry["full_name"] = playername

    # Load existing scores
    scores = []
    num_scores = DataStore.memory_map["individual"]["count"]
    #print("SCORE: num sores = ", num_scores, playernum)
    for i in range(num_scores):
        scores.append(DataStore.read_record("individual", i, playernum))

    scores.append(new_entry)
    scores.sort(key=lambda x: x["score"], reverse=True)
    scores = scores[:20]

    # Save the updated scores
    for i in range(num_scores):
        DataStore.write_record("individual", scores[i], i, playernum)

    #print(f"Updated scores for {initials}")
    return True




def update_leaderboard(new_entry):
    """called by check for new scores, one call for each valid new score entry"""
    global top_scores

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        log.log("SCORE: Bad Initials")
        return False

    year, month, day, _, _, _, _, _ = rtc.datetime()
    new_entry["date"] = f"{month:02d}/{day:02d}/{year}"

    #og.log( f"SCORE: Update Leader Board: {new_entry}")
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


def check_for_machine_high_scores(report=True):
    # check for high scores in machine that we dont have yet
    scores = _read_machine_score(UseHighScores= True)
    year, month, day, _, _, _, _, _ = rtc.datetime()
    for idx in range(5):   #with WPC could be 5 scores - - 

        if scores[idx][1] > 9000:  #ignore placed fake scores            
            new_score = {"initials": scores[idx][0], "full_name": "", "score": scores[idx][1], "date": f"{month:02d}/{day:02d}/{year}", "game_count": S.gameCounter}
            if report:
                log.log("SCORE: place game score into vector")
            update_leaderboard(new_score)
   



def update_tournament(new_entry):
    """place a single new score in the tournament board fram"""

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        log.log("SCORE: tournament add bad Initials")
        return False

    if new_entry["score"] < 10000 :
        log.log("SCORE: tournament add bad score")
        return False

    count = DataStore.memory_map["tournament"]["count"]
    rec = DataStore.read_record("tournament", 0)
    nextIndex = rec["index"]


    #check for a match in the tournament board, for Claim Score function
    #   look back 6 games x 4 scores = 24 places for a match
    if "game" in new_entry:  #claim will have a game count
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



GameEndCount =0
def CheckForNewScores(nState=[0]):
    """called by scheduler every 5 seconds"""
    global nGameIdleCounter,GameEndCount

    if nState[0] == 0:  # power up init        
        place_machine_scores()
        nState[0] = 1
        # if enter initials on game set high score rewards to zero
        if S.gdata["HSRewards"]["Type"] == 1 and DataStore.read_record("extras", 0)["enter_initials_on_game"]:
            shadowRam[S.gdata["HSRewards"]["HS1"]] = S.gdata["HSRewards"]["DisableByte"]
            shadowRam[S.gdata["HSRewards"]["HS2"]] = S.gdata["HSRewards"]["DisableByte"]
            shadowRam[S.gdata["HSRewards"]["HS3"]] = S.gdata["HSRewards"]["DisableByte"]
            shadowRam[S.gdata["HSRewards"]["HS4"]] = S.gdata["HSRewards"]["DisableByte"]
       
    if S.gdata["BallInPlay"]["Type"] == 1:  # 0 disables score tracking
       
        if nState[0] == 1:  # waiting for a game to start           
            GameEndCount =0
            nGameIdleCounter += 1  # claim score list expiration timer
            if nGameIdleCounter > (3 * 60 / 5):  # 3 min, push empty onto list so old games expire
                game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
                _place_game_in_claim_list(game)
                nGameIdleCounter = 0
                print("SCORE: game list 10 minute expire")

            #players could be putting in initials from last game in the event of top 5 score, always check here
            check_for_machine_high_scores(False)    

            print("SCORE: game start check ", nGameIdleCounter)
            if shadowRam[S.gdata["InPlay"]["GameActiveAdr"]] == S.gdata["InPlay"]["GameActiveValue"]:
                nState[0] = 2
                # Game Started!
                log.log("SCORE: Game Started")
                nGameIdleCounter = 0
                _remove_machine_scores()
                S.gameCounter = (S.gameCounter + 1) % 100

        elif nState[0] == 2:  # waiting for game to end
            print("SCORE: game end check ",GameEndCount)
            print(_read_machine_score(UseHighScores= True))           

            if shadowRam[S.gdata["InPlay"]["GameActiveAdr"]] != S.gdata["InPlay"]["GameActiveValue"]:
                GameEndCount += 1
                if GameEndCount > 30: 
                    nState[0] = 3   #timeout

                #game has ended but players can be putting in initials now, wait for scores to show up
                if S.gdata["HighScores"]["Type"] == 10 and DataStore.read_record("extras", 0)["enter_initials_on_game"] is True:   
                    #how many players? wait for all initials to go in and fake scoes to be replaced
                    scores = _read_machine_score(UseHighScores= True)
                    high_score_count = 0
                    for x in range(1,5):
                        if scores[x][1] > 10000: 
                            high_score_count += 1
                    if high_score_count >= shadowRam[S.gdata["InPlay"]["Players"]]:    
                        print("SCORE: initials are all entered now")                                            
                        nState[0] = 3                    
                    print("SCORE: waiting for initials, count = ", high_score_count, " players = ", shadowRam[S.gdata["InPlay"]["Players"]])    
                else:
                    #go ahead and end game, on game initials are not enabled
                    print("SCORE: game over, not waiting for initials")
                    nState[0]=3


        elif nState[0]==3:                
                    # game over
                    nState[0] = 1
                    if (DataStore.read_record("extras", 0)["enter_initials_on_game"] is False):
                        # in play scores
                        log.log("SCORE: end, use in-play scores")
                        scores = _read_machine_score(UseHighScores= False)                    
                    else:
                        # high scores
                        log.log("SCORE: end, use high scores")
                        scores = _read_machine_score(UseHighScores= True)
                
                    if DataStore.read_record("extras", 0)["tournament_mode"]:
                        for i in range(0, 4):
                            if scores[i][1] > 9000:    
                                update_tournament({"initials": scores[i][0], "score": scores[i][1]})
                    else:
                        for i in range(0, 4):        
                            if scores[i][1] > 9000:          
                                update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

                    game = [S.gameCounter, scores[0], scores[1], scores[2], scores[3]]
                    _place_game_in_claim_list(game)

                    # put high scores back in machine memory
                    place_machine_scores()


