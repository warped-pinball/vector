# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

"""
Game format mode management.

This module provides functions to retrieve and manage different game formats
(e.g., Standard, Practice, Golf, etc.) from game configuration files.
"""
import SharedState as S
import DataMapper

next_format_id = 0
next_format_options = {}


"""
    Default format definitions
    formats idetified by NAME (Key)
    only keys in JSON config file are used
    config file overrides defaults from all parameters
    -when selecting a format send in values that override defaults here and in json
"""
DEFAULT_FORMATS = {
    "Standard": {
        "Id": 0,
        "Description": "Classic pinball scoring - highest score wins",
    },
    "Limbo": {
        "Id": 1,
        "Description": "Score as low as possible",        
        "Options": {
            "GetPlayerID": {
                "Name": "Collect Player Initials",
                "Type": "fixed",
                "Value": True
            }
        }        
    },
    "LowBall": {
        "Id": 2,
        "Description": "Only the lowest scoring ball counts",
        "Options": {
            "GetPlayerID": {
                "Name": "Collect Player Initials",
                "Type": "fixed",
                "Value": True
            }
        }       
    },
    "Golf": {
        "Id": 3,
        "Description": "Hit a specific target in the least number of balls",
        "Options": {
            "GetPlayerID": {
                "Name": "Collect Player Initials",
                "Type": "fixed",
                "Value": True
            }
        }    
    },
    "Practice": {
        "Id": 4,
        "Description": "Practice mode with unlimited balls and no score tracking",
        #"Handler": practice_handler,
        "Options":{
            "MaxScore": {
                "Name": "Score Cap",
                "Type": "fixed",
                "Value": 0  #zero for no max
            },
            "GetPlayerID": {                
                "Type": "fixed",
                "Value": False
            }
        }    
    },
    "Decay": {
        "Id": 5,
        "Description": "Score decreases over time",
        "Options": {
            "ScoreDecay": {
                "Name": "Decay per 10 seconds",
                "type": "NumberRange",
                "Range": {
                    "Low": 100,
                    "High": 39000,
                    "Default": 3000
                }
            }
        }    
    },
}


FORMAT_HANDLERS = None

def empty_handler():
    pass
    return


def get_available_formats():
    """
    Retrieve available game formats from the current game configuration,
    overlaying config data onto defaults.
    """
    game_formats_config = S.gdata.get("Formats", {})
    result_formats = {}

    for name, config in game_formats_config.items():
        base = DEFAULT_FORMATS.get(name, {})
        result_formats[name] = _deep_merge(base, config)

    return result_formats


def _deep_merge(base, overlay):
    """
    Deep merge two dictionaries, with overlay values taking precedence.
    """
    result = base.copy()
    
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
            
    return result



def set_active_format(format_name, options=None):
    """
    Set the active game format by its name (key) in to "next_active_format"
    Loads format settings in layers: defaults → config → runtime options
    """
    global next_format_id, next_format_options

    # Get formats from game configuration
    game_formats_config = S.gdata.get("Formats", {})
    if format_name not in game_formats_config and format_name not in DEFAULT_FORMATS:
        return False

    # Merge defaults and config
    combined_format = _deep_merge(DEFAULT_FORMATS.get(format_name, {}), game_formats_config.get(format_name, {}))
    next_format_id = combined_format.get("Id", 0)

    # Only keep keys in Options with a "Value" key
    next_format_options = {}
    opts = combined_format.get("Options", {})
    for key, opt in opts.items():
        if isinstance(opt, dict) and "Value" in opt:
            next_format_options[key] = {"Value": opt["Value"]}

    # Overlay runtime options
    if options:
        next_format_options = _deep_merge(next_format_options, options)

    return True





def practice_handler():
    """
    Run practice mode (keep at ball 1 in play)
    """
    if DataMapper.get_game_active() is True:
            if next_format_id != 4:  #end on next ball drain
                DataMapper.write_ball_in_play(5)
                DataMapper.write_live_scores([1,1,1,1])  
            elif DataMapper.get_ball_in_play() >1:
                DataMapper.write_ball_in_play(1)
        
            if S.format_options.get("max_score", 0)>0:
                scores = DataMapper.get_live_scores()            
                for idx in range(4):
                    if scores[idx] >= S.format_options["max_score"]:
                        scores[idx] = S.format_options["max_score"]
                        DataMapper.write_live_scores(scores)
                        break






def formats_run():
    """
    periodic tasks related to game formats.   
        call rate 5 seconds
    """
    global next_format_id, next_format_options

    """
    ind=ind+1
    if ind == 15:        
        print("formats_chg to 0 - - - - - - - - - - - -  - - - - - ")
        next_format_id=0
        next_format_options = {}
    """

    #waiting to change format?
    if S.active_format != next_format_id:
        if DataMapper.get_game_active() is False:           
            S.active_format = next_format_id
            S.format_options = next_format_options   

    if S.active_format == 0:
        return


    # Practice Mode - - - - - - - - - - - - - - - - - -
    if S.active_format == 4:  
        print("ACTIVE FORMAT 4")

        # Example: Call the handler for format ID 4 (Practice)
        format_id = 4
        handler = FORMAT_HANDLERS[format_id]
        if handler:
            handler()
        

      
                    

                   


# List of handler functions indexed by format ID
FORMAT_HANDLERS = [
    empty_handler,              # 0: Standard
    practice_handler,   # 1: Limbo
    empty_handler,              # 2: LowBall
    empty_handler,              # 3: Golf
    empty_handler,      # 4: Practice
    empty_handler,              # 5: Decay
]






















#intitialize
from phew.server import schedule
schedule(formats_run, 15000, 5000)
S.active_format = 0
S.format_options = {}




def test():
    formats = get_available_formats()
    print("\n&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&\n")
    for key, value in formats.items():
        print(f"{key}: {value}\n")

  
    p = {
        "Target": {
            "Name": "Switch or feature to hit",
            "Value": 56
        }
    }

    print("set format 4 = ", set_active_format("Practice", p), "\n\n")

    for attr in dir(S):
        if not attr.startswith("__"):
            print(f"{attr}: {getattr(S, attr)}")





    print("\n\n")

