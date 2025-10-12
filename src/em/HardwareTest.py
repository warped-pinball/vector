import time

from machine import PWM, SPI, Pin, Timer

end_game = Pin(15, Pin.OUT)

import sensorRead

sensorRead.initialize()

# Pin assignments for Raspberry Pi Pico W
SPI_CLK_PIN = 6  # GP6 for SPI0 SCK
SPI_MOSI_PIN = 7  # GP7 for SPI0 MOSI
LOAD_PIN = 8  # GP8 for LOAD (GPIO)

# Second SPI port pins (SPI1)
SPI1_SCK_PIN = 10  # GP10 for SPI1 SCK
SPI1_MOSI_PIN = 11  # GP11 for SPI1 MOSI
SPI1_MISO_PIN = 12  # GP13 for SPI1 MISO
SPI1_LD = 13
SPI1_load_Pin = Pin(SPI1_LD, Pin.OUT)

# Initialize SPI0
spi = SPI(0, baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI_CLK_PIN), mosi=Pin(SPI_MOSI_PIN))

# Initialize LOAD pin
load = Pin(LOAD_PIN, Pin.OUT)
load.value(0)


# Configure PWM on GPIO18 ("HI") and GPIO19 ("LOW")
HI = PWM(Pin(19))
LOW = PWM(Pin(18))

# Set frequency (for example, 1kHz)
HI.freq(1000)
LOW.freq(1000)

# Set duty cycles (range is 0-65535 in MicroPython)
HI.duty_u16(int(65535 * 0.8))  # 80% duty cycle
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

# diag
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
# spi1_timer = Timer()
# spi1_timer.init(freq=1000, mode=Timer.PERIODIC, callback=spi1_timer_callback)


def spi1_timer_callback(timer):
    global spi1_buffer
    SPI1_load_Pin.value(1)
    time.sleep_us(2)
    buf = bytearray(2)
    spi1.readinto(buf)
    SPI1_load_Pin.value(0)
    value = int.from_bytes(buf, "big")
    spi1_buffer.append(value)


import machine
import rp2
from machine import Pin

# Fetch samples from PIO buffer
spi1_buffer = []


def fetch_pio_samples():
    while sm.rx_fifo() > 0:
        value = sm.get() & 0xFFFF
        print("pio samnple=", value)
        spi1_buffer.append(value)


def process_spi1_buffer():
    global spi1_buffer, last_lower_5, score, last_bits, roll1, roll2
    global lsb_pin, stable_lower_5, scoreDig, low_counts

    while spi1_buffer:
        value = spi1_buffer.pop(0)
        reversed_value = reverse_bits_16(value)
        lower_5 = reversed_value & 0x1F  # Only 5 bits

        # from here down 190uS

        # keep a count for each bit. each counter init to 100
        for bit in range(5):
            bit_val = (lower_5 >> bit) & 1
            if bit_val == 1:
                if 100 <= low_counts[bit]:
                    if low_counts[bit] < 200:
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

        LOW_THRES = 2
        HIGH_THRES = 18
        for bit in range(5):
            if low_counts[bit] < (100 - LOW_THRES):
                stable_lower_5 &= ~(1 << bit)
            if low_counts[bit] > (100 + HIGH_THRES):
                stable_lower_5 |= 1 << bit

        # Output the LSB of stable_lower_5 to GPIO#1 - DIAG
        lsb_pin.value(stable_lower_5 & 0x01)
        next_pin.value((stable_lower_5 >> 2) & 0x01)

        for i in range(5):
            mask = 1 << i
            if (stable_lower_5 & mask) == 0 and (last_bits & mask) != 0:
                if scoreDig[i] == 9:
                    scoreDig[i] = 0
                else:
                    scoreDig[i] += 1
        last_bits = stable_lower_5

        # roll over to correct lesser digits
        if (stable_lower_5 & 0x03) == 0:  # both LOW
            roll1 += 1
            if roll1 > 7:
                if scoreDig[0] != 0:
                    print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%10")
                    scoreDig[0] = 0
                roll1 = 0
        else:
            roll1 = 0

        SCORE_MULT = 10
        if stable_lower_5 != last_lower_5:
            score = scoreDig[0] * 1 + scoreDig[1] * 10 + scoreDig[2] * 100 + scoreDig[3] * 1000
            score = score * SCORE_MULT
            print(f"{stable_lower_5:05b}  Score: {score}")
            last_lower_5 = stable_lower_5


def send_led_data(data):
    """
    Send 16 bits of data to the LED driver via SPI0 and pulse the LOAD pin.
    :param data: 16-bit integer to send
    """
    # Convert to 2 bytes, MSB first
    buf = data.to_bytes(3, "big")
    spi.write(buf)
    # Pulse LOAD pin
    load.value(1)
    time.sleep_us(100)
    load.value(0)


def slow_pattern():
    """
    Send some slow patterns to the LEDs.
    """

    # Initialize SPI0
    spi = SPI(0, baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI_CLK_PIN), mosi=Pin(SPI_MOSI_PIN))

    # Initialize LOAD pin
    load = Pin(LOAD_PIN, Pin.OUT)
    load.value(0)

    # Initialize SPI1 (no output clock, just reading 16-bit words from MISO)
    spi1 = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI1_SCK_PIN), mosi=Pin(SPI1_MOSI_PIN), miso=Pin(SPI1_MISO_PIN))

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

    patterns = [
        (SEGMENTS[0] << 16) | 0x0001,
        (SEGMENTS[1] << 16) | 0x0002,
        (SEGMENTS[2] << 16) | 0x0004,
        (SEGMENTS[3] << 16) | 0x0008,
        (SEGMENTS[4] << 16) | 0x0010,
        (SEGMENTS[5] << 16) | 0x0020,
        (SEGMENTS[6] << 16) | 0x0040,
        (SEGMENTS[7] << 16) | 0x0080,
        (SEGMENTS[8] << 16) | 0x0100,
        (SEGMENTS[9] << 16) | 0x0200,
        (SEGMENTS[0] << 16) | 0x800400,
        (SEGMENTS[1] << 16) | 0x800800,
        (SEGMENTS[2] << 16) | 0x801000,
        (SEGMENTS[3] << 16) | 0x802000,
        (SEGMENTS[4] << 16) | 0x804000,
        (SEGMENTS[5] << 16) | 0x808000,
        (SEGMENTS[6] << 16) | 0x80FFFF,
        (SEGMENTS[7] << 16) | 0x800000,
    ]

    while True:
        for pat in patterns:
            send_led_data(pat)
            # print(pat)
            time.sleep(1.2)


def read_spi1_16bit_loop():
    # Initialize SPI0
    spi = SPI(0, baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI_CLK_PIN), mosi=Pin(SPI_MOSI_PIN))
    # Initialize LOAD pin
    load = Pin(LOAD_PIN, Pin.OUT)
    load.value(0)
    # Initialize SPI1 (no output clock, just reading 16-bit words from MISO)
    spi1 = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(SPI1_SCK_PIN), mosi=Pin(SPI1_MOSI_PIN), miso=Pin(SPI1_MISO_PIN))

    spi1 = setup_spi1()
    while True:
        SPI1_load_Pin.value(1)
        time.sleep_us(100)

        # Read 2 bytes (16 bits) from SPI1
        buf = bytearray(2)
        spi1.readinto(buf)
        # print("b->  ",buf)
        time.sleep_us(100)
        SPI1_load_Pin.value(0)

        buf[0] = ~buf[0] & 0xFF  # invert only MSB, mask to 8 bits
        value = int.from_bytes(buf, "big")
        print(f"Inverted MSB only SPI read: 0x{value:04X}")

        # value = int.from_bytes(buf, 'big')
        # print(f"SPI1 read: 0x{value:04X}")
        send_led_data(value)
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
        # if start_button.value() == 1:
        #    print("Game_Over_")
        if end_game.value() != endgame_lastval:
            print("END GAME State Change, now=", end_game.value())
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
    As PWM changes, read SPI1 16-bit input. When the LSB changes, print the duty for HI or LOW.
    At the end, set HI to discovered value +5% and LOW to discovered value +5%.
    """
    steps = 100
    delay = 20 / steps  # ~20 seconds for full travel

    spi1 = setup_spi1()

    # --- HI calibration ---
    print("Starting HI calibration (LOW fixed at 0%)")
    last_lsb = None
    hi_found = False
    hi_duty_found = None
    HI.duty_u16(65535)
    LOW.duty_u16(0)
    time.sleep(1)
    for i in range(steps + 1):
        hi_duty = int(65535 * (1 - i / steps))
        HI.duty_u16(hi_duty)
        print(".", end="")

        # Read SPI1 16-bit value
        SPI1_load_Pin.value(1)
        time.sleep_us(2)
        buf = bytearray(2)
        spi1.readinto(buf)
        SPI1_load_Pin.value(0)
        value = int.from_bytes(buf, "big")
        # reversed_value = reverse_bits_16(value)
        # lsb = reversed_value & 0x01
        lsb = value & 0x01

        if last_lsb is not None and lsb != last_lsb and not hi_found:
            print(f"HI calibration found at duty: {hi_duty} ({hi_duty/65535:.2%})")
            hi_duty_found = hi_duty
            hi_found = True
            break
        last_lsb = lsb
        time.sleep(delay)

    # --- LOW calibration ---
    print("Starting LOW calibration (HI fixed at 100%)")
    last_lsb = None
    low_found = False
    low_duty_found = None
    HI.duty_u16(65535)
    time.sleep(2)
    for i in range(steps + 1):
        low_duty = int(65535 * (i / steps))
        LOW.duty_u16(low_duty)

        print(".", end="")

        # Read SPI1 16-bit value
        SPI1_load_Pin.value(1)
        time.sleep_us(2)
        buf = bytearray(2)
        spi1.readinto(buf)
        SPI1_load_Pin.value(0)
        value = int.from_bytes(buf, "big")
        # reversed_value = reverse_bits_16(value)
        # lsb = reversed_value & 0x01
        lsb = value & 0x01

        if last_lsb is not None and lsb != last_lsb and not low_found:
            print(f"LOW calibration found at duty: {low_duty} ({low_duty/65535:.2%})")
            low_duty_found = low_duty
            low_found = True
            break
        last_lsb = lsb
        time.sleep(delay)

    # Set HI and LOW to discovered value +5%
    if hi_duty_found is not None:
        hi_plus_5 = min(int(hi_duty_found * 1.1), 65535)
        HI.duty_u16(hi_plus_5)
        print(f"HI PWM set to {hi_plus_5} ({hi_plus_5/65535:.2%})")
    if low_duty_found is not None:
        low_plus_5 = min(int(low_duty_found * 0.9), 65535)
        LOW.duty_u16(low_plus_5)
        print(f"LOW PWM set to {low_plus_5} ({low_plus_5/65535:.2%})")

    print("Calibration complete. HI and LOW duties are now set.")


def hardware_spi0_eeprom_test():
    """
    Assign SPI0 to GPIO 2/3/4/5 and test read/write to an attached EEPROM chip.
    GP2 = SCK (clock), GP3 = MOSI (tx), GP4 = MISO (rx), GP5 = CS (chip select).
    This example reads the first byte from a 25LC256/25AA256 EEPROM.
    """
    import time

    from machine import SPI, Pin

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

    # Example: Write then read address 0x0000
    print("Writing 0xA5 to EEPROM address 0x0000...")
    data = [1, 2, 3]
    mem_write(spi, cs, 0, data)
    print("Reading from EEPROM address 0x0000...")
    value = mem_read(spi, cs, 0, 4)
    print("EEPROM[0] =", value)

    # Clean up
    spi.deinit()
    cs.value(1)


def main():
    global score, scoreDig

    def menu():
        print("\nSelect a test:")
        print("1 - Test Switches")
        print("2 - Calibrate PWM HI/LOW")
        print("3 - PWM Ramp Test")
        print("4 - Slow LED Pattern")
        print("5 - SPI1 16-bit Read Loop")
        print("6 - FRAM")
        print("0 - Exit")
        return input("Enter choice: ")

    while True:
        choice = menu()
        if choice == "1":
            print("Running Test Switches. Press Ctrl+C to stop.")
            try:
                test_switches()
            except KeyboardInterrupt:
                print("\nTest Switches stopped.")
        elif choice == "2":
            # import SensorReader
            # sensor = SensorReader()
            # d = sensor.pull_sensor_value()
            # print("  0x{:04X}".format(d))

            print("Running Calibrate PWM HI/LOW. Press Enter to continue after calibration.")
            calibrate_pwm_hi_low()

        elif choice == "3":
            print("Running PWM Ramp Test. Press Ctrl+C to stop.")
            try:
                pwm_ramp_test()
            except KeyboardInterrupt:
                print("\nPWM Ramp Test stopped.")
        elif choice == "4":
            print("Running Slow LED Pattern. Press Ctrl+C to stop.")
            try:
                slow_pattern()
            except KeyboardInterrupt:
                print("\nSlow LED Pattern stopped.")
        elif choice == "5":
            print("Running SPI1 16-bit Read Loop. Press Ctrl+C to stop.")
            try:
                read_spi1_16bit_loop()
            except KeyboardInterrupt:
                print("\nSPI1 16-bit Read Loop stopped.")

        elif choice == "6":
            print("Running SPI0 EEPROM Hardware Test. Press Enter to return to menu.")
            hardware_spi0_eeprom_test()
            input("Press Enter to return to menu...")

        elif choice == "0":
            print("Exiting.")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
