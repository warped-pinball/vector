'''
    serial data via USB handler
    
    IRQ for incoming data
    call handler from system scheduler
    to send data - just print!    

'''
import machine
import sys
import uselect
import SharedState as S


incoming_data = [] #complete lines only
buffer = ""  #partial input line
poller = uselect.poll()
poller.register(sys.stdin, uselect.POLLIN)

def usb_data_handler(timer):
    '''IRQ druiven,  gets bytes from usb serial port
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
        in_buffer = incoming_data.pop(0)  #pops a complete string from the list        

        #initals and name coming in?
        search_str = "VECTOR: I: "
        index = in_buffer.find(search_str)
        if index != -1 and index + len(search_str) < len(in_buffer):
            start_index = index + len(search_str)
            S.zoom_incoming_intials = in_buffer[start_index:start_index + 3].strip()
        
            # NAME coming in?
            name_search_str = "N:"
            name_index = in_buffer.find(name_search_str)
            if name_index != -1 and name_index + len(name_search_str) < len(in_buffer):
                name_start_index = name_index + len(name_search_str)
                S.zoom_incomming_name = in_buffer[name_start_index:].strip()


            #finish intial clean up
            S.zoom_incoming_intials = S.zoom_incoming_intials.upper()
            i_intials = ""
            for c in S.zoom_incoming_intials:
                if 'A' <= c <= 'Z':
                    i_intials += c
            S.zoom_incoming_intials = (i_intials + "   ")[:3]

            print(f"USB: initials received: {S.zoom_incoming_intials}")
            print(f"USB: name received: {S.zoom_incomming_name}")

    

# Set up a timer to call usb_data_handler every 100ms
usb_timer = machine.Timer(-1)
usb_timer.init(period=100, mode=machine.Timer.PERIODIC, callback=usb_data_handler)


import GameStatus
import json
def send_game_status():
    gs = GameStatus.game_report()
    #gs['zoom_initials'] = S.zoom_initials  
    gs_json = json.dumps(gs)
    print(f"ZOOM: GAME: {gs_json}")
