import rp2
import machine
from machine import Timer





class SensorReader:
    '''
    Hall sensor read - from PIO over SPI
      manage analog calibration
    '''        
    # Pin assignments
    PIO_MISO_PIN = 12  
    PIO_SCK_PIN  = 10  
    PIO_CS_PIN   = 13  # CS (or Load...)
    ANALOG_HI_GPIO = 19
    ANALOG_LOW_GPIO = 18

    machine.Pin(12, machine.Pin.IN)
       
    @rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, set_init=rp2.PIO.OUT_HIGH, autopush=True, push_thresh=16 )
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

        in_(pins, 16) 

        #Delay loop for pause between reads - set up for 1mS cycle
        set(y, 21)
        label("delay")
        nop()                   [1]
        jmp(y_dec, "delay") [7]

        nop()                    .side(0)   [3]
        wrap()



    def __init__(self):

        self.sm = rp2.StateMachine(
            4, SensorReader.spi_master_16bit, freq=340000,
            in_base=machine.Pin(SensorReader.PIO_MISO_PIN),
            sideset_base=machine.Pin(SensorReader.PIO_SCK_PIN),
            set_base=machine.Pin(SensorReader.PIO_CS_PIN)
        )
        self.sm.active(1)

        self.hiPwm = machine.PWM(machine.Pin(19))
        self.lowPwm = machine.PWM(machine.Pin(18))
        self.hiPwm.freq(1000)
        self.lowPwm.freq(1000)
        self.hiPwm.duty_u16(int(65535 * 0.8))   # 80% duty cycle
        self.lowPwm.duty_u16(int(65535 * 0.2))  # 20% duty cycle

        self.buffer = []  # Buffer to store all sensor values
        self.timer = Timer()
        self.last_value = 0
        self.timer.init(freq=200, mode=Timer.PERIODIC, callback=self._timer_callback)  # 5ms interval
        


    def _timer_callback(self, t):
        MAX_BUFFER_SIZE = 2000  
        while self.sm.rx_fifo() > 0:
            value = self.sm.get()
            self.last_value = value
            if len(self.buffer) < MAX_BUFFER_SIZE:
                self.buffer.append(value)
            else:
                pass
                # drop oldest?
                #self.buffer.pop(0)
                #self.buffer.append(value)

    def pop_buffer(self):
        if self.buffer:
            return self.buffer.pop(0)
        return None

    def clear_buffer(self):
        self.buffer.clear()

    def reverse_bits_16(self,x):
        x = ((x & 0xAAAA) >> 1) | ((x & 0x5555) << 1)
        x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2)
        x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4)
        x = ((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)
        return x


    def calibratePwms(self):
        import time
        lowCal=0
        highCal=65535

        self.hiPwm.duty_u16(int(65535))   # HI at 100%
        self.lowPwm.duty_u16(int(0))      # LOW at 0%
        time.sleep(0.1)

        for duty in range(0, 65536, 256):  # Ramp in steps of 256 for speed
            #print ("     duty ",duty)
            print(".",end="")
            self.lowPwm.duty_u16(duty)
            self.clear_buffer()            
            time.sleep(0.13)  

            # Check buffer for two LSBs clear
            v = self.pop_buffer()
            v = self.reverse_bits_16(v)
            #print(hex(v))
            if v is not None:
                if (v & 0x03) == 0:  # Two LSBs clear
                    print(f"LOW PWM calibration found at duty: {duty} ({duty/65535:.2%})")  
                    lowCal=duty
                    break        


        self.lowPwm.duty_u16(int(0))
        time.sleep(0.1)
        for duty in range(65535, -1, -256): 
            #print("  duty high",duty)
            print(".",end="")
            self.hiPwm.duty_u16(duty)
            self.clear_buffer()            
            time.sleep(0.13)  

            # Check buffer for two LSBs clear
            v = self.pop_buffer()
            v = self.reverse_bits_16(v)
            if (v & 0x03) == 0:  # Two LSBs clear
                print(f"HIGH PWM calibration found at duty: {duty} ({duty/65535:.2%})")                
                highCal=duty
                break

        print(" claibration complete: ",lowCal,highCal)
        lowCalThres = int(lowCal*0.9)
        self.lowPwm.duty_u16(lowCalThres)
        highCalThres = int(highCal*1.1)
        self.hiPwm.duty_u16(highCalThres)
        print(" claibration thresholds: ", lowCalThres, highCalThres)
        print(" thresholds as percentage: LOW = {:.2%}, HIGH = {:.2%}".format(lowCalThres/65535, highCalThres/65535))




#test
if __name__ == "__main__":

    sensor = SensorReader()
    sensor.calibratePwms()

    print("end")




