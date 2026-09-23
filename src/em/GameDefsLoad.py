# This file is part of the Warped Pinball SYSEM-Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
   Game Definition load for EM games only - load comes from fram SPI_DataStore

"""
import json
from gc import collect as gc_collect

import deflate

import faults
import SharedState
import SPI_DataStore
from logger import logger_instance
Log = logger_instance


# Mirrors SPI_DataStore.blankStruct("EMData")'s manufacturing defaults, so a
# fallback boot (FRAM read failed) looks the same as a freshly factory-reset
# board rather than introducing a third, different set of numbers.
_filtermasks = bytearray(64)
for _ch in range(32):
    _filtermasks[_ch * 2] = 3
    _filtermasks[_ch * 2 + 1] = 9
_filtermasks = bytes(_filtermasks)

_carrythresholds = bytes([i % 256 for i in range(32)])

safe_defaults = {
    "gamename": "EM Game",
    "GameInfo": {"System": "EM", "GameName": "EM Game"},
    "players": 1,
    "digits": 4,
    "dummy_reels": 0,
    "filtermasks": _filtermasks,
    "carrythresholds": _carrythresholds,
    "sensorlevels": [31000, 32000],
    "startpause": 8,
    "endpause": 5,
    "sensitivity": 0,
    "timing_p1_score": [5, 5, 5, 3, 3],
    "timing_p1_reset": [8, 8, 8, 4, 4],
    "timing_p2_score": [5, 5, 5, 3, 3],
    "timing_p2_reset": [8, 8, 8, 4, 4],
    "timing_p3_score": [5, 5, 5, 3, 3],
    "timing_p3_reset": [8, 8, 8, 4, 4],
    "timing_p4_score": [5, 5, 5, 3, 3],
    "timing_p4_reset": [8, 8, 8, 4, 4],
}

_LIST_KEYS = (
    "sensorlevels",
    "timing_p1_score", "timing_p1_reset",
    "timing_p2_score", "timing_p2_reset",
    "timing_p3_score", "timing_p3_reset",
    "timing_p4_score", "timing_p4_reset",
)


def get_safe_defaults():
    """Copy so gdata never aliases (or mutates) the module-level defaults."""
    data = dict(safe_defaults)
    data["GameInfo"] = dict(safe_defaults["GameInfo"])
    for key in _LIST_KEYS:
        data[key] = list(safe_defaults[key])
    return data


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
        for line in iter_config_lines():
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
        SharedState.gdata = get_safe_defaults()
        print("Using safe defaults:", SharedState.gdata)
