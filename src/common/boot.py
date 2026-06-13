# boot python file
import machine

# reset output - hold mother board in reset until RAM task is ready
reset_output = machine.Pin(0, machine.Pin.OUT, value=1)
print("BOOT: Boot init file done now.")
