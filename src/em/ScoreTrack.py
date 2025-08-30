# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    This module is responsible for tracking scores and updating the leaderboard.
    
    EM version

"""
from machine import RTC,Timer,Pin
import sensorRead
import array
import time

import displayMessage
import SharedState as S
import SPI_DataStore as DataStore
from logger import logger_instance
log = logger_instance

rtc = RTC()
top_scores = []
nGameIdleCounter = 0

from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH

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

lastValue =0
segmentMS =0

GAME_HIST_SIZE = 20000
gameHistory=array.array('H', [0]*GAME_HIST_SIZE)
gameHistoryIndex=0



def reverse_bits_16(x):
    x = ((x & 0xAAAA) >> 1) | ((x & 0x5555) << 1)
    x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2)
    x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4)
    x = ((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)
    #x = x & 0x0F
    return x



PROCESS_IDLE = 0
PROCESS_START = 1
PROCESS_STORE = 2
PROCESS_RUN =3

PROCESS_START_PAUSE = 3
stateVar=0
stateCount=0

gpio0 = Pin(0, Pin.OUT)
gpio0.value(not gpio0.value())

gpio1 = Pin(1, Pin.OUT)
gpio1.value(not gpio1.value())


#called from phew schedeuler 
def processSensorData():
    ''' called each 1 or 2 seconds.  watch game active and decide when to operate on data
    coming in from sensor module -  either store for learning or process for live scores'''
    global lastValue, segmentMS, gameHistory,gameHistoryIndex
    global stateVar, stateCount


    global gpio0
    gpio0.value(not gpio0.value())


    if stateVar == PROCESS_IDLE:
        '''wait for game to start'''
        if sensorRead.gameActive() == 1:
            stateVar = PROCESS_START
        else:
            processEmpty()

    elif stateVar == PROCESS_START:
        '''game start delay'''
        if sensorRead.gameActive()==1:
            stateCount += 1
            if stateCount > PROCESS_START_PAUSE:

                #run or store for learning
                if S.run_learning_game == True:
                    stateVar = PROCESS_STORE
                else:
                    stateVar = PROCESS_RUN
        else:
            stateVar = PROCESS_IDLE  


    elif stateVar == PROCESS_STORE:
        #store data for learn
        processAndStore()
        if sensorRead.gameActive() == 0:
            stateVar = PROCESS_IDLE  


    elif stateVar == PROCESS_RUN:
        #run data now - live score
        processAndRun()
        if sensorRead.gameActive() == 0:
            stateVar = PROCESS_IDLE  




# Define the RAM as an array of 32-bit unsigned ints
import uctypes
ram_bytes = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
bufferPointerIndex = 0
SRAM_BIT_MASK = (SRAM_DATA_LENGTH-1)

def pullWithDelete():
    '''optimized for speed, 1000 calls approx = 50mS'''
    global bufferPointerIndex
    offset = bufferPointerIndex   
    b0 = ram_bytes[offset]
    b1 = ram_bytes[offset+1]
    b2 = ram_bytes[offset+2]
    b3 = ram_bytes[offset+3]
    word = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    if word != 0:        
        ram_bytes[offset] = 0
        ram_bytes[offset+1] = 0
        ram_bytes[offset+2] = 0
        ram_bytes[offset+3] = 0
        bufferPointerIndex += 4
        bufferPointerIndex &= SRAM_BIT_MASK
    return word


def processEmpty():
    ''' pull and discard during gameActive is false'''
    global bufferPointerIndex, gpio1
    for x in range(2500):
        if pullWithDelete() == 0:        
            return
                
        
    
def processAndStore():
    '''compress as data and time values - store into large buffer (gameHistory)'''
    gpio1.value(1)

    gpio1.value(0)
    return


def processAndRun():
    pass



    '''
    if sensor.gameActive() == 1:

        for i in range (400):

            newValue = sensor.pop_buffer()  
            if newValue is not None:
                newValue = reverse_bits_16(newValue)
                newValue = newValue & 0x0F     

                if segmentMS > 2000 or newValue != lastValue:  
                    # store value and time
                    if gameHistoryIndex < (GAME_HIST_SIZE-6):
                        gameHistory[gameHistoryIndex]=lastValue
                        gameHistoryIndex += 1
                        #gameHistory.append(lastValue)
                        gameHistory[gameHistoryIndex]=segmentMS
                        gameHistoryIndex += 1
                        #gameHistory.append(segmentMS)
                        print("!",lastValue,segmentMS, gameHistoryIndex)
                    else:
                        print("FULL")    

                    lastValue = newValue
                    segmentMS = 1

                else:
                    # if newValue == lastValue:
                    segmentMS = segmentMS + 1



    #for i in range(990):
    #    newValue = sensor.pop_buffer()   
        
    return
    

    import SharedState as S
    if S.game_status["game_active"] == False:
        if len(gameHistory) > 0:
            #gameHistory.clear()  # dump data in place            
            sensor.clear_buffer()          

    else:  # game is active       

        for i in range(500):
            newValue = sensor.pop_buffer()   


        return





        limit=5000
        #print("!")
        while True:
            newValue = sensor.pop_buffer()                      
            if newValue is None:
                print("     none")
                return
            
            newValue = reverse_bits_16(newValue)
            newValue = newValue & 0x0F            
            
            if segmentMS > 65533 or newValue != lastValue:
                # store value and time
                if len(gameHistory) < 1000:
                    gameHistory.append(lastValue)
                    gameHistory.append(segmentMS)
                    print("!",lastValue,segmentMS)
                else:
                    print("FULL")    

                lastValue = newValue
                segmentMS = 1

            else:
                # if newValue == lastValue:
                segmentMS = segmentMS + 1

            limit = limit -1
            if limit <0:
                print("store data exit",sensor.buffer_length())
                return
    '''




def plen():
    global lastValue, segmentMS, gameHistory
    return len(gameHistory)









def reset_scores():
    #reset leader board scores
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


def _read_machine_score(HighScores):
    """read machine scores
    and if HighScores is True try to get intials from highscore area
    """
    pass


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
    pass



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
    scores = scores[:20]

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

    year, month, day, _, _, _, _, _ = rtc.datetime()
    new_entry["date"] = f"{month:02d}/{day:02d}/{year}"

    log.log( f"SCORE: Update Leader Board: {new_entry}")
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


def check_for_machine_high_scores():
    pass

def update_tournament(new_entry):
    """place a single new score in the tournament board fram"""

    if new_entry["initials"] in ["@@@", "   ", "???"]:  # check for corruption/ no player
        log.log("SCORE: tournament add bad Initials")
        return False

    if new_entry["score"] < 1000 :
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



import resource

def CheckForNewScores(nState=[0]):
    """called by scheduler every 5 seconds"""
    global nGameIdleCounter
    global gameHistory

    resource.go()

    if nState[0] == 0:  # power up init       
        nState[0] = 1

    if nState[0] == 1:  # waiting for a game to start       
        nGameIdleCounter += 1  # claim score list expiration timer
        print("SCORE: game start check - ",  sensorRead.depthSensorRx() , gameHistoryIndex)

        if nGameIdleCounter > (3 * 60 / 5):  # 3 min, push empty onto list so old games expire
            game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
            _place_game_in_claim_list(game)
            nGameIdleCounter = 0
            print("SCORE: game list 10 minute expire")                     

        #if game_active_flag == True:
        if sensorRead.gameActive() == 1:
            #if S.game_status["game_active"]==True:    #comes from IRQs above
            S.game_status["game_active"]=True
            print("SCORE: Game Start")
            nState[0] = 2



    elif nState[0] == 2:  # waiting for game to end

    
        #process data in storeage...

        print("SCORE: game end check ",  sensorRead.depthSensorRx() ,  gameHistoryIndex  )

        if sensorRead.gameActive() == 0:
            print("SCORE: Game End")
            S.game_status["game_active"]=False
            #load scoes into scores[][]

            # game over
            nState[0] = 1           
            log.log("SCORE: game end")
                       
            if DataStore.read_record("extras", 0)["tournament_mode"]:
                for i in range(0, 4):
                    update_tournament({"initials": scores[i][0], "score": scores[i][1]})
            else:
                for i in range(0, 4):                    
                    update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

            game = [S.gameCounter, scores[0], scores[1], scores[2], scores[3]]
            _place_game_in_claim_list(game)


