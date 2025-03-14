'''
    serial data via USB handler
    
    IRQ for dincommng data
    call handler from system scheduler
    to send data - just print!    

'''
import machine
import sys
import uselect


incoming_data = [] #complete lines only
buffer = ""  #partial input line
poller = uselect.poll()
poller.register(sys.stdin, uselect.POLLIN)

def usb_data_handler(timer):
    '''gets bytes from usb serial port
        stash in global for main line to pick up
    '''
    global buffer, incoming_data
    #print(" P ",end="")
    loop_count = 0
    while poller.poll(0) and loop_count < 100:
        data = sys.stdin.read(1)
        if data in ('\n', '\r'):
            if buffer:  # if buffer is not empty and string has been terminated by \n or \r
                print(f"Data received at vector: {buffer}")
                incoming_data.append(buffer)
                buffer = ""
        else:
            buffer += data
            if len(buffer) > 500:
                buffer = ""
        loop_count += 1


def usb_data_process():
    '''processes the data from the usb serial port
        call on a schedule 
    '''        
    global incoming_data
    #print("USB")   
    loop_count=0     
    while incoming_data and loop_count<10:
        loop_count += 1
        in_buffer = incoming_data.pop(0)  #pops a string from the list        
        #print(f"Processing buffer in main_task: {buffer}")
        #print("incomming st#ff ")
        search_str = "VECTOR: display "

        index = in_buffer.find(search_str)            
        if index != -1 and index + len(search_str) < len(buffer):
            char_to_send = in_buffer[index + len(search_str)]
            print(f"Character to send to diagdisplay: {char_to_send}")
            
    

# Set up a timer to call usb_data_handler every 100ms
usb_timer = machine.Timer(-1)
usb_timer.init(period=100, mode=machine.Timer.PERIODIC, callback=usb_data_handler)



