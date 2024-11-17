# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
'''
   Game Definition File managemenet / load

   load the game setting from a json file in 
   /GameDefs based on game name in the config

   New version for SYSYEM 9
'''
import json
import SPI_DataStore as DataStore
import SharedState
from logger import logger_instance
Log = logger_instance

#loads a game def.json file into memory
def load_json(file_path):
    try:
        #print("open file ",file_path)
        with open(file_path, 'r') as file:
            data = json.load(file)
        return data
    except Exception as e:
        Log.log("DEFLOAD: Error loading JSON file:", str(e))
        raise

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


#take a game file name and build path with extension
def build_path(game_name):
    directory = 'GameDefs'
    file_extension = '.json'
    return f"{directory}/{game_name}{file_extension}"


def load_safe_defaults():
    #load up safe defaults
    print ("DEFLOAD: load safe defaults")
    data= {
        "GameInfo": {
            "GameName": "Generic Sys9",
            "System": "9"        
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
        "InPlayScores": {
            "Type": 0,
            "ScoreAdr": "0x38",
            "ZeroNibble": 15,
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
    SharedState.gdata = convert_hex_to_int(data)
    print ("DEFLOAD: default data")   

  
def go():  
    try:            
        name=DataStore.read_record("configuration",0)["gamename"].strip('\0')                     
    except:            
        name=None
        Log.log(f"Error reading game name: {e}")

    Log.log(f"DEFLOAD: game= {name}")

    try:
        data = load_json(build_path(name))    
        SharedState.gdata = convert_hex_to_int(data)
        #print ("DEFLOAD gdata= ",SharedState.gdata)
    except:
        load_safe_defaults()






