# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
'''
display message handling (custom message shown on the pinball machine display)

SYSYEM 9 Version  (Nov. 2024)
For system 9 show IP address on the high score display
'''

import json
import uctypes
from Shadow_Ram_Definitions import shadowRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
import SharedState as S
localCopyIp = 0

#
# fix adjustments checksum
#
def fixAdjustmentChecksum():   
    return True
   

def int_to_bcd(number):
    if not (0 <= number <= 99999999):
        raise ValueError("MSG: Number out of range")
    
    num_str = f"{number:08d}"    
    bcd_bytes = bytearray(4)
        
    bcd_bytes[0] = (int(num_str[0]) << 4) + int(num_str[1]) # Millions
    bcd_bytes[1] = (int(num_str[2]) << 4) + int(num_str[3]) # Hundred-th & ten-th
    bcd_bytes[2] = (int(num_str[4]) << 4) + int(num_str[5]) # Thousands & hundreds
    bcd_bytes[3] = (int(num_str[6]) << 4) + int(num_str[7]) # Tens & ones
    return bcd_bytes


#write ascii strings to memory
def set_mem(msg):
    #print("DISP gdata = ",S.gdata["DisplayMessage"]["Address"],msgText )
    
    if S.gdata["DisplayMessage"]["Type"] == 9:
        for i in range(4):                              
            address_offset = S.gdata["DisplayMessage"]["Address"] + i * 4
            n=int_to_bcd(msg[i])
            for offset in range(4):
                shadowRam[address_offset+offset]=n[offset]
                #print(" set ",address_offset+offset, " to",n[offset])


def typ1_DecimalandPad(input,length,spacechar):   
    return ""

def typ3_DecimalandPad(input, length): 
    return ""

#
#put display values in machine ram
#
def set(ipAddress):
    if not isinstance(ipAddress, str):
        ipAddress="000.000.000.000"
    msg=[0,0,0,0]  
    
    try:
        first_dot = ipAddress.find('.')
        second_dot = ipAddress.find('.', first_dot + 1)
        third_dot = ipAddress.find('.', second_dot + 1)

        msg[0] = int(ipAddress[:first_dot])
        msg[1] = int(ipAddress[first_dot + 1:second_dot])
        msg[2] = int(ipAddress[second_dot + 1:third_dot])
        msg[3] = int(ipAddress[third_dot + 1:])        
        set_mem(msg)                  
    except:
        print("MSG: Failure in set ip") 
    return

#
# set up display for ipaddress - get ip copied to local
#
def init(ipAddress):
    global localCopyIp
    localCopyIp = ipAddress
    set(localCopyIp)    
    return

#do not allow refresh from server - must be coordinated with score for system 9
def refresh():
    return

def refresh_9():
    global localCopyIp      
    init(localCopyIp)
    print("display message refreshed ",localCopyIp)
    return
    


if __name__ == "__main__":
        print("111.222.333.444")
        set("111.222.333.444")


