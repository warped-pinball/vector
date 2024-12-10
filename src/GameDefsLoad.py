# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
'''
   Game Definition File managemenet / load

   load the game setting from a json file in 
   /GameDefs based on game name in the config
'''
import json
import SharedState
from logger import logger_instance
Log = logger_instance

#convert any data entered as "0x" (hex) into integers
def convert_hex_to_int(data):
    if isinstance(data, dict):
        for key, value in data.items():
            data[key] = convert_hex_to_int(value)
    elif isinstance(data, list):
        for i in range(len(data)):
            data[i] = convert_hex_to_int(data[i])
    elif isinstance(data, str) and data.startswith("0x"):
        try:
            return int(data, 16)
        except ValueError as e:
            Log.log("DEFLOAD: game def Error converting:", str(e))
    return data

safe_defaults = {
    "GameInfo": {
        "GameName": "Generic Sys11",
        "System": "11x"        
    },
    "Definition": {
        "version": 1
    },
    "Memory" : {
        "Start": 0,
        "Length": 2048,
        "NvStart": 0,
        "NvLength": 2048
    },

    "BallInPlay": {
        "Type": 0,
        "Address": 56,
        "Ball1": "0xF1",
        "Ball2": "0xF2",
        "Ball3": "0xF3",
        "Ball4": "0xF4",
        "Ball5": "0xF5"
    },

    "DisplayMessage": {
        "Type": 0,
        "Address": "0x7B4",
        "Length": 7,
        "Number": 6,
        "EnableByteAddress": "0x7B0"
    },

    "Adjustments" :{
        "Type": 0,
        "ChecksumStartAdr": "0x780",
        "ChecksumEndAdr": "0x7E3",
        "ChecksumResultAdr": "0x7ED"
    },

    "HighScores": {
        "Type": 0,
        "ScoreAdr": "0x727",
        "InitialAdr": "0x737",
        "BytesInScore": 4
    },

    "HSRewards": {
        "Type": 0,
        "HS1": 1937,
        "HS2": 1938,
        "HS3": 1939,
        "HS4": 1940,
        "DisableByte": 0
    },

    "Switches": {
        "Type": 0,
        "Address": 56,
        "Length": 23
    },

    "CoinDrop": {
        "Type": 0
    }
}

  
def go(safe_mode=False):  
    Log.log("Loading game definitions with safe mode set to {safe_mode}")
    data = safe_defaults
    if not safe_mode:    
        try:   
            with open("game_config.json", "r") as f:
                data = json.load(f)
        except Exception as e:
            Log.log(f"Error loading game config: {e}")
            Log.log("Using safe defaults")
            # in case the variable was unset before error
            data = safe_defaults
    
    # This isn't wrapped in try/except because if this fails we want to stop execution
    SharedState.gdata = convert_hex_to_int(data)







