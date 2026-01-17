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


def get_available_formats():
    """
    Retrieve available game formats from the current game configuration.

    Formats are defined in the game configuration JSON file under the "Formats" key.
    Each format can have optional configuration parameters for customization.
    """
    # Default descriptions for common format names
    default_descriptions = {
        "Standard": "Classic pinball scoring - highest score wins",
        "Practice": "Non-competitive practice mode for skill building",
        "Golf": "Lowest score wins - try to minimize your points",
        "Limbo": "Score as low as possible",
        "LowBall": "Only the lowest scoring ball counts",
        "Decay": "Score decreases over time",
    }

    # Get formats from game configuration
    game_formats = S.gdata.get("Formats", {})

    # Fill in missing descriptions from default list
    for format_name, format_data in game_formats.items():
        # Check if description is missing or empty
        if "Description" not in format_data or not format_data["Description"]:
            # Look for matching description in default list
            if format_name in default_descriptions:
                format_data["Description"] = default_descriptions[format_name]

    return game_formats



def set_active_format(format_id, options=None):
    """
    Set the active game format by its identifier.
    
    Args:
        format_id (int): The format ID to set as active
        options (dict, optional): Configuration options for the selected format
        
    Returns:
        bool: True if format was found and set, False otherwise
    """
    global next_format_id, next_format_options

    # Get formats from game configuration
    game_formats = S.gdata.get("Formats", {})
    
    # Verify the format_id exists in game_formats
    for format_name, format_data in game_formats.items():
        if format_data.get("Id") == format_id:
            next_format_id = format_id

            if options:
                next_format_options = options
            else:
                next_format_options = {}

            print(f"Formats: set active format to {format_name} (ID {format_id}) with options {next_format_options}") 
            return True
          
    # Format ID not found
    return False




def formats_run():
    """
    periodic tasks related to game formats.   
        
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

        if DataMapper.get_game_active() is True:
            if next_format_id != 4:  #end on next ball drain
                DataMapper.write_ball_in_play(5)
            elif DataMapper.get_ball_in_play() >1:
                DataMapper.write_ball_in_play(1)
        
            if S.format_options.get("max_score", 0)>0:
                scores = DataMapper.get_live_scores()            
                for idx in range(4):
                    if scores[idx] >= S.format_options["max_score"]:
                        scores[idx] = S.format_options["max_score"]
                        DataMapper.write_live_scores(scores)
                        break




                    

                   



#intitialize
from phew.server import schedule
schedule(formats_run, 5000, 5000)
S.active_format = 0




def test():
    print ("\n\n",get_available_formats(),"\n\n")

  

    print("set format 4 = ",set_active_format(4,{"max_score":20000}))

    for attr in dir(S):
        if not attr.startswith("__"):
            print(f"{attr}: {getattr(S, attr)}")

