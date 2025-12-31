'''
Data East

FRAM map configuraiton


fram map constants for some of ther fram users.
see "fram and sFlash map.txt" for more details.
'''

DATA_STORE = {    # build from top of Fram down  0x4A67-0x7FFF
    "AddressStart": 0x4A67,
    "DataLength": 0x3598,
}


LOGGER_CONFIG = {   # 0x2600 - 0x45FF
    "AddressStart": 0x2600,
    "LoggerLength": 0x1FFF,
}


# Max requirred area for DataEast is 270 bytes
#    WPC is setup for 320 for reference
ADJUSTMENTS_CONFIG = {
    "NumRecords": 4,
    "AddressStart": 0x2000,
    "RecordSize":   0x140,     
    "NamesAddress": 0x2510,
    "NamesLength":  0x10,
    "LastLoadedAddress": 0x25F0,
    "TotalDataLength":   0x0600
}


#shadow ram                  0x0000-0x1FFF   (8k)

