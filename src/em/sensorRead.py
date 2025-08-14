import rp2
import machine

class SensorReader:
    '''
    Hall sensor read - from PIO over SPI
    '''
    machine.Pin(12, machine.Pin.IN)
    
    # Pin assignments
    PIO_MISO_PIN = 12  # MISO (data in)
    PIO_SCK_PIN  = 10  # SCK (clock out)
    PIO_CS_PIN   = 13  # CS (or Load...)

    @rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, set_init=rp2.PIO.OUT_HIGH, autopush=True, push_thresh=16)
    def spi_master_16bit():
        set(x, 15)                          #init first transfer bit length

        wrap_target()
        set(pins, 1)             [7]        #set load pin high

        label("bitloop")         
        nop()                    .side(1)   
        nop()                    .side(1)  [1]
        in_(pins, 1)             .side(0)  [1] #data in pin changes on rising edge of clock
        jmp(x_dec, "bitloop")    .side(0)

        set(pins, 0)             .side(0)
        set(x, 15)               .side(0) #bit length (-1)

        #Delay loop for pause between reads - set up for 1mS cycle
        set(y, 21)
        label("delay")
        nop()                   [1]
        jmp(y_dec, "delay") [7]

        nop()                    .side(0)   [3]
        wrap()

    def __init__(self, sm_id=4, freq=340000):
        self.sm = rp2.StateMachine(
            sm_id, SensorReader.spi_master_16bit, freq=freq,
            in_base=machine.Pin(SensorReader.PIO_MISO_PIN),
            sideset_base=machine.Pin(SensorReader.PIO_SCK_PIN),
            set_base=machine.Pin(SensorReader.PIO_CS_PIN)
        )
        self.sm.active(1)

    def pull_sensor_value(self):
        return self.sm.get()

if __name__ == "__main__":
    sensor = SensorReader()
    while True:
        d = sensor.pull_sensor_value()
        print("  0x{:04X}".format(d))




