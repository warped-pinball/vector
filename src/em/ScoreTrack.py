# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    This module is responsible for tracking scores and updating the leaderboard.
    
    EM version

"""
from machine import RTC,Pin
import sensorRead
import array
import time
import resource
from ScoreTrackFilter_viper import _viper_process

import displayMessage
import os
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


# Diagnostics LED - for test only
gpio26 = Pin(26, Pin.OUT)
gpio26.value(not gpio26.value())
gpio1 = Pin(1, Pin.OUT)
gpio1.value(not gpio1.value())


import gc

# Game History storage area and state machine defines
GAME_HIST_SIZE = 10000
gameHistory = None             # allocate lazily when capturing learning game
gameHistoryTime = None         # allocate lazily
gameHistoryIndex = 0

actualScores = [0, 0, 0, 0]
GAMEHIST_STATUS_EMPTY=0
GAMEHIST_STATUS_DONE=1
GAMEHIST_STATUS_OVERFLOW=2
gameHistoryStatus=GAMEHIST_STATUS_EMPTY

# default pauses (can be overridden from EMData/S.gdata in _loadState)
PROCESS_START_PAUSE = 8
PROCESS_END_PAUSE = 5

# SCORE Digits for all 4 players - Initialize sensorScores[player][digit]
sensorScores = [[0 for _ in range(8)] for _ in range(4)]


#config stuff to be sent to UI:
actualScoreFromLastGame = None
#actualScoreFromLastGame = [ 5248, 0,0,0]

# global file selector: 0..4 supported
fileNumber = 1  # change this to select which game_historyN.dat to use (0..4)

#GLOBALS for process sensor data - - - 
#switch to run normal or in file capture mode
#S.run_learning_game = True
S.run_learning_game = False

'''
Bit filter 
    uses viper for speed, setup score and rest masks to adjust filtering
    32 bit parallel capable (all input channels at once)

    score_mask - sets # of samples ==1 to latch bit on
    once on can only be unset by number of zeros defined in rest_mask
'''
MASK32 = 0xFFFFFFFF
DEPTH = 16
IDXMSK = 0x0F  # pointer wrap around - 16 samples

# use array.array('I') so viper can access as ptr32 via memoryview
# bit Buffer to pass data to viper function
bit_buf = array.array('I', [0] * DEPTH)
bit_ptr = -1
score_mask = array.array('I', [0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF] )
reset_mask = array.array('I', [0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF] )
scoreState = 0  # int

# per-bit depth copies - persistent so other code can inspect configured depths
scoreDepths = [0] * 32   # number of stages used for score detection per bit
resetDepths = [0] * 32   # number of stages used for reset detection per bit

# create memoryviews - to send to viper function
bit_buf_mv = memoryview(bit_buf)
score_mask_mv = memoryview(score_mask)
reset_mask_mv = memoryview(reset_mask)

# carryThresholds (timing) as a 4x4x2 array [player][digit][low,high]
carryThresholds = [[[12, 28] for _ in range(4)] for _ in range(4)]

#give a default here - stup in initialize according to configuration / datastore
sensorBitMask = 0x0000F0F
digitsPerPlayer=1



def initialize():
    """
    one time power up Initialize
    """ 
    from phew.server import schedule
    schedule(processSensorData, 1000, 800)

    loadState()

    #from displayMessage import init
    displayMessage.init()

    S.game_status["game_active"]=False


def loadState():
    """
    Initialize score tracking configuration from S.gdata.
    """
    global sensorBitMask, digitsPerPlayer, carryThresholds
    global PROCESS_START_PAUSE, PROCESS_END_PAUSE

    # required config values
    digitsPerPlayer = int(S.gdata["digits"])
    players = int(S.gdata["players"])

    # load start/end pause values from configuration (EMData -> S.gdata)
    # keys are "startpause" and "endpause"; fall back to current defaults if missing
    PROCESS_START_PAUSE = int(S.gdata.get("startpause", PROCESS_START_PAUSE))
    PROCESS_END_PAUSE = int(S.gdata.get("endpause", PROCESS_END_PAUSE))
    print("SCORE: pauses= ",PROCESS_START_PAUSE,PROCESS_END_PAUSE)
  
    # build sensorBitMask - single 32 bit word
    base_byte = (1 << digitsPerPlayer) - 1
    base_byte &= 0xFF
    sb = base_byte
    if players >= 2:
        sb |= (base_byte << 8)
    if players >= 3:
        sb |= (base_byte << 16)
    if players >= 4:
        sb |= (base_byte << 24)
    sensorBitMask = sb

    # carryThresholds (4 players * 4 digits * 2 values (1 byte each))
    ct_blob = S.gdata["carrythresholds"]
    if not isinstance(ct_blob, (bytes, bytearray)) or len(ct_blob) != 32:
        raise ValueError("S.gdata['carrythresholds'] must be 32-byte bytes or bytearray")
    b = bytes(ct_blob)
    pos = 0
    for p in range(4):
        for d in range(4):
            low = b[pos]; pos += 1
            high = b[pos]; pos += 1
            carryThresholds[p][d][0] = int(low)
            carryThresholds[p][d][1] = int(high)


    # filtermasks 64 bytes: (scoreDepth, resetDepth) for channels 0..31
    fm_blob = S.gdata["filtermasks"]
    if not isinstance(fm_blob, (bytes, bytearray)) or len(fm_blob) != 64:
        raise ValueError("S.gdata['filtermasks'] must be 64-byte bytes or bytearray")
    fm = bytes(fm_blob)
    for ch in range(32):
        scoreDepth = int(fm[ch * 2])
        resetDepth = int(fm[ch * 2 + 1])
        # set per-channel masks
        setScoreMask(ch, scoreDepth, resetDepth)

    log.log(f"ScoreTrack initialized: players={players} digits={digitsPerPlayer} sensorMask=0x{sensorBitMask:08X}")
    print("ScoreTrack pauses: startpause=%d endpause=%d" % (PROCESS_START_PAUSE, PROCESS_END_PAUSE))



def saveState():
    """store working config back to SPI_DataStore"""
    try:
        em = DataStore.read_record("EMData")
    except Exception as e:
        print("Error reading EMData:", e)
        return
    
    # Build 64-byte filtermasks: for channel 0..31 store (scoreDepth, resetDepth)
    fm = bytearray(64)
    for ch in range(32):
        s = int(scoreDepths[ch]) & 0xFF
        r = int(resetDepths[ch]) & 0xFF
        fm[ch * 2] = s
        fm[ch * 2 + 1] = r
    S.gdata["filtermasks"] = bytes(fm)

    # Build 32-byte carrythresholds: players 0..3, digit 0..3, two 1-byte values (low, high)
    ct = bytearray(32)
    pos = 0
    for p in range(4):
        for d in range(4):
            low = int(carryThresholds[p][d][0]) & 0xFF
            high = int(carryThresholds[p][d][1]) & 0xFF
            ct[pos] = low
            ct[pos + 1] = high
            pos += 2
    S.gdata["carrythresholds"] = bytes(ct)
    S.gdata["startpause"] = int(PROCESS_START_PAUSE)
    S.gdata["endpause"] = int(PROCESS_END_PAUSE)
  
    try:
        #DataStore.write_record("EMData", em)
        DataStore.write_record("EMData", S.gdata) #  <<< could just do this way - 
        print("EMData updated from globals (filtermasks, carrythresholds).")
    except Exception as e:
        print("Error writing EMData:", e)





def setScoreMask(bit, scoreDepth, resetDepth):
    """Set a single bit across score_mask and reset_mask.
    Parameters:
      bit         - bit number 0..31 to modify
      scoreDepth  - number of earliest stages (0..DEPTH) that should have the bit cleared;
                    all later stages will have the bit set.
      resetDepth  - same semantics for reset_mask
    """
    global score_mask, reset_mask, scoreDepths, resetDepths

    if not (0 <= bit < 32):
        log.log("SCORE: bit - out of range 0..31")
        bit=0
    if not (0 <= scoreDepth <= DEPTH):
        log.log(f"scoreDepth out of range 0..{scoreDepth}")
        scoreDepth=0
    if not (0 <= resetDepth <= DEPTH):
        log.log(f"resetDepth out of range 0..{resetDepth}")
        resetDepth=0

    # store configured depths for external inspection
    scoreDepths[bit] = int(scoreDepth)
    resetDepths[bit] = int(resetDepth)

    mask = 1 << bit
    inv = ~mask & MASK32

    # apply to all stages: first scoreDepth entries clear the bit, remaining set the bit
    for i in range(DEPTH):
        if i < scoreDepth:
            score_mask[i] &= inv
        else:
            score_mask[i] |= mask

        if i < resetDepth:
            reset_mask[i] &= inv
        else:
            reset_mask[i] |= mask



def printMasks():
    """Print score_mask and reset_mask in hex and grouped binary, plus carryThresholds by player/digit."""
    global score_mask, reset_mask, DEPTH, carryThresholds

    def grp32(x):
        b = "{:032b}".format(x)
        return " ".join(b[i:i+4] for i in range(0, 32, 4))

    print("Stage ScoreMask     ScoreBin                                 ResetMask    ResetBin")
    print("-----  -----------  --------------------------------         -----------  --------------------------------")
    for i in range(DEPTH):
        s = int(score_mask[i]) & MASK32
        r = int(reset_mask[i]) & MASK32
        print(f"{i:5d}  0x{s:08X}  {grp32(s)}  0x{r:08X}  {grp32(r)}")

    print("\nCarryThresholds (player x digit):")
    for player in range(len(carryThresholds)):
        print(f"Player {player}:")
        for digit in range(len(carryThresholds[player])):
            low, high = carryThresholds[player][digit]
            print(f"  Digit {digit}: low={low}, high={high}")
    print()




def processBitFilter(new_word):
    '''python (non-viper) for calling the bitfilter in _viper_process '''
    global bit_buf, bit_ptr, scoreState

    #store incoming word in rotating bit_buf
    bit_ptr = (bit_ptr + 1) & IDXMSK
    bit_buf[bit_ptr] = new_word  

    # call viper routine for filtering FAST!
    scoreState = _viper_process(bit_buf_mv, bit_ptr, IDXMSK, scoreState, score_mask_mv, reset_mask_mv)
    return scoreState















def game_history_filename(number=None):
    """Return filename for a given file number; uses global fileNumber when None."""
    if number is None:
        number = fileNumber
    return "game_history{}.dat".format(int(number) & 0xFF)

def add_actual_score_to_file(filename=None, actualScores=[0,0,0,0]):
    """Overwrite the 4 actualScores (4 bytes each) in an existing game history file """
    if filename is None:
        filename = game_history_filename()   

    print("################### incomming scores",actualScores)

    actualScores = list(actualScores)
    while len(actualScores) < 4:
        actualScores.append(0)

    dummy_reels = int(S.gdata.get("dummy_reels", 0))
    if dummy_reels > 0:
        scale = 10 ** dummy_reels
        for i in range(4):
            actualScores[i] = int(int(actualScores[i]) // scale)
    
    try:
        with open(filename, "r+b") as f:
            hdr = f.read(4)
            if hdr != b'GHDR':
                raise ValueError("Invalid file: GHDR marker not found")
            # actualScores live immediately after the GHDR marker (bytes 4..19)
            f.seek(4)
            for score in actualScores:
                f.write(int(score).to_bytes(4, "little"))
        print(f"\n\nWrote actualScores = {actualScores} to {filename}")
    except Exception as e:
        print("Error updating actualScores:", e)


def save_game_history(filename=None):
    """Save gameHistory, gameHistoryTime, gameHistoryIndex, and actualScores (4 players) to a file with section markers.
    If filename is None the global fileNumber is used.
    At the end, append S.gdata as a human-readable text block (for diagnostics only)."""
    global gameHistory, gameHistoryTime, gameHistoryIndex, actualScores

    if filename is None:
        filename = game_history_filename()

    try:
        with open(filename, "wb") as f:
            # Write a marker for the start of the file
            f.write(b'GHDR')

            # Write four player scores as 4 bytes each (player0..player3)
            for i in range(4):
                f.write(int(actualScores[i] & 0xFFFFFFFF).to_bytes(4, "little"))

            # Write a marker before gameHistoryIndex
            f.write(b'GHIX')
            f.write(int(gameHistoryIndex).to_bytes(4, "little"))

            # Write a marker before gameHistory values
            f.write(b'GHVL')
            if gameHistory is not None:
                for i in range(gameHistoryIndex):
                    f.write(int(gameHistory[i]).to_bytes(4, "little"))

            # Write a marker before gameHistoryTime values
            f.write(b'GHTM')
            if gameHistoryTime is not None:
                for i in range(gameHistoryIndex):
                    f.write(int(gameHistoryTime[i]).to_bytes(2, "little"))

            # Write a marker for end of file
            f.write(b'GEND')

            # --- Append S.gdata as human-readable text ---
            f.write(b'\n--- S.gdata dump ---\n')
            for k, v in S.gdata.items():
                f.write(f"{k}: {v}\n".encode())
            f.write(b'--- END S.gdata ---\n')

        print(f"Game history saved to {filename}")

    except Exception as e:
        print(f"Error saving game history: {e}")


def load_game_history(filename=None):
    """Restore gameHistory, gameHistoryTime, gameHistoryIndex, and actualScores from a file with section markers."""
    global gameHistory, gameHistoryTime, gameHistoryIndex, actualScores

    if filename is None:
        filename = game_history_filename()

    alloc_game_history()
    print("opening file ",filename)

    try:
        with open(filename, "rb") as f:
            if f.read(4) != b'GHDR':
                raise ValueError("File marker GHDR not found")

            # Read four player scores (4 * 4 bytes, little endian)
            scores_bytes = f.read(16)
            if len(scores_bytes) < 16:
                scores_bytes = scores_bytes.ljust(16, b"\0")
            actualScores = [int.from_bytes(scores_bytes[i*4:(i+1)*4], "little") for i in range(4)]
            print("LOAD ACTIA\\UAL SCORE - ",actualScores)
           

            # locate GHIX marker
            if f.read(4) != b'GHIX':
                raise ValueError("File marker GHIX not found")
            gameHistoryIndex = int.from_bytes(f.read(4), "little")

            # GHVL
            if f.read(4) != b'GHVL':
                raise ValueError("File marker GHVL not found")

            # allocate arrays if we need to actually load samples
            if gameHistoryIndex > 0:                
                for i in range(gameHistoryIndex):
                    gameHistory[i] = int.from_bytes(f.read(4), "little")
            else:
                # no samples, skip forward
                pass

            # GHTM
            if f.read(4) != b'GHTM':
                raise ValueError("File marker GHTM not found")
            if gameHistoryIndex > 0 and gameHistoryTime is not None:
                for i in range(gameHistoryIndex):
                    gameHistoryTime[i] = int.from_bytes(f.read(2), "little")
            else:
                # skip remaining times if any
                for _ in range(gameHistoryIndex):
                    f.read(2)

            if f.read(4) != b'GEND':
                raise ValueError("File marker GEND not found")

        print(f"Game history loaded from {filename}  actualScores={actualScores}")
    except Exception as e:
        print(f"Error loading game history: {e}")


def print_game_history_file(filename=None):
    """Print the contents of a gameHistory file: sensor data (binary), time (decimal), index, and actualScores.
    If filename is None the global fileNumber is used."""
    if filename is None:
        filename = game_history_filename()

    try:
        with open(filename, "rb") as f:
            # Check start marker
            if f.read(4) != b'GHDR':
                print("File marker GHDR not found")
                return

            # Read four player scores (4 * 4 bytes, little endian)
            scores_bytes = f.read(16)
            if len(scores_bytes) < 16:
                scores_bytes = scores_bytes.ljust(16, b"\0")
            scores = [int.from_bytes(scores_bytes[i*4:(i+1)*4], "little") for i in range(4)]

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
            print(f"GameHistory File: {filename}")
            print(f"GameHistory Length: {gameHistoryIndex}")
            print(f"Actual Scores: {scores}")
            print(f"{'Index':>5} {'Sensor Data':>26} {'Time':>12}")
            print("-" * 55)
            for i in range(gameHistoryIndex):
                print(f"{i:>5} {sensor_data[i]:032b} {time_data[i]:>8}")

    except Exception as e:
        print(f"Error reading game history file: {e}")



# Process Sensor Data state defines
PROCESS_IDLE = 0
PROCESS_START = 1
PROCESS_STORE = 2
PROCESS_RUN = 3
PROCESS_STORE_END = 4
PROCESS_RUN_END = 5


stateVar=0
stateCount=0



#sync up just the end of game - capture last transitions.. 
gameover=False

#called from phew schedeuler 
def processSensorData():
    ''' called each 1 or 2 seconds.  watch game active and decide when to operate on data
    coming in from sensor module -  either store for learning or process for live scores'''
    # removed unused globals: lastValue, segmentMS, gameHistory, gameHistoryTime, gameHistoryIndex
    global stateVar, stateCount, gameover
    global gpio26  #blink led

    global lastValue, segmentMS, gameHistory,gameHistoryTime,gameHistoryIndex


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
        '''game start delay - wait for score reset to happen
        -make smarted in the future?  wait fro a few seconds and more if signal detected....'''
        
        if sensorRead.gameActive()==1:  
            processEmpty()          
            lastValue = sensorBitMask   #init lastValue (alll ones) since scores are incremented on falling edges

            if stateCount > PROCESS_START_PAUSE:

                #run or store for learning
                if S.run_learning_game == True:
                    log.log("SCORE: Run learning game capture")
                    stateVar = PROCESS_STORE
                    alloc_game_history()
                    if gameHistory is None or gameHistoryTime is None:
                        log.log("SCORE: game history alloc fault")
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
            S.run_learning_game = False

            print("End of game - learning game- save and print")
            save_game_history()
            #print_game_history_file()
            free_game_history()

            displayMessage.setCaptureModeDigit(-1)
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


# This is the sensor ram buffer area (8k), data placed by PIO - pulled out here
# 0x0000 is invalid data and used to mark empty space.
# Define the RAM as an array of 32-bit unsigned ints
import uctypes
ram_bytes = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
bufferPointerIndex = 0
SRAM_BIT_MASK = (SRAM_DATA_LENGTH-1)

def reset_sensor_buffer_pointer():
    """Reset the SRAM read pointer used by pullWithDelete()."""
    global bufferPointerIndex
    bufferPointerIndex = 0
    
def pullWithDelete():
    '''pulls out one 32 bit value and erases the spot in ram
       optimized for speed, 1000 calls approx = 50mS    '''
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
    ''' pull and discard - used during gameActive == false'''
    # removed unused globals: bufferPointerIndex, gpio1
    for x in range(2500):
        if pullWithDelete() == 0:        
            return

#empty out buffer on power up                
for _ in range(5):       
    processEmpty()

    
def alloc_game_history():
    """Allocate gameHistory and gameHistoryTime arrays if they are not present."""
    global gameHistory, gameHistoryTime
    if gameHistory is None or gameHistoryTime is None:
        gameHistory = array.array('I', [0] * GAME_HIST_SIZE)
        gameHistoryTime = array.array('H', [0] * GAME_HIST_SIZE)
        gc.collect()

def free_game_history():
    """Free the game history arrays to release RAM. Resets index."""
    global gameHistory, gameHistoryTime, gameHistoryIndex
    gameHistory = None
    gameHistoryTime = None
    gameHistoryIndex = 0
    gc.collect()

storeCalibrationGameProgress=0

def processAndStore():
    '''compress as data and time values - store into large buffer (gameHistory)'''
    global lastValue, segmentMS, gameHistory, gameHistoryTime, gameHistoryIndex, storeCalibrationGameProgress
    gpio1.value(1)

    allActivesChannels=0

    # safe-guard: if not allocated, just discard (no storage)
    if gameHistory is None:
        # behave like processEmpty but still blink LED
        for x in range(2500):
            if pullWithDelete() == 0:
                break
        print("Capture Game -  setup")    
        # update display progress same as before (show 0)
        displayMessage.setCaptureModeDigit(-1)
        return

    #called ~~1 per second or more , will process up to 2.5 seconds worth of data
    for x in range(2500):
        newValue = pullWithDelete()
        if newValue != 0:
            newValue = newValue & sensorBitMask
            allActivesChannels = allActivesChannels | newValue

            if segmentMS > 40000 or newValue != lastValue:
                # store value and time
                if gameHistoryIndex < (GAME_HIST_SIZE-6):
                    gameHistory[gameHistoryIndex]=lastValue
                    gameHistoryTime[gameHistoryIndex]=segmentMS
                    gameHistoryIndex += 1
                else:
                    print("SCORE: capture game, data store overflow")

                lastValue = newValue
                segmentMS = 1
            else:
                segmentMS = segmentMS + 1
        else:
            break

    displayMessage.setSensorLeds(allActivesChannels)

    #put a numeral up on the board display - x10% full    
    displayMessage.setCaptureModeDigit(gameHistoryIndex // 1000)
    storeCalibrationGameProgress = (gameHistoryIndex // 100)

    #print("chk")
    return


def processAndStoreWrapUp():
    ''' call at game over to wrap up the ram store history, need to store return to zero'''
    global lastValue, segmentMS, gameHistory, gameHistoryTime, gameHistoryIndex

    if gameHistory is None:
        return

    gameHistory[gameHistoryIndex]=lastValue
    gameHistoryTime[gameHistoryIndex]=segmentMS
    gameHistoryIndex += 1
    log.log("SCORE: capture game, stored last file data point wrap up")





last_sc = 0
carryCount = [0] * 32


def processRisingEdge(sc,risingEdge):
    '''process rising edge and increment sensor Scores as needed
       used by run and replay stored game... 
       sc is sensor state (32 bit)
       rising edge bit=1 for single cycle on rising edge    '''
    global last_sc,sensorScores,carryThresholds,carryCount

    if (1):
        # increment digits based on risingEdge - count over laps for carry corrections - no loops for speed
        #PLR1-ONES
        if risingEdge & 0x00000001:
            sensorScores[0][0] = sensorScores[0][0] + 1     #inc score
            #carryCount[0] = 0
        if sc&0x01 == 0x01:
            carryCount[0]=carryCount[0]+1
        else:
            carryCount[0]=0

        #PLR1-TENS
        if risingEdge & 0x00000002:
            sensorScores[0][1] = sensorScores[0][1] + 1     #inc score
            if carryCount[0]>carryThresholds[0][0][0] and carryCount[0]<carryThresholds[0][0][1]:
                sensorScores[0][0] = 0                      #carry correction
            #carryCount[1] = 0
        if sc&0x02 == 0x02:
            carryCount[1]=carryCount[1]+1
        else:
            carryCount[1]=0

        #PLR1-HUNDERDS
        if risingEdge & 0x00000004:
            sensorScores[0][2] = sensorScores[0][2] + 1     #inc score
            if carryCount[1]>carryThresholds[0][1][0] and carryCount[1]<carryThresholds[0][1][1]:
                sensorScores[0][1] = 0                      #carry correction
            #carryCount[2]=0
        if sc&0x04 == 0x04:
            carryCount[2]=carryCount[2]+1
        else:
            carryCount[2]=0

        #PLR1-THOUSANDS
        if risingEdge & 0x00000008:
            sensorScores[0][3] = sensorScores[0][3] + 1     #inc score
            if carryCount[2]>carryThresholds[0][2][0] and carryCount[2]<carryThresholds[0][2][1]:
                sensorScores[0][2] = 0                      #carry correction
            #carryCount[3]=0
        if sc&0x08 == 0x08:
            carryCount[3]=carryCount[3]+1     
        else:
            carryCount[3]=0  

        #PLR1-TEN THOUSAND   
        if risingEdge & 0x00000010:
            sensorScores[0][4] = sensorScores[0][4] + 1     #inc score
            if carryCount[3]>carryThresholds[0][3][0] and carryCount[3]<carryThresholds[0][3][1]:
                sensorScores[0][3] = 0    



        #player 2
          #PLR2-ONES
        if risingEdge & 0x00000100:
            sensorScores[1][0] = sensorScores[1][0] + 1  #inc score
            carryCount[8] = 0
        if sc&0x0100 == 0x0100:
            carryCount[8]=carryCount[8]+1
        #PLR2-TENS
        if risingEdge & 0x00000200:
            sensorScores[1][1] = sensorScores[1][1] + 1     #inc score
            if carryCount[8]>carryThresholds[1][0][0] and carryCount[8]<carryThresholds[1][0][1]:
                sensorScores[1][0] = 0                      #carry correction
            carryCount[9] = 0
        if sc&0x0200 == 0x0200:
            carryCount[9]=carryCount[9]+1
        #PLR2-HUNDERDS
        if risingEdge & 0x00000400:
            sensorScores[1][2] = sensorScores[1][2] + 1     #inc score
            if carryCount[9]>carryThresholds[1][1][0] and carryCount[9]<carryThresholds[1][1][1]:
                sensorScores[1][1] = 0                      #carry correction
            carryCount[10]=0
        if sc&0x0400 == 0x0400:
            carryCount[10]=carryCount[10]+1
        #PLR2-THOUSANDS
        if risingEdge & 0x00000800:
            sensorScores[1][3] = sensorScores[1][3] + 1     #inc score
            if carryCount[10]>carryThresholds[1][2][0] and carryCount[10]<carryThresholds[1][2][1]:
                sensorScores[1][2] = 0                      #carry correction
            carryCount[11]=0
        if sc&0x0800 == 0x0800:
            carryCount[11]=carryCount[11]+1            
        #PLR2-TEN THOUSAND   
        if risingEdge & 0x00001000:
            sensorScores[1][4] = sensorScores[1][4] + 1     #inc score
            if carryCount[11]>carryThresholds[1][3][0] and carryCount[11]<carryThresholds[1][3][1]:
                sensorScores[1][3] = 0    

       #ADD Player 3

       #ADD Player 4



def processAndRun():
    '''pull data from ram buffer and feed to score module - for active game running'''
    global last_sc,sensorScores,carryThresholds
    allActivesChannels=0
    
    start_time = time.ticks_ms()  # Start timer
    for x in range(2500):
        d = pullWithDelete()
        if d == 0:
            break  #end of buffer data

        sc = processBitFilter(d & sensorBitMask)

        # keep all channels that go active for led display
        allActivesChannels = allActivesChannels | sc

        # Detect rising edges on all 32 bits at once
        risingEdge = (~last_sc) & sc
        processRisingEdge(sc,risingEdge)
        last_sc = sc

    #send to display green digit leds
    displayMessage.setSensorLeds(allActivesChannels)

    #10->0 truncate, except let last one acculmulate
    if digitsPerPlayer > 0:
        for i in (0,1,2,3):
            sensorScores[i][0] %= 10
        if digitsPerPlayer > 1:
            for i in (0,1,2,3):
                sensorScores[i][1] %= 10
            if digitsPerPlayer > 2:
                for i in (0,1,2,3):
                    sensorScores[i][2] %= 10
                if digitsPerPlayer >3:
                    for i in range(4):
                        sensorScores[i][3] %= 10  
    #if there is a fifth reel let it overflow and keep counting              

    end_time = time.ticks_ms()
    elapsed = time.ticks_diff(end_time, start_time)
    print("samples=",x,"process And Run execution time:", elapsed, "ms")

    print("scores=",getPlayerScore(0),getPlayerScore(1),getPlayerScore(2),getPlayerScore(3))

    return













def getPlayerScore(player):
    """
    Return the PRINTABLE score for the requested player index (0..3).
    """
    try:
        multiplier = 10 ** int(S.gdata.get("dummy_reels", 0))
    except Exception:        
        multiplier = 1

    score = 0
    for digit in range(5):
        score += sensorScores[player][digit] * (10 ** digit)

    score = score * multiplier
    
    return score

carry_measurements=[]

def replayStoredGame(quiet=False,carryDiag=False):
    ''' replay a stored game and report out scores'''
    global sensorScores,last_sc,carry_measurements

    sensorScores = [[0 for _ in range(6)] for _ in range(4)]

    index=0

    last_sc = 0xFFFFFFFF

    print("SCORE: replaying now, length=",gameHistoryIndex)

    for index in range(gameHistoryIndex):
            sensor_value = gameHistory[index]
            sample_count = gameHistoryTime[index]
            if sample_count > 20:
                sample_count=20

            if quiet==False:    
                print("send: val=",sensor_value,"  count=",sample_count)
            
            for _ in range(sample_count):              
                sc = processBitFilter(sensor_value)

                # edge detection
                risingEdge = (~last_sc) & sc
                processRisingEdge(sc,risingEdge)
                last_sc = sc

            '''during replay measure carry counts.... 
                not included in processRisingEdge for run time speed   '''
            if carryDiag == True:
                for player in range(4):
                    for digit in range(1, 4):  # only digits with a previous digit                        
                        if sensorScores[player][digit] == 10:
                            # carryCount index mapping: player blocks of 8 (0,8,16,24)
                            idx = player * 8 + (digit - 1)
                            if int(carryCount[idx]) > 1:
                                carry_measurements.append((player, digit, int(carryCount[idx])))
                                print("   carry count report            ",player, digit, carryCount[idx])                    

            #10->0 truncate, except let last one acculmulate
            if digitsPerPlayer > 0:
                for i in (0,1,2,3):
                    sensorScores[i][0] %= 10
                if digitsPerPlayer > 1:
                    for i in (0,1,2,3):
                        sensorScores[i][1] %= 10
                    if digitsPerPlayer > 2:
                        for i in (0,1,2,3):
                            sensorScores[i][2] %= 10
                        if digitsPerPlayer >3:
                            for i in range(4):
                                sensorScores[i][3] %= 10  
            #if there is a fifth reel let it overflow and keep counting              

            if quiet==False:    
                print("SCORE REPLAY: ", getPlayerScore(0),getPlayerScore(1),getPlayerScore(2),getPlayerScore(3))
        
    if quiet==False:    
        print("SCORE: replay DONE")
        print("SCORE REPLAY results -> ",  getPlayerScore(0),getPlayerScore(1),getPlayerScore(2),getPlayerScore(3))













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


def CheckForNewScores(nState=[0]):
    """called by scheduler every 5 seconds"""
    global nGameIdleCounter
    global gameHistory,sensorScores,gameover

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
            gameover = False
            S.game_status["game_active"]=True
            print("SCORE: Game Start")
            nState[0] = 2



    elif nState[0] == 2:  # waiting for game to end    
        #process data in storeage...

        if S.run_learning_game == False:
            print("SCORE: game end check - play mode                 SCORE=",getPlayerScore(0),getPlayerScore(1),getPlayerScore(2),getPlayerScore(3))
            
        else:
            print("SCORE: game end check. learn mode ",  sensorRead.depthSensorRx() ,  gameHistoryIndex  )

        #if sensorRead.gameActive() == 0:
        if gameover == True:
            print("SCORE: Game End 76")
            S.game_status["game_active"]=False
            #load scoes into scores[][]

            # game over
            nState[0] = 1           
            log.log("SCORE: game end")
         
            '''
            if S.run_learning_game == True:
                print("End of game - learning game- save and print")
                save_game_history()
                #print_game_history_file()
                free_game_history()
            '''

            sensorScores = [[0 for _ in range(6)] for _ in range(4)]

        

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






def findDataFiles():
    """
    Discover game_history files that contain at least one non-zero score.
    Returns a sorted list of tuples: (filename, sample_count, data_bytes)
      - sample_count: number of GHVL samples stored (gameHistoryIndex)
      - data_bytes: total bytes used by GHVL+GHTM (sample_count*4 + sample_count*2)
    """
    files = []
    try:
        for name in os.listdir():
            if not (name.startswith("game_history") and name.endswith(".dat")):
                continue
            try:
                print(name)
                with open(name, "rb") as f:
                    if f.read(4) != b"GHDR":
                        continue

                    # read four player scores (16 bytes)
                    scores_bytes = f.read(16)
                    if len(scores_bytes) < 16:
                        continue
                    scores = [int.from_bytes(scores_bytes[i*4:(i+1)*4], "little") for i in range(4)]

                    if not any(s != 0 for s in scores):
                        log.log("LEARN: File Empty Score")
                        continue

                    # read next marker; expect GHIX then 4-byte index
                    marker = f.read(4)
                    sample_count = 0
                    if marker == b"GHIX":
                        sample_count = int.from_bytes(f.read(4), "little")
                    else:
                        # try to find GHIX by scanning forward a bit (robustness)
                        f.seek(-4, 1)
                        data = f.read(256)  # small scan window
                        idx = data.find(b"GHIX")
                        if idx != -1 and idx + 4 + 4 <= len(data):
                            sample_count = int.from_bytes(data[idx+4:idx+8], "little")
                        else:
                            # fallback: leave sample_count as 0
                            sample_count = 0

                    files.append((name, sample_count))

            except OSError:
                # ignore unreadable / transient files
                continue
    except OSError:
        log.log("LEARN: file discovery fault")
        return []

    files.sort()
    return files


def breakScoreIntoDigits(targetScores):
    # Break down targetScores [1,2,3,4] into digits for direct comparison with sensorScores
    targetScoreDigits = []
    for score in targetScores:
        digits = []
        temp = score
        for d in range(5):
            digits.append(temp % 10)
            temp //= 10
        targetScoreDigits.append(digits)
    return targetScoreDigits
    


def find_good_combinations_per_digit(results):
    """
    Analyze `results` (list of dict with keys 'scorebits','resetbits','digit_matches')
    and return a dict mapping each digit index (0..4) to a sorted list of unique
    (scorebits, resetbits) tuples that produced a True match for that digit.
    """
    good = {d: [] for d in range(16)}    #enough for 2 players

    for rec in results:
        print(rec)
        sb = rec.get("scorebits")
        rb = rec.get("resetbits")
        dm = rec.get("digit_matches")
        for d in range(len(dm)):
            if dm[d] == True:
                good[d].append((int(sb), int(rb)))

    # deduplicate and sort each list
    for d in good:
        good[d] = sorted(set(good[d]), key=lambda x: (x[0], x[1]))

    return good


def pick_best_settings_from_results(good):
    """
    For each digit (0..4) pick one (scorebits, resetbits) pair from the valid matches
    that is closest to the average of the matching pairs.

    - results: list of dicts with keys "scorebits","resetbits","digit_matches"
    - Returns: dict digit -> (scorebits, resetbits)
    - Also applies the chosen setting by calling setScoreMask(digit, scorebits, resetbits)
      (assumes digit -> bit mapping is digit index).
    """
    # collect valid pairs per digit
    chosen = {}

    for d in sorted(good.keys()):
        pairs = good[d]
        if not pairs:
            # no valid pairs for this digit
            continue

        # compute average (mean) of scorebits and resetbits
        avg_sb = sum(sb for sb, _ in pairs) / len(pairs)
        avg_rb = sum(rb for _, rb in pairs) / len(pairs)

        # choose the actual pair (from the valid set) closest to the average
        def distance(pair):
            sb, rb = pair
            # primary metric: squared Euclidean distance; tie-breaks prefer closer sb then rb
            return ((sb - avg_sb) ** 2 + (rb - avg_rb) ** 2, abs(sb - avg_sb), abs(rb - avg_rb))

        best = min(pairs, key=distance)
        chosen[d] = (int(best[0]), int(best[1]))

    # apply chosen settings (map digit -> bit using same index)
    for d, (sb, rb) in chosen.items():
        try:
            setScoreMask(d, sb, rb)
        except Exception as e:
            print(f"Error applying mask for digit {d}: {e}")

    return chosen


def sort_out_carry_digits_and_apply():
    """Process carry_measurements, ignore counts < 4, group by (player,digit).
    If a group has 2+ samples compute low = floor(min*0.9), high = ceil(max*1.1)
    and store into carryThresholds[player][digit] = [low, high]."""
    global carry_measurements, carryThresholds

    if not carry_measurements:
        print("LEARN: no carry measurements")
        return

    # filter out low-count noise
    filtered = [(p, d, c) for (p, d, c) in carry_measurements if int(c) >= 4]
    if not filtered:
        log.log("LEARN: no carry measurements >=4")
        return

    # group counts by (player,digit)
    groups = {}
    for p, d, c in filtered:
        groups.setdefault((p, d), []).append(int(c))

    print("groups ",groups)    

    applied = []
    for (p, d), counts in groups.items():
        if len(counts) < 2:
            # require at least two measurements to be confident
            continue
        minc = min(counts)
        maxc = max(counts)
        low = int(minc*0.9)
        high = int(maxc * 1.1)
        # store computed thresholds
        carryThresholds[p][d][0] = low
        carryThresholds[p][d][1] = high
        applied.append((p, d, low, high, sorted(counts)))

    if applied:
        print("LEARN: applied carryThresholds (player,digit,low,high,counts):")
        for entry in applied:
            print("  ", entry)      
    else:
        print("LEARN: no grouped carry measurements found to apply")



#timer stuff to keep the digit display going during learn mode only
from machine import Timer
display_timer = Timer(-1) 
from displayMessage import displayUpdate
def dis(r):
    displayUpdate()
def startTimer():    
    display_timer.init(mode=Timer.PERIODIC, period=700, callback=dis)
def stopTimer():
    display_timer.deinit()
    del globals()['display_timer']


def learnModeProcessNow():
    ''' the BIG learn mode - process all files data and set all filter and score parameters'''
    global actualScores,fileNumber

    startTimer()
    results = []

    # count up the files and work to be done
    fileList = findDataFiles()
    log.log(f"\nLearn Mode Files={fileList}")

    # Sum all sample_counts
    total_samples = sum(sample_count for _, sample_count in fileList)
    print("Total sample count across all files:", total_samples)

    # issue warnings about missing scores or not enough data?
    if total_samples<8000:
        log.log("LEARN: low sample count")
    if len(fileList) < 2:
        print("LEARN: low file count")

    # init display count down to finish
    from displayMessage import setLearnModeDigit
    displayCounter=9
    setLearnModeDigit(displayCounter)    

    # process each file for filter counts
    SCORE_RANGE = (3,4,5,6,7,8,9)
    RESET_RANGE = (6,9,15)        

    # disable all carry thresholds
    for player in range(4):
        for digit in range(4):
            carryThresholds[player][digit][0] = 99
            carryThresholds[player][digit][1] = 99

    #setup digit countdown
    downDelta=(len(fileList) * len(SCORE_RANGE) * len(RESET_RANGE))//5
    downCount = 0

    # Loop over each file in fileList, set fileNumber to the number in the filename
    for file_info in fileList:
        filename = file_info[0]
        # Extract file number from filename (expects format "game_historyN.dat")
        try:
            fileNumber = int(filename.replace("game_history", "").replace(".dat", ""))
        except ValueError:
            log.log(f"LEARN: Could not extract file number from {filename}")
            continue

        load_game_history()
        targetScoreDigits = breakScoreIntoDigits(actualScores)       
        # Now targetScoreDigits[player][digit] matches sensorScores[player][digit]

        print(f"\nProcessing file: {filename} (fileNumber={fileNumber})")
        print("loaded actual score= ", actualScores,targetScoreDigits)
        print("digits per player=", digitsPerPlayer)
        print("carryThresholds before=", carryThresholds)
        for scorebits in SCORE_RANGE:
            for resetbits in RESET_RANGE:
                # count down
                downCount = downCount +1
                if downCount >= downDelta:
                    downCount=0
                    displayCounter = displayCounter -1
                    setLearnModeDigit(displayCounter)                

                # Set all digits of score mask the same
                for bit in range(32):    #all filter bits
                    setScoreMask(bit, scorebits, resetbits)

                #print("Testing: scorebits=", scorebits, " resetbits=", resetbits)
                replayStoredGame(quiet=True,carryDiag=False)

                print("score digits p0=", [sensorScores[0][d] for d in range(5)],
                      "(", sum(sensorScores[0][d] * (10 ** d) for d in range(5)),")",
                      "score digits p1=", [sensorScores[1][d] for d in range(5)],
                      "(", sum(sensorScores[1][d] * (10 ** d) for d in range(5)),")",
                      " with setting=", scorebits, resetbits)

                # Compare each digit in sensorScores
                digit_matches_p0 = [sensorScores[0][d] == targetScoreDigits[0][d] for d in range(5)]
                digit_matches_p1 = [sensorScores[1][d] == targetScoreDigits[1][d] for d in range(5)]
                spc = [True,True,True]
                digit_matches = digit_matches_p0 + spc + digit_matches_p1 + spc

                # Record scorebits, resetbits, digits, and digit_matches for both players in results
                results.append({
                    "scorebits": scorebits,
                    "resetbits": resetbits,
                    "digits_p0": [sensorScores[0][d] for d in range(5)],  #lesat sig in left most
                    "digit_matches_p0": digit_matches_p0,
                    "digits_p1": [sensorScores[1][d] for d in range(5)],
                    "digit_matches_p1": digit_matches_p1,
                    "digit_matches": digit_matches
                })

        # Print results in a more readable format            
        print("\nResults summary:")
        for idx, rec in enumerate(results):
            print("  [{}] sbits={}, rbits={}, digits_p0={}, matches_p0={}, digits_p1={}, matches_p1={}, match={}".format(
                idx, rec['scorebits'], rec['resetbits'], rec['digits_p0'], rec['digit_matches_p0'], rec['digits_p1'], rec['digit_matches_p1'], rec['digit_matches']  ))
        print()
    
        
    displayCounter = displayCounter -1
    setLearnModeDigit(displayCounter)

    # find good reset bits and score bits settings
    p=find_good_combinations_per_digit(results)

    # print out the results per digit..
    for k in p:
        print("Dig:",k,p[k])
    print("\n")


    import sys
    sys.exit()



    displayCounter = displayCounter -1
    setLearnModeDigit(displayCounter)

    # make picks for best settings (with out carry yet - -)
    q=pick_best_settings_from_results(p)
    print(q)

    #if a digit has no solutions - try somthing??  carry over??
    missing_digits = []
    for d in range(5):
        if not p.get(d): 
            missing_digits.append(d)

    if missing_digits:
        log.log(f"LEARN: missing digits {missing_digits}")
        # Compute average scorebits and resetbits from existing good digits
        all_good_pairs = [pair for digit in p if p[digit] for pair in p[digit]]
        if all_good_pairs:
            avg_scorebits = int(sum(sb for sb, _ in all_good_pairs) / len(all_good_pairs))
            avg_resetbits = int(sum(rb for _, rb in all_good_pairs) / len(all_good_pairs))
        else:
            avg_scorebits = 5  # fallback default
            avg_resetbits = 9  # fallback default

        # Fill in missing digits with the average values
        for d in missing_digits:
            p[d] = [(avg_scorebits, avg_resetbits)]
            log.log(f"Digit {d}: filled with average ({avg_scorebits}, {avg_resetbits})")

    displayCounter = displayCounter -1
    setLearnModeDigit(displayCounter)

    #set the scorebits and reset bits
    for digit, (scorebits, resetbits) in q.items():
        print(digit, scorebits, resetbits)
        setScoreMask(digit, scorebits, resetbits)
    printMasks()

    # process files looking for carry/rollover settings
    for file_info in fileList:
        filename = file_info[0]
        # Extract file number from filename (expects format "game_historyN.dat")
        try:
            fileNumber = int(filename.replace("game_history", "").replace(".dat", ""))
        except ValueError:
            print(f"LEARN: Could not extract file number from {filename}")
            continue

        load_game_history()
        targetScoreDigits = breakScoreIntoDigits(actualScores)       
        # Now targetScoreDigits[player][digit] matches sensorScores[player][digit]

        print(f"\nProcessing file for carry settings: {filename} (fileNumber={fileNumber})")
        print("Testing: scorebits=", scorebits, " resetbits=", resetbits)
        replayStoredGame(quiet=True,carryDiag=True)

    print("All carry measurements (player,digit,count) ",carry_measurements)
    displayCounter = displayCounter -1
    setLearnModeDigit(displayCounter)

    #sort out carry digits...
    sort_out_carry_digits_and_apply()
    printMasks()

    # - save to fram
    saveState()
    log.log("LEARN: done")

    stopTimer()








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






if __name__ == "__main__":

    #must load game data
    import GameDefsLoad
    GameDefsLoad.go()

    print(S.gdata)

    initialize()

    if actualScoreFromLastGame != None:
        add_actual_score_to_file(filename=None, actualScores=actualScoreFromLastGame)
   
    else:
   

        def print_score_reset_ranges(results, score_range, reset_range, targetScore):
            """
            Analyze `results` entries (scorebits, resetbits, digits-list) and print
            for each digit index the reset-bit ranges that produce the target digit.
            results: list of (scorebits, resetbits, digits)
            score_range, reset_range: iterables used when producing results (kept order)
            targetScore: full integer score used to pick expected digit per place
            """
            def compress_ranges(sorted_vals):
                """Compress sorted list of ints into list of (start,end) ranges."""
                if not sorted_vals:
                    return []
                ranges = []
                start = prev = sorted_vals[0]
                for v in sorted_vals[1:]:
                    if v == prev + 1:
                        prev = v
                    else:
                        ranges.append((start, prev))
                        start = prev = v
                ranges.append((start, prev))
                return ranges

            score_list = list(score_range)
            reset_list = list(reset_range)

            # Build lookup: (scorebits, resetbits) -> digits
            lookup = {}
            for sb, rb, digits in results:
                lookup[(sb, rb)] = digits

            # Compute expected digit per digit index from targetScore
            expected = []
            for d in range(5):
                expected.append((targetScores[0] // (10 ** d)) % 10)

            for digit_index in range(5):
                exp = expected[digit_index]
                print(f"\nDigit {digit_index} (place {10**digit_index}), expected={exp}:")
                any_found = False
                for sb in score_list:
                    ok_resets = []
                    for rb in reset_list:
                        digits = lookup.get((sb, rb))
                        if digits is not None and digits[digit_index] == exp:
                            ok_resets.append(rb)
                    if ok_resets:
                        any_found = True
                        ranges = compress_ranges(sorted(ok_resets))
                        ranges_str = ", ".join(f"{a}" if a==b else f"{a}-{b}" for (a,b) in ranges)
                        print(f"  scorebits={sb:2d}: resetbits -> {ranges_str}")
                if not any_found:
                    print("  (no combinations found)")

            # Example usage (uncomment/run after results populated):
            # print_score_reset_ranges(results, SCORE_RANGE, targetScore)

        
        results = []
        import time

        learnModeProcessNow()

        printMasks()

        '''
        load_game_history()
        targetScores = actualScores  # Load target score from the game file

        print("loaded actual score= ", targetScores)
        print("digits per player=", digitsPerPlayer)
        print("carryThresholds before=", carryThresholds)
        printMasks()
        # Set all carry thresholds to 255
        
        for player in range(4):
            for digit in range(4):
                carryThresholds[player][digit][0] = 24
                carryThresholds[player][digit][1] = 27
        
        
        print("carryThresholds after=")
        printMasks()


        start = time.ticks_ms()

      
        SCORE_RANGE = (2,3,4,5,6,7,8,9)
        RESET_RANGE = (0,1,2,3,4,5,6,7,8,9,10,11,12,13,14)

        SCORE_RANGE = (3,4,5,6,7,8)
        RESET_RANGE = (6,9,15)

        


        
        for scorebits in SCORE_RANGE:
            for resetbits in RESET_RANGE:

                # Set all digits of score mask the same
                for bit in range(10):
                    setScoreMask(bit, scorebits, resetbits)

                print("Testing: scorebits=",scorebits," resetbits=",resetbits)
                replayStoredGame(True)

                print("score digits=", [sensorScores[0][d] for d in range(5)], 
                    " full score=", sum(sensorScores[0][d] * (10 ** d) for d in range(5)), 
                    " with setting=", scorebits, resetbits)

                # Record z, one, and sensorScores[0][0:5] in results
                results.append((scorebits, resetbits, [sensorScores[0][d] for d in range(5)]))

                #elapsed = time.ticks_diff(time.ticks_ms(), start)
                #print("Replay execution time:", elapsed, "ms")
        '''

        '''
        # Print set/reset combinations for each digit place (1s, 10s, 100s, 1000s, 10000s)
        digit_places = [1, 10, 100, 1000]
        print("Taget Score = ",targetScore)
        for digit_index, digit_value in enumerate(digit_places):
            print(f"\nCombinations for digit place {digit_value}:")
            for record in results:
                scoreb, resetb, digits = record
                if digits[digit_index] == targetScore // digit_value % 10:
                    print(f"scorebits={scoreb}, resetbits={resetb}, digits={digits}")
        '''



