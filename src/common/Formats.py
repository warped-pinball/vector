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
import Switches

# Handler indices for FORMAT_HANDLERS list
HANDLER_INIT = 0
HANDLER_RUN = 1
HANDLER_CLOSE = 2

next_format_id = 0
next_format_options = {}

# Forward declaration - will be initialized at end of file after handler functions are defined
FORMAT_HANDLERS = []

player_scores=[0,0,0,0]
saved_high_scores = None  # Store original high scores before clearing
saved_high_scores = None  # Store original high scores before clearing 


MODE_ID_STANDARD = 0
MODE_ID_LIMBO = 1
MODE_ID_LOWBALL = 2
MODE_ID_GOLF = 3
MODE_ID_PRACTICE = 4
MODE_ID_DECAY = 5


"""
    Default format definitions
    formats idetified by NAME (Key)
    config file overrides defaults from all parameters
    -when selecting a format send in values that override defaults here and in json
"""
DEFAULT_FORMATS = {
    "Standard": {
        "Id": MODE_ID_STANDARD,
        "Description": "Classic pinball scoring - highest score wins",
    },
    "Limbo": {
        "Id": MODE_ID_LIMBO,
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
        "Id": MODE_ID_LOWBALL,
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
        "Id": MODE_ID_GOLF,
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
        "Id": MODE_ID_PRACTICE,
        "Description": "Practice mode with unlimited balls and no score tracking",
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
        "Id": MODE_ID_DECAY,
        "Description": "Score decreases over time",
        "Options": {
            "ScoreDecay": {
                "Name": "Decay per 10 seconds",
                "type": "NumberRange",
                "Range": {
                    "Low": 100,
                    "High": 39000,
                    "Value": 3000
                }
            }
        }    
    },
}


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


# ============================================================================
# Practice Mode Handlers
# ============================================================================
def practice_init():
    """Initialize practice mode"""
    print("FORMATS: Practice mode initializing")


def practice_run():
    """Run practice mode (keep at ball 1 in play)"""
    if next_format_id != MODE_ID_PRACTICE:  # end on next ball drain
        DataMapper.write_ball_in_play(5)
        DataMapper.write_live_scores([1, 1, 1, 1])
    elif DataMapper.get_ball_in_play() > 1:
        DataMapper.write_ball_in_play(1)

    max_score = S.format_options.get("MaxScore", {}).get("Value", 0)
    if max_score > 0:
        scores = DataMapper.get_live_scores()
        for idx in range(4):
            if scores[idx] >= max_score:
                scores[idx] = max_score
                DataMapper.write_live_scores(scores)
                break


def practice_close():
    """Close practice mode"""
    print("FORMATS: Practice mode closing")


# ============================================================================
# Golf Mode Handlers
# ============================================================================
golf_ball_in_play = 0
golf_player_up = 0
golf_player_complete = [False, False, False, False]
switch_callback_setup = False

def golf_init():
    """Initialize golf mode, called at game start each time"""
    global player_scores, golf_ball_in_play, golf_player_up, golf_player_complete, switch_callback_setup
    
    print("FORMATS - stting up call back for switch now - - - - - - - - - ")

    # Subscribe to target hit event
    if switch_callback_setup is False:
        target_name = S.format_options.get("Target", {}).get("Value", "")
        if target_name:
            switch_callback_setup = Switches.subscribe(target_name, golf_hit_callback)
            if switch_callback_setup:
                print(f"GOLF: Subscribed to target ++++++++++++++++++++++++++++++ '{target_name}'")
            else:
                print(f"GOLF: Failed to subscribe to target +++++++++++++++++++ '{target_name}'")
        else:
            print("GOLF: No target selected")
    
    # Reset player scores and state for new game
    golf_ball_in_play = 1
    golf_player_up = 1
    golf_player_complete = [False, False, False, False]
    player_scores = [1000, 1000, 1000, 1000]


def golf_run():
    """Run golf mode during gameplay"""
    global golf_ball_in_play, golf_player_up, golf_player_complete, player_scores
    
    ball_in_play = DataMapper.get_ball_in_play()
    player_up = DataMapper.get_player_up()
    
    if ball_in_play != golf_ball_in_play or player_up != golf_player_up:
        #had a change in ball or player - update scores etc
        num_players = DataMapper.get_players_in_game()
        
        # Check if all players are complete
        all_complete = True
        for idx in range(num_players):
            if not golf_player_complete[idx]:
                if (player_scores[idx]<5000):
                    all_complete = False
                break
        
        if all_complete:
            print("GOLF: All players complete! Ending game.")
            # End the game
            DataMapper.write_ball_in_play(5)
            for idx in range(DataMapper.get_players_in_game()):
                print(f"  Player {idx + 1}: {player_scores[idx]}")        
        
        else:
            if ball_in_play ==1:
                golf_player_up = player_up
            else:
                #so we have ball 2 for the player currently up, if they are not done score=score*2
                if golf_player_complete[player_up-1]==False:
                    player_scores[player_up - 1]=player_scores[player_up - 1] + 1000

            if (ball_in_play >2):
                DataMapper.write_ball_in_play(2)

            golf_ball_in_play = ball_in_play
            golf_player_up = player_up

            print(f"GOLF: Player {player_up} starting ball {ball_in_play}")
    
    #always re-write scores - 
    DataMapper.write_live_scores(player_scores)

def golf_close():
    """Close golf mode and unsubscribe from target"""
    global switch_callback_setup
    target_name = S.format_options.get("Target", {}).get("Value", "")
    if target_name:
        Switches.unsubscribe(target_name, golf_hit_callback)
        switch_callback_setup = False
        print(f"GOLF: Unsubscribed from target '{target_name}'")
    print("GOLF: Golf mode closing")


def golf_hit_callback(switch_idx):
    """
    Callback when the golf target switch is hit.
    Increments the current player's score (number of balls used).
    """
    try:
        player_up = DataMapper.get_player_up()       
        
        #golf_ball_in_play ==1 and
        if DataMapper.get_ball_in_play() == 1:
            if  player_scores[player_up - 1]<=1000 and player_scores[player_up - 1]>250 and golf_player_complete[player_up - 1] is True:
                #reduce score on first ball, from 1000->500->250
                player_scores[player_up - 1]=player_scores[player_up - 1]//2
                   
        golf_player_complete[player_up - 1] = True  #player done!
        print(f"GOLF: Player {player_up} hit target!!!!!!!!!!!!!!!!!!!!!!!!! Total attempts: {player_scores[player_up - 1]}")

        # Check if all players in game are complete
        num_players = DataMapper.get_players_in_game()
        all_complete = True
        for idx in range(num_players):
            if not golf_player_complete[idx]:
                all_complete = False
                break
        
        if all_complete:
            print("GOLF: All players complete! Ending game.")
            DataMapper.write_ball_in_play(5)

    except Exception as e:
        print(f"GOLF: Error in golf_hit_callback: {e}")


# ============================================================================
# Stub Mode Handlers
# ============================================================================
def empty_init():
    """Empty init handler"""
    pass

def empty_run():
    """Empty run handler"""
    pass

def empty_close():
    """Empty close handler"""
    pass







# ============================================================================
# FORMATS Runner
# ============================================================================
game_state =0
GameEndCount =0

def formats_run():
    """
    periodic tasks related to game formats.   
        call rate 5 seconds
    """
    global next_format_id, next_format_options, game_state,GameEndCount,player_scores,saved_high_scores

    """
    ind=ind+1
    if ind == 15:        
        print("formats_chg to 0 - - - - - - - - - - - -  - - - - - ")
        next_format_id=0
        next_format_options = {}
    """

    #waiting to change format?
    if S.active_format != next_format_id:
        if DataMapper.get_game_active() is False and game_state==0:           
            S.active_format = next_format_id
            S.format_options = next_format_options   
            print("Format START NOW - - - - - - - -  ")

            return                        
            
    if S.active_format == MODE_ID_STANDARD:
        return


    print("FORMATS HIGH SCORES -->",DataMapper.read_high_scores())

    #waiting for game to start
    if game_state == 0:
        if DataMapper.get_game_active() is True:  #game started
            game_state=1
            #remove machine high scores?
            get_player_id = S.format_options.get("GetPlayerID", {}).get("Value", False)
            if get_player_id:
                # Save original high scores before clearing
                saved_high_scores = DataMapper.read_high_scores()
                print("FORMATS: Saved original high scores:", saved_high_scores)
                # Clear machine high scores to force initial entry
                DataMapper.remove_machine_scores(grand_champ_mode="Max")
                print("FORMATS: Cleared machine scores for initials capture")

            #Run init function at each game start
            handlers = FORMAT_HANDLERS[S.active_format]                
            try:
                handlers[HANDLER_INIT]()
            except Exception as e:
                print(f"FORMATS: Error running init format {S.active_format}: {e}")
    

    # Call handler during game, wait for game end
    elif game_state == 1:       
        print("FORMATS: game end check - ")     
        handlers = FORMAT_HANDLERS[S.active_format]       
        try:
            handlers[HANDLER_RUN]()
        except Exception as e:
            print(f"FORMATS: Error running format {S.active_format}: {e}")

        if DataMapper.get_game_active() is False:   
            DataMapper.write_live_scores(player_scores) 
            game_state = 2

    #game over wait for intiials
    elif game_state == 2:
        get_player_id = S.format_options.get("GetPlayerID", {}).get("Value", False)
        if get_player_id:
            GameEndCount += 1    #wait for intials   
            if DataMapper.get_game_active() is True:
                   GameEndCount = 99  #if game starts - get out!
                   print("FORMATS: game started while waiting for intials")
        else:
            GameEndCount = 99    #dont wait for intials
            print("FORMATS: Do not wait for intiials")

        if GameEndCount > 50:
            game_state = 3  
            GameEndCount = 0
        else:
            scores = DataMapper.read_high_scores()
            print(" FORMATS     state 2 - high scores are= ",scores)
            high_score_count = 0
            high_score_count = sum(1 for x in range(1, 5) if scores[x][1] > 100)
            print("FORAMTS:  game over - high score count is = ",high_score_count," players in game=",DataMapper.get_players_in_game())

            if high_score_count >= DataMapper.get_players_in_game():
                print("SCORE: initials are all entered now")
                game_state=3
         
    elif game_state == 3:  #wrap up
            print("\n\nFORMATS: Game all done - results are:")
            
            # Get final scores
            final_scores = DataMapper.read_high_scores()
            num_players = DataMapper.get_players_in_game()
            
            # Print results for each player
            for idx in range(num_players):
                player_num = idx + 1
                initials = final_scores[player_num][0] if final_scores[player_num][0] else "___"
                score = final_scores[player_num][1]
                print(f"  Player {player_num} ({initials}): {score:,}")
            print("\n\n")
            
            # Restore original high scores if they were saved
            if saved_high_scores is not None:
                print("FORMATS: Restoring original high scores:", saved_high_scores)
                DataMapper.write_high_scores(saved_high_scores)
                saved_high_scores = None

            game_state=0



# List of handler lists indexed by format ID
# Each format has [init_handler, run_handler, close_handler]
FORMAT_HANDLERS = [
    # 0: Standard
    [empty_init, empty_run, empty_close],
    # 1: Limbo
    [practice_init, practice_run, practice_close],
    # 2: LowBall
    [empty_init, empty_run, empty_close],
    # 3: Golf
    [golf_init, golf_run, golf_close],
    # 4: Practice
    [practice_init, practice_run, practice_close],
    # 5: Decay
    [empty_init, empty_run, empty_close],
]

# Initialize SharedState attributes if they don't exist
if not hasattr(S, 'active_format'):
    S.active_format = 0
if not hasattr(S, 'format_options'):
    S.format_options = {}

# Schedule periodic format tasks
from phew.server import schedule
schedule(formats_run, 15000, 5000)





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

    z={}

    print("set format  = ", set_active_format("Golf", z), "\n\n")

    for attr in dir(S):
        if not attr.startswith("__"):
            print(f"{attr}: {getattr(S, attr)}")





    print("\n\n")

