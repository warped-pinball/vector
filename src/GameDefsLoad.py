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
import SPI_DataStore
from logger import logger_instance
import faults
from gc import collect as gc_collect
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
        "GameName": "Generic System 11",
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


def parse_config_line(line):
    """Parse a line in format: filename{json_data}"""
    try:
        # Find the first opening brace
        brace_index = line.find('{')
        if brace_index == -1:
            return None, None
            
        filename = line[:brace_index].strip()
        json_data = line[brace_index:].strip()
        data = json.loads(json_data)
        return filename, data
    except Exception as e:
        Log.log(f"Error parsing config line: {e}")
        return None, None

def find_config_in_file(target_filename):
    """Read the JSONL file line by line until we find the requested config."""
    try:
        with open("config/all.jsonl", "r") as f:
            for line in f:
                filename, data = parse_config_line(line.strip())
                gc_collect()
                if filename == target_filename:
                    return data
    except Exception as e:
        Log.log(f"Error reading config file: {e}")
        return None
    return None

def list_game_configs():
    '''List all the game configuration files on the device'''
    configs = {}
    try:
        with open("config/all.jsonl", "r") as f:
            for line in f:
                filename, data = parse_config_line(line.strip())
                gc_collect()
                if filename and data:
                    configs[filename] = {
                        'name': data["GameInfo"]["GameName"],
                        'rom': filename.split("_")[-1]
                    }
    except Exception as e:
        Log.log(f"Error listing game configs: {e}")
        return {}
    return configs

def go(safe_mode=False):  
    Log.log(f"Loading game definitions with safe mode set to {safe_mode}")
    data = safe_defaults
    
    if not safe_mode:    
        try:   
            config_filename = SPI_DataStore.read_record("configuration", 0)["gamename"]
            logger_instance.log(f"Loading game config {config_filename}")
            all_configs = list_game_configs()
            
            if config_filename not in all_configs.keys():
                faults.raise_fault(faults.CONF01, f"Game config {config_filename} not found")
                data = safe_defaults
            else:
                config_data = find_config_in_file(config_filename)
                if config_data:
                    data = config_data
                else:
                    faults.raise_fault(faults.CONF01, f"Error loading game config {config_filename}")
                    data = safe_defaults
                    
        except Exception as e:
            Log.log(f"Error loading game config: {e}")
            Log.log("Using safe defaults")
            faults.raise_fault(faults.CONF00)
            data = safe_defaults
    
    # This isn't wrapped in try/except because if this fails we want to stop execution
    SharedState.gdata = convert_hex_to_int(data)







