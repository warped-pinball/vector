# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
   Game Definition File managemenet / load

   load the game setting from a json file in
   /GameDefs based on game name in the config
"""
import json
from gc import collect as gc_collect

import deflate

import faults
import SharedState
import SPI_DataStore
from logger import logger_instance
Log = logger_instance


# convert any data entered as "0x" (hex) into integers
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
    "GameInfo": {"GameName": "Generic System", "System": "X"},
    "BallInPlay": {"Type": 0},
    "InPlay": {"Type": 0},
    "DisplayMessage": {"Type": 0},
    "Adjustments": {"Type": 0},
    "HighScores": {"Type": 0},
    "HSRewards": {"Type": 0},
    "Switches": {"Type": 0},
    "CoinDrop": {"Type": 0},
}


def parse_config_line(line):
    """Parse a line in format: filename{json_data}"""
    try:
        # Find the first opening brace
        brace_index = line.find("{")
        if brace_index == -1:
            return None, None

        filename = line[:brace_index].strip()
        json_data = line[brace_index:].strip()
        data = json.loads(json_data)
        return filename, data
    except Exception as e:
        Log.log(f"Error parsing config line: {e}")
        return None, None


def iter_config_lines():
    """Yield config lines one at a time from the compressed config file."""
    try:
        with open("config/all.jsonl.z", "rb") as f:
            with deflate.DeflateIO(f, deflate.ZLIB, 8) as zipped_file:
                while True:
                    line = zipped_file.readline()
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        yield line.decode("utf-8")
    except Exception as e:
        Log.log(f"Error opening config file config/all.jsonl.z: {e}")


def find_config_in_file(target_filename):
    """Read the JSONL file line by line until we find the requested config."""
    try:
        # Handle LinkTo by iterating instead of recursion to save memory
        while True:
            for line in iter_config_lines():
                filename, data = parse_config_line(line.strip())
                gc_collect()
                if filename == target_filename:
                    # Check for LinkTo field inside GameInfo - allows one config to alias another
                    if isinstance(data.get("GameInfo"), dict) and "LinkTo" in data["GameInfo"]:
                        linked_target = data["GameInfo"]["LinkTo"]
                        Log.log(f"Config {target_filename} links to {linked_target}")
                        target_filename = linked_target  # Follow the link
                        break  # Restart search with new target
                    return data
            else:
                # for loop completed without break - file not found
                return None
    except Exception as e:
        Log.log(f"Error reading config file: {e}")
        return None


def list_game_configs():
    """List all the game configuration files on the device"""
    configs = {}
    try:
        for line in iter_config_lines():
            filename, data = parse_config_line(line.strip())
            gc_collect()
            if filename and data:
                configs[filename] = {
                    "name": data["GameInfo"]["GameName"],
                    "rom": filename.split("_")[-1],
                }
    except Exception as e:
        Log.log(f"Error listing game configs: {e}")
        return {}
    return configs


def go(safe_mode=False):
    Log.log(f"Loading game definitions with safe mode set to {safe_mode}")

    data = safe_defaults.copy()

    if not safe_mode:
        try:
            config_filename = SPI_DataStore.read_record("configuration", 0)["gamename"]
            Log.log(f"Loading game config {config_filename}")
            all_configs = list_game_configs()

            if config_filename not in all_configs.keys():
                faults.raise_fault(faults.CONF01, f"Game config {config_filename} not found")
                data = safe_defaults
            else:
                config_data = find_config_in_file(config_filename)
                if config_data:
                    if "GameInfo" in config_data and "GameName" in config_data["GameInfo"]:
                        print(f"DEBUG: Game name is '{config_data['GameInfo']['GameName']}'")  
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
