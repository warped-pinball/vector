'''
WPC

FRAM map configuraiton


fram map constants for some of ther fram users.
see "fram and sFlash map.txt" for more details.
'''

DATA_STORE = {
    "AddressStart": 0x4A67,
    "DataLength": 0x3598,
}


LOGGER_CONFIG = {
    "AddressStart": 0x2600,
    "LoggerLength": 0x1FFF,
}


ADJUSTMENTS_CONFIG = {
    "NumRecords": 4,
    "AddressStart": 0x2000,
    "RecordSize":   320,  
    "NamesAddress": 0x2500,
    "NamesLength":  16,
    "LastLoadedAddress": 0x25F0,
    "TotalDataLength":   0x0600
}

#shadow ram 0x0000-0x1FFF

