# This file is part of the Warped Pinball SYSEM-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Score Track
    This module is responsible for tracking scores and updating the leaderboard.

    EM version_viper_process

"""
import array
import resource
import time

import displayMessage
import sensorRead
import SharedState as S
import SPI_DataStore as DataStore
import uctypes
from logger import logger_instance
from machine import RTC
from ScoreTrackFilter_viper import _viper_process
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH

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

lastValue = 0
segmentMS = 0

# Diagnostics #gpio26 = Pin(26, Pin.OUT)
# gpio26.value(not gpio26.value())
# gpio1 = Pin(1, Pin.OUT)
# gpio1.value(not gpio1.value())



# default pauses (can be overridden from EMData/S.gdata in _loadState)
PROCESS_START_PAUSE = 4
PROCESS_END_PAUSE = 5

gameover = False

# SCORE Digits for all 4 players - Initialize sensorScores[player][digit]
sensorScores = [[0 for _ in range(8)] for _ in range(4)]

"""
Bit filter
    uses viper for speed, setup score and rest masks to adjust filtering
    32 bit parallel capable (all input channels at once)

    score_mask - sets # of samples ==1 to latch bit on
    once on can only be unset by number of zeros defined in rest_mask
"""
MASK32 = 0xFFFFFFFF
DEPTH = 16
IDXMSK = 0x0F  # pointer wrap around - 16 samples

# use array.array('I') so viper can access as ptr32 via memoryview
# bit Buffer to pass data to viper function
bit_buf = array.array("I", [0] * DEPTH)
bit_ptr = -1
score_mask = array.array("I", [0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF])
reset_mask = array.array("I", [0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF])
scoreState = 0  # int

# per-bit depth copies - persistent so other code can inspect configured depths
scoreDepths = [0] * 32  # number of stages used for score detection per bit
resetDepths = [0] * 32  # number of stages used for reset detection per bit

# create memoryviews - to send to viper function
bit_buf_mv = memoryview(bit_buf)
score_mask_mv = memoryview(score_mask)
reset_mask_mv = memoryview(reset_mask)

# carryThresholds (timing) as a 4x4x2 array [player][digit][low,high]
carryThresholds = [[[12, 28] for _ in range(4)] for _ in range(4)]

# Temporary toggle: set False to disable carry-count correction logic.
CARRY_COUNT_CORRECTION_ENABLED = False


def _carry_window_hit(count, player_idx, digit_idx):
    if not CARRY_COUNT_CORRECTION_ENABLED:
        return False
    return count > carryThresholds[player_idx][digit_idx][0] and count < carryThresholds[player_idx][digit_idx][1]

# give a default here - stup in initialize according to configuration / datastore
sensorBitMask = 0x0000F0F
digitsPerPlayer = 1


def reset_live_scores_on_boot():
    """Reset all live scoring state so EM boots with zeroed scores."""
    global sensorScores, last_sc, scoreState
    global stateVar, stateCount, gameover, nGameIdleCounter
    global lastValue, segmentMS

    sensorScores = [[0 for _ in range(8)] for _ in range(4)]

    last_sc = 0
    scoreState = 0
    stateVar = PROCESS_IDLE
    stateCount = 0
    gameover = False
    nGameIdleCounter = 0
    lastValue = 0
    segmentMS = 0

    S.game_status["game_active"] = False

    # Drain any stale sensor words left in SRAM ring buffer.
    for _ in range(5):
        processEmpty()


def initialize():
    """
    one time power up Initialize
    """
    from phew.server import schedule

    schedule(processSensorData, 1000, 800)    

    reset_live_scores_on_boot()
    loadState()
    # from displayMessage import init
    displayMessage.init()
    S.game_status["game_active"] = False


def buildSensorBitMask():
    # build sensorBitMask used in sensor reads - single 32 bit word from players and digits
    global sensorBitMask

    digitsPerPlayer = int(S.gdata["digits"])
    players = int(S.gdata["players"])

    base_byte = (1 << digitsPerPlayer) - 1
    base_byte &= 0xFF
    sb = base_byte
    if players >= 2:
        sb |= base_byte << 8
    if players >= 3:
        sb |= base_byte << 16
    if players >= 4:
        sb |= base_byte << 24
    sensorBitMask = sb
    print(f"SCORE: sensor bit mask: {sb:#010x}")


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
    print(f"SCORE: Loading pauses from S.gdata: startpause={S.gdata.get('startpause', 'NOT SET')}, endpause={S.gdata.get('endpause', 'NOT SET')}")
    
    PROCESS_START_PAUSE = int(S.gdata.get("startpause", PROCESS_START_PAUSE))
    PROCESS_END_PAUSE = int(S.gdata.get("endpause", PROCESS_END_PAUSE))
    print("SCORE: pauses= ", PROCESS_START_PAUSE, PROCESS_END_PAUSE)

    buildSensorBitMask()

    # carryThresholds (4 players * 4 digits * 2 values (1 byte each))
    ct_blob = S.gdata["carrythresholds"]
    if not isinstance(ct_blob, (bytes, bytearray)) or len(ct_blob) != 32:
        raise ValueError("S.gdata['carrythresholds'] must be 32-byte bytes or bytearray")
    b = bytes(ct_blob)
    pos = 0
    for p in range(4):
        for d in range(4):
            low = b[pos]
            pos += 1
            high = b[pos]
            pos += 1
            carryThresholds[p][d][0] = int(low)
            carryThresholds[p][d][1] = int(high)

    # Build score/reset masks from timing arrays loaded from EMData.
    # Timing arrays are the source of truth; filtermasks is runtime-derived.
    def _coerce_timing_array(raw, fallback, value_min, value_max):
        try:
            vals = [int(v) for v in raw]
        except Exception:
            vals = list(fallback)
        if len(vals) != 5:
            vals = list(fallback)
        out = []
        for v in vals:
            if v < value_min:
                v = value_min
            if v > value_max:
                v = value_max
            out.append(int(v))
        return out

    def _apply_player_timing(player_index, score_key, reset_key):
        base = int(player_index) * 8

        # UI order is [10000s, 1000s, 100s, 10s, 1s] while channel bits are
        # [1s, 10s, 100s, 1000s, 10000s] at offsets [0..4].
        def _ch_for_ui_idx(ui_idx):
            return base + (4 - int(ui_idx))

        default_score = [8, 8, 8, 8, 8]
        default_reset = [8, 8, 8, 8, 8]
        score_vals = _coerce_timing_array(S.gdata.get(score_key, default_score), default_score, 1, 10)
        reset_vals = _coerce_timing_array(S.gdata.get(reset_key, default_reset), default_reset, 1, 15)

        for d in range(5):
            ch = _ch_for_ui_idx(d)
            setScoreMask(ch, score_vals[d], reset_vals[d])

        return score_vals, reset_vals

    p1_score_vals, p1_reset_vals = _apply_player_timing(0, "timing_p1_score", "timing_p1_reset")
    p2_score_vals, p2_reset_vals = _apply_player_timing(1, "timing_p2_score", "timing_p2_reset")
    p3_score_vals, p3_reset_vals = _apply_player_timing(2, "timing_p3_score", "timing_p3_reset")
    p4_score_vals, p4_reset_vals = _apply_player_timing(3, "timing_p4_score", "timing_p4_reset")

    S.gdata["timing_p1_score"] = p1_score_vals
    S.gdata["timing_p1_reset"] = p1_reset_vals
    S.gdata["timing_p2_score"] = p2_score_vals
    S.gdata["timing_p2_reset"] = p2_reset_vals
    S.gdata["timing_p3_score"] = p3_score_vals
    S.gdata["timing_p3_reset"] = p3_reset_vals
    S.gdata["timing_p4_score"] = p4_score_vals
    S.gdata["timing_p4_reset"] = p4_reset_vals

    # Keep runtime filtermasks for compatibility/inspection (not persisted).
    fm = bytearray(64)
    for ch in range(32):
        fm[ch * 2] = int(scoreDepths[ch]) & 0xFF
        fm[ch * 2 + 1] = int(resetDepths[ch]) & 0xFF
    S.gdata["filtermasks"] = bytes(fm)

    log.log(f"ScoreTrack initialized: players={players} digits={digitsPerPlayer} sensorMask=0x{sensorBitMask:08X}")
    print("ScoreTrack pauses: startpause=%d endpause=%d" % (PROCESS_START_PAUSE, PROCESS_END_PAUSE))

    print("LOAD", S.gdata)


def updatePauseGlobals():
    """
    Update PROCESS_START_PAUSE and PROCESS_END_PAUSE from S.gdata.
    Called when pause values are changed via API.
    """
    global PROCESS_START_PAUSE, PROCESS_END_PAUSE
    
    PROCESS_START_PAUSE = int(S.gdata.get("startpause", PROCESS_START_PAUSE))
    PROCESS_END_PAUSE = int(S.gdata.get("endpause", PROCESS_END_PAUSE))
    print(f"SCORE: Updated pause globals - startpause={PROCESS_START_PAUSE}, endpause={PROCESS_END_PAUSE}")



def saveState():
    """store working config back to SPI_DataStore"""
    # Ensure pause values exist in S.gdata (use globals if not set)
    if "startpause" not in S.gdata:
        S.gdata["startpause"] = int(PROCESS_START_PAUSE)
    if "endpause" not in S.gdata:
        S.gdata["endpause"] = int(PROCESS_END_PAUSE)
    
    def _coerce_timing_array(raw, fallback):
        try:
            vals = [int(v) for v in raw]
        except Exception:
            vals = list(fallback)
        if len(vals) != 5:
            vals = list(fallback)
        out = []
        for v in vals:
            if v < 0:
                v = 0
            if v > DEPTH:
                v = DEPTH
            out.append(int(v))
        return out

    def _apply_player_timing(player_index, score_key, reset_key):
        base = int(player_index) * 8

        # UI order is [10000s, 1000s, 100s, 10s, 1s] while channel bits are
        # [1s, 10s, 100s, 1000s, 10000s] at offsets [0..4].
        def _ch_for_ui_idx(ui_idx):
            return base + (4 - int(ui_idx))

        default_score = [int(scoreDepths[_ch_for_ui_idx(d)]) for d in range(5)]
        default_reset = [int(resetDepths[_ch_for_ui_idx(d)]) for d in range(5)]

        score_vals = _coerce_timing_array(S.gdata.get(score_key, default_score), default_score)
        reset_vals = _coerce_timing_array(S.gdata.get(reset_key, default_reset), default_reset)

        for d in range(5):
            ch = _ch_for_ui_idx(d)
            setScoreMask(ch, score_vals[d], reset_vals[d])

        return score_vals, reset_vals

    # Timing arrays from API map to channel groups as player*8 + digit(0..4)
    # P1: ch 0..4, P2: ch 8..12, P3: ch 16..20, P4: ch 24..28
    p1_score_vals, p1_reset_vals = _apply_player_timing(0, "timing_p1_score", "timing_p1_reset")
    p2_score_vals, p2_reset_vals = _apply_player_timing(1, "timing_p2_score", "timing_p2_reset")
    p3_score_vals, p3_reset_vals = _apply_player_timing(2, "timing_p3_score", "timing_p3_reset")
    p4_score_vals, p4_reset_vals = _apply_player_timing(3, "timing_p4_score", "timing_p4_reset")

    S.gdata["timing_p1_score"] = p1_score_vals
    S.gdata["timing_p1_reset"] = p1_reset_vals
    S.gdata["timing_p2_score"] = p2_score_vals
    S.gdata["timing_p2_reset"] = p2_reset_vals
    S.gdata["timing_p3_score"] = p3_score_vals
    S.gdata["timing_p3_reset"] = p3_reset_vals
    S.gdata["timing_p4_score"] = p4_score_vals
    S.gdata["timing_p4_reset"] = p4_reset_vals

    # Build runtime 64-byte filtermasks for compatibility/inspection only.
    # Persistence stores timing arrays; masks are regenerated on boot.
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

    # Note: startpause and endpause should already be set in S.gdata by the caller
    # Don't overwrite them here - just ensure they're written to SPI
    S.gdata["GameInfo"]["GameName"] = S.gdata["gamename"]
    buildSensorBitMask()

    try:
        # c=DataStore.read_record("configuration")
        # c["gamename"] =  S.gdata["gamename"]
        # DataStore.write_record("configuration",0)

        DataStore.write_record("EMData", S.gdata)
        
        #  printMasks()
    except Exception as e:
        print("Error writing EMData:", e)


def setScoreMask(bit, scoreDepth, resetDepth):
    """Set a single bit across score_mask and reset_mask.
            masks are used in high speed filter (viper function)
    Parameters:
      bit         - bit number 0..31 to modify
      scoreDepth  - number of earliest stages (0..DEPTH) that should have the bit cleared;
                    all later stages will have the bit set.
      resetDepth  - same semantics for reset_mask
    """
    global score_mask, reset_mask, scoreDepths, resetDepths


    print("SCORE: setting score mask",bit,scoreDepth,resetDepth)

    if not (0 <= bit < 32):
        log.log("SCORE: bit - out of range 0..31")
        bit = 0
    if not (0 <= scoreDepth <= DEPTH):
        log.log(f"scoreDepth out of range 0..{scoreDepth}")
        scoreDepth = 0
    if not (0 <= resetDepth <= DEPTH):
        log.log(f"resetDepth out of range 0..{resetDepth}")
        resetDepth = 0

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
        return " ".join(b[i : i + 4] for i in range(0, 32, 4))

    print("Stage ScoreMask     ScoreBin                                 ResetMask    ResetBin")
    print("-----  -----------  --------------------------------         -----------  --------------------------------")
    for i in range(DEPTH):
        s = int(score_mask[i]) & MASK32
        r = int(reset_mask[i]) & MASK32
        print(f"{i:5d}  0x{s:08X}  {grp32(s)}  0x{r:08X}  {grp32(r)}")

    print(f"PROCESS_START_PAUSE={PROCESS_START_PAUSE}  PROCESS_END_PAUSE={PROCESS_END_PAUSE}")

    print("\nCarryThresholds (player x digit):")
    for player in range(len(carryThresholds)):
        print(f"Player {player}:")
        for digit in range(len(carryThresholds[player])):
            low, high = carryThresholds[player][digit]
            print(f"  Digit {digit}: low={low}, high={high}")
    print()


def processBitFilter(new_word):
    """python (non-viper) for calling the bitfilter in _viper_process"""
    global bit_buf, bit_ptr, scoreState

    # store incoming word in rotating bit_buf
    bit_ptr = (bit_ptr + 1) & IDXMSK
    bit_buf[bit_ptr] = new_word

    # call viper routine for filtering FAST!
    scoreState = _viper_process(bit_buf_mv, bit_ptr, IDXMSK, scoreState, score_mask_mv, reset_mask_mv)
    return scoreState


# Process Sensor Data state defines
PROCESS_IDLE = 0
PROCESS_START = 1
PROCESS_RUN = 3
PROCESS_RUN_END = 5


stateVar = 0
stateCount = 0


# called from phew schedeuler
def processSensorData():
    """called each every 800mS.    watch game active and decide when to operate on data
    coming in from sensor module - process for live scores"""
    global stateVar, stateCount, gameover
    global lastValue, segmentMS,sensorScores 

    stateCount += 1

    if stateVar == PROCESS_IDLE:
        """wait for game to start"""
        processAndRun()  #run so lights blink for user cal       
        sensorScores = [[0 for _ in range(8)] for _ in range(4)]   #but keep scores at 000000 !
        if sensorRead.gameActive() == 1:
            stateVar = PROCESS_START
            stateCount = 0            
            
    elif stateVar == PROCESS_START:
        """game start delay - wait for score reset to happen
        -make smarter in the future?  wait fro a few seconds and more if signal detected...."""

        if sensorRead.gameActive() == 1:
            processEmpty()
            sensorScores = [[0 for _ in range(8)] for _ in range(4)]
            lastValue = sensorBitMask  # init lastValue (alll ones) since scores are incremented on falling edges

            if stateCount > PROCESS_START_PAUSE:
                log.log("SCORE: Run game scoring")
                processEmpty()
                stateVar = PROCESS_RUN
        else:
            stateVar = PROCESS_IDLE
            stateCount = 0

    elif stateVar == PROCESS_RUN:
        # run data now - live score
        processAndRun()
        if sensorRead.gameActive() == 0:
            stateVar = PROCESS_RUN_END
            stateCount = 0

    elif stateVar == PROCESS_RUN_END:
        # run data now - live score
        processAndRun()
        if stateCount > PROCESS_END_PAUSE:
            stateVar = PROCESS_IDLE
            gameover = True
            stateCount = 0


# This is the sensor ram buffer area (8k), data placed by PIO - pulled out here
# 0x0000 is invalid data and used to mark empty space.
# Define the RAM as an array of 32-bit unsigned ints

ram_bytes = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)
bufferPointerIndex = 0
SRAM_BIT_MASK = SRAM_DATA_LENGTH - 1


def reset_sensor_buffer_pointer():
    """Reset the SRAM read pointer used by pullWithDelete()."""
    global bufferPointerIndex
    bufferPointerIndex = 0


def pullWithDelete():
    """pulls out one 32 bit value and erases the spot in ram
    optimized for speed, 1000 calls approx = 50mS"""
    global bufferPointerIndex
    offset = bufferPointerIndex
    b0 = ram_bytes[offset]
    b1 = ram_bytes[offset + 1]
    b2 = ram_bytes[offset + 2]
    b3 = ram_bytes[offset + 3]
    word = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    if word != 0:
        ram_bytes[offset] = 0
        ram_bytes[offset + 1] = 0
        ram_bytes[offset + 2] = 0
        ram_bytes[offset + 3] = 0
        bufferPointerIndex += 4
        bufferPointerIndex &= SRAM_BIT_MASK
    return word


def processEmpty():
    """pull and discard - used during gameActive == false"""
    for x in range(2500):
        if pullWithDelete() == 0:
            return


# empty out buffer on power up
for _ in range(5):
    processEmpty()


last_sc = 0
zero_sample_streak = 0
ZERO_SAMPLE_WARN_EVERY = 20


def processRisingEdge(risingEdge):
    """process rising edge and increment sensor scores as needed
    used by run and replay stored game...
    risingEdge bit=1 for single cycle on rising edge"""
    global sensorScores

    # player 1
    if risingEdge & 0x00000001:
        sensorScores[0][0] += 1  # ONES
    if risingEdge & 0x00000002:
        sensorScores[0][1] += 1  # TENS
    if risingEdge & 0x00000004:
        sensorScores[0][2] += 1  # HUNDREDS
    if risingEdge & 0x00000008:
        sensorScores[0][3] += 1  # THOUSANDS
    if risingEdge & 0x00000010:
        sensorScores[0][4] += 1  # TEN THOUSANDS

    # player 2
    if risingEdge & 0x00000100:
        sensorScores[1][0] += 1
    if risingEdge & 0x00000200:
        sensorScores[1][1] += 1
    if risingEdge & 0x00000400:
        sensorScores[1][2] += 1
    if risingEdge & 0x00000800:
        sensorScores[1][3] += 1
    if risingEdge & 0x00001000:
        sensorScores[1][4] += 1

    # player 3
    if risingEdge & 0x00010000:
        sensorScores[2][0] += 1
    if risingEdge & 0x00020000:
        sensorScores[2][1] += 1
    if risingEdge & 0x00040000:
        sensorScores[2][2] += 1
    if risingEdge & 0x00080000:
        sensorScores[2][3] += 1
    if risingEdge & 0x00100000:
        sensorScores[2][4] += 1

    # player 4
    if risingEdge & 0x01000000:
        sensorScores[3][0] += 1
    if risingEdge & 0x02000000:
        sensorScores[3][1] += 1
    if risingEdge & 0x04000000:
        sensorScores[3][2] += 1
    if risingEdge & 0x08000000:
        sensorScores[3][3] += 1
    if risingEdge & 0x10000000:
        sensorScores[3][4] += 1


def processAndRun():
    """pull data from ram buffer and feed to score module - for active game running"""
    global last_sc, sensorScores, zero_sample_streak

    def _count_set_bits(v):
        c = 0
        while v:
            v &= v - 1
            c += 1
        return c

    allActivesChannels = 0
    samples_processed = 0

    start_time = time.ticks_ms()  # Start timer
    for samp in range(2500):
        d = pullWithDelete()
        if d == 0:
            samples_processed = samp
            break  # end of buffer data, drop ougta here

        # keep all channels that go active for led display
        allActivesChannels = allActivesChannels | (d & sensorBitMask) #sc

        sc = processBitFilter(d & sensorBitMask)       
        
        # Detect rising edges on all 32 bits at once
        risingEdge = (~last_sc) & sc
        processRisingEdge(risingEdge)
        last_sc = sc

    # send to display green digit leds
    displayMessage.setSensorLeds(allActivesChannels)

    # set SharedState for admin sensitivity indicator: off / green / red
    maskedActivesChannels = allActivesChannels & sensorBitMask

    #print("                                          sensor levels:", hex(maskedActivesChannels), samples_processed)

    if samples_processed == 0:
        zero_sample_streak += 1
        if zero_sample_streak == 1 or (zero_sample_streak % ZERO_SAMPLE_WARN_EVERY) == 0:
            try:
                fifo_depth = sensorRead.depthSensorRx()
            except Exception:
                fifo_depth = -1
            warn = f"SCORE: WARN #$%#$%#$%#$%#$%#$%#$%#$%#$%#$%       zero-sample streak={zero_sample_streak} fifo_depth={fifo_depth} game_active={sensorRead.gameActive()} buf_idx={bufferPointerIndex}"
            print(warn)
            log.log(warn)
            sensorRead.initialize()

    elif zero_sample_streak > 0:
        log.log(f"SCORE: zero-sample streak cleared at {zero_sample_streak}")
        zero_sample_streak = 0

    # stamp SharedState for web indicator lamp
    if maskedActivesChannels:
        S.sensor_last_hit_ms = time.ticks_ms()

    # 10->0 truncate, except let last one acculmulate
    if digitsPerPlayer > 0:
        for i in (0, 1, 2, 3):
            sensorScores[i][0] %= 10
        if digitsPerPlayer > 1:
            for i in (0, 1, 2, 3):
                sensorScores[i][1] %= 10
            if digitsPerPlayer > 2:
                for i in (0, 1, 2, 3):
                    sensorScores[i][2] %= 10
                if digitsPerPlayer > 3:
                    for i in range(4):
                        sensorScores[i][3] %= 10
    # if there is a fifth reel let it overflow and keep counting

    end_time = time.ticks_ms()
    elapsed = time.ticks_diff(end_time, start_time)
    print("SCORE: samples=", samples_processed, "process/Run time=", elapsed, "ms/sensors=", hex(maskedActivesChannels))

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
        score += sensorScores[player][digit] * (10**digit)

    score = score * multiplier

    return score


def reset_scores():
    # reset leader board scores
    from SPI_DataStore import blankStruct

    blankStruct("leaders")


def get_claim_score_list():
    result = []
    if DataStore.read_record("extras", 0)["claim_scores"]:
        for game in recent_scores[:4]:
            # if there are any unclaimed non zero scores, add them to the list
            if any(score[0] == "" and score[1] != 0 for score in game[1:]):
                # add the game to the list, with all zero scores removed
                result.append([score for score in game[1:] if score[1] != 0])
    return result


def claim_score(initials, player_index, score):
    # claim a score from the recent scores list
    global recent_scores

    # condition the initials - more important than one would think.  machines freak if non printables get in
    initials = initials.upper()
    i_initials = ""
    for c in initials:
        if "A" <= c <= "Z":
            i_initials += c
    initials = (i_initials + "   ")[:3]

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
    recent_scores.insert(0, game)
    recent_scores.pop()
    print("SCORE: add to claims list: ", recent_scores)
    from origin import push_end_of_game

    push_end_of_game(game)


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

    year, month, day, _, _, _, _, _ = rtc.datetime()
    new_entry["date"] = f"{month:02d}/{day:02d}/{year}"

    log.log(f"SCORE: Update Leader Board: {new_entry}")
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
    global nGameIdleCounter
    global sensorScores, gameover

    resource.go()

    if nState[0] == 0:  # power up init
        printMasks()
        S.game_status["game_active"] = False
        nState[0] = 1

    if nState[0] == 1:  # waiting for a game to start
        nGameIdleCounter += 1  # claim score list expiration timer
        print("SCORE: game start check - ", sensorRead.depthSensorRx())

        if nGameIdleCounter > (3 * 60 / 5):  # 3 min, push empty onto list so old games expire
            game = [S.gameCounter, ["", 0], ["", 0], ["", 0], ["", 0]]
            _place_game_in_claim_list(game)
            nGameIdleCounter = 0
            print("SCORE: game list 10 minute expire")

        # if game_active_flag == True:
        if sensorRead.gameActive() == 1:
            gameover = False
            S.game_status["game_active"] = True
            print("SCORE: Game Start")
            nState[0] = 2

    elif nState[0] == 2:  # waiting for game to end
        # process data in storeage...
        print("SCORE: game end check - play mode                 SCORE=", getPlayerScore(0), getPlayerScore(1), getPlayerScore(2), getPlayerScore(3))

        # if sensorRead.gameActive() == 0:
        if gameover:
            print("SCORE: Game End 76")
            S.game_status["game_active"] = False

            # load scoes into scores[][]
            if DataStore.read_record("extras", 0)["tournament_mode"]:
                for i in range(0, 4):
                    update_tournament({"initials": "", "score": getPlayerScore(i)})
            else:
                for i in range(0, 4):
                    update_leaderboard({"initials": "", "score": getPlayerScore(i)})

            game = [S.gameCounter, ["", getPlayerScore(0)], ["", getPlayerScore(1)], ["", getPlayerScore(2)], ["", getPlayerScore(3)]]
            _place_game_in_claim_list(game)

            # game over
            nState[0] = 1
            log.log("SCORE: game end")
            sensorScores = [[0 for _ in range(8)] for _ in range(4)]

