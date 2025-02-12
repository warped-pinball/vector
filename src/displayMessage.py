# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
display message handling (custom message shown on the pinball machine display)

updated for system 9 - optionally shows IP address in high score display
"""

import json
import uctypes
from Shadow_Ram_Definitions import shadowRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
import SharedState as S
localCopyIp = 0


def fixAdjustmentChecksum():   
    """
    fixes the CRC in the adjustments according to machine type
        not used on system 9
        system 11 with type 0 will only report check sum, not fix it
    """
    if "11" in S.gdata["GameInfo"]["System"]:
        if S.gdata["Adjustments"]["Type"]==0  or  S.gdata["Adjustments"]["Type"]==1:  
            start = S.gdata["Adjustments"]["ChecksumStartAdr"]
            end = S.gdata["Adjustments"]["ChecksumEndAdr"]
            resultLoc = S.gdata["Adjustments"]["ChecksumResultAdr"]
            origCS = shadowRam[resultLoc]
            cs=0
            for i in range(start, end + 1):
                cs = (cs + shadowRam[i]) % 256 
            cs = 255 - cs        

            if S.gdata["Adjustments"]["Type"] == 0:
                print("DISP: checksum TEST: ",cs)
                print("DISP: checksum value in memory: ",shadowRam[resultLoc])
            else:
                print("DISP: adjustments checksum: ",cs)
                shadowRam[resultLoc]=cs
            if cs == origCS: return True  #checksum was a match
            else: return False  #was not a match, corrected


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


def set_mem(msgText):
    """
    Put the message in the shadow ram
    
    """
    #system 11  (1)
    if S.gdata["DisplayMessage"]["Type"] == 1:
        for i, text in enumerate(msgText):                              
            address_offset = S.gdata["DisplayMessage"]["Address"] + i * 7  
            for k in range(len(text)):                
                shadowRam[address_offset + k] = text[k]
        shadowRam[S.gdata["DisplayMessage"]["EnableByteAddress"]]=0

    #system 11  (2,3)
    elif S.gdata["DisplayMessage"]["Type"] in [2,3]:            
        try:
            #print("msgtext----> ",msgText)
            address_offset = S.gdata["DisplayMessage"]["Address"]

            for k in range(len(msgText[0])):
                shadowRam[address_offset + k] = msgText[0][k]
            address_offset=address_offset+16      
            for k in range(len(msgText[1])):               
                shadowRam[address_offset + k] = msgText[1][k]
            address_offset=address_offset+16
            for k in range(len(msgText[2])):                
                shadowRam[address_offset + k] = msgText[2][k]
            shadowRam[S.gdata["DisplayMessage"]["EnableByteAddress"]]=0
        except Exception as e:
            print(f"MSG Fault 87: {e}")

    #system 9
    elif S.gdata["DisplayMessage"]["Type"] == 9:
        for i in range(4):                              
            address_offset = S.gdata["DisplayMessage"]["Address"] + i * 4
            n=int_to_bcd(msgText[i])
            for offset in range(4):
                shadowRam[address_offset+offset]=n[offset]
                #print(" set ",address_offset+offset, " to",n[offset])


def typ1_DecimalandPad(input,length,spacechar):
    """
    type one 
        spaces=0x40 and deicmals are |0x80
    """
    out = []    
    for char in input:
        if char == ' ' or char == '.':
            out.append(spacechar)
        else:
            out.append(ord(char))  
      
    while len(out) < length:
        out.insert(0, spacechar)      
    return out
    

def typ3_DecimalandPad(input, length):
    """
    type three 
        spaces=0x00
    """
    out = []    
    for char in input:
        if char == ' ' or char == '.':
            out.append(0x00)
        elif '0' <= char <= '9':  
            out.append(ord(char) - 0x2F) 
        elif 'A' <= char <= 'Z': 
            out.append(ord(char) - 0x36) 
        else:
            print(f"Warning: Unsupported character '{char}'")
    while len(out) < length:
        out.insert(0, 0x00)             
    return out


def set(ipAddress):
    """
    put ip address values in shadow ram
    """
    if not isinstance(ipAddress, str):
        ipAddress="000.000.000.000"

    if S.gdata["DisplayMessage"]["Type"] == 1:    
        try:
            #7 char 6 lines.  IP address split between two 7 digit displays
            msg=['','','','','','']  
            first_dot = ipAddress.find('.')
            second_dot = ipAddress.find('.', first_dot + 1)
            first_part = ipAddress[:second_dot]
            second_part = ipAddress[second_dot + 1:]

            msg[2]=typ1_DecimalandPad(first_part,7,0x20)
            msg[3]=typ1_DecimalandPad(second_part,7,0x20)       
            msg[0] = [ord(char) for char in "WARPED "]
            msg[1] = [ord(char) for char in "PINBALL"]        
            msg[4] = msg[2]
            msg[5] = msg[3]
            set_mem(msg)       
            fixAdjustmentChecksum()           
        except:
            print("MSG: Failure in set ip") 
        
    elif S.gdata["DisplayMessage"]["Type"] == 2:  #2 display modules
        #16 char 3 lines,  IP address shown complete on each 16 digit display
        msg=['','',''] 
        msg[0] = [ord(char) for char in "WARPED  PINBALL "]   
        msg[1]=typ1_DecimalandPad(ipAddress,16,0x20)         
        msg[2] = msg[1]        
        #print(msg)
        set_mem(msg)   
        fixAdjustmentChecksum()

    elif S.gdata["DisplayMessage"]["Type"] == 3:  
        #16 char 3 lines, but lines split on 2 displays (8 char each)      
        msg = ['','','']  
        inp = " WARPED PINBALL "
        msg[0]=typ3_DecimalandPad(inp,16)
              
        first_dot = ipAddress.find('.')
        second_dot = ipAddress.find('.', first_dot + 1)
        first_part = ipAddress[:second_dot]
        second_part = ipAddress[second_dot + 1:]

        #print("first part:",first_part," second part:",second_part)

        msg[1] = typ3_DecimalandPad(first_part,8)
        msg[1].extend(typ3_DecimalandPad(second_part,8))   
        msg[2]=msg[1][:]
        set_mem(msg)  
        fixAdjustmentChecksum()

    elif S.gdata["DisplayMessage"]["Type"] == 9:  
        msg_nums=[0,0,0,0]      
        try:
            first_dot = ipAddress.find('.')
            second_dot = ipAddress.find('.', first_dot + 1)
            third_dot = ipAddress.find('.', second_dot + 1)

            msg_nums[0] = int(ipAddress[:first_dot])
            msg_nums[1] = int(ipAddress[first_dot + 1:second_dot])
            msg_nums[2] = int(ipAddress[second_dot + 1:third_dot])
            msg_nums[3] = int(ipAddress[third_dot + 1:])        
            set_mem(msg_nums)                  
        except:
            print("MSG: Failure in set ip") 


#
# set up display for ipaddress - get ip copied to local
#  grab the address - do not display yet!
def init(ipAddress):
    global localCopyIp
    localCopyIp = ipAddress
    return


def refresh():
    """
    refresh IP address display
        this one only good for system 11
        also set high score rewards to zero if supported in defs
    """
    global localCopyIp    
    if "11" not in S.gdata["GameInfo"]["System"]:
        #do not allow refresh from server - must be coordinated with score for system 9
        return

    if S.gdata["HSRewards"]["Type"] == 1:
        #temp patch in here - set high score rewards to 0
        shadowRam[S.gdata["HSRewards"]["HS1"]]=S.gdata["HSRewards"]["DisableByte"]
        shadowRam[S.gdata["HSRewards"]["HS2"]]=S.gdata["HSRewards"]["DisableByte"]
        shadowRam[S.gdata["HSRewards"]["HS3"]]=S.gdata["HSRewards"]["DisableByte"]
        shadowRam[S.gdata["HSRewards"]["HS4"]]=S.gdata["HSRewards"]["DisableByte"]              
    #init(localCopyIp)
    set(localCopyIp)
    print("MSG: refreshed ",localCopyIp)
    return

  

def refresh_9():
    """
    called from score track
      refresh ip address in highscore display for system 9 
    """
    if S.gdata["DisplayMessage"]["Type"] == 9:          
        global localCopyIp      
        set(localCopyIp)
        print("MSG: refreshed ",localCopyIp)
        

"""
Game Def font types:

    type 1:  spaces are 0x20
             capital alpa are normal ascii
             add 0x80 for decimal point
             7x6 characters


    type 2:  spaces are 0x20
             capital alpa are normal ascii
             add 0x80 for decimal point
             16x3 characters

    type 3:   spaces are 0x00
              subtract 0x36 from ascii codes for letters
              add 0x55 for deciaml point
              numbers are 0x01-0x0A = 0,1,2,9

"""
