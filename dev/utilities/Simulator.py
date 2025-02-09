"""
Simulator

This is the PICO side of the software only simulator system
a host computer (pi zero for example) will run the main simulator
code and send memory read/write commands to the pico side over
the usb port.

This code only reads and writes to the shadow ram just like a
real pinball machine.



place this file in the pico root as a .py
optionally also place DiagDisplay.py in the root
this code fragment placed in server.py wil automatically detect and start the simulator:

    # simulator - only if it exists in stand alone py file
    if file_exists("Simulator.py"):
        print("SIMULATOR: Loading")
        from Simulator import simulator_input
        schedule(simulator_input, 1000, 100)
    else:
        print("SIMULATOR: Not Found")

"""

#from uctypes import BF_LEN, BF_POS, BFUINT32, UINT32, struct
from Shadow_Ram_Definitions import (
    SRAM_COUNT_BASE,
    SRAM_DATA_BASE,
    SRAM_DATA_LENGTH,
    shadowRam,
)
import sys
import os
import uselect
import json

def file_exists(filename):
    try:
        return (os.stat(filename)[0] & 0x4000) == 0
    except OSError:
        return False

# load up 7 segement diagnostic LED display if it is here
try:
    import DiagDisplay as disp
    disp.initialize()
    print("SIMULATOR: Load Diagnostic single digit display")
except:
    print("SIMULATOR: No Display")


if 'disp' in globals():
    disp.write_char("A")

# Set up the polling stuff
print("SIMULATOR py loaded")
incoming_data = []
poller = uselect.poll()
poller.register(sys.stdin, uselect.POLLIN)
buffer = ""



def simulator_input():
    """get serial data from the serial port, store and process if eol detected"""
    global incoming_data,buffer
       
    while poller.poll(0):
        data = sys.stdin.read(1)
        if data in ('\n', '\r'):
            if buffer:  # if buffer is not empty and string has been terminated by \n or \r
                #print(f"Data received at vector: {buffer}")
                incoming_data.append(buffer)
                buffer = ""
        else:
            buffer += data
            if len(buffer) > 500:
                buffer = ""
    _process_input()


def _process_input():
    """process complete lines of input"""
    global incoming_data
    if incoming_data:
        buffer = incoming_data.pop(0)  # pops a string from the list

        search_strs = {
            "LED: ": lambda data: _led(data),
            "WRITE: ": lambda data: _write(data),
            "READ: ": lambda data: _read(data)
        }

        for search_str, action in search_strs.items():
            index = buffer.find(search_str)
            if index != -1 and index + len(search_str) < len(buffer):
                data_to_send = buffer[index + len(search_str):]
                action(data_to_send)
                break  # Exit the loop after the first match


def _led(input_data):
    """set the 7 segment display, support char and string"""
    if len(input_data) == 1:
        disp.write_char(input_data)
    elif len(input_data) > 0:
        disp.display_string(input_data)


def _read(input_data):
    """read data from the shadow ram"""
    print("READ---",input_data)         
    try:
        # Parse the input JSON string
        input_json = json.loads(input_data)
        address = int(input_json["address"])
        num_bytes = int(input_json["num_bytes"])
        
        # Read data from shadow RAM
        data = shadowRam[address:address + num_bytes]
        data_str = ','.join(str(byte) for byte in data)

        # Create the response JSON string
        response_json = {
            "address": str(address),
            "num_bytes": str(num_bytes),
            "data": data_str
        }
        response_str = json.dumps(response_json)
        
        print(f"SIM_READ: {response_str}")
        return response_str
    except Exception as e:
        print(f"Error in read function: {e}")
        return json.dumps({"error": str(e)})



def _write(input_data):
    """write data to the shadow ram"""
    print("WRITE~ ",input_data)

    try:
        input_json = json.loads(input_data)
        address = int(input_json["address"])
        data = input_json["data"]
        if isinstance(data, int):
            data = bytearray([data])
        else:
            data = bytearray(data)
     
        print(f"Write to address: {address}, data: {data}")
        
        # Write data to shadow RAM
        shadowRam[address:address + len(data)] = data
        #read back
        data = shadowRam[address:address + len(data)]
        data_str = ','.join(str(byte) for byte in data)
        
        # Create the response JSON string
        response_json = {
            "address": str(address),
            "data": data_str,
            "num_bytes": str(len(data))
        }
        response_str = json.dumps(response_json)
        
        print(f"SIM_WRITE: {response_str}")
        return response_str
    except Exception as e:
        print(f"Error in write function: {e}")
        return json.dumps({"error": str(e)})


# Example cmds
if __name__ == "__main__":
    incoming_data.append("LED: C")
    incoming_data.append("WRITE: {\"address\": \"0x00\", \"data\": [11, 2, 332, 4, 5]}")
    incoming_data.append("WRITE: {\"address\": 0, \"data\": 2}")
    incoming_data.append("READ: {\"address\": \"0x00\", \"num_bytes\": 5}")
    _process_input()
    _process_input()
    _process_input()