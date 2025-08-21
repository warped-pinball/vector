import rp2
import machine
from machine import Timer
from collections import deque
import time



class SensorReader:
    '''
    Hall sensor read - from PIO over SPI
      manage analog calibration
      and read in 16 bit data fiedl from SPI - repeat
    '''        
    # Pin assignments
    PIO_MISO_PIN = 12  
    PIO_SCK_PIN  = 10  
    PIO_CS_PIN   = 13  # CS (or Load...)
    ANALOG_HI_GPIO = 19
    ANALOG_LOW_GPIO = 18

    machine.Pin(12, machine.Pin.IN, machine.Pin.PULL_DOWN)
       
    @rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, set_init=rp2.PIO.OUT_HIGH) #, autopush=True, push_thresh=16 )
    def spi_master_16bit():
        set(x, 15)                          #init first transfer bit length

        wrap_target()
        set(pins, 1)             [7]        #set load pin high

        label("bitloop")         

        nop()                    .side(0)  [1]
        in_(pins, 1)             .side(0)  [1] #data in pin changes on rising edge of clock
        nop()                    .side(1)   
        nop()                    .side(1)  [1]
        
        jmp(x_dec, "bitloop")    .side(0)

        set(pins, 0)             .side(0)
        set(x, 15)               .side(0) #bit length (-1)

        #in_(pins, 16) 
        push(noblock)

        #Delay loop for pause between reads - set up for 1mS cycle
        set(y, 21)
        label("delay")
        nop()                   [1]
        jmp(y_dec, "delay")     [7]

        nop()                   .side(0)   [3]
        wrap()




    # GAME active detector - - - first level filering
    INPUT_PIN = 20  # Input to sample
    OUTPUT_PIN = 17 # Output to set/clear
    machine.Pin(INPUT_PIN, machine.Pin.IN)
    @rp2.asm_pio(set_init=rp2.PIO.OUT_HIGH)
    def sample_and_count():
        wrap_target()
        label("top")

        set(y, 31)         # number of readings
        set(x, 10)         # number that need to be low for game over

        label("next_sample")

        jmp(pin,"high")         # jmp pin is the game over lamp input, low=lamp on
        jmp(x_dec,"confirmed_low")       # decrement, if 0 then we have low for sure
        label("high")

        #delay between readings
        nop()                   [7]    
        jmp(y_dec,"next_sample")        

        #sampling done here
        set(pins,1)
        jmp("top")

        label("confirmed_low")
        set(pins,0)
        wrap()


    # GAME active detector - - second level filtering
    OUTPUT_GAME_ACTIVE_PIN = 15    #output on pin#15 to be picked up in mpython
    @rp2.asm_pio(set_init=rp2.PIO.OUT_HIGH)
    def drive_game_active_pin():

        wrap_target()
        label("topg")       
        set(x, 30) 

        label("loopg")
        jmp(pin,"highb")  [31] 
        #pin is low, set output low and start again
        set(pins,0) 
        jmp("topg")
        
        label("highb") 
        jmp(x_dec,"loopg")   [31]  #non zero take the branch
    
        set(pins,1) 
        wrap()



    def __init__(self):

        #state machine - for SPI read of coil sensors
        self.sm = rp2.StateMachine(4, SensorReader.spi_master_16bit, freq=340000,
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

        self.buffer = deque([],1000)

        self.timer = Timer()
        self.last_value = 0
        self.timer.init(freq=100, mode=Timer.PERIODIC, callback=self._timer_callback) 


        # Set up state machine for the game active detection
        sma = rp2.StateMachine(
            5, SensorReader.sample_and_count, freq=100000,  
            set_base=machine.Pin(SensorReader.OUTPUT_PIN),
            jmp_pin=machine.Pin(SensorReader.INPUT_PIN)           
        )
        sma.active(1)

        
        # Set up state machine - game active filter
        smb = rp2.StateMachine(
            6, SensorReader.drive_game_active_pin, freq=40000,  
            set_base=machine.Pin(SensorReader.OUTPUT_GAME_ACTIVE_PIN),
            jmp_pin=machine.Pin(SensorReader.OUTPUT_PIN),
            sideset_base=machine.Pin(0)
        )
        smb.active(1)


    def _timer_callback(self, t):
        while self.sm.rx_fifo() > 0:
            value = self.sm.get()
            #print("%",hex(value))
            #self.last_value = value
            if len(self.buffer)>998:
                print("buffer full ++++++++++++++")
                self.clear_buffer()
            else:    
                self.buffer.append (value) # (self.reverse_bits_16(value))

    def pop_buffer(self):
        if len(self.buffer)>0:
            return self.buffer.popleft()  # FIFO: pop from left
        return None

    def buffer_length(self):
        return len(self.buffer)

    def clear_buffer(self):
        while len(self.buffer)>0:
            self.buffer.popleft()

    def reverse_bits_16(self,x):
        x = ((x & 0xAAAA) >> 1) | ((x & 0x5555) << 1)
        x = ((x & 0xCCCC) >> 2) | ((x & 0x3333) << 2)
        x = ((x & 0xF0F0) >> 4) | ((x & 0x0F0F) << 4)
        x = ((x & 0xFF00) >> 8) | ((x & 0x00FF) << 8)
        #x = x & 0x0F
        return x

    def calibratePwms(self):
        import time
        lowCal=0
        highCal=65535

        self.hiPwm.duty_u16(int(65535))   # HI at 100%
        self.lowPwm.duty_u16(int(0))      # LOW at 0%
        time.sleep(0.1)




        '''
        self.hiPwm.duty_u16(int(65535*0.75))  
        self.lowPwm.duty_u16(int(65535*0.25))     
        while True:
            v = self.pop_buffer()   
           
            if v is None:
                v=0
            else:    
                v = self.reverse_bits_16(v)
                v = v & 0x0F
                print("&   >> ",hex(v))
        '''



        for duty in range(0, 65536, 256):  # Ramp in steps of 256 for speed        
            print(".",end="")
            self.lowPwm.duty_u16(duty)
            self.clear_buffer()            
            time.sleep(0.08)  

            # Check buffer for two LSBs clear
            v = self.pop_buffer()                      
            if v is not None:
                v = self.reverse_bits_16(v)
                v = v & 0x0F
                if (v & 0x03) == 0:  # Two LSBs clear
                    print(f"LOW PWM calibration found at duty: {duty} ({duty/65535:.2%})")  
                    lowCal=duty
                    break        


        self.lowPwm.duty_u16(int(0))
        time.sleep(0.1)
        for duty in range(65535, -1, -256):             
            print(".",end="")
            self.hiPwm.duty_u16(duty)
            self.clear_buffer()            
            time.sleep(0.08)  

            # Check buffer for two LSBs clear
            v = self.pop_buffer()
            if v is not None:
                v = self.reverse_bits_16(v)
                v = v & 0x0F            
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

    while True:
        print("end")
        time.sleep(2)




