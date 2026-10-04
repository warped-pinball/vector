import time
from machine import Pin, SPI, PWM, Timer


end_game = Pin(15, Pin.OUT)

import sensorRead
sensorRead.initialize()

# Pin assignments for Raspberry Pi Pico W
SPI_CLK_PIN = 6   # GP6 for SPI0 SCK
SPI_MOSI_PIN = 7  # GP7 for SPI0 MOSI
LOAD_PIN = 8      # GP8 for LOAD (GPIO)
LED_ENABLE_PIN = 9  # GP9 for LED driver output-enable

# LED enable - low to enable the LED driver outputs for testing
led_enable = Pin(LED_ENABLE_PIN, Pin.OUT)
led_enable.value(0)

# Second SPI port pins (SPI1)
SPI1_SCK_PIN = 10   # GP10 for SPI1 SCK
SPI1_MOSI_PIN = 11  # GP11 for SPI1 MOSI
SPI1_MISO_PIN = 12  # GP13 for SPI1 MISO
SPI1_LD = 13
SPI1_load_Pin = Pin(SPI1_LD, Pin.OUT)

# Initialize SPI0
spi = SPI(0, baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI_CLK_PIN), mosi=Pin(SPI_MOSI_PIN))

# Initialize LOAD pin
load = Pin(LOAD_PIN, Pin.OUT)
load.value(0)

# ---- Board variant (2player vs 4player) ----
# Same GPIO14 strap main.py's detect_hardware_version() reads: LOW=2player,
# HIGH=4player. The 2player board has 2 shift registers (5 bits each, one
# per player) followed by a 3rd register driving the 7-segment digit (all
# 8 bits used). The 4player board has 4 player registers (5 bits each)
# followed by the same kind of digit register -- one extra register, same
# per-register layout.
HW_VERSION_PIN = Pin(14, Pin.IN)

def _detect_num_players(checks=10, interval_ms=5):
    """Read GPIO14 until stable across `checks` consecutive reads."""
    last = HW_VERSION_PIN.value()
    stable_count = 1
    while stable_count < checks:
        time.sleep_ms(interval_ms)
        current = HW_VERSION_PIN.value()
        if current == last:
            stable_count += 1
        else:
            last = current
            stable_count = 1
    return 4 if last else 2

NUM_PLAYERS = _detect_num_players()
NUM_SHIFT_BYTES = NUM_PLAYERS + 1  # one register per player + one for the 7-seg digit
ALL_BITS_MASK = (1 << (NUM_SHIFT_BYTES * 8)) - 1
print(f"HWTEST: detected {NUM_PLAYERS}-player board ({NUM_SHIFT_BYTES} shift registers)")

# Game Over and Aux LEDs live on the player-2 shift register, bits 6/7.
# P2's byte always sits at bit-offset 8 within the full frame (see
# build_frame()), so within the frame these land at bits 14/15 -- same
# physical register on both board variants, independent of NUM_PLAYERS.
GAME_OVER_BIT = 1 << 6
AUX_BIT = 1 << 7
GAME_OVER_FRAME_BIT = GAME_OVER_BIT << 8  # bit 14 of the full frame
AUX_FRAME_BIT = AUX_BIT << 8              # bit 15 of the full frame


# Configure PWM on GPIO18 ("HI") and GPIO19 ("LOW")
HI = PWM(Pin(19))
LOW = PWM(Pin(18))

# Set frequency (for example, 1kHz)
HI.freq(1000)
LOW.freq(1000)

# Set duty cycles (range is 0-65535 in MicroPython)
HI.duty_u16(int(65535 * 0.8))   # 80% duty cycle
LOW.duty_u16(int(65535 * 0.2))  # 20% duty cycle

# Helper function to reverse bits in a 16-bit integer
def reverse_bits_16(x):
    x = ((x & 0xAAAA) >> 1) | ((x & 0x5555) << 1)
    x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2)
    x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4)
    x = ((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)
    return x

HISTORY_LENGTH = 6  # Number of history values to use for stability check

# Timer callback to read SPI1, reverse bits, and print lower 5 bits only if value changes
last_lower_5 = None  # global variable to track last value
score = 0
last_bits = 0  # Track previous lower_5 bits
stable_lower_5 = 0
scoreDig = bytearray([0] * 8)  # hold score as array of byte with each digit in its own byte, initialized to all 0s
low_counts = [100, 100, 100, 100, 100, 100, 100, 100]  # initialize low_counts to 100 for each element

roll1 = 0
roll2 = 0

#diag
lsb_pin = Pin(0, Pin.OUT)
next_pin = Pin(1, Pin.OUT)

# Buffer for SPI1 16-bit values
spi1_buffer = []




def setup_spi1():
    # Initialize SPI1 (no output clock, just reading 16-bit words from MISO)
    spi1 = SPI(1, baudrate=1000000, polarity=0, phase=0,
        sck=Pin(SPI1_SCK_PIN), mosi=Pin(SPI1_MOSI_PIN), miso=Pin(SPI1_MISO_PIN))
    
    return spi1
    
# Set up a timer to call the callback at 1kHz (every 1ms)
#spi1_timer = Timer()
#spi1_timer.init(freq=1000, mode=Timer.PERIODIC, callback=spi1_timer_callback)

def spi1_timer_callback(timer):
    global spi1_buffer
    SPI1_load_Pin.value(1)
    time.sleep_us(2)
    buf = bytearray(2)
    spi1.readinto(buf)
    SPI1_load_Pin.value(0)
    value = int.from_bytes(buf, 'big')
    spi1_buffer.append(value)





import rp2
from machine import Pin
import machine



# Fetch samples from PIO buffer
spi1_buffer = []
def fetch_pio_samples():
    while sm.rx_fifo() > 0:
        value = sm.get() & 0xFFFF
        print("pio samnple=",value)
        spi1_buffer.append(value)


def process_spi1_buffer():
    global spi1_buffer, last_lower_5, score, last_bits, roll1, roll2
    global lsb_pin, stable_lower_5, scoreDig, low_counts

    while spi1_buffer:

    



        value = spi1_buffer.pop(0)
        reversed_value = reverse_bits_16(value)
        lower_5 = reversed_value & 0x1F  # Only 5 bits

        #from here down 190uS

        # keep a count for each bit. each counter init to 100
        for bit in range(5):
            bit_val = (lower_5 >> bit) & 1
            if bit_val == 1:
                if 100 <= low_counts[bit]:
                    if low_counts[bit]<200:
                        low_counts[bit] += 1                    
                else:
                    low_counts[bit] = 100
            # If bit is 0
            else:
                if low_counts[bit] <= 100:
                    if low_counts[bit] > 0:
                        low_counts[bit] -= 1                
                else:
                    low_counts[bit] = 100

        LOW_THRES=2
        HIGH_THRES=18
        for bit in range(5):
            if low_counts[bit] < (100-LOW_THRES):
                stable_lower_5 &= ~(1 << bit)
            if low_counts[bit] > (100+HIGH_THRES):
                stable_lower_5 |= (1 << bit)

        # Output the LSB of stable_lower_5 to GPIO#1 - DIAG
        lsb_pin.value (stable_lower_5 & 0x01)
        next_pin.value((stable_lower_5 >> 2) & 0x01)

        for i in range(5):
            mask = 1 << i
            if (stable_lower_5 & mask)==0 and  (last_bits & mask)!=0:    
                if scoreDig[i] == 9:
                    scoreDig[i] = 0               
                else:
                    scoreDig[i] += 1     
        last_bits = stable_lower_5 

        #roll over to correct lesser digits
        if (stable_lower_5 & 0x03) == 0:  #both LOW
            roll1 +=1
            if roll1 > 7:
                if scoreDig[0]!=0:
                    print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%10")    
                    scoreDig[0]=0
                roll1=0
        else:        
            roll1=0

        SCORE_MULT=10
        if stable_lower_5 != last_lower_5:
            score = scoreDig[0]*1 + scoreDig[1]*10 + scoreDig[2]*100 + scoreDig[3]*1000
            score = score * SCORE_MULT
            print(f"{stable_lower_5:05b}  Score: {score}")
            last_lower_5 = stable_lower_5



def send_led_data(data):
    """
    Send data to the LED driver shift-register chain via SPI0 and pulse LOAD.
    Frame width adapts to the detected board: NUM_SHIFT_BYTES bytes (3 for
    2player, 5 for 4player). Build the value with build_frame() rather than
    hand-packing bytes so patterns stay correct across both board variants.
    :param data: integer to send, MSB first
    """
    buf = data.to_bytes(NUM_SHIFT_BYTES, 'big')
    spi.write(buf)
    # Pulse LOAD pin
    load.value(1)
    time.sleep_us(100)
    load.value(0)


def build_frame(digit_code=0, player_bits=None):
    """
    Build the MSB-first shift-register frame value for send_led_data().

    Chain wiring, closest to the Pico's MOSI first: P1[5 bits] register ->
    P2[5 bits] register -> ... -> Pn[5 bits] register -> 7-segment[8 bits]
    register (last in the chain). Because whatever is shifted in first ends
    up furthest down the chain once LOAD latches, the frame must be sent
    digit-byte first, followed by player bytes in reverse (Pn .. P1) order.

    digit_code: 8-bit 7-segment code (all bits significant)
    player_bits: list of NUM_PLAYERS ints in player order [P1, P2, ...];
                 only the low 5 bits of each are wired. Defaults to all off.
    """
    if player_bits is None:
        player_bits = [0] * NUM_PLAYERS
    frame = digit_code & 0xFF
    for p in reversed(player_bits):
        frame = (frame << 8) | (p & 0xFF)
    return frame


def blink_all_leds_test(cycles=3, interval_s=1.0):
    """
    Diagnostic: drive all SPI output bits low, then all high, alternating
    every `interval_s` seconds, `cycles` times. Frame width adapts to the
    detected 2player/4player board via ALL_BITS_MASK.
    """
    print(f"Running all-outputs blink test: {cycles} cycle(s) at {interval_s}s ({NUM_PLAYERS}-player board)")
    for _ in range(cycles):
        send_led_data(0)
        time.sleep(interval_s)
        send_led_data(ALL_BITS_MASK)
        time.sleep(interval_s)
    # all off when done
    send_led_data(0)
    print("All-outputs blink test complete.")


def slow_pattern():
    """
    Send some slow patterns to the LEDs: walk a single lit LED through each
    player's 5 bits in turn (cycling the 7-seg digit along with it), then
    finish with Game Over and Aux. Adapts to the detected 2player/4player
    board via NUM_PLAYERS.
    """
    SEGMENTS = [
        0x3F,  # 0
        0x06,  # 1
        0x5B,  # 2
        0x4F,  # 3
        0x66,  # 4
        0x6D,  # 5
        0x7D,  # 6
        0x07,  # 7
        0x7F,  # 8
        0x6F,  # 9
    ]
    SEG_g = 0x80  # decimal point (Game Over)
    SEG_A = 0x77  # 'A' (Aux)

    patterns = []
    for player in range(NUM_PLAYERS):
        for bit in range(5):
            digit = (player * 5 + bit) % 10
            player_bits = [0] * NUM_PLAYERS
            player_bits[player] = 1 << bit
            patterns.append(build_frame(SEGMENTS[digit], player_bits))

    game_over_bits = [0] * NUM_PLAYERS
    game_over_bits[1] = GAME_OVER_BIT
    patterns.append(build_frame(SEG_g, game_over_bits))

    aux_bits = [0] * NUM_PLAYERS
    aux_bits[1] = AUX_BIT
    patterns.append(build_frame(SEG_A, aux_bits))

    while True:
        for pat in patterns:
            send_led_data(pat)
            #print(pat)
            time.sleep(1.2)

def sensor_read_loop():
    """
    Continuously read raw sensor data over SPI1 and print it: the raw value
    in hex, followed by a 5-bit binary field per player (channel bits are
    byte-aligned per player, low 5 bits of each byte). Also mirrors the
    read value out to the LEDs via send_led_data() for a visual check.

    The sensor board has a hardware inversion built into part of the chain:
      - 2player board: 16-bit read (2 bytes); MSByte (1st byte) inverted.
      - 4player board: 32-bit read (4 bytes); 1st and 3rd bytes inverted.
    Adapts automatically based on NUM_PLAYERS (detected from GPIO14).
    """
    nbytes = 4 if NUM_PLAYERS == 4 else 2
    hex_width = nbytes * 2

    spi1 = setup_spi1()

    print(f"Sensor Read Loop: {NUM_PLAYERS}-player board, {nbytes}-byte reads. Press Ctrl+C to stop.")
    while True:
        SPI1_load_Pin.value(1)
        time.sleep_us(100)

        buf = bytearray(nbytes)
        spi1.readinto(buf)
        time.sleep_us(100)
        SPI1_load_Pin.value(0)

        if nbytes == 2:
            buf[0] = ~buf[0] & 0xFF  # MSByte inverted (hardware inversion)
        else:
            buf[0] = ~buf[0] & 0xFF  # 1st byte inverted
            buf[2] = ~buf[2] & 0xFF  # 3rd byte inverted

        value = int.from_bytes(buf, 'big')

        fields = " ".join(
            f"P{p + 1}: {(value >> (8 * p)) & 0x1F:05b}" for p in range(NUM_PLAYERS)
        )
        print(f"RAW: 0x{value:0{hex_width}X}  {fields}")

        # Sensor bits can alias onto the Game Over/Aux LED positions; force
        # those off when mirroring raw sensor data to the LEDs.
        send_led_data(value & (0xFFFFFFFF ^ GAME_OVER_FRAME_BIT ^ AUX_FRAME_BIT))
        time.sleep(1)

def test_switches():
    up_pin = Pin(28, Pin.IN, Pin.PULL_UP)
    down_pin = Pin(27, Pin.IN, Pin.PULL_UP)
    wifi_pin = Pin(22, Pin.IN, Pin.PULL_UP)
    led_pin = Pin(26, Pin.OUT)

   
    global end_game
    endgame_lastval = end_game.value()

    print("Testing switches on GPIO 28 (UP), 27 (DOWN), 22 (WIFI), 21 (START), 20 (END GAME)")
    while True:
        if up_pin.value() == 0:
            print("UP")
        if down_pin.value() == 0:
            print("DOWN")
        if wifi_pin.value() == 0:
            print("WIFI")
            led_pin.value(0)  # Actively pull LED low (turn on)
        else:
            led_pin.value(1)  # Turn LED off (high)
        #if start_button.value() == 1:
        #    print("Game_Over_")
        if end_game.value() != endgame_lastval:
            print("END GAME State Change, now=",end_game.value())
            endgame_lastval = end_game.value()
        time.sleep(0.2)

def pwm_ramp_test():
    """
    Ramps HI and LOW PWM outputs from 0% to 100% duty cycle over 6 seconds.
    """
    steps = 100
    delay = 6 / steps  # 6 seconds total ramp time

    while True:
        # Ramp up
        for i in range(steps + 1):
            duty = int(65535 * (i / steps))
            HI.duty_u16(duty)
            LOW.duty_u16(duty)
            time.sleep(delay)
        # Ramp down
        for i in range(steps, -1, -1):
            duty = int(65535 * (i / steps))
            HI.duty_u16(duty)
            LOW.duty_u16(duty)
            time.sleep(delay)

def calibrate_pwm_hi_low():
    """
    Calibrate HI and LOW PWM outputs separately.
    First, HI ramps down from 100% to 0% with LOW fixed at 0%.
    Then, LOW ramps up from 0% to 100% with HI fixed at 100%.
    As PWM changes, read SPI1 16-bit input; when the LSB changes, that
    marks the found threshold duty for HI or LOW. Prints a live status
    line with the current PWM values while each ramp runs, then a
    formatted summary of the calibration results at the end.
    """
    steps = 100
    delay = 20 / steps  # ~20 seconds for full travel

    spi1 = setup_spi1()

    def pct(duty):
        return duty / 65535 * 100

    # P1 always ends up in the least-significant byte of the assembled
    # value (see build_frame()/sensor_read_loop()), so bit 0 is always
    # Player 1 channel 0 (sensor 1) -- on BOTH board variants -- as long as
    # the full frame width is read and the matching hardware inversion is
    # undone. A fixed 2-byte read on a 4player board would instead capture
    # P4/P3 (the first bytes shifted out), never reaching P1 at all.
    read_nbytes = 4 if NUM_PLAYERS == 4 else 2

    def read_lsb():
        SPI1_load_Pin.value(1)
        time.sleep_us(2)
        buf = bytearray(read_nbytes)
        spi1.readinto(buf)
        SPI1_load_Pin.value(0)

        if read_nbytes == 2:
            buf[0] = ~buf[0] & 0xFF  # MSByte inverted (hardware inversion)
        else:
            buf[0] = ~buf[0] & 0xFF  # 1st byte inverted
            buf[2] = ~buf[2] & 0xFF  # 3rd byte inverted

        value = int.from_bytes(buf, 'big')
        return value & 0x01  # Player 1, channel 0 (sensor 1)

    print("\n=== PWM HI/LOW Calibration ===")
    print("\n=Uses sensor 1 of player 1 - sensor must be plugged in=")

    # --- HI calibration ---
    print("\n-- HI ramp: 100% -> 0% (LOW fixed at 0%) --")
    last_lsb = None
    hi_duty_found = None
    HI.duty_u16(65535)
    LOW.duty_u16(0)
    time.sleep(1)
    for i in range(steps + 1):
        hi_duty = int(65535 * (1 - i / steps))
        HI.duty_u16(hi_duty)

        lsb = read_lsb()
        print(f"\r  HI: {hi_duty:5d} ({pct(hi_duty):5.1f}%)  LOW: {0:5d} (  0.0%)  P1 S1: {lsb}", end='')

        if last_lsb is not None and lsb != last_lsb and hi_duty_found is None:
            hi_duty_found = hi_duty
            print(f"\n  -> HI threshold found at duty {hi_duty} ({pct(hi_duty):.1f}%)")
            break
        last_lsb = lsb
        time.sleep(delay)
    print()

    # --- LOW calibration ---
    print("\n-- LOW ramp: 0% -> 100% (HI fixed at 100%) --")
    last_lsb = None
    low_duty_found = None
    HI.duty_u16(65535)
    time.sleep(2)
    for i in range(steps + 1):
        low_duty = int(65535 * (i / steps))
        LOW.duty_u16(low_duty)

        lsb = read_lsb()
        print(f"\r  HI: {65535:5d} (100.0%)  LOW: {low_duty:5d} ({pct(low_duty):5.1f}%)  P1 S1: {lsb}", end='')

        if last_lsb is not None and lsb != last_lsb and low_duty_found is None:
            low_duty_found = low_duty
            print(f"\n  -> LOW threshold found at duty {low_duty} ({pct(low_duty):.1f}%)")
            break
        last_lsb = lsb
        time.sleep(delay)
    print()

    # Set HI and LOW to discovered value +/-10%
    hi_final = None
    low_final = None
    if hi_duty_found is not None:
        hi_final = min(int(hi_duty_found * 1.1), 65535)
        HI.duty_u16(hi_final)
    if low_duty_found is not None:
        low_final = min(int(low_duty_found * 0.9), 65535)
        LOW.duty_u16(low_final)

    print("\n=== Calibration Results ===")
    hi_found_str = f"{hi_duty_found} ({pct(hi_duty_found):.1f}%)" if hi_duty_found is not None else "NOT FOUND"
    low_found_str = f"{low_duty_found} ({pct(low_duty_found):.1f}%)" if low_duty_found is not None else "NOT FOUND"
    print(f"  HI  threshold found: {hi_found_str}")
    print(f"  LOW threshold found: {low_found_str}")
    if hi_final is not None:
        print(f"  HI  PWM set to:      {hi_final} ({pct(hi_final):.1f}%)")
    if low_final is not None:
        print(f"  LOW PWM set to:      {low_final} ({pct(low_final):.1f}%)")
    print("Calibration complete.\n")


def hardware_spi0_eeprom_test():
    """
    Assign SPI0 to GPIO 2/3/4/5 and test read/write to an attached EEPROM chip.
    GP2 = SCK (clock), GP3 = MOSI (tx), GP4 = MISO (rx), GP5 = CS (chip select).
    This example reads the first byte from a 25LC256/25AA256 EEPROM.
    """
    from machine import SPI, Pin
    import time

    # Assign pins
    SCK = 2
    MOSI = 3
    MISO = 4
    CS = 5

    OPCODE_WREN = 0x06  # set write enable latch
    OPCODE_WRDI = 0x04  # write disable              <<clears WEL
    OPCODE_RDSR = 0x05  # read status register
    OPCODE_WRSR = 0x01  # write status register      <<clears WEL
    OPCODE_READ = 0x03  # read memory
    OPCODE_WRITE = 0x02  # write memory               <<clears WEL
    STATUS_REG_VAL = 0x82  # wrill write this val i

    # Set up SPI0
    spi = SPI(0, baudrate=600000, polarity=1, phase=1, sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
    cs = Pin(CS, Pin.OUT)
    cs.value(1)  # Deselect EEPROM


    # FRAM write just one byte cmd
    def reg_cmd(spi, cs, reg):
        msg = bytearray()
        msg.append(0x00 | reg)
        cs.value(0)
        spi.write(msg)
        cs.value(1)


    # FRAM write one byte to one register location
    def reg_write(spi, cs, reg, data):
        msg = bytearray()
        msg.append(0x00 | reg)
        msg.append(data)
        cs.value(0)
        spi.write(msg)  # blocking
        cs.value(1)


    # FRAM
    def mem_write(spi, cs, address, data):
        # Enable write operations
        reg_cmd(spi, cs, OPCODE_WREN)

        # Split data into chunks of 16 bytes
        chunk_size = 16
        for i in range(0, len(data), chunk_size):
            # print("x",i)
            chunk = data[i : i + chunk_size]
            print(chunk)
            reg_cmd(spi, cs, OPCODE_WREN)

            msg = bytearray()
            msg.append(0x00 | OPCODE_WRITE)
            msg.append((address & 0xFF00) >> 8)
            msg.append(address & 0x00FF)
            msg.extend(chunk)

            cs.value(0)
            spi.write(msg)
            cs.value(1)
            address += chunk_size


    # FRAM
    def write(address, data):
        mem_write(spi, cs, address, data)


    # FRAM
    def mem_read(spi, cs, address, nbytes):
        data = bytearray()
        chunk_size = 16
        offset = 0

        while offset < nbytes:
            remaining = nbytes - offset
            read_size = min(chunk_size, remaining)

            # Prepare the message
            msg = bytearray()
            msg.append(OPCODE_READ)
            msg.append((address & 0xFF00) >> 8)
            msg.append(address & 0x00FF)

            # Send the message and read the data
            cs.value(0)
            spi.write(msg)
            data.extend(spi.read(read_size))
            cs.value(1)

            # Update the address and offset for the next chunk
            address += chunk_size
            offset += chunk_size
        return data


    # FRAM
    def read(address, nbytes):
        return mem_read(spi, cs, address, nbytes)


    # Alternate between two complementary patterns (0xA5/0x5A) each run,
    # based on what's currently stored -- no random source needed, and the
    # bit-inverted pair is good at catching stuck-at bits.
    test_len = 16
    pattern_a = bytearray([0xA5] * test_len)
    pattern_b = bytearray([0x5A] * test_len)
    current = mem_read(spi, cs, 0, 1)
    pattern = pattern_b if current[0] == pattern_a[0] else pattern_a

    print(f"Writing {test_len}-byte pattern 0x{pattern[0]:02X} to EEPROM address 0x0000...")
    mem_write(spi, cs, 0, pattern)
    print("Reading back from EEPROM address 0x0000...")
    readback = mem_read(spi, cs, 0, test_len)
    print("Readback:", list(readback))

    if bytes(readback) == bytes(pattern):
        print("FRAM TEST PASSED: readback matches written pattern.")
    else:
        print("FRAM TEST FAILED: readback does not match written pattern.")
        for i, (w, r) in enumerate(zip(pattern, readback)):
            if w != r:
                print(f"  byte {i}: wrote 0x{w:02X}, read 0x{r:02X}")

    # Clean up
    spi.deinit()
    cs.value(1)


def main():
    global score, scoreDig

    # Quick visual sanity check on power-up: all outputs off/on, 3 times,
    # before dropping into the test menu.

    blink_all_leds_test(cycles=3, interval_s=1.0)

    def menu():
        print("\nSelect a test:")
        print("1 - Test Switches")
        print("2 - Calibrate PWM HI/LOW")
        print("3 - PWM Ramp Test")
        print("4 - Slow LED Pattern")
        print("5 - Sensor Read Loop")
        print("6 - FRAM")
        print("7 - Blink All LEDs Test")
        print("0 - Exit")
        return input("Enter choice: ")

    while True:
        choice = menu()
        if choice == '1':
            print("Running Test Switches. Press Ctrl+C to stop.")
            try:
                test_switches()
            except KeyboardInterrupt:
                print("\nTest Switches stopped.")
        elif choice == '2':

            #import SensorReader
            #sensor = SensorReader()
            #d = sensor.pull_sensor_value()
            #print("  0x{:04X}".format(d))

            print("Running Calibrate PWM HI/LOW. Press Enter to continue after calibration.")
            calibrate_pwm_hi_low()

        elif choice == '3':
            print("Running PWM Ramp Test. Press Ctrl+C to stop.")
            try:
                pwm_ramp_test()
            except KeyboardInterrupt:
                print("\nPWM Ramp Test stopped.")
        elif choice == '4':
            print("Running Slow LED Pattern. Press Ctrl+C to stop.")
            try:
                slow_pattern()
            except KeyboardInterrupt:
                print("\nSlow LED Pattern stopped.")
        elif choice == '5':
            print("Running Sensor Read Loop. Press Ctrl+C to stop.")
            try:
                sensor_read_loop()
            except KeyboardInterrupt:
                print("\nSensor Read Loop stopped.")



        elif choice == '6':
            print("Running SPI0 EEPROM Hardware Test. Press Enter to return to menu.")
            hardware_spi0_eeprom_test()
            input("Press Enter to return to menu...")

        elif choice == '7':
            print("Running Blink All LEDs Test.")
            blink_all_leds_test(cycles=3, interval_s=1.0)

        elif choice == '0':
            print("Exiting.")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
