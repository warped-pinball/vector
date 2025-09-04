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



GAME_HIST_SIZE = 10000
gameHistory=array.array('I', [0]*GAME_HIST_SIZE)        #32 bit
gameHistoryTime=array.array('H', [0]*GAME_HIST_SIZE)    #16 bit
gameHistoryIndex=0
GAMEHIST_STATUS_EMPTY=0
GAMEHIST_STATUS_DONE=1
GAMEHIST_STATUS_OVERFLOW=2
gameHistoryStatus=GAMEHIST_STATUS_EMPTY
















MASK32 = 0xFFFFFFFF
DEPTH = 16
IDXMSK = 0x0F  # pointer wrap around - 16 samples

# Circular buffer and pointer
bit_buf = [0] * DEPTH
bit_ptr = -1
bit_count = 0

# Masks for score and reset (all zeros initially)
score_mask = [0] * DEPTH
reset_mask = [0] * DEPTH

# Score state
scoreState = 0

def set_score_mask(stage, mask):
    score_mask[stage] = mask & MASK32

def set_reset_mask(stage, mask):
    reset_mask[stage] = mask & MASK32

def reset_bit_filter(init_value=0):
    global bit_buf, bit_ptr, bit_count, scoreState
    iv = init_value & MASK32
    bit_buf = [iv] * DEPTH
    bit_ptr = -1
    bit_count = 0
    scoreState = 0

def process_bit_filter(new_word):
    global bit_buf, bit_ptr, scoreState
    bit_ptr = (bit_ptr + 1) & IDXMSK
    bit_buf[bit_ptr] = new_word & MASK32
  

    # Score detection
    score_hits = 0
    reset_hits = 0
    
    cumulative_low = ~bit_buf[bit_ptr] & MASK32
    cumulative_high = bit_buf[bit_ptr] & MASK32

    for i in range(1, 6):  # depth reduced for speed

        cumulative_low &= ~bit_buf[(bit_ptr - i) & IDXMSK] 
        score_hits |= cumulative_low & scoreState & score_mask[i]

        cumulative_high &= bit_buf[(bit_ptr - i) & IDXMSK] & MASK32
        reset_hits |= cumulative_high & (~scoreState) & reset_mask[i]
       
    scoreState &= ~score_hits
    scoreState |= reset_hits
    
    return score_hits




























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
PROCESS_RUN = 3
PROCESS_STORE_END = 4
PROCESS_RUN_END = 5

PROCESS_START_PAUSE = 8
PROCESS_END_PAUSE = 5
stateVar=0
stateCount=0

gpio26 = Pin(26, Pin.OUT)
gpio26.value(not gpio26.value())

gpio1 = Pin(1, Pin.OUT)
gpio1.value(not gpio1.value())


#switch to run normal or in file capture mode
#S.run_learning_game = True
S.run_learning_game = False


#sync up just the end of game - capture last transitions.. 
gameover=False


def save_game_history(filename="game_history.dat"):
    """Save gameHistory, gameHistoryTime, gameHistoryIndex, and actualScore to a file with section markers."""
    global gameHistory, gameHistoryTime, gameHistoryIndex

    try:
        with open(filename, "wb") as f:
            # Write a marker for the start of the file
            f.write(b'GHDR')  # 4-byte marker: Game History Data Record

            # Write actualScore as 4 bytes (placeholder, value 0 for now)
            actualScore = 0
            f.write(actualScore.to_bytes(4, "little"))

            # Write a marker before gameHistoryIndex
            f.write(b'GHIX')
            f.write(gameHistoryIndex.to_bytes(4, "little"))

            # Write a marker before gameHistory values
            f.write(b'GHVL')
            for i in range(gameHistoryIndex):
                f.write(gameHistory[i].to_bytes(4, "little"))

            # Write a marker before gameHistoryTime values
            f.write(b'GHTM')
            for i in range(gameHistoryIndex):
                f.write(gameHistoryTime[i].to_bytes(2, "little"))

            # Write a marker for end of file
            f.write(b'GEND')
        print(f"Game history saved to {filename}")
    except Exception as e:
        print(f"Error saving game history: {e}")



def load_game_history(filename="game_history.dat"):
    """Restore gameHistory, gameHistoryTime, gameHistoryIndex, and actualScore from a file with section markers."""
    global gameHistory, gameHistoryTime, gameHistoryIndex

    try:
        with open(filename, "rb") as f:
            # Check start marker
            if f.read(4) != b'GHDR':
                raise ValueError("File marker GHDR not found")

            # Read actualScore (4 bytes, little endian)
            actualScore = int.from_bytes(f.read(4), "little")

            # Check gameHistoryIndex marker
            if f.read(4) != b'GHIX':
                raise ValueError("File marker GHIX not found")
            gameHistoryIndex = int.from_bytes(f.read(4), "little")

            # Check gameHistory values marker
            if f.read(4) != b'GHVL':
                raise ValueError("File marker GHVL not found")
            for i in range(gameHistoryIndex):
                gameHistory[i] = int.from_bytes(f.read(4), "little")

            # Check gameHistoryTime values marker
            if f.read(4) != b'GHTM':
                raise ValueError("File marker GHTM not found")
            for i in range(gameHistoryIndex):
                gameHistoryTime[i] = int.from_bytes(f.read(2), "little")

            # Check end marker
            if f.read(4) != b'GEND':
                raise ValueError("File marker GEND not found")

        print(f"Game history loaded from {filename}")
    except Exception as e:
        print(f"Error loading game history: {e}")



def print_game_history_file(filename="game_history.dat"):
    """Print the contents of a gameHistory file: sensor data (binary), time (decimal), index, and actualScore."""
    try:
        with open(filename, "rb") as f:
            # Check start marker
            if f.read(4) != b'GHDR':
                print("File marker GHDR not found")
                return

            # Read actualScore (4 bytes, little endian)
            actualScore = int.from_bytes(f.read(4), "little")

            # Check gameHistoryIndex marker
            if f.read(4) != b'GHIX':
                print("File marker GHIX not found")
                return
            gameHistoryIndex = int.from_bytes(f.read(4), "little")

            # Check gameHistory values marker
            if f.read(4) != b'GHVL':
                print("File marker GHVL not found")
                return
            sensor_data = []
            for i in range(gameHistoryIndex):
                sensor_data.append(int.from_bytes(f.read(4), "little"))

            # Check gameHistoryTime values marker
            if f.read(4) != b'GHTM':
                print("File marker GHTM not found")
                return
            time_data = []
            for i in range(gameHistoryIndex):
                time_data.append(int.from_bytes(f.read(2), "little"))

            # Check end marker
            if f.read(4) != b'GEND':
                print("File marker GEND not found")
                return

            # Print header
            print(f"GameHistory Length: {gameHistoryIndex}")
            print(f"Actual Score: {actualScore}")
            print(f"{'Index':>5} {'Sensor Data':>36} {'Time':>8}")
            print("-" * 55)
            for i in range(gameHistoryIndex):
                print(f"{i:>5} {sensor_data[i]:032b} {time_data[i]:>8}")

    except Exception as e:
        print(f"Error reading game history file: {e}")




#called from phew schedeuler 
def processSensorData():
    ''' called each 1 or 2 seconds.  watch game active and decide when to operate on data
    coming in from sensor module -  either store for learning or process for live scores'''
    global lastValue, segmentMS, gameHistory,gameHistoryTime,gameHistoryIndex
    global stateVar, stateCount, gameover


    global gpio26  #blink led
    gpio26.value(not gpio26.value())

    stateCount += 1

    if stateVar == PROCESS_IDLE:
        '''wait for game to start'''
        if sensorRead.gameActive() == 1:
            stateVar = PROCESS_START
            stateCount=0
        else:
            processEmpty()

    elif stateVar == PROCESS_START:
        '''game start delay'''
        if sensorRead.gameActive()==1:  
            processEmpty()          
            if stateCount > PROCESS_START_PAUSE:

                #run or store for learning
                if S.run_learning_game == True:
                    log.log("SCORE: Run learning game capture")
                    stateVar = PROCESS_STORE
                else:
                    log.log("SCORE: Run game scoring")
                    processEmpty()  
                    stateVar = PROCESS_RUN
        else:
            stateVar = PROCESS_IDLE  
            stateCount = 0


    elif stateVar == PROCESS_STORE:
        #store data for learn
        processAndStore()
        if sensorRead.gameActive() == 0:          
            stateVar = PROCESS_STORE_END  
            stateCount = 0

    elif stateVar == PROCESS_STORE_END:
        #store data for learn
        processAndStore()
        if stateCount > PROCESS_END_PAUSE:
            stateVar = PROCESS_IDLE  
            processAndStoreWrapUp()
            gameover = True
            stateCount = 0

    elif stateVar == PROCESS_RUN:
        #run data now - live score
        processAndRun()
        if sensorRead.gameActive() == 0:
            stateVar = PROCESS_RUN_END  
            stateCount = 0

    elif stateVar == PROCESS_RUN_END:
        #run data now - live score
        processAndRun()
        if stateCount > PROCESS_END_PAUSE:
            stateVar = PROCESS_IDLE  
            gameover = True
            stateCount = 0


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
                
       
processEmpty()
processEmpty()
processEmpty()

    
def processAndStore():
    '''compress as data and time values - store into large buffer (gameHistory)'''
    global lastValue, segmentMS, gameHistory, gameHistoryTime, gameHistoryIndex
    gpio1.value(1)

    for x in range(2500):
        
        newValue = pullWithDelete()      
        if newValue != 0:
            newValue = reverse_bits_16(newValue)
            newValue = newValue & 0x0F          #for now only player 1 - needs to be confiuguratble

            if segmentMS > 20000 or newValue != lastValue:  
                # store value and time
                if gameHistoryIndex < (GAME_HIST_SIZE-6):
                    gameHistory[gameHistoryIndex]=lastValue                                    
                    gameHistoryTime[gameHistoryIndex]=segmentMS
                    gameHistoryIndex += 1                    
                    #print("!",lastValue,segmentMS, gameHistoryIndex)
                else:
                    print("FULL!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")    

                lastValue = newValue
                segmentMS = 1

            else:
                # if newValue == lastValue:
                segmentMS = segmentMS + 1
        else:
            break

    gpio1.value(0)
    return


def processAndStoreWrapUp():
    ''' call at gema over to wrap up the ram store history'''
    global lastValue, segmentMS, gameHistory, gameHistoryTime, gameHistoryIndex

    gameHistory[gameHistoryIndex]=lastValue                                    
    gameHistoryTime[gameHistoryIndex]=segmentMS
    gameHistoryIndex += 1               

    print("stored last file data point wrap up - - -")



#import bitFilter as bf
#bf_instance = bf.BitStreamFilter32()


def processAndRun():
    '''pull data from ram buffer and feed to score module'''
    global holdOffCount

    start_time = time.ticks_ms()  # Start timer

    for x in range(2500):
        d = pullWithDelete()
        if d==0:
            end_time = time.ticks_ms()
            elapsed = time.ticks_diff(end_time, start_time)
            print("end   processAndRun execution time:", elapsed, "ms")
            return
        
        process_bit_filter(d)
        #bf_instance.process(d)
 
    end_time = time.ticks_ms()
    elapsed = time.ticks_diff(end_time, start_time)
    print("2500   processAndRun execution time:", elapsed, "ms")
    return


    '''
    for x in range(1500):
        # Use saved values from previous call if available
        a = a_saved if 'a_saved' in globals() else pullWithDelete()
        b = b_saved if 'b_saved' in globals() else pullWithDelete()
        c = pullWithDelete()

        # If buffer runs out, save a and b for next call and return
        if a == 0:
            a_saved = None
            b_saved = None
            print(" aa  processandRun: over  - - - ",x*2)
            end_time = time.ticks_ms()
            elapsed = time.ticks_diff(end_time, start_time)
            print("processAndRun execution time:", elapsed, "ms")    
            #print(holdOffCount)
            return
        if b == 0:
            a_saved = a
            b_saved = None           
            return
        if c == 0:
            a_saved = a
            b_saved = b           
            return

        # Buffer is not empty, clear saved values
        a_saved = None
        b_saved = None

        scrValue = (a|b) & (b|c)   #any two in a row low - output a low bit
        chgValue = (a^b) | (b^c)   #any bit change - output a high bit

        optSensorToScore(reverse_bits_16(scrValue) |0xFFF0 , reverse_bits_16(chgValue) &0x000F)
    '''

        



    '''
        if newValue != 0:
            newValue = reverse_bits_16(newValue)
            newValue = newValue & 0x0F          #for now only player 1 - needs to be confiuguratble
            sensorToScore(newValue)
        else:                   
            print(" processandRun: did ",x*2," records")
            end_time = time.ticks_ms()
            elapsed = time.ticks_diff(end_time, start_time)
            print("processAndRun execution time:", elapsed, "ms")
            
            return
    '''

  


previousSensorValue=0
filteredSensorValue=0
previousFilteredSensorValue=0
changeCounter = [0] *32
#                player 1          player 2           player 3          player4
#                1  
#                | 10
#                | | 100
#                | | | 1000
#                | | | |
zeroThreshold = [1,1,1,1,4,9,9,9  ,1,1,1,1,1,9,9,9   ,1,1,1,1,1,9,9,9   ,1,1,1,1,1,9,9,9  ]
oneThreshold =  [5,5,5,5,4,9,9,9  ,7,7,7,7,7,9,9,9   ,7,7,7,7,7,9,9,9   ,7,7,7,7,7,9,9,9  ]

#scores stored as individual digits to make run time math simple and fast
#sensorScores = [0] *4
sensorScores = [array.array('B', [0]*5) for _ in range(4)]   #sensorScores[player0-3][digit0-4]

'''
score_map = [
    (0, [0, 1, 2, 3, 4]),    # score[0]  bits 0-4
    (1, [8, 9,10,11,12]),    # score[1]  bits 8-12
    (2, [16,17,18,19,20]),   # score[2]  bits 16-20   
    (3, [24,25,26,27,28])    # score[3]  bits 24-28
]
'''


score_map = [
    (0, [0, 1, 2, 3, 4])    # score[0]  bits 0-4
   
]   

def sensorToScore(newSensorValue):
    '''take raw sensor data (1x32bits) interpret to score - store score locally  '''
    global previousSensorValue,changeCounter,zeroThreshold,oneThreshold,sensorScores
    global gameHistoryIndex, score_map

    filteredSensorValue = globals()['filteredSensorValue']
    previousFilteredSensorValue = globals()['previousFilteredSensorValue']

    if newSensorValue==0:  #no reading
        return
    
    # Optimized bit processing for speed using local variables and reduced Python overhead
    prevSensor = previousSensorValue
    filtSensor = filteredSensorValue
    changeCnt = changeCounter
    zeroThr = zeroThreshold
    oneThr = oneThreshold

    nsVal = newSensorValue

    #for i in (0,1,2,3,4,8,9,10,11,12,16,17,18,19,20,24,25,26,27,28):
    for i in (0,1,2,3,4): #,8,9,10,11,12):
        new_bit = (nsVal >> i) & 1
        prev_bit = (prevSensor >> i) & 1

        cnt = changeCnt[i] + (new_bit == prev_bit)
        changeCnt[i] = cnt if new_bit == prev_bit else 0

        if new_bit == 0:
            if cnt >= zeroThr[i]:
                filtSensor &= ~(1 << i)
        else:
            if cnt >= oneThr[i]:
                filtSensor |= (1 << i)

    previousSensorValue = nsVal
    filteredSensorValue = filtSensor

    
    #now that we have filtered sensor data - use it to change scores...
    # Fast score update using local variables and bitwise ops
    pfsv = previousFilteredSensorValue
    fsv = filteredSensorValue
    ss = sensorScores

    for score_idx, bits in score_map:
        s = ss[score_idx]
        for i, bit in enumerate(bits):
            prev = (pfsv >> bit) & 1
            curr = (fsv >> bit) & 1
            if prev == 1 and curr == 0:
                v = s[i]
                s[i] = 0 if v > 8 else v + 1

    previousFilteredSensorValue = fsv
    

    #print("new: {:032b}, filtered: {:032b}".format(newSensorValue, filteredSensorValue))

    globals()['filteredSensorValue'] = filteredSensorValue
    globals()['previousFilteredSensorValue'] = previousFilteredSensorValue



holdOffCount= [0]*32

def optSensorToScore(scrValue,chgValue):
    global holdOffCount

    #count number times a bit in scrValue is zero

    for score_idx, bits in score_map:
        for i, bit in enumerate(bits):
            #cycle for each bit - - - 
            if ((scrValue>>bit)&1)==0 and holdOffCount[bit]==0:
                #increment digit
                v = sensorScores[score_idx][i]
                sensorScores[score_idx][i] = 0 if v > 8 else v + 1
                holdOffCount[bit] = 2

            if ((chgValue>>bit)&1) == 1:
                holdOffCount[bit] = 2
            else:
                if (holdOffCount[bit]>0):
                    holdOffCount[bit] -= 1









def buildPrintableScores():
    scores = []
    for player in range(4):
        score = 0
        for digit in range(5):
            score += sensorScores[player][digit] * (10 ** digit)

        scores.append(score)
    return tuple(scores)



def replayStoredGame():
    global previousSensorValue,filteredSensorValue,changeCounter,zeroThreshold,oneThreshold,sensorScores

    index=0
    #print("SCORE: replay now",gameHistoryIndex)

    for index in range(gameHistoryIndex):
            sensor_value = gameHistory[index]
            sample_count = gameHistoryTime[index]
            if sample_count > 20:
                sample_count=20
            #print("send: val=",sensor_value,"  count=",sample_count)
            for _ in range(sample_count):
                sensorToScore(sensor_value)

            #print("SCORE REPLAY", *buildPrintableScores())
        
    #print("SCORE: replay DONE")
    print("SCORE REPLAY", *buildPrintableScores())








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
                # store value and timel
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
            S.game_status["game_active"]=True
            print("SCORE: Game Start")
            nState[0] = 2



    elif nState[0] == 2:  # waiting for game to end    
        #process data in storeage...

        if S.run_learning_game == False:
            print("SCORE: game end check - play mode                          SCORE=",*buildPrintableScores())
            
        else:
            print("SCORE: game end check. learn mode ",  sensorRead.depthSensorRx() ,  gameHistoryIndex  )

        #if sensorRead.gameActive() == 0:
        if gameover == True:
            print("SCORE: Game End")
            S.game_status["game_active"]=False
            #load scoes into scores[][]

            # game over
            nState[0] = 1           
            log.log("SCORE: game end")

         
            save_game_history()

            #replay stored game - print out progress
            #print("SCORE: REPLAY GAME DATA:xxx   history length=",gameHistoryIndex)
            #replayStoredGame()




            '''                       
            if DataStore.read_record("extras", 0)["tournament_mode"]:
                for i in range(0, 4):
                    update_tournament({"initials": scores[i][0], "score": scores[i][1]})
            else:
                for i in range(0, 4):                    
                    update_leaderboard({"initials": scores[i][0], "score": scores[i][1]})

            game = [S.gameCounter, scores[0], scores[1], scores[2], scores[3]]
            _place_game_in_claim_list(game)
            '''




















def test_processAndStore():
    """
    Test processAndStore() by overriding pullWithDelete to provide controlled test data.
    Prints what is stored in gameHistory and gameHistoryTime.
    """

    global gameHistory, gameHistoryTime, gameHistoryIndex, lastValue, segmentMS

    # Backup the original pullWithDelete
    original_pullWithDelete = pullWithDelete

    # Helper to reset history
    def reset_history():
        global gameHistory, gameHistoryTime, gameHistoryIndex, lastValue, segmentMS
        gameHistory = array.array('I', [0]*GAME_HIST_SIZE)
        gameHistoryTime = array.array('H', [0]*GAME_HIST_SIZE)
        gameHistoryIndex = 0
        lastValue = 0
        segmentMS = 1

    print("Test 1: Same value many times (should result in one entry with long time)")
    reset_history()
    #test_values = [7<<12] * 55530  # 100 times the same value
    def pull_same():
        return (7<<12)  #test_values.pop(0) if test_values else 0
    globals()['pullWithDelete'] = pull_same
    
    for x in range(30):
        processAndStore()

    print("gameHistoryIndex",gameHistoryIndex)
    print("gameHistory:", list(gameHistory[:gameHistoryIndex]))
    print("gameHistoryTime:", list(gameHistoryTime[:gameHistoryIndex]))

    print("\nTest 2: Rapidly changing values (should result in many entries)")
    reset_history()
    test_values = [0x2300, 0x2400, 0xff00, 0x5500, 0x7600, 0x3200, 0x9900, 0x8900, 0x3400, 0x4300] * 10  # 10 cycles of 10 different values
    def pull_rapid():
        return test_values.pop(0) if test_values else 0
    globals()['pullWithDelete'] = pull_rapid
    processAndStore()
    print("gameHistoryIndex",gameHistoryIndex)
    print("gameHistory:", list(gameHistory[:gameHistoryIndex]))
    print("gameHistoryTime:", list(gameHistoryTime[:gameHistoryIndex]))

    # Restore original pullWithDelete
    globals()['pullWithDelete'] = original_pullWithDelete



def test_replay():
  global lastValue, segmentMS, gameHistory,gameHistoryTime,gameHistoryIndex
  global stateVar, stateCount

  gameHistoryIndex=0

  gameHistory[gameHistoryIndex]=0x0F
  gameHistoryTime[gameHistoryIndex]=15
  gameHistoryIndex+=1

  gameHistory[gameHistoryIndex]=0x0E
  gameHistoryTime[gameHistoryIndex]=18
  gameHistoryIndex+=1

  gameHistory[gameHistoryIndex]=0x0F
  gameHistoryTime[gameHistoryIndex]=10
  gameHistoryIndex+=1

  gameHistory[gameHistoryIndex]=0x0F-2
  gameHistoryTime[gameHistoryIndex]=18
  gameHistoryIndex+=1

  replayStoredGame()

import time



if __name__ == "__main__":

    results = []


    targetScore = 1166  # Set your correct score target here
    fileName = "game_history.dat"

    load_game_history(fileName)
    start = time.ticks_ms()

    ZERORANGE = 6
    ONESRANGE = 19

    for z in range(ZERORANGE):
        for one in range(ONESRANGE):

            # Set all digits of zeroThreshold and oneThreshold to the same value
            for d in range(5):
                zeroThreshold[d] = z
                oneThreshold[d] = one            

            #reset score trackers
            for player in range(4):
                for digit in range(5):
                    sensorScores[player][digit] = 0

            print("Testing ", z*ONESRANGE+one, "from ", ONESRANGE*ZERORANGE)

            replayStoredGame()
            print("score digits=", [sensorScores[0][d] for d in range(5)], 
                  " full score=", sum(sensorScores[0][d] * (10 ** d) for d in range(5)), 
                  " with setting=", z, one)

            # Record z, one, and sensorScores[0][0:5] in results
            results.append((z, one, [sensorScores[0][d] for d in range(5)]))

            elapsed = time.ticks_diff(time.ticks_ms(), start)
            print("Replay execution time:", elapsed, "ms")

    # Print only results where any digit matches targetScore
    print(f"Results (z, one, any digit == {targetScore}):")
    for record in results:
        print(record)

    # Print z/one combinations for each digit place (1s, 10s, 100s, 1000s)
    digit_places = [1, 10, 100, 1000]
    for digit_index, digit_value in enumerate(digit_places):
        print(f"\nCombinations for digit place {digit_value}:")
        for record in results:
            z, one, digits = record
            if digits[digit_index] == targetScore // digit_value % 10:
                print(f"z={z}, one={one}, digits={digits}")