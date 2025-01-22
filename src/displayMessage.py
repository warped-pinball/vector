# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
display message handling (custom message shown on the pinball machine display)
"""

import SharedState as S
from Shadow_Ram_Definitions import shadowRam


#
# fix adjustments checksum
#
def fixAdjustmentChecksum():
    if S.gdata["Adjustments"]["Type"] == 0 or S.gdata["Adjustments"]["Type"] == 1:  # 0 will at least test and report the checksum, no changes
        start = S.gdata["Adjustments"]["ChecksumStartAdr"]
        end = S.gdata["Adjustments"]["ChecksumEndAdr"]
        resultLoc = S.gdata["Adjustments"]["ChecksumResultAdr"]
        origCS = shadowRam[resultLoc]
        cs = 0
        for i in range(start, end + 1):
            cs = (cs + shadowRam[i]) % 256
        cs = 255 - cs

        if S.gdata["Adjustments"]["Type"] == 0:
            print("DISP: checksum TEST: ", cs)
            print("DISP: checksum value in memory: ", shadowRam[resultLoc])
        else:
            print("DISP: adjustments checksum: ", cs)
            shadowRam[resultLoc] = cs
        if cs == origCS:
            return True  # checksum was a match
        else:
            return False  # was not a match, corrected


# write ascii strings to memory
def set_mem(msgText):
    # print("DISP gdata = ",S.gdata["DisplayMessage"]["Address"],msgText )

    if S.gdata["DisplayMessage"]["Type"] == 1:
        for i, text in enumerate(msgText):
            address_offset = S.gdata["DisplayMessage"]["Address"] + i * 7
            for k in range(len(text)):
                shadowRam[address_offset + k] = text[k]
        shadowRam[S.gdata["DisplayMessage"]["EnableByteAddress"]] = 0

    if S.gdata["DisplayMessage"]["Type"] in [2, 3]:
        try:
            # print("msgtext----> ",msgText)
            address_offset = S.gdata["DisplayMessage"]["Address"]

            for k in range(len(msgText[0])):
                shadowRam[address_offset + k] = msgText[0][k]
            address_offset = address_offset + 16
            for k in range(len(msgText[1])):
                shadowRam[address_offset + k] = msgText[1][k]
            address_offset = address_offset + 16
            for k in range(len(msgText[2])):
                shadowRam[address_offset + k] = msgText[2][k]
            shadowRam[S.gdata["DisplayMessage"]["EnableByteAddress"]] = 0
        except Exception as e:
            print(f"Unexpected error 56744 : {e}")


# type one with spaces=0x40 and deicmals are |0x80
def typ1_DecimalandPad(input, length, spacechar):
    out = []
    for char in input:
        if char == " " or char == ".":
            out.append(spacechar)
        else:
            out.append(ord(char))

    while len(out) < length:
        out.insert(0, spacechar)
    # hex_output = ' '.join(f'{byte:02X}' for byte in out)
    # print(f"Output in hex: {hex_output}")
    return out


# type three with spaces=0x00
def typ3_DecimalandPad(input, length):
    out = []
    for char in input:
        if char == " " or char == ".":
            out.append(0x00)
        elif "0" <= char <= "9":
            out.append(ord(char) - 0x2F)
        elif "A" <= char <= "Z":
            out.append(ord(char) - 0x36)
        else:
            print(f"Warning: Unsupported character '{char}'")
    while len(out) < length:
        out.insert(0, 0x00)

    return out


#
# put display values in machine ram
#
def set(ipAddress):
    if not isinstance(ipAddress, str):
        ipAddress = "000.000.000.000"

    if S.gdata["DisplayMessage"]["Type"] == 1:
        try:
            # 7 char 6 lines.  IP address split between two 7 digit displays
            msg = ["", "", "", "", "", ""]
            first_dot = ipAddress.find(".")
            second_dot = ipAddress.find(".", first_dot + 1)
            first_part = ipAddress[:second_dot]
            second_part = ipAddress[second_dot + 1 :]

            msg[2] = typ1_DecimalandPad(first_part, 7, 0x20)
            msg[3] = typ1_DecimalandPad(second_part, 7, 0x20)
            msg[0] = [ord(char) for char in "WARPED "]
            msg[1] = [ord(char) for char in "PINBALL"]
            msg[4] = msg[2]
            msg[5] = msg[3]
            set_mem(msg)
        except Exception:
            print("MSG: Failure in set ip")

    elif S.gdata["DisplayMessage"]["Type"] == 2:  # 2 display modules
        # 16 char 3 lines,  IP address shown complete on each 16 digit display
        msg = ["", "", ""]
        msg[0] = [ord(char) for char in "WARPED  PINBALL "]
        msg[1] = typ1_DecimalandPad(ipAddress, 16, 0x20)
        msg[2] = msg[1]
        # print(msg)
        set_mem(msg)

    elif S.gdata["DisplayMessage"]["Type"] == 3:
        # 16 char 3 lines, but lines split on 2 displays (8 char each)
        msg = ["", "", ""]
        inp = " WARPED PINBALL "
        msg[0] = typ3_DecimalandPad(inp, 16)

        first_dot = ipAddress.find(".")
        second_dot = ipAddress.find(".", first_dot + 1)
        first_part = ipAddress[:second_dot]
        second_part = ipAddress[second_dot + 1 :]

        print("first part:", first_part, " second part:", second_part)

        msg[1] = typ3_DecimalandPad(first_part, 8)
        msg[1].extend(typ3_DecimalandPad(second_part, 8))
        msg[2] = msg[1][:]
        set_mem(msg)
    fixAdjustmentChecksum()
    return


#
# set up display for ipaddress - get ip copied to local
#
def init(ipAddress):
    S.ipAddress = ipAddress
    set(ipAddress)
    return


def refresh():
    if S.gdata["HSRewards"]["Type"] == 1:
        # temp patch in here - set high score rewards to 0
        shadowRam[S.gdata["HSRewards"]["HS1"]] = S.gdata["HSRewards"]["DisableByte"]
        shadowRam[S.gdata["HSRewards"]["HS2"]] = S.gdata["HSRewards"]["DisableByte"]
        shadowRam[S.gdata["HSRewards"]["HS3"]] = S.gdata["HSRewards"]["DisableByte"]
        shadowRam[S.gdata["HSRewards"]["HS4"]] = S.gdata["HSRewards"]["DisableByte"]
    init(S.ipAddress)
    print("display message refreshed ", S.ipAddress)
    return


if __name__ == "__main__":
    print("111.222.333.444")
    set("111.222.333.444")


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
