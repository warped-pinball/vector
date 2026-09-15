# This file is part of the Warped Pinball SYSEM-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
   Game Definition load for EM games only - load comes from fram SPI_DataStore

"""
import json
from gc import collect as gc_collect

import faults
import SharedState
import SPI_DataStore
from logger import logger_instance
Log = logger_instance


safe_defaults = {"gamename": "EM Generic", "players": 1, "digits": 4, "dummy_reels": 0, "filtermasks": bytes(40), "carrythresholds": bytes(32), "startpause": 5,"endpause":5,"sensorlevels": [0, 0]}


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
    """List all the game configuration files on the device"""
    configs = {}
    try:
        with open("config/all.jsonl", "r") as f:
            for line in f:
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
    """for EM game just load from SPI_DataStore"""
    Log.log(f"Loading EM definition, safe mode ={safe_mode}")

    try:
        em_data = SPI_DataStore.read_record("EMData", 0)
        SharedState.gdata = em_data

        if not isinstance(SharedState.gdata.get("GameInfo"), dict):
            SharedState.gdata["GameInfo"] = {}
        SharedState.gdata["GameInfo"]["System"] = "EM"
        SharedState.gdata["GameInfo"]["GameName"] = em_data["gamename"]
        print("Loaded EMData from SPI_DataStore")

    except Exception as e:
        Log.log(f"Error loading EMData: {e}")        
        faults.raise_fault(faults.CONF00)
        SharedState.gdata = safe_defaults
        print("Using safe defaults:", safe_defaults)
